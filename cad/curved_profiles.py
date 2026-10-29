"""Source-closed planar contours; no curve flattening in the CAD output.

Circular edges use analytic checks. General positive-weight NURBS/ellipses
use bounded locator chords; export requires independent exact OCC face checks.
"""
import copy
import math
from collections import defaultdict
import networkx as nx
from shapely.geometry import Polygon,Point
from cad.geometry import near

TOL=1e-5
TAU=math.tau


def angle(edge,point):return math.atan2(point[1]-edge['center'][1],point[0]-edge['center'][0])
def sweep(edge):
    a,b=angle(edge,edge['start']),angle(edge,edge['end'])
    return ((b-a) if edge['ccw'] else (a-b))%TAU


def contains_angle(edge,a,interior=False):
    first=angle(edge,edge['start']);t=((a-first) if edge['ccw'] else (first-a))%TAU
    eps=TOL/max(edge['radius'],TOL)
    if min(t,TAU-t)<=eps:t=0
    return eps<t<sweep(edge)-eps if interior else t<=sweep(edge)+eps


def arc_point(edge,a):
    c=edge['center'];r=edge['radius']
    return [c[0]+r*math.cos(a),c[1]+r*math.sin(a),c[2]]


def edge_points(edge,sample=False):
    if edge['kind']=='line':return [edge['start'],edge['end']]
    if edge['kind']=='nurbs':
        from cad.nurbs_profiles import locator
        return locator(edge)
    first=angle(edge,edge['start']);span=sweep(edge);direction=1 if edge['ccw'] else -1
    values=[0.,span]
    for a in (0,math.pi/2,math.pi,3*math.pi/2):
        if contains_angle(edge,a):values.append(((a-first)*direction)%TAU)
    if sample:
        count=max(1,math.ceil(span/math.radians(1)))
        values.extend(span*i/count for i in range(1,count))
    points=[arc_point(edge,first+direction*t) for t in sorted(set(values))]
    points[0]=edge['start'];points[-1]=edge['end']
    return points


def primitives(record):
    g=record.get('geometry',{});kind=record['type'];result=[]
    if kind=='SPLINE':
        from cad.spline_arcs import primitives as spline_primitives
        from cad.nurbs_profiles import primitives as nurbs_primitives
        return spline_primitives(record) or nurbs_primitives(record)
    if kind=='ELLIPSE':
        from cad.nurbs_profiles import ellipse_primitives
        return ellipse_primitives(record)
    if kind=='LINE' and g:return [dict(kind='line',start=g['start'],end=g['end'],ref=record['ref'],segment_index=0)]
    if kind=='ARC' and g and near(g.get('extrusion'),[0,0,1]) and g['radius']>TOL:
        e=dict(kind='arc',center=g['center'],radius=g['radius'],ccw=True,ref=record['ref'],segment_index=0)
        e['start']=arc_point(e,math.radians(g['start_angle']));e['end']=arc_point(e,math.radians(g['end_angle']))
        return [e] if sweep(e)>1e-8 else []
    if kind not in ('LWPOLYLINE','POLYLINE') or not g or not near(g.get('extrusion'),[0,0,1]) or any(p[2] or p[3] for p in g['points']) or any(g.get('default_widths',[])):return []
    pts=g['points']
    for index,(a,b) in enumerate(zip(pts,pts[1:]+(pts[:1] if g['closed'] else []))):
        p=[a[0],a[1],g['elevation']];q=[b[0],b[1],g['elevation']];bulge=a[4]
        if math.dist(p,q)<=TOL:return []
        edge=dict(kind='line',start=p,end=q,ref=record['ref'],segment_index=index)
        if abs(bulge)>1e-12:
            dx,dy=q[0]-p[0],q[1]-p[1];length=math.hypot(dx,dy)
            factor=(1-bulge*bulge)/(4*bulge)
            edge.update(kind='arc',center=[(p[0]+q[0])/2-dy*factor,(p[1]+q[1])/2+dx*factor,p[2]],
                        radius=length*(1+bulge*bulge)/(4*abs(bulge)),ccw=bulge>0)
        result.append(edge)
    return result


