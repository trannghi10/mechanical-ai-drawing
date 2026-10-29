"""Bounded inventory audit for adding two references without changing geometry."""
from cad.geometry import near


def validate_inventory(before, after, root, targets):
    """Allow only declared reactors/dictionaries, DIM graphics and name renumbering.

    Anonymous block labels may be renumbered by AutoCAD save, but block handles,
    membership and every member's ownership must remain consistent.
    """
    a={r['handle']:r for r in before['entities']};b={r['handle']:r for r in after['entities']}
    ba={r['handle']:r for r in before['blocks']};bb={r['handle']:r for r in after['blocks']}
    if ba.keys()!=bb.keys():raise ValueError('Block inventory changed')
    visual_owners=set();new_associations=set()
    for handle in targets:
        x,y=a[handle],b[handle]
        owner=x['dimension_block_handle']
        if not owner or y['dimension_block_handle']!=owner:raise ValueError('DIM visual ownership changed')
        visual_owners.add(owner)
        refs=y.get('extension_records',[])
        if x.get('extension_dictionary_handle') or len(refs)!=1 or refs[0]['name']!='ACAD_DIMASSOC':
            raise ValueError('Unexpected DIM dictionary')
        assoc=refs[0]['handle'];new_associations.add(assoc)
        if set(y['persistent_reactor_handles'])!=set(x['persistent_reactor_handles'])|{assoc}:
            raise ValueError('Native B DIM reactor changed')
        ignored={'extension_dictionary_handle','extension_records','persistent_reactor_handles'}
        if not near({k:v for k,v in x.items() if k not in ignored},{k:v for k,v in y.items() if k not in ignored},1e-8):
            raise ValueError('DIM geometry/style changed')
    if len(new_associations)!=len(targets):raise ValueError('Duplicate new DIM associations')
    if set(b[root]['persistent_reactor_handles'])!=set(a[root]['persistent_reactor_handles'])|new_associations:
        raise ValueError('Polyline reactor ownership changed')
    added=b.keys()-a.keys();removed=a.keys()-b.keys()
    if any(b[h]['owner_handle'] not in visual_owners for h in added) or any(a[h]['owner_handle'] not in visual_owners for h in removed):
        raise ValueError('Objects outside DIM visuals added/removed')
    renamed=[]
    for h in ba:
        x,y=ba[h],bb[h];ignored=set()
        if x['name']!=y['name']:
            if not x['name'].startswith('*D') or not y['name'].startswith('*D'):
                raise ValueError('Named block changed')
            ignored.add('name');renamed.append(h)
        if h in visual_owners:ignored.add('members')
        if not near({k:v for k,v in x.items() if k not in ignored},{k:v for k,v in y.items() if k not in ignored},1e-8):
            raise ValueError('Block metadata/membership changed')
    checked=0
    for h in a.keys()&b.keys():
        if h in targets or a[h]['owner_handle'] in visual_owners:continue
        x,y=a[h],b[h];ignored=set()
        if h==root:ignored.add('persistent_reactor_handles')
        if x.get('block')!=y.get('block'):
            owner=x['owner_handle']
            if owner!=y['owner_handle'] or owner not in renamed or x['block']!=ba[owner]['name'] or y['block']!=bb[owner]['name']:
                raise ValueError('Entity block reference changed')
            ignored.add('block')
        if not near({k:v for k,v in x.items() if k not in ignored},{k:v for k,v in y.items() if k not in ignored},1e-8):
            raise ValueError('Unselected inventory changed: '+h)
        if h!=root:checked+=1
    return dict(status='verified_bounded_native_reference_inventory',unselected_entries_checked=checked,
                recreated_visual_entities=dict(added=len(added),removed=len(removed)),
                anonymous_blocks_renumbered=renamed,numeric_tolerance=1e-8)
