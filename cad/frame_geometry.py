"""Reversible 2D similarity transforms for source geometry and measurements."""
import copy
import math
from ezdxf.math import Matrix44,Vec3
from cad.geometry import near


def matrix(record):
    rows=record.get('frame_to_layout')
    return Matrix44([v for row in rows for v in row]) if rows else Matrix44()


def planar_similarity(m):
    x,y,z=[m.transform_direction(Vec3(p)) for p in [(1,0,0),(0,1,0),(0,0,1)]]
    scale=x.magnitude
    determinant=x.x*y.y-x.y*y.x
    if scale<1e-12 or abs(y.magnitude-scale)>1e-8*max(1,scale) or abs(x.dot(y))>1e-8*scale**2 or max(abs(x.z),abs(y.z),abs(z.x),abs(z.y))>1e-8 or abs(determinant)<1e-16:
        raise ValueError('Frame chưa hỗ trợ: cần phép quay/tịnh tiến/tỷ lệ đều trong mặt phẳng 2D')
    return scale,math.degrees(math.atan2(x.y,x.x)),1 if determinant>0 else -1


def similarity(m):
    """Legacy callers that depend on orientation still require a direct map."""
    scale,angle,orientation=planar_similarity(m)
    if orientation<0:raise ValueError('Frame phản chiếu cần adapter định hướng riêng')
    return scale,angle


def transform(kind,g,m):
    scale,angle,orientation=planar_similarity(m);r=copy.deepcopy(g)
    def point(p):return list(m.transform(Vec3(p)))
    if kind in ('LINE','DIMENSION'):
        for k in ('start','end','defpoint','defpoint2','defpoint3','defpoint4','defpoint5'):
            if k in r:r[k]=point(r[k])
        if kind=='DIMENSION' and 'angle' in r:r['angle']=(orientation*r['angle']+angle)%360
    elif kind in ('LWPOLYLINE','POLYLINE'):
        if not near(g['extrusion'],[0,0,1]):raise ValueError('Polyline OCS nghiêng chưa hỗ trợ')
        z=None
        for p in r['points']:
            q=point([p[0],p[1],g['elevation']]);p[:2]=q[:2];p[2]*=scale;p[3]*=scale;p[4]*=orientation;z=q[2]
        r['elevation']=z if z is not None else g['elevation']
        if 'default_widths' in r:r['default_widths']=[v*scale for v in r['default_widths']]
    elif kind in ('CIRCLE','ARC'):
        if not near(g['extrusion'],[0,0,1]):raise ValueError('Circle/arc OCS nghiêng chưa hỗ trợ')
        r['center']=point(g['center']);r['radius']*=scale
        if kind=='ARC':
            start,end=g['start_angle'],g['end_angle']
            if orientation<0:start,end=end,start
            r['start_angle']=(orientation*start+angle)%360;r['end_angle']=(orientation*end+angle)%360
    elif kind=='SPLINE':
        for k in ('control_points','fit_points'):r[k]=[point(p) for p in r[k]]
    elif kind=='ELLIPSE':
        if not near(g.get('extrusion',[0,0,1]),[0,0,1]):raise ValueError('Ellipse OCS nghiêng chưa hỗ trợ')
        r['center']=point(g['center']);r['major_axis']=list(m.transform_direction(Vec3(g['major_axis'])))
        if orientation<0:r['start_param'],r['end_param']=-g['end_param'],-g['start_param']
    elif kind=='LEADER':r['vertices']=[point(p) for p in r['vertices']]
    else:raise ValueError('Chưa hỗ trợ chuyển frame: '+kind)
    return r


def world(record):
    m=matrix(record);r=dict(record)
    scale=planar_similarity(m)[0] if record.get('geometry') or record.get('radial_geometry') else 1
    if record.get('geometry'):r['geometry']=transform(record['type'],record['geometry'],m)
    if record.get('radial_geometry'):r['radial_geometry']=transform(record['type'],record['radial_geometry'],m)
    if record.get('position'):r['position']=list(m.transform(Vec3(record['position'])))
    if record['type']=='DIMENSION':r['linear_factor']=record.get('linear_factor',1)/scale
    r['coordinate_frame']='layout:'+str(record.get('layout'))
    r['frame_to_layout']=[list(Matrix44().get_row(i)) for i in range(4)]
    return r


def world_scope(context,required_refs,outline_refs):
    """Unsupported geometry outside the edit region remains source metadata."""
    from itertools import product
    from backend.services.geometry_retrieval import local_bounds
    required=set(required_refs);outlines=set(outline_refs);normalized={};points=[]
    for e in context['entities']:
        if e['ref'] not in required:continue
        r=world(e);normalized[e['ref']]=r
        if e['ref'] in outlines:
            g=r.get('geometry',{})
            points.extend(g[k] for k in ('start','end') if k in g)
            points.extend([p[0],p[1],g['elevation']] for p in g.get('points',[]))
            if r['type'] in ('ARC','SPLINE','ELLIPSE') or r['type'] in ('LWPOLYLINE','POLYLINE') and any(p[4] for p in g.get('points',[])):
                from cad.curved_profiles import primitives,edge_points
                points.extend(p for edge in primitives(r) for p in edge_points(edge))
    if not points:raise ValueError('Thiếu đường bao để kiểm tra phạm vi chuyển frame')
    low=[min(p[i] for p in points) for i in range(3)];high=[max(p[i] for p in points) for i in range(3)]
    result=[]
    for e in context['entities']:
        if e['ref'] in normalized:result.append(normalized[e['ref']]);continue
        try:r=world(e)
        except ValueError:
            bounds=local_bounds(e)
            if bounds is None:raise ValueError('Chưa định vị được geometry ở frame không hỗ trợ: '+e['ref'])
            m=matrix(e);corners=[m.transform(Vec3(p)) for p in product(*zip(*bounds))]
            a=[min(p[i] for p in corners) for i in range(3)];b=[max(p[i] for p in corners) for i in range(3)]
            if all(a[i]<=high[i]+1e-5 and b[i]>=low[i]-1e-5 for i in range(3)):
                raise ValueError('Có geometry trong profile ở frame chưa hỗ trợ: '+e['ref'])
            r=dict(e);r.pop('geometry',None);r.pop('radial_geometry',None)
            r['world_geometry_unavailable']='unsupported frame outside edit bounds; original source retained'
            r['coordinate_frame']='unmapped:'+str(e.get('coordinate_frame'))
        result.append(r)
    return dict(context,entities=result)


def local_geometry(record,world_geometry):
    m=matrix(record);m.inverse();r=transform(record['type'],world_geometry,m)
    old=record.get('geometry') or record.get('radial_geometry')
    if not old:raise ValueError('Thiếu snapshot native để chuyển frame')
    if record['type'] in ('LWPOLYLINE','POLYLINE'):
        if abs(r['elevation']-old['elevation'])>1e-6:raise ValueError('Sửa profile làm đổi mặt phẳng')
        r['elevation']=old['elevation'];r['extrusion']=old['extrusion']
        for a,b in zip(r['points'],old['points']):
            if not near(a[2:],b[2:],1e-6):raise ValueError('Sửa profile làm đổi width/bulge')
            a[2:]=b[2:]
    if record['type']=='DIMENSION' and 'angle' in old:
        if abs(math.remainder(r['angle']-old['angle'],360))>1e-6:raise ValueError('Sửa profile làm đổi góc DIM')
        r['angle']=old['angle']
    return r