def distance(edge,point):
    if edge['kind']=='nurbs':
        from shapely.geometry import LineString
        # A lower bound prevents hole clearances being overstated by a chord.
        return max(0,LineString([p[:2] for p in edge_points(edge)]).distance(Point(point[:2]))-edge['locator_error'])
    if edge['kind']=='arc':
        if contains_angle(edge,angle(edge,point)):return abs(math.dist(point[:2],edge['center'][:2])-edge['radius'])
        return min(math.dist(point[:2],edge[k][:2]) for k in ('start','end'))
    a,b=edge['start'],edge['end'];d=[b[i]-a[i] for i in (0,1)];den=sum(v*v for v in d)
    if den<TOL*TOL:return math.dist(a[:2],point[:2])
    t=max(0,min(1,sum((point[i]-a[i])*d[i] for i in (0,1))/den))
    return math.hypot(*(point[i]-a[i]-t*d[i] for i in (0,1)))


def intersections(a,b):
    """None means overlapping analytic edges; list contains finite intersections."""
    # Reject spatially separate edges before flattening NURBS. Positive
    # rational Bezier curves lie in their control hull; a full circle bound is
    # conservative for every arc. This preserves the exact near/crossing
    # checks while avoiding thousands of expensive locator subdivisions for
    # decorations and other views far from the edited profile.
    def bounds(edge):
        if edge['kind']=='nurbs':points=edge['control_points']
        elif edge['kind']=='arc':
            c=edge['center'];r=edge['radius']
            return ([c[0]-r,c[1]-r],[c[0]+r,c[1]+r])
        else:points=[edge['start'],edge['end']]
        return ([min(p[k] for p in points) for k in (0,1)],
                [max(p[k] for p in points) for k in (0,1)])
    al,ah=bounds(a);bl,bh=bounds(b)
    if any(ah[k]<bl[k]-TOL or bh[k]<al[k]-TOL for k in (0,1)):return []
    if 'nurbs' in (a['kind'],b['kind']):
        from shapely.geometry import LineString
        points=[[list(p[:2]) for p in edge_points(e,True)] for e in (a,b)]
        # Knot insertion/division can leave coincident endpoints a few ULPs
        # apart after a rotated block transform. Only normalize those source
        # endpoints, not interior curves or genuine gaps.
        for i in (0,-1):
            for j in (0,-1):
                if math.dist(points[0][i],points[1][j])<=1e-7:
                    points[1][j]=points[0][i]
        lines=[LineString(p) for p in points]
        hit=lines[0].intersection(lines[1])
        if hit.is_empty:
            error=sum(e.get('locator_error',e.get('radius',0)*(1-math.cos(math.radians(.5)))) for e in (a,b))
            return None if lines[0].distance(lines[1])<=error else []
        if hit.geom_type=='Point':return [[hit.x,hit.y]]
        if hit.geom_type=='MultiPoint':return [[p.x,p.y] for p in hit.geoms]
        return None
    if a['kind']=='line' and b['kind']=='line':
        from shapely.geometry import LineString
        hit=LineString([a['start'][:2],a['end'][:2]]).intersection(LineString([b['start'][:2],b['end'][:2]]))
        if hit.is_empty:return []
        if hit.geom_type=='Point':return [[hit.x,hit.y]]
        return None
    if a['kind']=='arc' and b['kind']=='line':a,b=b,a
    if a['kind']=='line':
        p,q=a['start'],a['end'];c=b['center'];v=[q[i]-p[i] for i in (0,1)];w=[p[i]-c[i] for i in (0,1)]
        aa=sum(t*t for t in v);bb=2*sum(x*y for x,y in zip(v,w));cc=sum(t*t for t in w)-b['radius']**2
        disc=bb*bb-4*aa*cc
        if aa<=TOL*TOL or disc<-TOL*TOL:return []
        ts=[(-bb+sign*math.sqrt(max(0,disc)))/(2*aa) for sign in (-1,1)]
        return [[p[i]+t*v[i] for i in (0,1)] for t in ts if -TOL<=t<=1+TOL and contains_angle(b,angle(b,[p[i]+t*v[i] for i in (0,1)]))]
    ca,cb=a['center'],b['center'];r,s=a['radius'],b['radius'];d=math.dist(ca[:2],cb[:2])
    if d<=TOL and abs(r-s)<=TOL:
        for e,f in ((a,b),(b,a)):
            mid=angle(e,e['start'])+(1 if e['ccw'] else -1)*sweep(e)/2
            if contains_angle(f,mid,True):return None
            if any(contains_angle(f,angle(f,e[k]),True) for k in ('start','end')):return None
        return [a[k][:2] for k in ('start','end') if distance(b,a[k])<=TOL]
    if d<=TOL or d>r+s+TOL or d<abs(r-s)-TOL:return []
    along=(r*r-s*s+d*d)/(2*d);height=math.sqrt(max(0,r*r-along*along))
    unit=[(cb[i]-ca[i])/d for i in (0,1)];base=[ca[i]+along*unit[i] for i in (0,1)]
    points=[[base[0]-sign*height*unit[1],base[1]+sign*height*unit[0]] for sign in (-1,1)]
    return [p for p in points if contains_angle(a,angle(a,p)) and contains_angle(b,angle(b,p))]


