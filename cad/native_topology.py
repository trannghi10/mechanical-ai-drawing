"""Compare listed native reactor/dictionary handles with a DXF readback.

Equality covers these listed references, never every native object or a mechanical group.
"""


def compare(inventory, doc):
    differences=[];unavailable=[];checked=0;reactor_differences=0;extension_differences=0
    for row in inventory.get('entities',[]):
        handle=row['handle']
        if 'persistent_reactor_handles' not in row or 'extension_dictionary_handle' not in row:
            unavailable.append(handle);continue
        entity=doc.entitydb.get(handle)
        if entity is None or not entity.is_alive or entity.dxftype()!=row['type'] or entity.dxf.owner!=row['owner_handle']:
            differences.append(dict(handle=handle,reason='entity_type_or_owner_mismatch'));continue
        native=set(row['persistent_reactor_handles']);actual=set(entity.get_reactors())
        extension=entity.get_extension_dict().dictionary.dxf.handle if entity.has_extension_dict else None
        checked+=1
        reactor_differences+=native!=actual
        extension_differences+=extension!=row['extension_dictionary_handle']
        if native!=actual or extension!=row['extension_dictionary_handle']:
            differences.append(dict(handle=handle,reason='listed_references_differ',
                native_reactors_not_listed_by_dxf=sorted(native-actual),dxf_reactors_not_listed_by_native=sorted(actual-native),
                native_extension_dictionary=row['extension_dictionary_handle'],dxf_extension_dictionary=extension,
                dxf_extension_entries=[dict(name=k,type=v.dxftype(),handle=v.dxf.handle) for k,v in entity.get_extension_dict().items()] if entity.has_extension_dict else []))
    status='listed_topology_differs' if differences else 'topology_unavailable' if unavailable or not checked else 'matched_listed_topology'
    return dict(status=status,checked_entity_count=checked,unavailable_entity_count=len(unavailable),
                difference_count=len(differences),reactor_difference_count=reactor_differences,extension_dictionary_difference_count=extension_differences,differences=differences,
                policy='Read-only comparison of listed reactor and extension dictionary handles; not edit authorization or proof of complete mechanical dependencies.')
