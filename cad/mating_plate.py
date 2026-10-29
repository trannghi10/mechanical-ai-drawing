"""Symmetric plate-width change with fixed drilling and verified center marks."""
import copy
import json
import math
from ezdxf.math import Matrix44
from cad.edit_engine import Operation
from cad.geometry import near


def widen(records,dimension,new_width):
    dg=dimension['geometry']
    if dimension.get('dimension_type',0)!=0 or dg['text'] not in ('','<>') or dg['angle']!=0 or dimension.get('linear_factor',1)!=1:
        raise ValueError('Bas cần kích thước bề rộng ngang đo thật')
    lo,hi=sorted(dg[k][0] for k in ('defpoint2','defpoint3'))
    caps=[]
    lines=[e for e in records if e['type']=='LINE' and '/' not in e['ref']]
    for e in lines:
        g=e['geometry']
        if near(g['start'][1],g['end'][1]) and near(sorted([g['start'][0],g['end'][0]]),[lo,hi]):caps.append(e)
    candidates=[]
    for a in caps:
        for b in caps:
            if a['ref']>=b['ref'] or near(a['geometry']['start'][1],b['geometry']['start'][1]):continue
            ys=sorted([a['geometry']['start'][1],b['geometry']['start'][1]])
            sides=[e for e in lines if near(e['geometry']['start'][0],e['geometry']['end'][0]) and any(near(e['geometry']['start'][0],x) for x in (lo,hi)) and near(sorted([e['geometry']['start'][1],e['geometry']['end'][1]]),ys)]
            if len(sides)==2:candidates.append(([a,b,*sides],ys))
    if len(candidates)!=1:raise ValueError('Không xác định duy nhất biên bas theo kích thước')
    outline,(bottom,top)=candidates[0]
    holes=[e for e in records if e['type']=='CIRCLE' and '/' not in e['ref'] and lo<=e['geometry']['center'][0]<=hi and bottom<=e['geometry']['center'][1]<=top]
    delta=(new_width-(hi-lo))/2
    if not math.isfinite(new_width) or new_width<=0 or abs(delta)<1e-9:
        raise ValueError('Bề rộng bas mới phải dương và khác nguồn')
    for e in holes:
        g=e['geometry'];x,y,z=g['center'];r=g['radius']
        if r<=0 or not (lo+r<x<hi-r and bottom+r<y<top-r) or not near(g['extrusion'],[0,0,1]):raise ValueError('Lỗ bas không nằm trọn trong đường bao')
        if not lo-delta+r<x<hi+delta-r:raise ValueError('Thu bas làm lỗ vượt biên đường bao mới')
    known={e['ref'] for e in outline+holes}
    def inside(p):return lo-1e-6<=p[0]<=hi+1e-6 and bottom-1e-6<=p[1]<=top+1e-6
    # Center mark blocks are retained only when every child is a small axial LINE
    # contained in an actual circular hole, not an arbitrary hidden structural block.
    for e in records:
        if e['type']!='INSERT' or '/' in e['ref'] or not inside(e['position']):continue
        hole=next((h for h in holes if near(h['geometry']['center'],e['position'])),None)
        children=[r for r in records if r['ref'].startswith(e['ref']+'/')]
        if not hole or 'center' not in e['layer'].lower() or not children or any(r['type']!='LINE' for r in children):raise ValueError('Block trong bas chưa chứng minh là dấu tâm lỗ')
        for child in children:
            matrix=Matrix44([v for row in child['frame_to_layout'] for v in row]);g=child['geometry']
            if not (near(g['start'][0],g['end'][0]) or near(g['start'][1],g['end'][1])):raise ValueError('Dấu tâm có LINE không theo trục')
            if any(math.dist(list(matrix.transform(g[k])),hole['geometry']['center'])>=hole['geometry']['radius'] for k in ('start','end')):raise ValueError('Dấu tâm vượt biên lỗ')
        known.add(e['ref'])
    for e in records:
        if '/' in e['ref'] or e['ref'] in known or e['type'] not in ('LINE','LWPOLYLINE','POLYLINE','ARC','ELLIPSE','SPLINE','INSERT','CIRCLE'):continue
        g=e.get('geometry',{});anchors=[g[k] for k in ('start','end','center') if k in g]+g.get('control_points',[])+g.get('fit_points',[])
        anchors += [[p[0],p[1],g.get('elevation',0)] for p in g.get('points',[])]
        if any(inside(p) for p in anchors):raise ValueError('Hình học trong bas chưa xác định ownership: '+e['ref'])
    centers=[h['geometry']['center'] for h in holes]
    def point(p):
        if any(near(p,center) for center in centers):return list(p)
        shift=-delta if p[0]<(lo+hi)/2-1e-6 else delta if p[0]>(lo+hi)/2+1e-6 else 0
        return [p[0]+shift,p[1],p[2]]
    operations=[]
    def add(e,after):
        if not near(e['geometry'],after):operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(after),xyz=[],reason='Đổi bề rộng bas đối xứng để giữ khe hở; giữ nguyên tâm và đường kính lỗ'))
    for e in outline:
        after=copy.deepcopy(e['geometry'])
        for key in ('start','end'):after[key]=point(after[key])
        add(e,after)
    for e in records:
        if e['type']!='DIMENSION' or '/' in e['ref'] or not e.get('geometry'):continue
        g=e['geometry']
        if not all(inside(g[k]) for k in ('defpoint2','defpoint3')):continue
        if g['text'] not in ('','<>') or e.get('dimension_type',0) not in (0,1):raise ValueError('Kích thước bas ghi đè hoặc chưa hỗ trợ')
        after=copy.deepcopy(g)
        for key in ('defpoint','defpoint2','defpoint3'):after[key]=point(g[key])
        # Width changes leave longitudinal/drilling dimensions numerically and
        # geometrically valid. Keep their native constraints and display offsets.
        angle=math.radians(g['angle'])
        def measured(geom):
            d=[b-a for a,b in zip(geom['defpoint2'],geom['defpoint3'])]
            return math.dist(geom['defpoint2'],geom['defpoint3']) if e.get('dimension_type',0)==1 else abs(d[0]*math.cos(angle)+d[1]*math.sin(angle))
        if near(measured(g),measured(after)):continue
        add(e,after)
    if not any(o.ref==dimension['ref'] for o in operations):raise ValueError('Chưa cập nhật kích thước bề rộng bas')
    return operations,outline,holes
