"""Close a read-only DIMASSOC graph before copying its owning block."""
from cad.dimension_associations import source_binding
from cad.dimensions import serialize


def extend(doc,owner,reactors,members):
    objects=set();extensions=set();pending=list(members);visited=set()
    while pending:
        handle=pending.pop()
        if handle in visited:continue
        visited.add(handle);entity=doc.entitydb[handle]
        for link in set(entity.get_reactors())-reactors.get(handle,set()):
            assoc=doc.entitydb.get(link)
            if assoc is None or assoc.dxftype()!='DIMASSOC':raise ValueError('DIMASSOC có reactor ngoài nhóm chưa hỗ trợ')
            raw=serialize(assoc);pairs=[(int(raw[i]),raw[i+1].strip().decode('utf8')) for i in range(0,len(raw),2)]
            start=next((i for i,p in enumerate(pairs) if p==(100,'AcDbDimAssoc')),None)
            if start is None:raise ValueError('DIMASSOC thiếu subclass native')
            dimension_refs=[v for c,v in pairs[start+1:] if c==330]
            dim=doc.entitydb.get(dimension_refs[0]) if len(dimension_refs)==1 else None
            if dim is None or dim.dxftype()!='DIMENSION' or dim.dxf.owner!=owner or not dim.has_extension_dict:
                raise ValueError('DIMASSOC cần DIM cùng definition')
            extension=dim.get_extension_dict();dictionary=extension.dictionary
            if set(extension.keys())!={'ACAD_DIMASSOC'} or extension['ACAD_DIMASSOC'] is not assoc or dictionary.dxf.owner!=dim.dxf.handle or assoc.dxf.owner!=dictionary.dxf.handle:
                raise ValueError('DIMASSOC ownership không khớp')
            if set(dim.get_reactors())!={link} or set(assoc.get_reactors())-{dictionary.dxf.handle} or assoc.has_extension_dict or dictionary.get_reactors():
                raise ValueError('DIMASSOC có dữ liệu ngoài nhóm')
            binding=source_binding(dim)
            if binding is None or binding['status']!='verified_source_points' or handle not in binding['source_refs']:
                raise ValueError('DIMASSOC chưa chứng minh điểm đo nguồn')
            for ref in binding['source_refs']:
                source=doc.entitydb.get(ref)
                if source is None or source.dxf.owner!=owner or source.has_extension_dict or link not in source.get_reactors():
                    raise ValueError('DIMASSOC biên thiếu hoặc vượt definition')
                reactors.setdefault(ref,set()).add(link);members.add(ref);pending.append(ref)
            reactors[dim.dxf.handle]={link};members.add(dim.dxf.handle)
            extensions.add(dim.dxf.handle);objects.update([dictionary.dxf.handle,link])
    return objects,extensions
