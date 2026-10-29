"""Solve a proposed rigid fit to a horizontal floor and an inner circular face.

This geometric solver establishes neither part identity nor a mating datum.
Its result must not be executed without separately confirmed correspondence.
"""
import itertools,math
import numpy as np
from cad.geometry import near


def propose(points,before_arc,after_arc,before_floor,after_floor,factor):
    if not math.isfinite(factor) or factor<=0:raise ValueError('Thiếu tỷ lệ đo thật')
    p=np.asarray(points,dtype=float)
    if p.shape!=(4,3) or not np.isfinite(p).all() or np.ptp(p[:,2])>1e-5:raise ValueError('Cần bốn đỉnh đồng phẳng')
    low=p.min(axis=0);high=p.max(axis=0)
    expected=[(x,y,low[2]) for x,y in itertools.product([low[0],high[0]],[low[1],high[1]])]
    if min(high[:2]-low[:2])<=1e-5 or not all(any(near(v.tolist(),list(q),1e-5) for v in p) for q in expected):raise ValueError('Cần tiết diện chữ nhật đủ đỉnh')
    for arc in (before_arc,after_arc):
        if not near(arc.get('extrusion'),[0,0,1]) or abs(arc['center'][2]-low[2])>1e-5 or not math.isfinite(arc['radius']) or arc['radius']<=0:
            raise ValueError('Cung cần cùng mặt phẳng XY')
    if not near(before_arc['center'],after_arc['center'],1e-5):raise ValueError('Mốc tâm cung đã đổi')
    for floor in (before_floor,after_floor):
        if abs(floor['start'][1]-floor['end'][1])>1e-5 or any(abs(floor[k][2]-low[2])>1e-5 for k in ('start','end')):raise ValueError('Cần mặt kê ngang cùng mặt phẳng')
    center=np.asarray(before_arc['center']);side=1 if low[0]>center[0] else -1 if high[0]<center[0] else 0
    if not side:raise ValueError('Chưa xác định duy nhất phía cung')
    distances=np.linalg.norm(p[:,:2]-center[:2],axis=1);maximum=float(max(distances));corner=int(np.argmax(distances))
    if sum(abs(v-maximum)<1e-5 for v in distances)!=1:raise ValueError('Mốc khoảng hở hướng kính chưa duy nhất')
    radial=before_arc['radius']-maximum;floor_gap=low[1]-before_floor['start'][1]
    if min(radial,floor_gap)<-1e-5:raise ValueError('Nguồn đã chồng mặt lắp')
    dy=after_floor['start'][1]-before_floor['start'][1];target=after_arc['radius']-radial
    square=target*target-(p[corner,1]+dy-center[1])**2
    if square<=0:raise ValueError('Không có giao điểm giữ hai khoảng hở')
    dx=center[0]+side*math.sqrt(square)-p[corner,0];shift=np.array([dx,dy,0.]);after=p+shift
    for vertices,arc,floor in ((p,before_arc,before_floor),(after,after_arc,after_floor)):
        a,b=sorted([floor['start'][0],floor['end'][0]])
        if min(vertices[:,0])<a-1e-5 or max(vertices[:,0])>b+1e-5:raise ValueError('Mặt kê chưa phủ tiết diện')
        start=arc['start_angle']%360;span=(arc['end_angle']-arc['start_angle'])%360
        if span<1e-8:raise ValueError('Cần cung trích có khoảng góc rõ')
        angles=[math.degrees(math.atan2(v[1]-center[1],v[0]-center[0]))%360 for v in vertices]
        if any((angle-start)%360>span+1e-7 for angle in angles):raise ValueError('Tiết diện vượt miền cung được vẽ')
    new_radial=after_arc['radius']-max(np.linalg.norm(after[:,:2]-center[:2],axis=1))
    if abs(new_radial-radial)>1e-5:raise ValueError('Đỉnh chi phối khoảng hở đã đổi')
    return dict(status='unconfirmed_geometric_fit',points=after.tolist(),delta=shift.tolist(),
        source_radial_gap_mm=radial*factor,source_floor_gap_mm=floor_gap*factor,
        fixed_position_radial_gap_mm=(after_arc['radius']-maximum)*factor,
        fixed_position_floor_gap_mm=(low[1]-after_floor['start'][1])*factor,
        proposed_radial_gap_mm=new_radial*factor,proposed_floor_gap_mm=(min(after[:,1])-after_floor['start'][1])*factor,
        policy='Geometric proposal only. Part identity, complete neighbouring group and mating datum require independent confirmation.')
