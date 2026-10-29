"""One uniquely solvable size for repeated native parts in a contact chain.

    Reuse of a complete source CAD definition proves equal part parameters.
    No equal-share rule is invented for different parts or branching assemblies.
"""
import math
import networkx as nx
from cad.geometry import near
from cad.frame_geometry import world

TOL=1e-5


def proofs(plan,context,by,local,old,after,driven,sid,auto_codes,tagged,stationary=None):
    from graph.native_span_fits import NativeSpanFit,measured_gap,held_envelope
    from graph.native_instances import equivalent_flat_refs
    # A bounded adapter, not a partial certificate of a large cutting layout.
    # Unsolved contacts retain the existing validation/approval gates.
    if len(local)>128:return []
    results=[];ops={o.ref for o in plan.operations if o.action=='replace_geometry'}
    occupied=[f['points'] for f in local.values()]
    def connection(a,b,axis):
        return measured_gap(local[a]['points'],local[b]['points'],axis,by,sid,occupied,context.get('preserve_source_contact_gaps',False))
    for axis in (0,1):
        holders={r:d for (r,k),d in {**(stationary or {}),**driven}.items() if k==axis}
        if len(holders)<2:continue
        # A stationary peer may be part of the receiving chain. Its unchanged
        # source DIM does not distinguish it from a stationary end support.
        # Identify the entire equivalent chain first, then prove its two ends.
        eligible={r:f for r,f in local.items() if (r,axis) not in driven
            and (f['part_code'] in auto_codes or not any(ref in ops for ref in f['refs']))
            and (r in tagged or not any(o.ref==r and o.action=='move_insert' for o in plan.operations))}
        for code in sorted({f['part_code'] for f in eligible.values()}):
            refs=sorted(r for r,f in eligible.items() if f['part_code']==code)
            if len(refs)<2:continue
            graph=nx.DiGraph();graph.add_nodes_from(refs)
            for a in refs:
                for b in refs:
                    if a==b or old[b][0,axis]<old[a][1,axis]-TOL:continue
                    gap=connection(a,b,axis)
                    if gap is not None:graph.add_edge(a,b,gap=gap)
            for component in nx.weakly_connected_components(graph):
                if len(component)<2 or len(component)>32:continue
                chain=graph.subgraph(component)
                if not nx.is_directed_acyclic_graph(chain) or any(chain.in_degree(r)>1 or chain.out_degree(r)>1 for r in chain):continue
                starts=[r for r in chain if chain.in_degree(r)==0];ends=[r for r in chain if chain.out_degree(r)==0]
                if len(starts)!=1 or len(ends)!=1:continue
                ordered=list(nx.topological_sort(chain));first,last=ordered[0],ordered[-1]
                low={r:connection(r,first,axis) for r in holders if r not in component}
                high={r:connection(last,r,axis) for r in holders if r not in component}
                low={r:g for r,g in low.items() if g is not None};high={r:g for r,g in high.items() if g is not None}
                if len(low)!=1 or len(high)!=1:continue
                left,right=next(iter(low)),next(iter(high))
                if not any((r,axis) in driven for r in (left,right)):continue
                if not near(after[left][0,axis],old[left][0,axis],TOL) or not near(after[right][1,axis],old[right][1,axis],TOL):continue
                envelope=held_envelope(plan,context,by,local,old,driven,left,right,axis,sid)
                if envelope is None:continue
                outside,fixed_refs=envelope
                inner=[chain[a][b]['gap'] for a,b in zip(ordered,ordered[1:])]
                gaps=[low[left][1],high[right][1]];gap_refs=[low[left][0],high[right][0]]
                space=after[right][0,axis]-after[left][1,axis]-sum(gaps)-sum(g[1] for g in inner)
                source_space=sum(old[r][1,axis]-old[r][0,axis] for r in ordered)
                if near(space,source_space,TOL):continue
                dimensions=[];valid=True
                for r in ordered:
                    dims=[d for d in local[r]['dimensions'] if abs(abs(d['axis'][axis])-1)<1e-7 and near(d['measurement']/d['linear_factor'],old[r][1,axis]-old[r][0,axis],TOL)]
                    if len(dims)!=1:raise ValueError('Thiếu DIM đo thật duy nhất cho chi tiết nối tiếp: '+code)
                    dimensions.append(dims[0])
                d=dimensions[0]
                # Equal BOM code alone does not prove matching geometry or the
                # same local measured axis. Check a complete native bijection.
                for r,other in zip(ordered[1:],dimensions[1:]):
                    mapping=equivalent_flat_refs(by,first,r)
                    if not mapping or {mapping.get(ref) for ref in local[first]['refs']}!=set(local[r]['refs']) or mapping.get(d['ref'])!=other['ref'] or not near(other['measurement'],d['measurement'],TOL):
                        valid=False;break
                if not valid:raise ValueError('Các chi tiết nối tiếp cùng mã chưa có định nghĩa CAD tương đương: '+code)
                weights=[1/x['linear_factor'] for x in dimensions];target=space/sum(weights)
                if not math.isfinite(target) or target<=TOL:raise ValueError('Chuỗi chi tiết không còn chiều dài hợp lệ sau sửa')
                g=world(by[d['ref']])['geometry'];anchor='first' if g['defpoint2'][axis]<g['defpoint3'][axis] else 'second'
                binding=NativeSpanFit(receiver_ref=first,dimension_ref=d['ref'],support_refs=[left,right],support_dimension_refs=[holders[left]['ref'],holders[right]['ref']],axis=axis,sheet_id=sid,source_hash=context['source_hash'],
                    clearances=gaps,clearance_dimension_refs=gap_refs,peer_refs=ordered[1:],peer_dimension_refs=[x['ref'] for x in dimensions[1:]],
                    clearance_policy='source_faces_on_explicit_keep_gap_request' if any(g>TOL and not ref for ref,g in [low[left],high[right],*inner]) else 'native_dimension',
                    inner_clearance_refs=[g[0] for g in inner],inner_clearances=[g[1] for g in inner],outside_dimension_ref=outside,fixed_support_refs=fixed_refs)
                evidence=sorted({ref for r in [left,*ordered,right] for ref in [r,*local[r]['evidence_refs']]}|{x['ref'] for x in dimensions}|set(binding.support_dimension_refs)|{ref for ref in [*gap_refs,*binding.inner_clearance_refs,outside] if ref})
                results.append(dict(binding=binding,part_code=code,source_parts=[local[left]['part_code'],local[right]['part_code']],old_mm=d['measurement'],new_mm=target,
                    anchor=anchor,evidence_refs=evidence,coefficients=[1/holders[left]['linear_factor'],*weights,1/holders[right]['linear_factor']]))
    return results
