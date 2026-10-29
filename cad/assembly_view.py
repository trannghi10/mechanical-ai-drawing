"""Source-bound transport of a plate, its weld marks and viewing apertures.

Decorative weld circles are explicitly registered; manufacturing drill circles
are never selected by proximity. Every attachment is checked against the source.
"""
import copy, math
import numpy as np
from cad.geometry import near
from cad.projected_plate import rebuild


def ellipse_point(g, parameter):
    a=np.asarray(g['major_axis'][:2]);b=np.array([-a[1],a[0]])*g['ratio']
    return np.asarray(g['center'][:2])+a*math.cos(parameter)+b*math.sin(parameter)


def clip_endpoint(point, other, old, new, tolerance=.003):
    """Extend an unchanged background line to its resized elliptic aperture."""
    def basis(g):
        a=np.asarray(g['major_axis'][:2]);return np.column_stack((a,np.array([-a[1],a[0]])*g['ratio']))
    local=np.linalg.solve(basis(old),np.asarray(point)-old['center'][:2])
    if abs(np.linalg.norm(local)-1)*np.linalg.norm(basis(old),2)>tolerance:
        raise ValueError('Điểm cắt không nằm trên lỗ nguồn đã đăng ký')
    p=np.asarray(other);v=np.asarray(point)-p
    B=basis(new);q=np.linalg.solve(B,p-new['center'][:2]);d=np.linalg.solve(B,v)
    roots=np.roots([d@d,2*q@d,q@q-1])
    real=[float(r.real) for r in roots if abs(r.imag)<1e-9 and r.real>0]
    if not real:raise ValueError('Đường phía sau không cắt lỗ mới')
    return p+min(real,key=lambda r:abs(r-1))*v


def rebuild_welded_plate(view, records, size, radius, hole_radius, wall_delta):
    by={e['ref']:e for e in records}
    # The template stores complete original snapshots, not just nearest points.
    for ref,g in view['source_geometry'].items():
        if ref not in by or not near(by[ref].get('geometry'),g,2e-7):
            raise ValueError('Hình lắp đã khác nguồn đăng ký: '+ref)
    out=rebuild(view['plate'],records,size,radius,hole_radius)
    tube=view.get('tube')
    if tube:
        tube_size=[v+2*wall_delta for v in tube['size']]
        out.update(rebuild(tube,records,tube_size,tube['radius']+wall_delta))
    M=np.asarray(view['plate']['matrix'])
    changes=(np.asarray(size)-view['plate']['size'])/2
    # Each short row keeps its length and pitch; only its mating edge moves.
    for weld in view['welds']:
        vector=M[:,weld['axis']]*changes[weld['axis']]*weld['side']
        for ref in weld['refs']:
            g=copy.deepcopy(by[ref]['geometry'])
            if by[ref]['type']!='CIRCLE':raise ValueError('Ký hiệu hàn đăng ký phải là CIRCLE')
            g['center'][:2]=(np.asarray(g['center'][:2])+vector).tolist();out[ref]=g
    # A seam can join the plate and tube: move only its plate endpoint here.
    for link in view.get('links',[]):
        g=copy.deepcopy(by[link['ref']]['geometry'])
        for key,attachment in link['attachments'].items():
            ref=attachment['curve'];p=attachment['parameter']
            old=ellipse_point(by[ref]['geometry'],p)
            if math.dist(old,g[key][:2])>2e-4:raise ValueError('Mối nối không khớp góc bas nguồn')
            g[key][:2]=ellipse_point(out[ref],p).tolist()
        out[link['ref']]=g
    for item in view.get('aperture_clips',[]):
        g=copy.deepcopy(by[item['ref']]['geometry']);key=item['endpoint'];other='end' if key=='start' else 'start'
        ref=item['aperture']
        g[key][:2]=clip_endpoint(g[key][:2],g[other][:2],by[ref]['geometry'],out[ref]).tolist()
        out[item['ref']]=g
    return out
