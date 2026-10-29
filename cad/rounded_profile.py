"""Checked axial rectangle profiles with zero, two or four round corners.

Stretch translates corner arcs instead of scaling them. Holes are kept fixed.
Only a single closed boundary with the canonical tangent segments is accepted.
"""
import copy
import json
import math
from dataclasses import dataclass
from ezdxf.math import bulge_to_arc
from cad.geometry import near
from cad.edit_engine import Operation

TOL=1e-5


@dataclass
class Profile:
    boundary: list
    holes: list
    bbox: list
    corners: dict


def _key(p): return tuple(round(float(v),5) for v in p[:2])


def _segments(records):
    segments=[]
    for e in records:
        g=e['geometry'];kind=e['type']
        if kind=='LINE':
            if any(len(g[k])!=3 or not near(g[k][2],0,TOL) for k in ('start','end')):raise ValueError('Profile LINE không ở mặt phẳng XY')
            segments.append(('LINE',list(g['start'][:2]),list(g['end'][:2]),None,0))
        elif kind=='ARC':
            if not near(g['extrusion'],[0,0,1]) or not near(g['center'][2],0,TOL):raise ValueError('Profile ARC không ở mặt phẳng XY')
            a,b=g['start_angle'],g['end_angle']
            if not near((b-a)%360,90) or any(not near(v/90,round(v/90)) for v in (a,b)):
                raise ValueError('Chỉ nhận cung bo một phần tư theo trục')
            c=g['center'];r=g['radius']
            points=[[c[0]+r*math.cos(math.radians(v)),c[1]+r*math.sin(math.radians(v))] for v in (a,b)]
            segments.append(('ARC',*points,list(c[:2]),r))
        elif kind in ('LWPOLYLINE','POLYLINE'):
            if any(g.get('default_widths',[])):raise ValueError('Không kéo giãn polyline có default width')
            if not g['closed'] or not near(g['extrusion'],[0,0,1]) or not near(g['elevation'],0):
                raise ValueError('Profile polyline cần đóng trên XY')
            points=g['points']
            for a,b in zip(points,points[1:]+points[:1]):
                if any(abs(v)>TOL for v in a[2:4]):raise ValueError('Không kéo giãn polyline có width')
                if abs(a[4])<TOL:segments.append(('LINE',a[:2],b[:2],None,0))
                else:
                    if not near(abs(a[4]),math.tan(math.pi/8)):raise ValueError('Polyline chỉ nhận góc bo 90 độ')
                    c,sa,ea,r=bulge_to_arc(a[:2],b[:2],a[4])
                    segments.append(('ARC',a[:2],b[:2],list(c),r))
        else:raise ValueError('Profile chứa loại đường bao chưa hỗ trợ')
    return segments


def inspect(boundary, holes=()):
    segments=_segments(boundary)
    if not segments:raise ValueError('Thiếu đường bao')
    points=[p for _,a,b,_,_ in segments for p in (a,b)]
    box=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    lo,bt,hi,tp=box
    if hi-lo<=TOL or tp-bt<=TOL:raise ValueError('Profile suy biến')
    corners={};actual_lines=[];actual_arcs=[]
    for kind,a,b,c,r in segments:
        if kind=='LINE':
            if near(a,b,TOL):raise ValueError('Cạnh profile có chiều dài 0')
            if not (near(a[0],b[0],TOL) or near(a[1],b[1],TOL)):raise ValueError('Cạnh profile không theo trục')
            actual_lines.append(tuple(sorted((_key(a),_key(b)))))
        else:
            if r<=0 or 2*r>=min(hi-lo,tp-bt)-TOL:raise ValueError('Bán kính bo vượt profile')
            locations=[(x,y) for x in (0,1) for y in (0,1) if near(c,[lo+r if x==0 else hi-r,bt+r if y==0 else tp-r],TOL)]
            if len(locations)!=1 or locations[0] in corners:raise ValueError('Cung chưa chứng minh là góc bo tiếp tuyến')
            corner=locations[0];corners[corner]=r
            actual_arcs.append((corner,tuple(sorted((_key(a),_key(b))))))
    if len(corners) not in (0,2,4):raise ValueError('Profile cần 0, 2 hoặc 4 góc bo')
    if corners and not all(near(r,next(iter(corners.values())),TOL) for r in corners.values()):raise ValueError('Bán kính góc bo không đồng nhất')
    expected_lines=[];expected_arcs=[]
    def radius(x,y):return corners.get((x,y),0)
    expected_lines.extend([
        tuple(sorted((_key([lo+radius(0,0),bt]),_key([hi-radius(1,0),bt])))),
        tuple(sorted((_key([lo+radius(0,1),tp]),_key([hi-radius(1,1),tp])))),
        tuple(sorted((_key([lo,bt+radius(0,0)]),_key([lo,tp-radius(0,1)])))),
        tuple(sorted((_key([hi,bt+radius(1,0)]),_key([hi,tp-radius(1,1)]))))])
    for (x,y),r in corners.items():
        cx=lo if x==0 else hi;cy=bt if y==0 else tp
        expected_arcs.append(((x,y),tuple(sorted((_key([cx+(-r if x else r),cy]),_key([cx,cy+(-r if y else r)]))))))
    if sorted(actual_lines)!=sorted(expected_lines) or sorted(actual_arcs)!=sorted(expected_arcs):
        raise ValueError('Đường bao hở, trùng hoặc chưa đúng profile bo chữ nhật')
    for hole in holes:
        if hole['type']!='CIRCLE':raise ValueError('Lỗ profile cần CIRCLE')
        g=hole['geometry'];cx,cy,cz=g['center'];r=g['radius']
        if not near(g['extrusion'],[0,0,1]) or not near(cz,0) or r<=0:raise ValueError('Lỗ không hợp lệ')
        if not (lo+r<cx<hi-r and bt+r<cy<tp-r):raise ValueError('Lỗ vượt đường bao')
        for (x,y),cr in corners.items():
            cc=[lo+cr if x==0 else hi-cr,bt+cr if y==0 else tp-cr]
            if (cx<cc[0] if x==0 else cx>cc[0]) and (cy<cc[1] if y==0 else cy>cc[1]) and math.dist([cx,cy],cc)+r>cr+TOL:
                raise ValueError('Lỗ cắt vào vùng góc bo')
    return Profile(list(boundary),list(holes),box,corners)


