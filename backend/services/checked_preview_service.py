"""A separate, explicitly partial preview; never relax full-backup coverage."""
import json
import uuid

from backend.services import catalog_service as storage
from cad.edit_engine import apply_patch, digest


def candidate(plan, context, request_review=None):
    if request_review and request_review.get('status') != 'complete':
        return None
    if plan.questions or not plan.operations:
        return None
    from backend.services.change_service import validate_plan
    try:
        checked = validate_plan(plan.model_copy(deep=True), context)
    except ValueError:
        return None
    return checked.model_dump()


def reviews(candidate,context):
    """Review executable preview operations, never the cleared full-plan ops."""
    from backend.services.change_service import DrawingChangePlan
    from graph.packaging_fit import review as packaging_review
    from backend.services.curved_wall_service import review as forming_review
    checked=DrawingChangePlan.model_validate(candidate)
    if checked.questions or not checked.operations:raise ValueError('Không có thao tác xem trước đã kiểm chứng để lập báo cáo')
    return dict(packaging_review=packaging_review(checked,context),forming_review=forming_review(checked,context))


def apply(document_id, plan_id):
    from backend.services.revision_service import safe_id, current_impact, compute_changed_targets
    from backend.services.change_service import context_for, DrawingChangePlan, validate_plan
    from backend.services.design_choices import attach
    from backend.services.compound_planner import verify_bundle
    folder = storage.folder(document_id)
    proposal = json.loads((folder / 'change-plans' / (safe_id(plan_id) + '.json')).read_text(encoding='utf8'))
    from backend.services.document_request_service import validate_plan_source
    validate_plan_source(document_id,proposal)
    if proposal.get('part_selection'):
        from backend.services.design_model_service import resolve_part_selection
        roots=[t for t in proposal['targets'] if t['id'] in proposal['root_target_ids']]
        resolve_part_selection(document_id,roots,proposal['part_selection'],proposal.get('user_request',proposal['request']))
    if proposal.get('execution_available') or not proposal.get('checked_preview_plan'):
        raise ValueError('Kế hoạch này không có bản sửa một phần đã kiểm chứng.')
    source = folder / storage.read_status(document_id)['dxf']
    if digest(source) != proposal['source_hash']:
        raise ValueError('Nguồn đã đổi; cần phân tích lại yêu cầu.')
    inputs={source.resolve()}
    inputs.update(p.resolve() for p in (folder/'original.dwg',folder/'original.dxf') if p.is_file())
    input_hashes={p:digest(p) for p in inputs}
    review_ids = proposal.get('review_only_ids', [])
    context = context_for(source, proposal['targets'], review_ids) if review_ids else context_for(source, proposal['targets'])
    attach(context, folder)
    from graph.native_span_fits import attach_envelope_request
    attach_envelope_request(context,proposal.get('request',''),proposal.get('clarifications'))
    context['root_target_ids'] = proposal.get('root_target_ids', [])
    context['root_bom_refs'] = proposal.get('root_bom_refs', [])
    impact = current_impact(document_id, proposal, source, context)
    context['part_graph'] = impact
    from cad.measured_features import index
    context['source_features'] = index(context, impact)
    plan = DrawingChangePlan.model_validate(proposal['checked_preview_plan'])
    if plan.questions or not plan.operations:
        raise ValueError('Thao tác CAD trực tiếp chưa đủ dữ liệu để xem trước.')
    from backend.services.height_request_service import verify as verify_height
    verify_height(plan,context,proposal.get('request',''),proposal.get('clarifications'))
    verify_bundle(plan, context, proposal.get('request', ''), proposal.get('clarifications'))
    validate_plan(plan, context)
    from backend.services.solid_validation_service import validate_solids
    from graph.change_dependencies import propagate, CoordinateRule
    rules = [CoordinateRule.model_validate(d.coordinate_rule) for d in plan.dependencies if d.coordinate_rule]
    operations = propagate(plan.operations, rules, context)
    from graph.fit_constraints import validate_fits
    from graph.measurement_rules import validate_equations
    validate_fits(operations, [d.fit_rule for d in plan.dependencies if d.fit_rule], context)
    validate_equations(operations, [d.equation_rule for d in plan.dependencies if d.equation_rule], context)
    solid = validate_solids(plan.model_copy(update={'operations':operations}), context)
    revision_id = uuid.uuid4().hex
    output = folder / 'revisions' / revision_id
    from graph.confirmed_inner_tubes import validate as nominal_bindings_for
    nominal_bindings = nominal_bindings_for(plan.model_copy(update={'operations':operations}),context)
    from backend.services.edit_gate_service import require_plan
    gate=require_plan(document_id,proposal,context,preview=True,validated=True)
    report = apply_patch(source, output / 'modified.dxf', operations,
                         {e['ref'] for e in context['entities']}, proposal['source_hash'],nominal_bindings=nominal_bindings)
    remaining = proposal['plan'].get('questions', [])
    from graph.drawing_sync import assembly_sync_review
    from graph.packaging_fit import review as packing
    from backend.services.curved_wall_service import review as forming
    data = dict(id=revision_id, plan_id=plan_id, status='validated', validation=report,nominal_dimension_bindings=nominal_bindings,edit_gate=gate,
                relationship_evidence=gate.get('relationship_evidence',[]),
                targets=proposal['targets'], root_target_ids=proposal.get('root_target_ids', []),
                approved_hash=None, dwg_ready=False, previewed_hash=None, previewed_targets=[],
                dependencies=[d.model_dump() for d in plan.dependencies], confirmed_dependencies=[],
                pending_dependencies=list(range(len(plan.dependencies))), complete_product_backup=False,
                preview_only_reason='; '.join(remaining) or 'Chưa kiểm chứng đầy đủ các liên kết công đoạn.',
                process_policy_version=1, process_assessments=[r.model_dump() for r in plan.process_assessments],
                process_groups=impact.get('process_groups', []), drawing_sync=assembly_sync_review(plan, context),
                packaging_review=packing(plan, context), forming_review=forming(plan, context),
                request_review=proposal.get('request_review'), solid_validation=solid,
                size_interpretation=proposal.get('size_interpretation',[]),
                solid_validation_required=bool(plan.profile_cut_recipes or plan.resize_recipes or plan.curved_wall_recipes or plan.hole_recipes))
    from graph.request_fulfillment import review as fulfillment_review
    data['fulfillment_review']=fulfillment_review(plan,context)
    if proposal.get('part_selection'):data['part_selection']=proposal['part_selection']
    from bom.stage_links import review_material_inputs
    data['material_input_review']=review_material_inputs(plan,impact,context)
    if any(digest(p)!=before for p,before in input_hashes.items()):
        raise ValueError('File nguồn đã đổi trong lúc tạo bản xem trước; chưa chấp nhận bản sửa.')
    data['source_preservation']=dict(policy='new_revision_only',status='verified_unchanged',
        files=[dict(filename=p.relative_to(folder.resolve()).as_posix(),sha256=input_hashes[p]) for p in sorted(inputs)])
    from backend.services.revision_service import ensure_changed_targets
    data['changed_targets']=compute_changed_targets(report.get('changes',[]),context,data['targets'])
    if not data['changed_targets']:
        ensure_changed_targets(data,context,data['targets'])
    storage.write_json(output / 'revision.json', data)
    import os
    if os.environ.get('CAD_AUTO_PRE_EXPORT','1')=='1' and (os.environ.get('CAD_FREE_MODE','0')!='1' or os.environ.get('CAD_DWG_ENABLED','0')=='1'):
        try:
            from backend.services.export_jobs import start as start_export
            start_export(document_id, revision_id, format='dwg', scope='document', preview=True)
        except Exception:
            pass
    return data
