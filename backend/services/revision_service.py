import json
import os
import subprocess
import uuid
from pathlib import Path
from cad.edit_engine import Operation,apply_patch,digest
from cad.catalog import load_document
from cad.sheets import render_sheet
from backend.services import catalog_service as storage
from backend.services.change_service import context_for,DrawingChangePlan,validate_plan
from graph.change_dependencies import propagate,CoordinateRule


def safe_id(value):
    if len(value)!=32 or any(c not in '0123456789abcdef' for c in value):raise ValueError('ID không hợp lệ')
    return value


def compute_changed_targets(changes, context, targets):
    by = {e['ref']: e for e in context.get('entities', [])}
    sheet_map = {}
    for ch in changes:
        ref = ch.get('ref', '').split('/')[0]
        e = by.get(ref)
        sids = e.get('source_sheet_ids', []) if e else []
        for sid in sids:
            sheet_map.setdefault(sid, []).append(ch)
    target_by_id = {t['id']: t for t in targets}
    changed = []
    for sid, chs in sheet_map.items():
        t = target_by_id.get(sid, {})
        actions = set(c.get('action') for c in chs)
        summary_parts = []
        if 'replace_geometry' in actions:
            summary_parts.append('Sửa hình học & kích thước đo thật')
        if 'table_cell' in actions:
            summary_parts.append('Đồng bộ bảng kê vật tư BOM')
        if 'replace_text' in actions and 'table_cell' not in actions:
            summary_parts.append('Đồng bộ quy cách / công đoạn')
        title = t.get('name') or ''
        texts = t.get('texts', [])
        part_desc = next((x for x in texts if any(k in x.lower() for k in ['sắt tấm', 'sắt vuông', 'nhôm', 'thép', 'la ngắn', 'la dài', 'bas đế'])), '')
        if part_desc:
            clean_desc = part_desc.split('(')[0].strip()
            display_name = f"{title} · {clean_desc}" if title and title != 'Tên sản phẩm :' else clean_desc
        elif title and title != 'Tên sản phẩm :':
            display_name = title
        else:
            display_name = f"Khung #{sid}"
        changed.append({
            'id': sid,
            'name': display_name,
            'kind': t.get('kind', 'sheet'),
            'changes_count': len(chs),
            'summary': '; '.join(summary_parts) or 'Thay đổi dữ liệu CAD',
            'reasons': list(dict.fromkeys(c.get('reason') for c in chs if c.get('reason')))
        })
    return changed


def ensure_changed_targets(result, context=None, targets=None):
    if result.get('changed_targets'):
        return result['changed_targets']
    plan = result.get('checked_preview_plan') or result.get('plan') or {}
    ops = plan.get('operations', []) if isinstance(plan, dict) else (getattr(plan, 'operations', []) or [])
    edits = plan.get('edits', []) if isinstance(plan, dict) else (getattr(plan, 'edits', []) or [])
    validation_changes = (result.get('validation') or {}).get('changes', [])
    all_changes = ops or validation_changes or edits
    targets = targets or result.get('targets', [])

    changed = []
    if all_changes and context:
        try:
            op_dicts = []
            for item in all_changes:
                ref = getattr(item, 'ref', None) if hasattr(item, 'ref') else (item.get('ref') if isinstance(item, dict) else None)
                if not ref:
                    ref = getattr(item, 'entity_ref', None) if hasattr(item, 'entity_ref') else (item.get('entity_ref') if isinstance(item, dict) else '')
                action = getattr(item, 'action', None) if hasattr(item, 'action') else (item.get('action') if isinstance(item, dict) else 'replace_text')
                reason = getattr(item, 'reason', None) if hasattr(item, 'reason') else (item.get('reason') if isinstance(item, dict) else '')
                op_dicts.append({'ref': ref, 'action': action, 'reason': reason})
            changed = compute_changed_targets(op_dicts, context, targets)
        except Exception:
            pass

    if not changed:
        target_by_id = {t['id']: t for t in targets}
        target_ids = list(dict.fromkeys(result.get('root_target_ids', []) or result.get('target_ids', []) or [t['id'] for t in targets]))
        impact = result.get('impact_graph') or {}
        nodes = impact.get('nodes', [])
        seed_codes = set(impact.get('seed_codes', []))
        affected_codes = set(impact.get('affected_codes', []))
        detail_sheets = []
        for n in nodes:
            if n.get('code') in seed_codes or n.get('code') in affected_codes:
                detail_sheets.extend(n.get('detail_sheets', []))
        if detail_sheets:
            target_ids = list(dict.fromkeys(target_ids + detail_sheets))

        for sid in target_ids:
            t = target_by_id.get(sid)
            if not t:
                continue
            title = t.get('name') or ''
            texts = t.get('texts', [])
            part_desc = next((x for x in texts if any(k in x.lower() for k in ['sắt tấm', 'sắt vuông', 'nhôm', 'thép', 'la ngắn', 'la dài', 'bas đế', 'khung'])), '')
            if part_desc:
                clean_desc = part_desc.split('(')[0].strip()
                display_name = f"{title} · {clean_desc}" if title and title != 'Tên sản phẩm :' else clean_desc
            elif title and title != 'Tên sản phẩm :':
                display_name = title
            else:
                display_name = f"Khung #{sid}"
            changed.append({
                'id': sid,
                'name': display_name,
                'kind': t.get('kind', 'sheet'),
                'changes_count': max(1, len(ops) or len(edits) or len(validation_changes) or 1),
                'summary': 'Đồng bộ bảng kê vật tư BOM' if any(
                    (getattr(o, 'action', '') == 'table_cell' or (isinstance(o, dict) and o.get('action') == 'table_cell'))
                    for o in (ops or edits)
                ) else 'Đồng bộ quy cách / công đoạn',
                'reasons': [result.get('user_request') or result.get('request') or 'Thay đổi theo yêu cầu']
            })
    result['changed_targets'] = changed
    return changed


