"""Private repair proposals for native DIM heads lacking source references."""
from cad.native_action_review import review
from cad.dimensions import dimension_snapshot
from cad.dimension_associations import source_binding


def propose(doc,group,report):
    assessment=review(doc,group,report);actions={r['dimension_handle']:r for r in group['native_actions']};repairs=[]
    for endpoint in assessment['endpoints']:
        if endpoint['source_bound']:continue
        if endpoint['field']!='defpoint2' or endpoint['status']!='no_matching_reference_in_inspected_action_parameters' or len(endpoint['candidate_vertex_indices'])!=1:
            raise ValueError('Native head candidate does not have complete bounded evidence')
        handle=endpoint['dimension_handle'];dim=doc.entitydb[handle];snapshot=dimension_snapshot(dim)
        if dim.has_extension_dict or snapshot['text'] not in ('','<>'):raise ValueError('Native head DIM already associated or text overridden')
        b=next(e for e in assessment['endpoints'] if e['dimension_handle']==handle and e['field']=='defpoint3')
        if not b['source_bound'] or len(b['candidate_vertex_indices'])!=1:raise ValueError('Native B vertex evidence required')
        repairs.append(dict(**actions[handle],a_vertex=endpoint['candidate_vertex_indices'][0],b_vertex=b['candidate_vertex_indices'][0],
                            a=snapshot['defpoint2'],b=snapshot['defpoint3'],design_intent_confirmed=False))
    if len(repairs)!=2:raise ValueError('Exactly two native head candidates required')
    return dict(polyline_handle=group['polyline_handle'],dimension_handles=group['dimension_handles'],repairs=repairs,
                repair_native_heads=True,native_endpoint_review=assessment,proposal_only=True,mechanical_group_complete=False,customer_revision_created=False)


def hybrid_binding(dim,native_dependency):
    """Parse legacy snap data in a temporary DXF model, preserving native reactors.

    Native ownership must independently be verified by the AutoCAD receipt. This
    helper is not used by production geometry writers and never saves the model.
    """
    if not dim.has_extension_dict:return None
    ext=dim.get_extension_dict()
    if set(ext.keys())!={'ACAD_DIMASSOC'}:raise ValueError('Unsupported hybrid DIM dictionary')
    association=ext['ACAD_DIMASSOC'].dxf.handle;reactors=list(dim.get_reactors())
    if set(reactors)!={association,native_dependency}:raise ValueError('Unexpected hybrid DIM reactors')
    try:
        dim.set_reactors([association]);binding=source_binding(dim)
    finally:dim.set_reactors(reactors)
    return binding