def valid_edges(edges):
    for i,a in enumerate(edges):
        for b in edges[i+1:]:
            hits=intersections(a,b)
            if hits is None:return False
            shared=[a[k] for k in ('start','end') if any(math.dist(a[k],b[j])<=TOL for j in ('start','end'))]
            if any(not any(math.dist(p,q[:2])<=TOL for q in shared) for p in hits):return False
    return True


def contours(records,measurement_bounds=None):
    if not any(e['type'] in ('ARC','SPLINE','ELLIPSE') or e['type'] in ('LWPOLYLINE','POLYLINE') and any(p[4] for p in e.get('geometry',{}).get('points',[])) for e in records):return []
    graph=nx.MultiGraph();items={}
    def key(p):return tuple(round(float(v),5) for v in p)
    for record in records:
        for edge in primitives(record):
            a,b=key(edge['start']),key(edge['end'])
            if a==b:continue
            i=len(items);items[i]=edge;graph.add_edge(a,b,key=i)
    result=[]
    for component in nx.connected_components(graph):
        if len(component)<2 or any(graph.degree(p)!=2 for p in component):continue
        ids={i for a,b,i in graph.edges(component,keys=True)}
        if not any(items[i]['kind']!='line' for i in ids):continue
        if measurement_bounds is not None:
            hull=[p for i in ids for p in (items[i]['control_points'] if items[i]['kind']=='nurbs' else edge_points(items[i]))]
            low=[min(p[k] for p in hull) for k in range(3)];high=[max(p[k] for p in hull) for k in range(3)]
            if not any(all(low[k]-TOL<=p[k]<=high[k]+TOL for p in pair for k in range(3)) for pair in measurement_bounds):continue
        current=min(component);start=current;seen=set();edges=[]
        while len(seen)<len(ids):
            options=[(b if a==current else a,i) for a,b,i in graph.edges(current,keys=True) if i not in seen]
            if not options:break
            nxt,i=min(options);edge=copy.deepcopy(items[i])
            if key(edge['start'])!=current:
                edge['start'],edge['end']=edge['end'],edge['start']
                if edge['kind']=='arc':edge['ccw']=not edge['ccw']
                if edge['kind']=='nurbs':
                    for k in ('control_points','weights'):edge[k]=edge[k][::-1]
            edges.append(edge);seen.add(i);current=nxt
        if seen!=ids or current!=start:continue
        try:
            if not valid_edges(edges):continue
            points=[]
            for edge in edges:
                points.extend(edge_points(edge,True)[:-1])
                if len(points)>65536:raise ValueError('Profile locator budget exceeded')
        except ValueError:continue  # bounded subdivision failed; unsupported profile
        if len(points) < 3 or max(p[2] for p in points)-min(p[2] for p in points)>TOL:continue
        try:
            polygon=Polygon([p[:2] for p in points])
            if polygon.is_valid and polygon.area>TOL*TOL:
                result.append(dict(refs=sorted({e['ref'] for e in edges}),points=points,edges=edges,
                                   curve_chord_error=max(e.get('locator_error',e.get('radius',0)*(1-math.cos(math.radians(.5)))) for e in edges)))
        except Exception:
            continue
    return result


