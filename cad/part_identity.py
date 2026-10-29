"""Exact BOM identity from an INSERT name or explicit part-code attributes."""
from bom.reader import normalized, plain

PART_TAGS={'part no','part number','part code','partno','partnumber','partcode',
           'ma chi tiet','machitiet','ma vat tu','mavattu','ma hang','mahang'}


def identity(name, attributes, codes):
    codes=set(codes);candidates=set();declared=[]
    if name in codes:candidates.add(name)
    items=attributes.items() if isinstance(attributes,dict) else attributes
    for tag,value in items:
        label=normalized(tag).replace('_',' ').replace('-',' ')
        if label not in PART_TAGS:continue
        value=plain(value)
        if not value:continue
        declared.append(value)
        if value in codes:candidates.add(value)
    # A conflicting or unknown explicit part-code attribute invalidates the
    # name too. Generic label/value proximity is never identity evidence.
    if len(candidates)!=1:return None
    code=next(iter(candidates))
    if any(value!=code for value in declared):return None
    return code


def entity_identity(entity,codes):
    from cad.block_provenance import source_name
    name=entity.dxf.name;origin=source_name(entity.doc,name)
    if origin and name in codes and origin in codes and origin!=name:return None
    return identity(name if name in codes else origin or name,[(a.dxf.tag,a.dxf.text) for a in entity.attribs],codes)


def record_identity(record,codes):
    if record.get('type')!='INSERT':return None
    name=record.get('name');origin=record.get('source_block_name')
    if origin and name in codes and origin in codes and origin!=name:return None
    return identity(name if name in codes else origin or name,record.get('attributes',[]),codes)
