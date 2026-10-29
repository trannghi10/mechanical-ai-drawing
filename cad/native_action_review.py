"""Describe missing native endpoint evidence without manufacturing a binding."""
from cad.geometry import near
from cad.dimensions import dimension_snapshot
from cad.native_subentity_bindings import vertex_bindings


def review(doc,group,report):
    proven,fingerprint=vertex_bindings(doc,group,report)
    params={r['action_handle']:r for r in report.get('action_parameters',[])}
    points=[[p[0],p[1],doc.entitydb[group['polyline_handle']].dxf.elevation] for p in doc.entitydb[group['polyline_handle']].get_points()]
    result=[]
    for action in group['native_actions']:
        handle=action['dimension_handle'];snapshot=dimension_snapshot(doc.entitydb[handle]);param=params.get(action['action_handle'])
        complete=param is not None and param.get('errors')==[] and param.get('truncated') is False
        refs=[r['values']['vertex_ref'].get('Point') for r in (param or {}).get('rows',[]) if 'vertex_ref' in r.get('values',{})]
        for field in ('defpoint2','defpoint3'):
            matches=[i for i,p in enumerate(points) if near(p,snapshot[field],1e-6)]
            supported=(handle,field) in proven
            result.append(dict(dimension_handle=handle,field=field,source_bound=supported,
                status='verified_native_vertex' if supported else 'no_matching_reference_in_inspected_action_parameters' if complete and refs and not any(near(p,snapshot[field],1e-6) for p in refs if p is not None) else 'native_endpoint_evidence_incomplete',
                candidate_vertex_indices=matches,action_handle=action['action_handle'],parameter_tree_inspected=complete,
                design_intent_confirmed=False,automatic_repair_allowed=False))
    return dict(report_sha256=fingerprint,endpoints=result,unresolved_count=sum(not r['source_bound'] for r in result),
                coverage='Only the reported dependency, OwnedParams tree and VertexRef points; missing evidence is not proof about every possible native relation.')
