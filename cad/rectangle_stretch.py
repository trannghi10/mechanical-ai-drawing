"""Bounded rectangle operation validation and independent native readback."""
import json,math
from cad.geometry import near


def validate_operation(op):
    if op['expected_type']!='LWPOLYLINE' or op.get('instance_path'):
        raise ValueError('Rectangle requires layout LWPOLYLINE')
    if len({op['handle'],op.get('dimension_handle'),op.get('association_handle')})!=3 or not op.get('dimension_handle') or not op.get('association_handle'):
        raise ValueError('Distinct polyline, DIM and association handles required')
    try:before,after=[json.loads(op[k]) for k in ('before','after')]
    except (ValueError,TypeError) as error:raise ValueError('Rectangle geometry must be encoded as JSON arrays') from error
    for pts in (before,after):
        if not isinstance(pts,list) or len(pts)!=4 or any(not isinstance(p,list) or len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in pts):raise ValueError('Four finite XYZ vertices required')
        x,y,z=pts[0];w=pts[1][0]-x;h=pts[3][1]-y
        if w<=1e-6 or h<=1e-6 or not near(pts,[[x,y,z],[x+w,y,z],[x+w,y+h,z],[x,y+h,z]],1e-7):raise ValueError('Axis-aligned positive rectangle required')
    if not near(before[0],after[0],1e-7) or not near(before[3],after[3],1e-7) or any(abs(before[i][j]-after[i][j])>1e-7 for i in (1,2) for j in (1,2)) or abs(before[1][0]-after[1][0])<=1e-7:
        raise ValueError('Keep left edge and height; change width only')
    return before,after


def verify_result(operations,inventory,dxf_path,source_hash,output_hash):
    import ezdxf
    from cad.dimension_associations import source_binding
    if len(operations)!=1 or operations[0]['action']!='stretch_rectangle':raise ValueError('Isolated rectangle operation required')
    op=operations[0];_,points=validate_operation(op)
    effect=inventory.get('rectangle_stretch_effects',{})
    if effect.get('status')!='native_point_stretch_reopened' or effect.get('source_sha256')!=source_hash or effect.get('output_sha256')!=output_hash or effect.get('fixed_edge_verified') is not True or any(effect.get(key)!=op[key] for key in ('dimension_handle','association_handle')) or effect.get('polyline_handle')!=op['handle']:
        raise ValueError('Rectangle native receipt mismatch')
    d=ezdxf.readfile(dxf_path);poly=d.entitydb.get(op['handle']);dim=d.entitydb.get(op['dimension_handle'])
    if d.units!=4 or poly is None or dim is None or poly.dxftype()!='LWPOLYLINE' or dim.dxftype()!='DIMENSION' or poly.dxf.owner!=op['owner_handle'] or dim.dxf.owner!=op['owner_handle'] or not poly.closed or len(poly)!=4 or not near(list(poly.dxf.extrusion),[0,0,1]) or dim.dxf.dimtype&15!=0 or dim.dxf.get('text','') not in ('','<>'):
        raise ValueError('Invalid rectangle/DIM readback')
    if not near([[p[0],p[1],poly.dxf.elevation] for p in poly.get_points()],points,1e-7) or any(any(abs(v)>1e-10 for v in p[2:]) for p in poly.get_points()) or abs(poly.dxf.const_width)>1e-10:
        raise ValueError('Rectangle coordinates or topology differ')
    width=points[1][0]-points[0][0]
    binding=source_binding(dim)
    if abs(dim.get_measurement()-width)>1e-7 or binding.get('status')!='verified_source_points' or binding.get('association_ref')!=op['association_handle'] or binding.get('source_refs')!=[op['handle']] or [p.get('vertex_index') for p in binding['points']]!=[0,1]:
        raise ValueError('Rectangle DIM measurement or source binding differs')
    labels=[e.plain_text() if e.dxftype()=='MTEXT' else e.dxf.text for e in d.blocks[dim.dxf.geometry] if e.dxftype() in ('TEXT','MTEXT')]
    try:correct=any(abs(float(label)-width)<1e-7 for label in labels)
    except ValueError:correct=False
    if not correct:raise ValueError('Rectangle DIM visible label differs')