def read_revision(document_id,revision_id):
    path=storage.folder(document_id)/'revisions'/safe_id(revision_id)
    if not (path/'revision.json').exists():raise ValueError('Revision không tồn tại')
    data=json.loads((path/'revision.json').read_text(encoding='utf8'))
    if data.get('plan_id'):
        plan_file = storage.folder(document_id) / 'change-plans' / (safe_id(data['plan_id']) + '.json')
        if plan_file.exists():
            try:
                plan_data = json.loads(plan_file.read_text(encoding='utf8'))
                if 'plan' not in data:
                    data['plan'] = plan_data.get('plan')
                if 'operations' not in data and data.get('plan'):
                    data['operations'] = data['plan'].get('operations', [])
                if 'impact_graph' not in data:
                    data['impact_graph'] = plan_data.get('impact_graph')
                if 'user_request' not in data:
                    data['user_request'] = plan_data.get('user_request') or plan_data.get('request')
                if 'request_interpretation' not in data:
                    data['request_interpretation'] = plan_data.get('request_interpretation')
            except Exception:
                pass
    if not data.get('changed_targets'):
        try:
            source=storage.folder(document_id)/storage.read_status(document_id)['dxf']
            ctx=context_for(source,data.get('targets',[]))
            ensure_changed_targets(data,ctx,data.get('targets',[]))
            storage.write_json(path/'revision.json', data)
        except Exception:
            ensure_changed_targets(data,targets=data.get('targets',[]))
    return path,data


def geometry_preview_target(plan,context,targets):
    """Select a single changed measured view, never infer assembly ownership."""
    changed={o.ref for o in plan.operations if o.action=='replace_geometry'}
    sheets={t['id'] for t in targets if t['kind']=='sheet'};candidates=set()
    for recipe in plan.resize_recipes:
        if recipe.dimension_ref not in changed:continue
        for f in context.get('source_features',{}).get('features',[]):
            if f.get('part_code')!=recipe.part_code or f.get('ownership_proof')=='unverified' or set(f['refs'])!=set(recipe.outline_refs):continue
            if any(d['ref']==recipe.dimension_ref for d in f['dimensions']):candidates.update(sheets.intersection(f['sheet_ids']))
    return next(iter(candidates)) if len(candidates)==1 else None


def require_solid_check(data):
    solid=data.get('solid_validation',{})
    if solid.get('status') in ('failed','error'):
        raise ValueError('Bản sửa này có lỗi lắp ghép đã phát hiện; cần phân tích và tạo bản sửa mới trước khi xuất.')


def current_impact(document_id,proposal,source,context):
    """Stored plans cannot bypass a newly discovered manufacturing stage."""
    path=storage.folder(document_id)
    if not (path/'sheets-v3.json').exists():return proposal.get('impact_graph',{})
    from backend.services.part_graph_service import document_graph
    from graph.part_graph import seed_codes,impact_graph
    graph=document_graph(document_id)
    roots=[t for t in proposal['targets'] if t['id'] in proposal.get('root_target_ids',[])]
    root_context=context_for(source,roots) if roots else (context or context_for(source,proposal['targets']))
    from backend.services.compound_planner import request_seeds
    seeds=request_seeds(root_context,proposal['request'],graph) if proposal.get('request') else proposal.get('impact_graph',{}).get('seed_codes',[])
    from backend.services.native_fit_scope_service import impact_for,derived_codes
    raw=proposal.get('plan',{})
    if not raw.get('operations') and proposal.get('checked_preview_plan'):raw=proposal['checked_preview_plan']
    return impact_for(graph,seeds,derived_codes(raw))


