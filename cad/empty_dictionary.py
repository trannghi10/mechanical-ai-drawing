"""Preserve narrowly recognized, owner-bound empty extension dictionaries."""


def handle(entity):
    if not entity.has_extension_dict:return None
    dictionary=entity.get_extension_dict().dictionary
    if (dictionary.dxftype()!='DICTIONARY' or len(dictionary) or dictionary.dxf.owner!=entity.dxf.handle
            or dictionary.has_extension_dict or dictionary.get_reactors() or dictionary.xdata
            or dictionary.dxf.hard_owned!=1 or dictionary.dxf.cloning!=1):return None
    from ezdxf.lldxf.tagwriter import TagCollector
    tags=TagCollector.dxftags(dictionary)
    expected=[(0,'DICTIONARY'),(5,dictionary.dxf.handle),(330,entity.dxf.handle),(100,'AcDbDictionary'),(280,1),(281,1)]
    return dictionary.dxf.handle if [(t.code,t.value) for t in tags]==expected else None


def verify_mapping(original,modified,mapping):
    for old,new in mapping.items():
        entity=original.entitydb.get(old)
        if entity is None:continue
        empty=handle(entity)
        if empty is None or empty not in mapping:continue
        actual=modified.entitydb.get(new)
        if actual is None or handle(actual)!=mapping[empty]:
            raise ValueError('Empty extension dictionary lost ownership or content after clone')
