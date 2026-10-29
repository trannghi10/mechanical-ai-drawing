"""Rigid planar displacement of a source snapshot, preserving its topology."""
import copy
import math
from cad.geometry import near


TYPES=('LINE','LWPOLYLINE','POLYLINE','CIRCLE','DIMENSION')


def translated(record,vector):
    if record['type'] not in TYPES or len(vector)!=3 or not all(math.isfinite(v) for v in vector) or abs(vector[2])>1e-8:
        raise ValueError('Dịch biên chi tiết chỉ hỗ trợ các đối tượng phẳng đã kiểm chứng')
    g=copy.deepcopy(record['geometry']);kind=record['type']
    if kind in ('LWPOLYLINE','POLYLINE','CIRCLE') and not near(g.get('extrusion'),[0,0,1]):
        raise ValueError('Dịch biên chi tiết cần mặt phẳng XY nguồn')
    def point(p):return [a+b for a,b in zip(p,vector)]
    if kind=='LINE':
        g['start']=point(g['start']);g['end']=point(g['end'])
    elif kind in ('LWPOLYLINE','POLYLINE'):
        for p in g['points']:p[0]+=vector[0];p[1]+=vector[1]
    elif kind=='CIRCLE':g['center']=point(g['center'])
    else:
        if record.get('dimension_type') not in (0,1):raise ValueError('Chỉ dịch DIM linear/aligned cùng chi tiết')
        for key in ('defpoint','defpoint2','defpoint3'):g[key]=point(g[key])
    return g
