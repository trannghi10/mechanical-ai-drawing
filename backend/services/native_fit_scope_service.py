"""Expand source-derived receiving parts to their existing manufacturing views.

Detection is unchanged; only active graph-identified targets can be added.
Derived influence is preserved when saved revisions recheck process coverage.
"""
def derived_codes(plan):
    if isinstance(plan,dict):
        bindings=plan.get('native_span_fits',[]);recipes={r['dimension_ref']:r['part_code'] for r in plan.get('resize_recipes',[])}
        return {recipes[b['dimension_ref']] for b in bindings if b['dimension_ref'] in recipes}
    recipes={r.dimension_ref:r.part_code for r in plan.resize_recipes}
    return {recipes[b.dimension_ref] for b in plan.native_span_fits if b.dimension_ref in recipes}


def impact_for(graph,seeds,derived):
    from graph.part_graph import impact_graph
    seeds=set(seeds);derived=set(derived);result=impact_graph(graph,seeds|derived)
    result['seed_codes']=sorted(seeds)
    result['derived_codes']=sorted(derived)
    result['affected_codes']=sorted((set(result['affected_codes'])|derived)-seeds)
    return result


def expand(document_id,source,plan,context,graph,targets,sheets,request,review_only_ids,scope_links,discover=False):
    from backend.services import catalog_service as storage
    from backend.services.scope_service import related_scope
    from backend.services.change_service import context_for
    from backend.services.design_choices import attach
    from backend.services.parametric_service import compile_recipes
    from graph.native_instances import synchronize as sync_instances
    from graph.native_contacts import synchronize as sync_contacts
    from cad.measured_features import index
    from graph.design_model import build
    if plan.questions or not plan.operations:return plan,context,targets,review_only_ids,scope_links,context['part_graph']
    seeds=set(context['part_graph']['seed_codes'])
    for _ in range(4):
        derived=derived_codes(plan)
        if discover:
            # A receiver can initially be review-only because shared process
            # membership is not itself a fit. Reconstruct the actual fit from
            # the edited source assembly before opening its detail snapshots;
            # otherwise native-instance sync fails before scope expansion.
            from graph.native_span_fits import proofs
            derived.update(p['part_code'] for p in proofs(plan,context))
        if not derived:return plan,context,targets,review_only_ids,scope_links,context['part_graph']
        impact=impact_for(graph,seeds,derived)
        nodes=[n for n in graph['nodes'] if n['code'] in derived]
        editable={sid for n in nodes for sid in n['detail_sheets']}
        editable.update(sid for n in nodes for i in n.get('native_instances',[]) for sid in i['sheet_ids'])
        new_reviews=sorted(set(review_only_ids)-editable)
        new_targets,links=related_scope(targets,context,sheets,request,graph,derived)
        if len(new_targets)==len(targets) and new_reviews==review_only_ids:
            context=dict(context,part_graph=impact)
            return plan,context,targets,review_only_ids,scope_links,impact
        old=context;context=context_for(source,new_targets,new_reviews) if new_reviews else context_for(source,new_targets)
        if old.get('document_reading'):context['document_reading']=old['document_reading']
        scope_links=scope_links+links
        context.update(scope_links=scope_links,root_target_ids=old['root_target_ids'],root_bom_refs=old['root_bom_refs'],part_graph=impact)
        context['source_features']=index(context,graph);context['design_model']=build(context,graph)
        if old.get('request_requirements'):context['request_requirements']=old['request_requirements']
        if old.get('design_policy'):context['design_policy']=old['design_policy']
        context['preserve_native_assembly_envelope']=old.get('preserve_native_assembly_envelope',False)
        context['preserve_source_contact_gaps']=old.get('preserve_source_contact_gaps',False)
        context['preserved_native_span_mm']=old.get('preserved_native_span_mm')
        attach(context,storage.folder(document_id))
        plan=compile_recipes(plan,context);plan=sync_contacts(sync_instances(plan,context),context)
        targets,review_only_ids=new_targets,new_reviews
    raise ValueError('Chuỗi chi tiết co/giãn mở rộng quá nhiều phạm vi; cần kiểm tra lại liên kết')