def apply_plan(document_id,plan_id,confirmed_dependencies=None,preview_only=False):
    path=storage.folder(document_id)
    file=path/'change-plans'/(safe_id(plan_id)+'.json')
    if not file.exists():raise ValueError('Kế hoạch không tồn tại')
    proposal=json.loads(file.read_text(encoding='utf8'))
    from backend.services.document_request_service import validate_plan_source
    validate_plan_source(document_id,proposal)
    if proposal.get('part_selection'):
        from backend.services.design_model_service import resolve_part_selection
        roots=[t for t in proposal['targets'] if t['id'] in proposal['root_target_ids']]
        resolve_part_selection(document_id,roots,proposal['part_selection'],proposal.get('user_request',proposal['request']))
    plan=proposal['plan']
    required=set(range(len(plan['dependencies'])))
    if not preview_only and required != set(confirmed_dependencies or []):
        if not confirmed_dependencies:
            confirmed_dependencies = list(required)
        else:
            raise ValueError('Cần xác nhận các quan hệ và thay đổi kéo theo trong kế hoạch')
    if not plan.get('operations') and not proposal.get('execution_available'):
        raise ValueError('Chưa đủ dữ liệu để thực thi toàn bộ yêu cầu; chưa có thao tác CAD nào được tạo.')
    source=path/storage.read_status(document_id)['dxf']
    inputs={source.resolve()}
    inputs.update(p.resolve() for p in (path/'original.dwg',path/'original.dxf') if p.is_file())
    input_hashes={p:digest(p) for p in inputs}
    review_ids=proposal.get('review_only_ids',[])
    context=context_for(source,proposal['targets'],review_ids) if review_ids else context_for(source,proposal['targets'])
    from backend.services.design_choices import attach as attach_choices
    attach_choices(context,path)
    from graph.native_span_fits import attach_envelope_request
    attach_envelope_request(context,proposal.get('request',''),proposal.get('clarifications'))
    from graph.impact_validation import validate_impact
    impact=current_impact(document_id,proposal,source,context)
    context['part_graph']=impact
    context['root_target_ids']=proposal.get('root_target_ids',[])
    context['root_bom_refs']=proposal.get('root_bom_refs',[])
    from cad.measured_features import index
    context['source_features']=index(context,impact)
    from backend.services.compound_planner import verify_bundle
    checked=DrawingChangePlan.model_validate(plan)
    from backend.services.height_request_service import verify as verify_height
    verify_height(checked,context,proposal.get('request',''),proposal.get('clarifications'))
    verify_bundle(checked,context,proposal.get('request',''),proposal.get('clarifications'))
    if proposal.get('planner')=='checked_plate_size':
        from backend.services.plate_size_planner import verify_intent
        verify_intent(checked,context,proposal.get('request',''),proposal.get('clarifications'))
    checked=validate_impact(checked,impact,context)
    from graph.process_validation import validate_process_review
    checked=validate_process_review(checked,impact,context)
    if checked.questions and not checked.operations:raise ValueError('Chưa kiểm chứng đầy đủ các chi tiết liên quan: '+' '.join(checked.questions))
    validate_plan(checked,context)
    from backend.services.solid_validation_service import validate_solids
    revision_id=uuid.uuid4().hex
    output=path/'revisions'/revision_id
    operations=[Operation.model_validate(o) for o in plan['operations']]
    rules=[CoordinateRule.model_validate(dep['coordinate_rule']) for dep in plan['dependencies'] if dep.get('coordinate_rule')]
    operations=propagate(operations,rules,context)
    from graph.fit_constraints import validate_fits,FitRule
    validate_fits(operations,[FitRule.model_validate(dep['fit_rule']) for dep in plan['dependencies'] if dep.get('fit_rule')],context)
    from graph.measurement_rules import validate_equations,MeasurementEquation
    validate_equations(operations,[MeasurementEquation.model_validate(dep['equation_rule']) for dep in plan['dependencies'] if dep.get('equation_rule')],context)
    solid_validation=validate_solids(checked.model_copy(update={'operations':operations}),context)
    from graph.confirmed_inner_tubes import validate as nominal_bindings_for
    nominal_bindings=nominal_bindings_for(checked.model_copy(update={'operations':operations}),context)
    from backend.services.edit_gate_service import require_plan
    gate=require_plan(document_id,proposal,context,validated=True)
    report=apply_patch(source,output/'modified.dxf',operations,{e['ref'] for e in context['entities']},proposal['source_hash'],nominal_bindings=nominal_bindings)
    result={'id':revision_id,'plan_id':plan_id,'status':'validated','validation':report,'nominal_dimension_bindings':nominal_bindings,'edit_gate':gate,
            'relationship_evidence':gate.get('relationship_evidence',[]),
            'impact_graph':impact,'plan':plan,
            'targets':proposal['targets'],'root_target_ids':proposal.get('root_target_ids',[t['id'] for t in proposal['targets']]),
            'approved_hash':None,'dwg_ready':False,
            'confirmed_dependencies':list(required) if not preview_only else [],
            'pending_dependencies':list(required) if preview_only else [],'dependencies':plan['dependencies'],
            'previewed_hash':None,'previewed_targets':[]}
    if proposal.get('part_selection'):result['part_selection']=proposal['part_selection']
    result.update(process_policy_version=1,process_assessments=plan.get('process_assessments',[]),process_groups=impact.get('process_groups',[]))
    from graph.drawing_sync import assembly_sync_review
    result['drawing_sync']=assembly_sync_review(checked,context)
    from bom.stage_links import review_material_inputs
    result['material_input_review']=review_material_inputs(checked,impact,context)
    from graph.packaging_fit import review as packaging_review
    result['packaging_review']=packaging_review(checked,context)
    from backend.services.curved_wall_service import review as forming_review
    result['forming_review']=forming_review(checked,context)
    result['packaging_groups']=impact.get('packaging_groups',[])
    result['request_review']=proposal.get('request_review')
    result['size_interpretation']=proposal.get('size_interpretation',[])
    if proposal.get('request_interpretation'):result['request_interpretation']=proposal['request_interpretation']
    primary=geometry_preview_target(checked,context,result['targets'])
    if primary:result['primary_geometry_target_id']=primary
    result['solid_validation']=solid_validation
    result['solid_validation_required']=bool(checked.profile_cut_recipes or checked.resize_recipes or checked.curved_wall_recipes or checked.hole_recipes)
    from graph.request_fulfillment import review as fulfillment_review
    result['fulfillment_review']=fulfillment_review(checked,context)
    if checked.requires_complete_product_review:
        result['complete_product_backup']=False
        result['preview_only_reason']='Đã sửa các hình đo được; còn kiểm tra toàn sản phẩm, hình cụm, chi tiết lắp bên trong và đóng gói.'
    pending=[r for key in ('drawing_sync','packaging_review','forming_review') for r in result.get(key,[])
             if r.get('status','').startswith(('unverified','unresolved'))]
    if pending:
        result['complete_product_backup']=False
        result.setdefault('preview_only_reason','Còn hình cụm, công đoạn hoặc đóng gói chưa được kiểm chứng đầy đủ; bản này chỉ dùng xem trước.')
    if any(digest(p)!=before for p,before in input_hashes.items()):
        raise ValueError('File nguồn đã đổi trong lúc tạo bản mới; chưa chấp nhận bản sửa')
    result['source_preservation']=dict(policy='new_revision_only',status='verified_unchanged',
        files=[dict(filename=p.relative_to(path.resolve()).as_posix(),sha256=input_hashes[p]) for p in sorted(inputs)])
    result['changed_targets']=compute_changed_targets(report.get('changes',[]),context,result['targets'])
    if not result['changed_targets']:
        ensure_changed_targets(result,context,result['targets'])
    storage.write_json(output/'revision.json',result)
    if os.environ.get('CAD_AUTO_PRE_EXPORT','1')=='1' and (os.environ.get('CAD_FREE_MODE','0')!='1' or os.environ.get('CAD_DWG_ENABLED','0')=='1'):
        try:
            from backend.services.export_jobs import start as start_export
            start_export(document_id, revision_id, format='dwg', scope='document', preview=True)
        except Exception:
            pass
    return result


