"""Preserve complete, unchanged native HATCH/contour graphs in one block."""
from cad.hatch_translation import validate_preserved,preserved_snapshot


def graph(doc,block):
    allowed={};members=set();hatches={}
    for hatch in block.query('HATCH'):
        if not hatch.dxf.associative:continue
        if hatch.has_extension_dict or hatch.get_reactors():raise ValueError('HATCH association có dữ liệu ngoài chưa hỗ trợ')
        boundaries=[list(p.source_boundary_objects) for p in hatch.paths]
        if not boundaries or any(not p for p in boundaries):raise ValueError('HATCH association thiếu biên')
        detached=hatch.copy();detached.dxf.associative=0
        for p in detached.paths:p.source_boundary_objects=[]
        validate_preserved(detached)
        for handle in {h for p in boundaries for h in p}:
            boundary=doc.entitydb.get(handle)
            if boundary is None or boundary.dxf.owner!=hatch.dxf.owner or boundary.dxftype() not in ('LINE','LWPOLYLINE','CIRCLE','ARC','ELLIPSE','TEXT','MTEXT'):
                raise ValueError('HATCH association cần biên native cùng definition')
            if boundary.has_extension_dict or hatch.dxf.handle not in boundary.get_reactors():
                raise ValueError('HATCH association thiếu reactor ngược hoặc có dữ liệu ngoài')
            allowed.setdefault(handle,set()).add(hatch.dxf.handle);members.add(handle)
        hatches[hatch.dxf.handle]=boundaries;members.add(hatch.dxf.handle)
    from cad.dimension_preservation import extend
    objects,extensions=extend(doc,block.block_record_handle,allowed,members)
    for handle,reactors in allowed.items():
        if set(doc.entitydb[handle].get_reactors())!=reactors:raise ValueError('HATCH association có reactor ngoài nhóm')
    return dict(reactors=allowed,members=members,hatches=hatches,objects=objects,extensions=extensions)


def source_snapshot(entity):
    doc=entity.doc;owner=doc.entitydb.get(entity.dxf.owner) if doc else None
    block=doc.blocks.get(owner.dxf.name) if owner is not None and owner.dxftype()=='BLOCK_RECORD' else None
    if block is None:raise ValueError('HATCH association thiếu owner')
    proof=graph(doc,block)
    if entity.dxf.handle not in proof['hatches']:raise ValueError('HATCH association chưa có bằng chứng')
    detached=entity.copy();detached.dxf.associative=0
    for p in detached.paths:p.source_boundary_objects=[]
    return dict(preserved_snapshot(detached),associative=True)


def verify_mapping(original,selected,mapping,omitted=()):
    """Check exact contour handles and reciprocal reactors after remapping."""
    for old,new in mapping.items():
        if new in omitted:continue
        a=original.entitydb.get(old);b=selected.entitydb.get(new)
        if a is not None and a.dxftype()=='DIMENSION' and a.has_extension_dict:
            from cad.dimension_associations import source_binding
            from cad.geometry import near
            before=source_binding(a);after=source_binding(b) if b is not None else None
            if before is None or before['status']!='verified_source_points' or after is None or after['status']!='verified_source_points':
                raise ValueError('DIMASSOC mất binding sau sao chép')
            expected=dict(before,association_ref=mapping.get(before['association_ref'],before['association_ref']),
                source_refs=sorted(mapping.get(r,r) for r in before['source_refs']),
                points=[dict(p,source_ref=mapping.get(p['source_ref'],p['source_ref'])) for p in before['points']])
            if not near(expected,after,1e-6):raise ValueError('DIMASSOC sai ánh xạ hoặc điểm đo sau sao chép')
        if a is None or a.dxftype()!='HATCH' or not a.dxf.associative:continue
        if b is None or b.dxftype()!='HATCH':raise ValueError('HATCH association mất đối tượng sao chép')
        source_snapshot(a);source_snapshot(b)
        expected=[[mapping.get(h,h) for h in p.source_boundary_objects] for p in a.paths]
        if expected!=[list(p.source_boundary_objects) for p in b.paths]:raise ValueError('HATCH association sai ánh xạ biên')