def find_profiles(records):
    """Return individually verified closed boundaries, ignoring labels/dimensions."""
    candidates=[]
    for e in records:
        if e['type'] in ('LWPOLYLINE','POLYLINE') and e.get('geometry'):
            try:candidates.append(inspect([e]))
            except ValueError:pass
    primitives=[e for e in records if e['type'] in ('LINE','ARC') and e.get('geometry')]
    ends={e['ref']:[_key(s[1]) for s in _segments([e])]+[_key(s[2]) for s in _segments([e])] for e in primitives if e['type']=='LINE' or near((e['geometry']['end_angle']-e['geometry']['start_angle'])%360,90)}
    by={e['ref']:e for e in primitives};unused=set(ends)
    while unused:
        component={unused.pop()};front=list(component)
        while front:
            ref=front.pop();touching={r for r in unused if set(ends[r])&set(ends[ref])}
            unused-=touching;component|=touching;front.extend(touching)
        try:candidates.append(inspect([by[r] for r in sorted(component)]))
        except ValueError:pass
    return candidates


def resize(profile,new_size,new_radius=None):
    lo,bt,hi,tp=profile.bbox;old=[hi-lo,tp-bt]
    if len(new_size)!=2 or any(not math.isfinite(v) or v<=0 for v in new_size):raise ValueError('Kích thước profile mới không hợp lệ')
    delta=[(a-b)/2 for a,b in zip(new_size,old)];mid=[(lo+hi)/2,(bt+tp)/2]
    def point(p):return [v+(delta[i] if v>mid[i]+TOL else -delta[i] if v<mid[i]-TOL else 0) if i<2 else v for i,v in enumerate(p)]
    if new_radius is not None:
        if not profile.corners or not math.isfinite(new_radius) or not 0<2*new_radius<min(new_size)-TOL:raise ValueError('Bán kính bo mới không hợp lệ')
        old_radius=next(iter(profile.corners.values()))
        limits=[(lo,hi),(bt,tp)]
        maps=[]
        for axis,(low,high) in enumerate(limits):
            nl,nh=low-delta[axis],high+delta[axis]
            maps.append([(low,nl),(low+old_radius,nl+new_radius),(high-old_radius,nh-new_radius),(high,nh)])
        def point(p):
            result=list(p)
            for axis in (0,1):
                matches=[b for a,b in maps[axis] if near(p[axis],a,TOL)]
                if len(matches)!=1:raise ValueError('Không gắn được điểm tiếp tuyến với góc bo nguồn')
                result[axis]=matches[0]
            return result
    changed=[];operations=[]
    for e in profile.boundary:
        g=copy.deepcopy(e['geometry'])
        if e['type'] in ('LWPOLYLINE','POLYLINE'):
            g['points']=[point(p[:2])+p[2:] for p in g['points']]
        else:
            for k in ('start','end','center'):
                if k in g:g[k]=point(g[k])
            if e['type']=='ARC' and new_radius is not None:g['radius']=new_radius
        changed.append(dict(e,geometry=g))
        if not near(g,e['geometry']):operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(g),xyz=[],reason='Giữ khe hở lắp; đồng bộ biên và góc bo, giữ lỗ' if new_radius is not None else 'Giữ khe hở lắp; dịch góc bo, giữ bán kính và lỗ'))
    checked=inspect(changed,profile.holes)
    if not near([checked.bbox[2]-checked.bbox[0],checked.bbox[3]-checked.bbox[1]],new_size,TOL):raise ValueError('Kích thước sau kéo giãn không đúng')
    return operations,checked
