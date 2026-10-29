"""Follow an angular DIM only when both complete source legs lie on a profile."""
import copy
import math
from shapely.geometry import LineString
from ezdxf.math import intersection_line_line_2d,Vec2


def resize_bound_angle(before,polygon,uv,z,transform):
    pairs=[('defpoint','defpoint4'),('defpoint3','defpoint2')]
    for a,b in pairs:
        if any(abs(before[k][2]-z)>1e-6 for k in (a,b)):return None
        line=LineString([uv(before[a]),uv(before[b])])
        if line.length<1e-6 or not polygon.boundary.buffer(1e-6).covers(line):return None
    if before.get('text') not in ('','<>'):raise ValueError('DIM góc gắn profile đang ghi đè số')
    after=copy.deepcopy(before)
    for key in ('defpoint','defpoint2','defpoint3','defpoint4'):after[key]=transform(before[key])
    def angle(g):
        vectors=[Vec2(g[b])-Vec2(g[a]) for a,b in pairs]
        if any(v.magnitude<1e-6 for v in vectors):raise ValueError('Cạnh DIM góc suy biến sau sửa')
        return math.atan2(vectors[0].det(vectors[1]),vectors[0].dot(vectors[1]))
    if abs(math.remainder(angle(after)-angle(before),2*math.pi))>1e-7:
        raise ValueError('Co/giãn làm đổi góc nguồn; cần quy tắc góc riêng')
    def center(g):
        return intersection_line_line_2d(tuple(Vec2(g[k]) for k in pairs[0]),tuple(Vec2(g[k]) for k in pairs[1]))
    old,new=center(before),center(after)
    if old is None or new is None:raise ValueError('Hai cạnh DIM góc không có giao điểm duy nhất')
    shift=new-old
    after['defpoint5']=[before['defpoint5'][0]+shift.x,before['defpoint5'][1]+shift.y,before['defpoint5'][2]]
    after['text']='<>'
    return after
