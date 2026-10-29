"""Source-bound closing plate, bore occlusion and welds in assembly views."""
import copy
import math
import numpy as np
from cad.geometry import near
from cad.projection_mapping import Projection


def ellipse_basis(g):
    a=np.asarray(g['major_axis'][:2]);return np.column_stack((a,[-a[1]*g['ratio'],a[0]*g['ratio']]))


def retrim_bore(front,back,source_front,source_back):
    """Rear rim terminates at the front rim, rather than showing through it."""
    basis=ellipse_basis(front)
    if not np.allclose(basis,ellipse_basis(back),atol=1e-8,rtol=0):
        raise ValueError('Hai mép lỗ không cùng hệ elip')
    for key in ('start_param','end_param'):
        p=np.asarray(source_back['center'][:2])+ellipse_basis(source_back)@np.array([math.cos(source_back[key]),math.sin(source_back[key])])
        u=np.linalg.solve(ellipse_basis(source_front),p-source_front['center'][:2])
        if abs(np.linalg.norm(u)-1)>2e-4:raise ValueError('Mép lỗ nguồn không cắt tại mép trước')
    d=np.linalg.solve(basis,np.asarray(back['center'][:2])-front['center'][:2]);length=np.linalg.norm(d)
    if not 0<length<2:raise ValueError('Hai mép lỗ không giao nhau')
    phi=math.atan2(d[1],d[0]);alpha=math.acos(-length/2)
    roots=[phi-alpha,phi+alpha]
    result=copy.deepcopy(back)
    for key in ('start_param','end_param'):
        old=source_back[key]
        candidates=[p+2*math.pi*round((old-p)/(2*math.pi)) for p in roots]
        result[key]=min(candidates,key=lambda p:abs(p-old))
    return result


def rebuild(view,records,delta):
    by={e['ref']:e for e in records};out={}
    for ref,g in view['source_geometry'].items():
        if ref not in by or not near(by[ref].get('geometry'),g,2e-7):raise ValueError('Hình bas đứng khác nguồn: '+ref)
    camera=Projection(view['matrix'],view['origin'],view.get('scale',1))
    for b in view['lines']:
        g=by[b['ref']]['geometry'];old=[b[k]['base'] for k in ('start','end')]
        new=[[p+offset+delta*d for p,offset,d in zip(b[k]['base'],b[k]['offset'],b[k]['delta'])] for k in ('start','end')]
        result=camera.line(g,old,new)
        for key,ref in b.get('clips',{}).items():
            circle=by[ref]['geometry'];center=np.asarray(circle['center'][:2]);radius=circle['radius']
            if abs(np.linalg.norm(np.asarray(g[key][:2])-center)-radius)>2e-4:raise ValueError('Điểm cắt khác biên Detail nguồn')
            other='end' if key=='start' else 'start';p=np.asarray(result[other][:2]);v=np.asarray(result[key][:2])-p
            roots=np.roots([v@v,2*v@(p-center),(p-center)@(p-center)-radius*radius])
            choices=[p+float(r.real)*v for r in roots if abs(r.imag)<1e-8]
            if not choices:raise ValueError('Cạnh không cắt biên Detail')
            result[key][:2]=min(choices,key=lambda x:np.linalg.norm(x-result[key][:2])).tolist()
        out[b['ref']]=result
    for b in view['bores']:
        front=by[b['front']]['geometry'];back=by[b['back']]['geometry']
        camera.concentric_arc(front,b['front_center'],b['radius'],b['radius'],axes=(1,2))
        camera.concentric_arc(back,b['back_center'],b['radius'],b['radius'],axes=(1,2))
        moved=copy.deepcopy(back)
        moved['center']=camera.move_bound_point(back['center'],b['back_center'],b['new_back_center'])
        out[b['back']]=retrim_bore(front,moved,front,back)
    for group in view['welds']:
        movement=camera.matrix@np.array([o+delta*d for o,d in zip(group['offset'],group['delta'])])
        for ref in group['refs']:
            result=copy.deepcopy(by[ref]['geometry']);result['center'][:2]=(np.asarray(result['center'][:2])+movement).tolist();out[ref]=result
    return out