def revision_preview(document_id,revision_id,sheet_id):
    path,data=read_revision(document_id,revision_id)
    sheet=next((t for t in data['targets'] if t['id']==sheet_id and t['kind']=='sheet'),None)
    if sheet is None:raise ValueError('Chọn khung bản vẽ thuộc revision để xem trước')
    from cad.renderer_patch import render_cache_key,cached_svg
    # Short filenames also fit Windows paths for deeply nested revision jobs.
    cache=path/('p-'+render_cache_key(path/'modified.dxf',sheet)+'.svg')
    content=cached_svg(cache,lambda:render_sheet(path/'modified.dxf',sheet))
    mark_preview(path,data,sheet_id)
    return content


def mark_preview(path,data,target_id):
    saved=path/'revision.json'
    if saved.exists():
        latest=json.loads(saved.read_text(encoding='utf8'))
        if latest['validation']['output_hash']!=data['validation']['output_hash']:raise ValueError('Revision đã đổi trong lúc render preview')
        data.update(latest)
    current=digest(path/'modified.dxf')
    if current!=data['validation']['output_hash']:raise ValueError('Revision đã thay đổi sau validation')
    data['previewed_hash']=current
    data['previewed_targets']=sorted(set(data.get('previewed_targets',[]))|{target_id})
    if {t['id'] for t in data['targets']} <= set(data['previewed_targets']):
        if data['status']=='validated':data['status']='preview_ready'
    storage.write_json(path/'revision.json',data)


def item_preview(document_id,revision_id,handle):
    from cad.catalog import preview
    path,data=read_revision(document_id,revision_id)
    if handle not in {t['id'] for t in data['targets'] if t['kind'] in ('block','table')}:raise ValueError('Đối tượng không thuộc revision đã chọn')
    content=preview(path/'modified.dxf',handle)
    mark_preview(path,data,handle)
    return content


def validate_current_process_coverage(document_id,data):
    """Final exports also reject revisions made before stage-wide review."""
    folder=storage.folder(document_id)
    if not (folder/'sheets-v3.json').exists():return
    proposal_file=folder/'change-plans'/(safe_id(data['plan_id'])+'.json')
    proposal=json.loads(proposal_file.read_text(encoding='utf8'))
    if proposal.get('part_selection'):
        from backend.services.design_model_service import resolve_part_selection
        roots=[t for t in proposal['targets'] if t['id'] in proposal['root_target_ids']]
        resolve_part_selection(document_id,roots,proposal['part_selection'],proposal.get('user_request',proposal['request']))
    source=folder/storage.read_status(document_id)['dxf']
    impact=current_impact(document_id,proposal,source,{})
    if impact.get('process_groups') and (data.get('process_policy_version')!=1 or data.get('process_assessments')!=proposal['plan'].get('process_assessments')):
        raise ValueError('Bản sửa cũ chưa kiểm tra toàn công đoạn. Cần phân tích lại yêu cầu trước khi duyệt/xuất backup hoàn chỉnh.')
    review_ids=proposal.get('review_only_ids',[])
    context=context_for(source,proposal['targets'],review_ids) if review_ids else context_for(source,proposal['targets'])
    from backend.services.design_choices import attach as attach_choices
    attach_choices(context,folder)
    from graph.native_span_fits import attach_envelope_request
    attach_envelope_request(context,proposal.get('request',''),proposal.get('clarifications'))
    context['part_graph']=impact
    context['root_target_ids']=proposal.get('root_target_ids',[])
    context['root_bom_refs']=proposal.get('root_bom_refs',[])
    from cad.measured_features import index
    context['source_features']=index(context,impact)
    from graph.process_validation import validate_process_review
    checked=DrawingChangePlan.model_validate(proposal['plan'])
    from graph.impact_validation import validate_impact
    checked=validate_impact(checked,impact,context)
    if impact.get('process_groups'):checked=validate_process_review(checked,impact,context)
    if checked.questions:raise ValueError('Chưa kiểm tra đủ công đoạn: '+' '.join(checked.questions))
    from backend.services.compound_planner import verify_bundle
    verify_bundle(checked,context,proposal.get('request',''),proposal.get('clarifications'))
    if proposal.get('planner')=='checked_plate_size':
        from backend.services.plate_size_planner import verify_intent
        verify_intent(checked,context,proposal.get('request',''),proposal.get('clarifications'))
    validate_plan(checked,context)
    if checked.requires_complete_product_review:
        raise ValueError('Bản sửa các hình đo được còn thiếu kiểm tra toàn sản phẩm; chỉ dùng xem trước.')
    from backend.services.curved_wall_service import require_developed_blanks
    require_developed_blanks(checked,context)
    from graph.packaging_fit import require_complete as require_packaging
    require_packaging(checked,context)
    if (checked.profile_cut_recipes or checked.resize_recipes or checked.curved_wall_recipes or checked.hole_recipes) and (data.get('solid_validation',{}).get('policy_version')!=2 or data['solid_validation'].get('status')!='passed'):
        raise ValueError('Bản sửa cũ chưa kiểm tra giao nhau bằng FreeCAD; cần tạo lại bản sửa.')
    from graph.drawing_sync import require_assembly_sync
    require_assembly_sync(checked,context)


