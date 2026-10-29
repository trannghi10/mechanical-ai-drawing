"""Locate exact BOM-coded INSERT instances, including nested assemblies."""
from functools import lru_cache
from ezdxf import bbox
from ezdxf.math import Matrix44
from cad.catalog import load_document
from cad.sheets import inside


def native_part_scopes(source,sheets,codes):
    from cad.part_identity import entity_identity
    doc=load_document(str(source));codes=set(codes)
    if not codes:return []
    # Check before bbox.extents(), which recursively expands nested INSERTs.
    # A cyclic coded definition must not hang during ownership discovery.
    visited=set()
    def check_definition(name,trail=()):
        if name in trail:raise ValueError('Block tham chiếu vòng khi tìm chủ sở hữu chi tiết: '+name)
        if len(trail)>=128:raise ValueError('Block lồng quá 128 cấp khi tìm chủ sở hữu chi tiết')
        if name in visited:return
        for child in doc.blocks.get(name,[]):
            if child.dxftype()=='INSERT':check_definition(child.dxf.name,trail+(name,))
        visited.add(name)
    for layout in doc.layouts:
        for entity in layout.query('INSERT'):check_definition(entity.dxf.name)
    @lru_cache(maxsize=None)
    def contains(name,trail=()):
        if name in codes:return True
        if name in trail:raise ValueError('Block tham chiếu vòng khi tìm chủ sở hữu chi tiết: '+name)
        if len(trail)>=128:raise ValueError('Block lồng quá 128 cấp khi tìm chủ sở hữu chi tiết')
        return any(entity_identity(e,codes) or contains(e.dxf.name,trail+(name,)) for e in doc.blocks.get(name,[]) if e.dxftype()=='INSERT')
    result=[];cache=bbox.Cache()
    def visit(entity,ref,parent,layout,trail=()):
        name=entity.dxf.name
        code=entity_identity(entity,codes)
        if name in trail:raise ValueError('Block tham chiếu vòng khi tìm chủ sở hữu chi tiết: '+name)
        if len(trail)>=128:raise ValueError('Block lồng quá 128 cấp khi tìm chủ sở hữu chi tiết')
        if not (code or contains(name)):return
        if code:
            extent=bbox.extents([entity],fast=True,cache=cache)
            if extent.has_data:
                corners=[parent.transform(p) for p in extent.cube_vertices()]
                box=[min(p.x for p in corners),min(p.y for p in corners),max(p.x for p in corners),max(p.y for p in corners)]
                owners=[s['id'] for s in sheets if s['layout']==layout and inside(box[:2],s['bbox']) and inside(box[2:],s['bbox'])]
                if owners:result.append(dict(part_code=code,instance_ref=ref,sheet_ids=owners,bbox=box,
                    evidence='Native INSERT name or explicit part-code ATTRIB equals verified BOM code; full placed geometry lies inside frame'))
        if len(result)>64000:raise ValueError('Quá 64000 instance chi tiết; cần chia nhóm trước khi sửa')
        matrix=entity.matrix44()*parent
        for child in doc.blocks.get(name,[]):
            if child.dxftype()=='INSERT':visit(child,ref+'/'+child.dxf.handle,matrix,layout,trail+(name,))
    for layout in doc.layouts:
        for entity in layout.query('INSERT'):
            visit(entity,entity.dxf.handle,Matrix44(),layout.name)
    return result
