"""Source-measured straight rectangular tube sections, no product templates."""
import copy
import json
import math
from cad.edit_engine import Operation
from cad.geometry import near


def rectangle(record):
    if record['type']!='LWPOLYLINE' or '/' in record['ref']:return None
    if not math.isfinite(record.get('constant_width',0)) or abs(record.get('constant_width',0))>1e-9:return None
    g=record.get('geometry',{})
    if not g.get('closed') or len(g.get('points',[]))!=4 or not near(g.get('extrusion'),[0,0,1],1e-7):return None
    points=g['points']
    if any(len(p)!=5 or any(abs(v)>1e-9 for v in p[2:]) for p in points):return None
    low=[min(p[i] for p in points) for i in (0,1)];high=[max(p[i] for p in points) for i in (0,1)]
    if min(high[i]-low[i] for i in (0,1))<=1e-7:return None
    corners={(round(p[0],6),round(p[1],6)) for p in points}
    if corners!={(round(x,6),round(y,6)) for x in (low[0],high[0]) for y in (low[1],high[1])}:return None
    if any(abs(a[0]-b[0])>1e-6 and abs(a[1]-b[1])>1e-6 for a,b in zip(points,points[1:]+points[:1])):return None
    return low,high


def straight_wall(records,old,new):
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (old,new)):
        raise ValueError('Độ dày hộp phải là số dương hữu hạn')
    rectangles=[(e,rectangle(e)) for e in records];rectangles=[(e,box) for e,box in rectangles if box]
    candidates=[]
    for inner,(low,high) in rectangles:
        for outer,(a,b) in rectangles:
            if inner is outer or abs(inner['geometry']['elevation']-outer['geometry']['elevation'])>1e-6:continue
            if near([low[i]-a[i] for i in (0,1)],[old,old],1e-6) and near([b[i]-high[i] for i in (0,1)],[old,old],1e-6):
                candidates.append((inner,outer,low,high,a,b))
    if len(candidates)!=1:raise ValueError('Chưa nhận diện duy nhất cặp polyline ngoài/trong của tiết diện hộp')
    inner,outer,low,high,a,b=candidates[0]
    if any(b[i]-a[i]<=2*new for i in (0,1)):raise ValueError('Độ dày mới làm rỗng mặt trong hộp')
    after=copy.deepcopy(inner['geometry'])
    for point in after['points']:
        for i in (0,1):point[i]=a[i]+new if abs(point[i]-low[i])<1e-6 else b[i]-new
    return Operation(ref=inner['ref'],action='replace_geometry',before=json.dumps(inner['geometry']),after=json.dumps(after),xyz=[],
                     reason='Giữ polyline ngoài; sửa bốn đỉnh mặt trong theo độ dày và tiết diện nguồn')