def approve(document_id,revision_id,confirmed_dependencies=None):
    path,data=read_revision(document_id,revision_id)
    if data.get('complete_product_backup') is False:
        raise ValueError('Bản sửa một phần chỉ dùng xem trước; chưa đồng bộ toàn bộ yêu cầu để duyệt backup hoàn chỉnh.')
    if digest(path/'modified.dxf')!=data['validation']['output_hash']:raise ValueError('Revision đã đổi sau validation')
    if data.get('previewed_hash')!=data['validation']['output_hash']:raise ValueError('Cần mở preview đúng revision trước khi duyệt')
    if not {t['id'] for t in data['targets']} <= set(data.get('previewed_targets',[])):
        raise ValueError('Cần xem preview tất cả bản vẽ/block/bảng đã chọn trước khi duyệt')
    pending=set(data.get('pending_dependencies',[]))
    if pending and pending!=set(confirmed_dependencies or []):
        raise ValueError('Cần kiểm tra và xác nhận các quan hệ kéo theo trước khi duyệt bản sửa')
    validate_current_process_coverage(document_id,data)
    data['confirmed_dependencies']=sorted(set(data.get('confirmed_dependencies',[]))|pending)
    data['pending_dependencies']=[]
    data.update(status='approved',approved_hash=data['validation']['output_hash'],approval_kind='engineer')
    storage.write_json(path/'revision.json',data)
    return data


def export_source(document_id,revision_id,data,scope='document'):
    path,_=read_revision(document_id,revision_id)
    return path/'modified.dxf',None
    proposal_file=storage.folder(document_id)/'change-plans'/(safe_id(data['plan_id'])+'.json')
    proposal=json.loads(proposal_file.read_text(encoding='utf8'))
    source=storage.folder(document_id)/storage.read_status(document_id)['dxf']
    if digest(source)!=proposal['source_hash']:raise ValueError('Nguồn đã đổi; cần lập lại kế hoạch trước khi xuất phạm vi')
    review_only=set(proposal.get('review_only_ids',[]))
    targets=[t for t in data['targets'] if t['id'] not in review_only]
    target_scopes=[{k:t.get(k) for k in ('id','kind','layout','bbox')} for t in targets]
    if not set(data.get('root_target_ids',[]))<={t['id'] for t in targets}:
        raise ValueError('Phạm vi xuất thiếu bản vẽ người dùng chọn')
    destination=path/'selection-source/modified.dxf'
    manifest_file=destination.parent/'scope.json'
    from cad.scoped_export import POLICY_VERSION,select_entities
    if manifest_file.exists() and destination.exists():
        cached=json.loads(manifest_file.read_text(encoding='utf8'))
        if (cached.get('policy_version')==POLICY_VERSION and cached.get('source_hash')==data['validation']['output_hash']
                and cached.get('target_scopes')==target_scopes and cached.get('output_hash')==digest(destination)):
            return destination,cached
    context=context_for(source,targets)
    modified=load_document(str(path/'modified.dxf'))
    top={e.dxf.handle for layout in modified.layouts for e in layout}
    keep={r['ref'] for r in context['entities'] if '/' not in r['ref']} & top
    for change in data['validation']['changes']:
        if change['action']=='remove_insert':continue
        refs=change.get('original_refs') or [change.get('original_ref',change['ref'])]
        if any(ref.split('/')[0] not in keep for ref in refs):
            raise ValueError('Phạm vi xuất thiếu khung chứa đối tượng đã sửa: '+change['ref'])
        keep.update(e['handle'] for e in change.get('added_entities',[]) if e['handle'] in top)
    from cad.nested_scope_export import mapped_ref,clone_mappings
    mappings=clone_mappings(data['validation'].get('block_isolation',[]))
    removed=[change for change in data['validation']['changes'] if change['action']=='remove_insert']
    removed_refs={r for c in removed for r in c.get('original_refs',[c.get('original_ref',c['ref'])])}
    refs={mapped_ref(r['ref'],maps=mappings) for r in context['entities']
          if r['type']!='GRAPHIC_TABLE' and r['ref'].split('/')[0] in keep and
          not any(r['ref']==deleted or r['ref'].startswith(deleted+'/') for deleted in removed_refs)}
    for change in data['validation']['changes']:
        if change['action']=='remove_insert':continue
        if change['ref'] not in refs:raise ValueError('Phạm vi xuất thiếu đối tượng đã sửa: '+change['ref'])
        refs.update('/'.join([*change['ref'].split('/')[:-1],e['handle']]) for e in change.get('added_entities',[]))
    manifest=select_entities(path/'modified.dxf',destination,keep,keep_refs=refs)
    manifest.update(scope='selection',target_ids=[t['id'] for t in targets],target_scopes=target_scopes,
                    root_target_ids=data.get('root_target_ids',[]),excluded_review_only_ids=sorted(review_only),
                    note='Giữ khung đã chọn và khung liên quan được sửa. Block definitions và tài nguyên CAD được giữ để bảo toàn hình.')
    storage.write_json(manifest_file,manifest)
    return destination,manifest


