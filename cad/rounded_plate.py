"""Bind a small rounded plate to source dimensions and its side projection."""
import copy
import json
import math
from cad.geometry import near
from cad.edit_engine import Operation
from cad.rounded_profile import find_profiles,inspect,resize,_segments,TOL
from ezdxf.math import Matrix44


def resize_plate(records,size,new_size,thickness,new_radius=None):
    roots=[e for e in records if '/' not in e['ref']]
    candidates=[p for p in find_profiles(roots) if p.corners and near([p.bbox[2]-p.bbox[0],p.bbox[3]-p.bbox[1]],size,TOL)]
    if len(candidates)!=1:raise ValueError('Chưa chứng minh duy nhất profile bo theo BOM')
    p=candidates[0];lo,bt,hi,tp=p.bbox
    inside=lambda q:lo-TOL<=q[0]<=hi+TOL and bt-TOL<=q[1]<=tp+TOL
    holes=[e for e in roots if e['type']=='CIRCLE' and inside(e['geometry']['center'])]
    p=inspect(p.boundary,holes)
    known={e['ref'] for e in p.boundary+holes}
    # Center marks inside a real hole are preserved, not stretched.
    for e in roots:
        if e['type']=='LINE' and 'center' in e.get('layer','').lower() and holes:
            if any(all(near(e['geometry'][k][i],h['geometry']['center'][i],TOL) for k in ('start','end')) for h in holes for i in (0,1)):
                known.add(e['ref'])
        if e['type']=='INSERT' and 'center' in e.get('layer','').lower():
            hole=next((h for h in holes if near(h['geometry']['center'],e['position'],TOL)),None)
            children=[q for q in records if q['ref'].startswith(e['ref']+'/')]
            if not hole or not children or any(q['type']!='LINE' for q in children):continue
            center=hole['geometry']['center'];valid=True;axes=set()
            for child in children:
                matrix=Matrix44([v for row in child['frame_to_layout'] for v in row])
                a,b=[list(matrix.transform(child['geometry'][k])) for k in ('start','end')]
                axis=next((i for i in (0,1) if near(a[i],center[i],TOL) and near(b[i],center[i],TOL)),None)
                if axis is None or not all(inside(q) for q in (a,b)):valid=False;break
                axes.add(axis)
            if valid and axes=={0,1}:known.add(e['ref'])
    for e in roots:
        if e['ref'] in known or e['type'] not in ('LINE','ARC','LWPOLYLINE','CIRCLE','ELLIPSE','SPLINE','INSERT'):continue
        g=e.get('geometry',{});points=[g[k] for k in ('start','end','center') if k in g]+[q[:2] for q in g.get('points',[])]
        if e.get('position'):points.append(e['position'])
        if any(inside(q) for q in points):raise ValueError('Hình học chưa rõ ownership trong profile bas: '+e['ref'])
    dimensions=[]
    for axis in (0,1):
        ds=[]
        for e in roots:
            if e['type']!='DIMENSION' or not e.get('geometry'):continue
            g=e['geometry'];values=sorted(g[k][axis] for k in ('defpoint2','defpoint3'))
            limits=[lo,hi] if axis==0 else [bt,tp]
            if e.get('dimension_type',0)==0 and e.get('linear_factor',1)==1 and g['text'] in ('','<>') and near(g['angle']%180,axis*90,TOL) and near(values,limits,TOL):ds.append(e)
        if len(ds)!=1:raise ValueError('Thiếu DIMENSION đo thật duy nhất cho trục profile bas')
        dimensions.append(ds[0])
    operations,after=resize(p,new_size,new_radius)
    mid=[(lo+hi)/2,(bt+tp)/2];delta=[(n-o)/2 for n,o in zip(new_size,size)]
    def moved(q):return [v+(-delta[i] if v<mid[i]-TOL else delta[i] if v>mid[i]+TOL else 0) if i<2 else v for i,v in enumerate(q)]
    old_segments,new_segments=_segments(p.boundary),_segments(after.boundary)
    def endpoint(q):
        matches=[b for old,new in zip(old_segments,new_segments) for a,b in zip(old[1:3],new[1:3]) if near(q[:2],a,TOL)]
        if not matches:return moved(q)
        if not all(near(matches[0],b,TOL) for b in matches):raise ValueError('Điểm DIM có nhiều biên đích')
        return list(matches[0])+list(q[2:])
    for e in dimensions:
        g=copy.deepcopy(e['geometry'])
        g['defpoint']=moved(g['defpoint'])
        for key in ('defpoint2','defpoint3'):g[key]=endpoint(g[key])
        if not near(g,e['geometry']):operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(g),xyz=[],reason='Kích thước đo thật theo biên bas mới'))
    if new_radius is not None and not near(new_radius,next(iter(p.corners.values())),TOL):
        radial=[]
        for e in roots:
            g=e.get('radial_geometry')
            if e['type']!='DIMENSION' or not g:continue
            if e.get('linear_factor',1)!=1:raise ValueError('DIM bán kính cần đo thật theo mm')
            c,q=g['defpoint'],g['defpoint4']
            for old,new in zip(old_segments,new_segments):
                if old[0]!='ARC' or not near(c[:2],old[3],TOL) or not near([c[2],q[2]],[0,0],TOL) or not near(math.dist(c,q),old[4],TOL):continue
                # Quarter-arc ownership requires the radius point to be on its span.
                if not all(min(old[1][i],old[2][i])-TOL<=q[i]<=max(old[1][i],old[2][i])+TOL for i in (0,1)):continue
                if g['text'] not in ('','<>') and '<>' not in g['text']:raise ValueError('DIM bán kính có số ghi đè')
                updated=copy.deepcopy(g);updated['defpoint']=list(new[3])+[c[2]]
                updated['defpoint4']=[updated['defpoint'][i]+(q[i]-c[i])*new_radius/old[4] for i in range(3)]
                radial.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(g),after=json.dumps(updated),xyz=[],reason='Đo thật góc bo theo góc trong hộp mới'))
        if len(radial)!=1:raise ValueError('Thiếu DIM bán kính duy nhất gắn cung bo nguồn')
        operations.extend(radial)
    # Exactly one side view aligned in X and showing the verified sheet gauge.
    sides=[q for q in find_profiles(roots) if not q.corners and near([q.bbox[0],q.bbox[2]],[lo,hi],TOL) and near(q.bbox[3]-q.bbox[1],thickness,TOL) and q.bbox[3]<bt-TOL]
    if len(sides)!=1:raise ValueError('Chưa xác định duy nhất hình chiếu cạnh bas theo độ dày nguồn')
    side=sides[0]
    side_ops,side_after=resize(side,[new_size[0],thickness]);operations.extend(side_ops)
    # Hidden edges of holes are bound to their exact projection and stay fixed.
    hole_xs=[h['geometry']['center'][0]+sign*h['geometry']['radius'] for h in holes for sign in (-1,1)]
    side_known={e['ref'] for e in side.boundary}
    for e in roots:
        if e['ref'] in side_known or e['type']!='LINE':continue
        g=e['geometry']
        in_side=any(side.bbox[0]-TOL<=g[k][0]<=side.bbox[2]+TOL and side.bbox[1]-TOL<=g[k][1]<=side.bbox[3]+TOL for k in ('start','end'))
        if in_side and not (near(g['start'][0],g['end'][0],TOL) and any(near(g['start'][0],x,TOL) for x in hole_xs) and near(sorted([g['start'][1],g['end'][1]]),[side.bbox[1],side.bbox[3]],TOL)):
            raise ValueError('Hình chiếu cạnh có hình học chưa gán chi tiết')
    return operations,p,dimensions
