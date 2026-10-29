"""Candidate repairs of partial legacy DIM associations; no design approval."""
from cad.dimension_associations import source_binding
from cad.dimensions import dimension_snapshot
from cad.geometry import near


def legacy_endpoint_proposals(doc,group):
    poly=doc.entitydb[group['polyline_handle']]
    if poly.dxftype()!='LWPOLYLINE' or not poly.closed or len(poly)!=8 or doc.units!=4:
        raise ValueError('Bounded millimeter eight-vertex profile required')
    if tuple(poly.dxf.extrusion)!=(0,0,1) or any(any(abs(v)>1e-10 for v in p[2:]) for p in poly.get_points()):
        raise ValueError('Straight XY profile without widths required')
    points=[[p[0],p[1],poly.dxf.elevation] for p in poly.get_points()]
    repairs=[]
    for row in group['legacy_associations']:
        dim=doc.entitydb[row['dimension_handle']];binding=source_binding(dim)
        if not binding or binding!=row['binding']:raise ValueError('Stale source association evidence')
        fields={p['dimension_field'] for p in binding['points']}
        if fields=={'defpoint2','defpoint3'}:continue
        if fields!={'defpoint2'} or binding['points'][0]['endpoint']!='vertex':raise ValueError('Unsupported partial association repair')
        snapshot=dimension_snapshot(dim)
        if snapshot['text'] not in ('','<>'):raise ValueError('Overridden DIM text cannot establish repair intent')
        indices=[]
        for field in ('defpoint2','defpoint3'):
            matches=[i for i,p in enumerate(points) if near(snapshot[field],p,1e-6)]
            if len(matches)!=1:raise ValueError('Repair endpoint does not uniquely match a source vertex')
            indices.append(matches[0])
        if indices[0]==indices[1]:raise ValueError('Repair endpoints collapse')
        repairs.append(dict(dimension_handle=row['dimension_handle'],association_ref=binding['association_ref'],
            a_vertex=indices[0],b_vertex=indices[1],a=snapshot['defpoint2'],b=snapshot['defpoint3'],
            original_binding=binding,proposal='Attach missing second point to unique coincident source vertex',
            design_intent_confirmed=False))
    if len(repairs)!=2:raise ValueError('Expected exactly two partial legacy DIM candidates')
    return dict(polyline_handle=group['polyline_handle'],dimension_handles=group['dimension_handles'],repairs=repairs,
                mechanical_group_complete=False,customer_revision_created=False,proposal_only=True)