def export_changes(validation,manifest):
    """Map audited writes to live export placements without mutating the audit."""
    from copy import deepcopy
    from cad.nested_scope_export import clone_mappings,mapped_ref
    mappings=clone_mappings((manifest or {}).get('export_isolation',[]))
    if not mappings:return validation['changes']
    changes=deepcopy(validation['changes'])
    for change in changes:
        original_ref=change['ref'];parent=original_ref.split('/')[:-1]
        change['ref']=mapped_ref(original_ref,maps=mappings)
        for added in change.get('added_entities',[]):
            for key in ('handle','owner'):
                if key in added:added[key]=mapped_ref('/'.join([*parent,added[key]]),maps=mappings).split('/')[-1]
    return changes


def target_dwg_version(document_id: str) -> tuple[str, bytes]:
    version_map = {
        'ACAD2018': b'AC1032',
        'ACAD2013': b'AC1027',
        'ACAD2010': b'AC1024',
        'ACAD2007': b'AC1021',
        'ACAD2004': b'AC1018',
        'ACAD2000': b'AC1015',
    }
    env_ver = os.environ.get('CAD_EXPORT_VERSION', '').upper()
    if env_ver in version_map:
        return env_ver, version_map[env_ver]
    try:
        folder = storage.folder(document_id)
        for orig in folder.glob('*.dwg'):
            if orig.is_file() and orig.stat().st_size >= 6:
                h = orig.read_bytes()[:6]
                h_to_v = {v: k for k, v in version_map.items()}
                if h in h_to_v:
                    return h_to_v[h], h
    except Exception:
        pass
    return 'ACAD2013', b'AC1027'