def profile_from(records):
    found=contours(records)
    if len(found)!=1 or set(found[0]['refs'])!={e['ref'] for e in records}:
        raise ValueError('Đường bao cong chưa khép kín duy nhất hoặc có cạnh trùng/tự giao')
    return found[0]


def touches(profile,point):return min(distance(e,point) for e in profile['edges'])<=TOL


def direction_points(profile,axis):
    values=[p for e in profile['edges'] for p in edge_points(e)]
    first=math.atan2(axis[1],axis[0])
    for e in profile['edges']:
        if e['kind']!='arc':continue
        for a in (first,first+math.pi,first+math.pi/2,first-math.pi/2):
            if contains_angle(e,a):values.append(arc_point(e,a))
    return values


def stretch(records,profile,transform,axis):
    """Curves move rigidly. Only straight bridges parallel to DIM may stretch."""
    arc_shifts={}
    for edge in profile['edges']:
        # Positive-weight convex hulls also prove the whole NURBS stays in
        # one end zone, even when a control pole lies beyond sampled extrema.
        points=edge['control_points'] if edge['kind']=='nurbs' else edge_points(edge)
        if edge['kind']=='arc':
            first=math.atan2(axis[1],axis[0])
            points+= [arc_point(edge,a) for a in (first,first+math.pi) if contains_angle(edge,a)]
        shifts=[[b-a for a,b in zip(p,transform(p))] for p in points]
        rigid=all(near(s,shifts[0],TOL) for s in shifts)
        if edge['kind']=='arc' and not rigid:raise ValueError('Cung đi qua vùng co/giãn; không thể giữ nguyên bán kính')
        if edge['kind']=='nurbs' and not rigid:raise ValueError('NURBS/ellipse đi qua vùng co/giãn; cần quy tắc đường cong riêng')
        if edge['kind']=='arc':arc_shifts[edge['ref']]=shifts[0]
        if edge['kind']=='line' and not rigid:
            direction=[b-a for a,b in zip(edge['start'],edge['end'])]
            projected=sum(a*b for a,b in zip(direction,axis))
            if math.sqrt(sum((a-projected*b)**2 for a,b in zip(direction,axis)))>TOL:
                raise ValueError('Cạnh chéo đi qua vùng co/giãn; cần quy tắc riêng')
            old=sum(a*b for a,b in zip(direction,axis))
            new=sum((b-a)*v for a,b,v in zip(transform(edge['start']),transform(edge['end']),axis))
            if old*new<=TOL*TOL:raise ValueError('Co chiều dài làm đảo cạnh hoặc chồng các đầu cong')
    updated=[]
    for record in records:
        r=copy.deepcopy(record);g=r['geometry']
        if r['type']=='ARC':g['center']=[a+b for a,b in zip(g['center'],arc_shifts[r['ref']])]
        elif r['type']=='SPLINE':
            shifts=[[b-a for a,b in zip(p,transform(p))] for p in g['control_points']]
            if not all(near(s,shifts[0],TOL) for s in shifts):
                raise ValueError('SPLINE đi qua vùng co/giãn; cần quy tắc đường cong riêng')
            g['control_points']=[transform(p) for p in g['control_points']]
        elif r['type']=='ELLIPSE':
            shifts=[]
            for edge in profile['edges']:
                if edge['ref']==r['ref']:
                    shifts.extend([[b-a for a,b in zip(p,transform(p))] for p in edge['control_points']])
            if not shifts or not all(near(s,shifts[0],TOL) for s in shifts):
                raise ValueError('Ellipse đi qua vùng co/giãn; cần quy tắc đường cong riêng')
            g['center']=[a+b for a,b in zip(g['center'],shifts[0])]
        elif r['type']=='LINE':
            for k in ('start','end'):g[k]=transform(g[k])
        else:
            for p in g['points']:p[:2]=transform([p[0],p[1],g['elevation']])[:2]
        updated.append(r)
    after=profile_from(updated)
    return updated,after