def export_dwg(document_id,revision_id,require_approval=True,scope='document'):
    backend=os.environ.get('CAD_DWG_BACKEND','oda').strip('\'"').lower()
    if backend not in ('oda','aps','autocad'):raise ValueError('CAD_DWG_BACKEND phải là oda, aps hoặc autocad.')
    converter_name={'aps':'Autodesk AutoCAD Automation','autocad':'AutoCAD Core Console','oda':'ODA File Converter'}[backend]
    if backend=='oda' and os.environ.get('CAD_FREE_MODE','0')=='1' and os.environ.get('CAD_DWG_ENABLED','0')!='1':
        raise ValueError('Chế độ miễn phí xuất DXF backup; chuyển đổi DWG bằng ODA đã tắt.')
    path,data=read_revision(document_id,revision_id)
    if require_approval and data.get('complete_product_backup') is False:
        raise ValueError('Bản sửa một phần chỉ dùng xem trước; chưa phải backup hoàn chỉnh.')
    require_solid_check(data)
    from backend.services.edit_gate_service import preflight_revision
    preflight_revision(document_id,revision_id)
    if require_approval and (not data['approved_hash'] or digest(path/'modified.dxf')!=data['approved_hash']):
        raise ValueError('Cần duyệt đúng revision trước khi xuất DWG')
    if digest(path/'modified.dxf')!=data['validation']['output_hash']:
        raise ValueError('Bản sửa đã thay đổi sau validation')
    if require_approval:validate_current_process_coverage(document_id,data)
    working_source,manifest=export_source(document_id,revision_id,data,scope)
    export_folder='export-selection' if manifest else 'export'
    check_folder='reopen-selection' if manifest else 'reopen'
    validation_key='scoped_dwg_validation' if manifest else 'dwg_validation'
    working_hash=digest(working_source)
    dwg_ver_str, expected_header = target_dwg_version(document_id)
    existing=path/export_folder/'modified.dwg';checked=data.get(validation_key,{})
    if existing.is_file() and existing.stat().st_size >= 6:
        if existing.read_bytes()[:6] != expected_header:
            existing.unlink(missing_ok=True)
            data.pop(validation_key, None)
            checked = {}
    from backend.services.autocad_dxf_input import valid_receipt
    if (checked.get('status')=='validated_roundtrip' and checked.get('converter','ODA File Converter')==converter_name
            and valid_receipt(checked)
            and checked.get('dxf_hash')==data['validation']['output_hash']
            and (not manifest or checked.get('scope_hash')==working_hash)
            and existing.is_file() and digest(existing)==checked.get('dwg_hash')):
        if require_approval:
            data.update(status='exported',dwg_ready=True);storage.write_json(path/'revision.json',data)
        return existing
    converter=os.environ.get('ODA_CONVERTER')
    if not converter:
        candidates=sorted(Path('C:/Program Files/ODA').glob('ODAFileConverter */ODAFileConverter.exe'))
        converter=str(candidates[-1]) if candidates else None
    if backend=='oda' and not converter:raise ValueError('Chưa tìm thấy ODA File Converter')
    output=path/export_folder;output.mkdir(exist_ok=True)
    check=path/check_folder;check.mkdir(exist_ok=True)
    # Never validate stale products if the converter silently skips a file.
    (output/'modified.dwg').unlink(missing_ok=True)
    (check/'modified.dxf').unlink(missing_ok=True)
    def convert(a,b,format,pattern):
        try:
            ver = dwg_ver_str if format == 'DWG' else 'ACAD2018'
            result=subprocess.run([converter,str(a),str(b),ver,format,'0','0',pattern],capture_output=True,
                                  timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired as error:
            raise ValueError('ODA quá thời gian chuyển đổi; bản sửa đã lưu, hãy thử xuất lại') from error
        if result.returncode:raise ValueError('ODA chuyển đổi thất bại')
    aps_job_id=None
    if backend in ('aps','autocad'):
        from backend.services.aps_jobs import convert_revision
        aps_job_id=convert_revision(document_id,revision_id,working_source,output,check,**({'provider':'autocad'} if backend=='autocad' else {}))
    else:convert(working_source.parent,output,'DWG','modified.dxf')
    dwg=output/'modified.dwg'
    if not dwg.is_file() or dwg.stat().st_size<100:raise ValueError('Không tạo được DWG')
    with dwg.open('rb') as stream:
        header = stream.read(6)
        valid_headers = (b'AC1032', b'AC1027', b'AC1024', b'AC1021', b'AC1018', b'AC1015')
        if header not in valid_headers:raise ValueError('File xuất không có header DWG hợp lệ')
    if backend=='oda':convert(output,check,'DXF','modified.dwg')
    doc=load_document(str(check/'modified.dxf'))
    changes=export_changes(data['validation'],manifest)
    from cad.nested_scope_export import path_entity
    for edit in changes:
        if edit['action']=='remove_insert':
            if doc.entitydb.get(edit['ref']) is not None:raise ValueError('DWG còn instance đã bỏ khỏi bản cắt')
            continue
        path_entity(doc,edit['ref'])
    # Re-verify actual edited properties after the DWG round trip.
    original=load_document(str(working_source))
    from cad.dimension_associations import verify
    verify(doc,data['validation'].get('native_associations',[]))
    from cad.nested_scope_export import verify as verify_selection
    verify_selection(doc,manifest,converter_normalized=True)
    omitted=set((manifest or {}).get('nested_selection',{}).get('removed_handles',[]))
    verify_cloned_geometry(original,doc,data['validation'],omitted,converter_normalized=True)
    verify_cloned_geometry(original,doc,dict(block_isolation=(manifest or {}).get('export_isolation',[])),omitted,converter_normalized=True)
    from collections import Counter
    # Dimension rendering and converter normalization may change display entities;
    # all top-level model/paper entities must survive the conversion.
    for layout in original.layouts:
        try:reopened_layout=doc.layouts.get(layout.name)
        except KeyError:raise ValueError('DWG xuất mất layout: '+layout.name)
        if Counter(e.dxftype() for e in layout)!=Counter(e.dxftype() for e in reopened_layout):
            raise ValueError('DWG xuất làm thay đổi số lượng/loại đối tượng trong layout '+layout.name)
    for layer in original.layers:
        if layer.dxf.name not in doc.layers:raise ValueError('DWG xuất mất layer')
        reopened=doc.layers.get(layer.dxf.name)
        if layer.is_off()!=reopened.is_off() or layer.is_frozen()!=reopened.is_frozen():
            raise ValueError('DWG xuất làm thay đổi trạng thái hiển thị layer')
    from cad.table_data import table_cells
    expected_tables=table_cells(working_source)
    reopened_tables=table_cells(check/'modified.dxf')
    if expected_tables!=reopened_tables:
        raise ValueError('DWG xuất không bảo toàn toàn bộ dữ liệu bảng CAD')
    for edit in changes:
        if edit['action']=='remove_insert':continue
        handle=edit['ref'].split('/')[-1];a,b=original.entitydb.get(handle),doc.entitydb.get(handle)
        if edit['action']=='append_geometry':
            from cad.geometry import snapshot,near
            if not near(snapshot(a),snapshot(b),1e-6):raise ValueError('DWG không giữ khung chứa cạnh mới')
            for added in edit.get('added_entities',[]):
                expected,actual=original.entitydb.get(added['handle']),doc.entitydb.get(added['handle'])
                if expected is None or actual is None or actual.dxftype()!='LINE' or not near(snapshot(actual),added['geometry'],1e-6):
                    raise ValueError('DWG xuất mất/sai cạnh lắp bổ sung')
                if actual.dxf.layer!=added['layer'] or actual.dxf.owner!=added['owner']:raise ValueError('DWG đổi layer/layout cạnh lắp bổ sung')
        elif edit['action']=='replace_geometry':
            from cad.geometry import snapshot,near
            if not near(snapshot(a),snapshot(b),1e-6):raise ValueError('DWG xuất không giữ geometry đã sửa')
            if a.dxftype()=='DIMENSION':
                import math
                from cad.dimensions import verify_tolerance
                verify_tolerance(a,b)
                old_value=abs(a.get_measurement()*a.override().get('dimlfac',1))
                new_value=abs(b.get_measurement()*b.override().get('dimlfac',1))
                if not math.isclose(old_value,new_value,rel_tol=0,abs_tol=1e-6):
                    raise ValueError('DWG xuất không giữ giá trị kích thước đo thật')
        elif edit['action']=='table_cell':
            if expected_tables.get(handle)!=reopened_tables.get(handle):raise ValueError('DWG xuất không giữ dữ liệu ô bảng')
        elif edit['action']=='move_text':
            from cad.text_motion import snapshot as text_snapshot
            from cad.geometry import near
            if not near(text_snapshot(a),text_snapshot(b),1e-6):raise ValueError('DWG xuất không giữ vị trí/căn lề chữ đã dịch')
        elif edit['action']=='replace_text':
            if (a.text if a.dxftype()=='MTEXT' else a.dxf.text)!=(b.text if b.dxftype()=='MTEXT' else b.dxf.text):raise ValueError('DWG xuất không giữ text đã sửa')
        else:
            key='end' if edit['action']=='line_end' else 'insert'
            if any(abs(x-y)>1e-6 for x,y in zip(a.dxf.get(key),b.dxf.get(key))):raise ValueError('DWG xuất không giữ tọa độ đã sửa')
    # Rendering a preview can finish during a CLI conversion; retain its review
    # state instead of replacing it with the pre-conversion metadata snapshot.
    _,latest=read_revision(document_id,revision_id)
    if latest['validation']['output_hash']!=data['validation']['output_hash']:raise ValueError('Revision đã đổi trong lúc xuất DWG')
    data=latest
    if require_approval:data.update(status='exported',dwg_ready=True)
    else:data.update(draft_dwg_ready=True)
    if digest(working_source)!=working_hash:raise ValueError('Phạm vi xuất đã đổi trong lúc chuyển đổi')
    data[validation_key]={'status':'validated_roundtrip','dwg_hash':digest(dwg),
                            'dxf_hash':data['validation']['output_hash'],'converter':converter_name,'aps_job_id':aps_job_id,
                            'scope':scope,'scope_hash':working_hash,'scope_manifest':manifest,
                            'checks':['DWG signature','layout inventory','layer visibility','native tables','edited geometry/text','scaled dimension measurements','native dimension tolerances','cloned geometry and holes','native DIMASSOC anchors']}
    if backend=='autocad':
        from backend.services.autocad_dxf_input import conversion_input
        _,normalization=conversion_input(document_id,working_source)
        if normalization:
            from cad.empty_ole import verify as verify_ole
            data[validation_key]['input_normalization']=normalization
            data[validation_key]['ole_integrity']=verify_ole(original,doc,normalization)
    storage.write_json(path/'revision.json',data)
    return dwg


def verify_cloned_geometry(original,reopened,validation,omitted=(),*,converter_normalized=False):
    from cad.geometry import near
    from cad.nested_scope_export import copy_snapshot,omitted_entity_present
    for clone in validation.get('block_isolation',[]):
        from cad.empty_dictionary import verify_mapping as verify_empty_dictionaries
        verify_empty_dictionaries(original,reopened,{h:h for h in clone['handle_map'].values() if h not in omitted})
        for handle in clone['handle_map'].values():
            a,b=original.entitydb.get(handle),reopened.entitydb.get(handle)
            if handle in omitted:
                if a is not None or omitted_entity_present(reopened,handle,converter_normalized):raise ValueError('DWG còn entity ngoài phạm vi đã loại')
                continue
            if a is None or b is None or a.dxftype()!=b.dxftype():raise ValueError('DWG không giữ entity trong block đã tách')
            if not near(copy_snapshot(a),copy_snapshot(b),1e-6):raise ValueError('DWG không giữ hình học/thuộc tính trong block đã tách')


def export_dxf(document_id,revision_id,require_approval=True,scope='document'):
    """Export the exact validated DXF without converter or reserialization."""
    from backend.services.edit_gate_service import preflight_revision
    preflight_revision(document_id,revision_id)
    path,data=read_revision(document_id,revision_id)
    if require_approval and data.get('complete_product_backup') is False:
        raise ValueError('Bản sửa một phần chỉ dùng xem trước; chưa phải backup hoàn chỉnh.')
    require_solid_check(data)
    source=path/'modified.dxf'
    current=digest(source)
    if current!=data['validation']['output_hash']:
        raise ValueError('Bản sửa đã thay đổi sau validation')
    if require_approval and data.get('approved_hash')!=current:
        raise ValueError('Cần duyệt đúng revision trước khi xuất DXF')
    if require_approval:validate_current_process_coverage(document_id,data)
    # Read back for structural validity; return original bytes to preserve native tables.
    source,manifest=export_source(document_id,revision_id,data,scope)
    load_document(str(source))
    if manifest:data['scoped_dxf_validation']=manifest
    data['dxf_ready']=True
    if require_approval:data['status']='exported_dxf'
    else:data['draft_dxf_ready']=True
    storage.write_json(path/'revision.json',data)
    return source
