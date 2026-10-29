"""One evidence-based AUTO / REVIEW / BLOCK policy for DWG edits.

This gate never accepts model-provided confidence/approval flags. Decisions are
recomputed from current source, deterministic validators, revision artifacts
and engineer-issued certificates. Draft generation is distinct from release.
"""
import copy
import hashlib
import json
import time
import uuid
from backend.services import catalog_service as storage
from cad.edit_engine import digest

VERSION=1


def fingerprint(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def decision(phase,checks,*,preview_allowed=False,manual_release_allowed=False,certificate=None,binding=None,questions=None):
    blocked=any(c['status']=='blocked' for c in checks)
    auto=phase=='release' and not blocked and certificate is not None and all(c['status']=='passed' for c in checks if c['id']!='manual_approval')
    return dict(version=VERSION,phase=phase,mode='BLOCK' if blocked else 'AUTO' if auto else 'REVIEW',
        preview_allowed=bool(preview_allowed and not blocked),auto_release_allowed=auto,
        manual_release_allowed=bool(manual_release_allowed and not blocked),certificate=certificate,
        checks=checks,questions=questions or [],binding=binding or {},
        basis='current_source_and_verified_artifacts',model_confidence_used=False,
        policy='AUTO cần loại sửa được chứng nhận, đủ quan hệ và DWG toàn hồ sơ mở lại đạt kiểm. REVIEW chỉ tạo bản đề xuất khi kiểm trực tiếp đạt. BLOCK không ghi CAD.')


def check(key,status,detail,refs=None):return dict(id=key,status=status,detail=detail,evidence_refs=refs or [])


def relationship_evidence(proposal,context,raw):
    """Return only unresolved source facts that touch this edit.

    A file can contain unrelated ambiguous balloons or unfinished detail views.
    Those must remain visible in the design model, but must not be used to
    reject an otherwise isolated edit.  Conversely, an ambiguity touching an
    edited entity or its identified part may never be hidden by a generic
    "confidence" flag.
    """
    model=context.get('design_model') or {}
    if not model:return []
    changed={o.get('ref') for o in raw.get('operations',[]) if o.get('ref')}
    codes=set()
    for key in ('resize_recipes','curved_wall_recipes','hole_recipes','cut_recipes','profile_cut_recipes'):
        for recipe in raw.get(key,[]):
            if isinstance(recipe,dict) and recipe.get('part_code'):codes.add(str(recipe['part_code']))
    if raw.get('target_part'):codes.add(str(raw['target_part']))
    for dependency in raw.get('dependencies',[]):
        if isinstance(dependency,dict):codes.update(str(dependency[k]) for k in ('source_part','target_part') if dependency.get(k))
    owners=model.get('geometry_owners',{})
    for ref in changed:
        owner=owners.get(ref,{})
        codes.update(owner.get('part_ids',[]))
    relations={r.get('id'):r for r in model.get('relationship_observations',[])}
    result=[]
    labels=dict(
        unmapped_detail_view='Có hình chi tiết cùng mã chưa gắn được với hình học đo thật.',
        part_definition_conflict='Quy cách BOM của chi tiết nguồn đang mâu thuẫn.',
        geometry_owner_conflict='Một entity CAD được gắn với nhiều chi tiết nguồn.',
        feature_owner='Hình học liên quan chưa có chủ sở hữu chi tiết được xác minh.',
        ambiguous_dimension='DIM nguồn liên quan chưa có ý nghĩa duy nhất.',
        relationship_constraint='Có quan hệ chi tiết liên quan nhưng chưa có quy tắc/mốc hình học thực thi.')
    for item in model.get('unresolved',[]):
        kind=item.get('kind','unknown');related=False;refs=[];parts=[]
        if item.get('part_id') in codes:related=True;parts=[item['part_id']]
        if item.get('ref') in changed:related=True;refs=[item['ref']]
        refs.extend(r for r in item.get('evidence_refs',[]) if r in changed)
        if refs:related=True
        relation=relations.get(item.get('relation_id'),{})
        relation_parts=[p for p in (relation.get('source'),relation.get('target')) if p]
        if codes.intersection(relation_parts):related=True;parts.extend(relation_parts)
        if not related:continue
        status='blocked' if (kind in ('geometry_owner_conflict','feature_owner') and (bool(refs) or item.get('ref') in changed)) else 'review'
        result.append(dict(kind=kind,status=status,detail=labels.get(kind,'Có bằng chứng nguồn chưa đủ để xác định quan hệ chỉnh sửa.'),
            evidence_refs=sorted(set(refs)),part_codes=sorted(set(parts))))
    # Deduplicate evidence because one unresolved relation can be represented in
    # the design registry and in a selected detail view.
    return sorted({json.dumps(item,sort_keys=True,ensure_ascii=False):item for item in result}.values(),
                  key=lambda item:(item['status'],item['kind'],item['part_codes'],item['evidence_refs']))


def assess_plan(proposal,context,*,preview=False,validated=False):
    raw=proposal.get('checked_preview_plan') if preview else proposal.get('plan')
    raw=raw or {};checks=[];questions=list(proposal.get('plan',{}).get('questions',[]))
    binding=dict(source_hash=context.get('source_hash'),plan_hash=fingerprint(raw),document_id=proposal.get('document_id'),plan_id=proposal.get('id'))
    same=bool(context.get('source_hash') and context['source_hash']==proposal.get('source_hash'))
    checks.append(check('source_identity','passed' if same else 'blocked','Nguồn CAD khớp kế hoạch.' if same else 'Nguồn CAD đã đổi hoặc thiếu hash; cần phân tích lại.'))
    reading=proposal.get('document_reading') or {}
    incomplete=reading.get('traversal_complete') is False
    checks.append(check('source_reading','blocked' if incomplete else 'passed' if reading.get('traversal_complete') is True else 'review',
        'Chưa đọc đủ cấu trúc toàn file.' if incomplete else 'Đã đọc cấu trúc toàn file.' if reading.get('traversal_complete') is True else 'Chưa có bằng chứng đọc toàn file; chưa cho phép tự phát hành.'))
    executable=bool(raw.get('operations')) and not raw.get('questions')
    valid=False
    if executable and same and not incomplete:
        try:
            if not validated:
                from backend.services.change_service import DrawingChangePlan,validate_plan
                validate_plan(DrawingChangePlan.model_validate(raw),context)
            valid=True;checks.append(check('constraints','passed','Các thao tác trực tiếp đã qua kiểm nguồn, ràng buộc và hình học.',[o['ref'] for o in raw['operations']]))
        except (ValueError,KeyError,TypeError) as error:
            checks.append(check('constraints','blocked',str(error)))
    else:checks.append(check('constraints','review','Chưa có bộ thao tác CAD đầy đủ, không mơ hồ để tạo bản sửa.'))
    request=proposal.get('request_review') or {}
    partial=preview or bool(questions) or request.get('status','complete')!='complete' or raw.get('requires_complete_product_review') is True
    checks.append(check('intent_and_impact','review' if partial else 'passed','Còn ý đồ/phạm vi cần đối chiếu; bản sửa chỉ là đề xuất.' if partial else 'Không còn câu hỏi trong kế hoạch đã kiểm.'))
    pending=any(d.get('needs_confirmation',True) for d in raw.get('dependencies',[]))
    checks.append(check('dependency_confirmation','review' if pending else 'passed','Cần xác nhận các quan hệ được liệt kê trước khi dùng sản xuất.' if pending else 'Không có phụ thuộc đang yêu cầu xác nhận.'))
    ambiguities=relationship_evidence(proposal,context,raw) or proposal.get('relationship_evidence',[])
    ambiguity_status='blocked' if any(item['status']=='blocked' for item in ambiguities) else 'review' if ambiguities else 'passed'
    checks.append(check('relationship_evidence',ambiguity_status,
        'Có entity/hình học sửa nhưng chưa xác định được chủ sở hữu duy nhất.' if ambiguity_status=='blocked' else
        'Có hình chi tiết, DIM hoặc quan hệ liên quan chưa đủ bằng chứng; cần kỹ sư đối chiếu.' if ambiguities else
        'Không có mối quan hệ nguồn mơ hồ nào chạm phạm vi sửa.',
        sorted({ref for item in ambiguities for ref in item['evidence_refs']})))
    certificate=None
    try:
        from backend.services.edit_certification_service import matching
        if valid and not partial:certificate=matching(proposal,context)
    except Exception:pass # Unavailable certificate storage cannot grant AUTO.
    checks.append(check('certification','passed' if certificate else 'review','Có chứng nhận còn hiệu lực, đúng phiên bản và khoảng áp dụng.' if certificate else 'Chưa có chứng nhận loại sửa phù hợp; không tự phát hành.'))
    checks.append(check('native_reopen','review','Phải kiểm DWG kết quả sau lưu/mở lại trước khi phát hành.'))
    result=decision('plan',checks,preview_allowed=valid,certificate=certificate,binding=binding,questions=questions)
    result['changed_refs']=[o['ref'] for o in raw.get('operations',[])]
    result['relationship_evidence']=ambiguities
    return result


def plan_review(document_id,plan_id):
    from backend.services.revision_service import safe_id,current_impact
    from backend.services.change_service import context_for
    from backend.services.document_request_service import validate_plan_source
    folder=storage.folder(document_id);proposal=json.loads((folder/'change-plans'/(safe_id(plan_id)+'.json')).read_text(encoding='utf8'))
    try:
        validate_plan_source(document_id,proposal)
        source=folder/storage.read_status(document_id)['dxf']
        context=context_for(source,proposal['targets'],proposal.get('review_only_ids',[]))
        from backend.services.design_choices import attach
        attach(context,folder)
        from graph.native_span_fits import attach_envelope_request
        attach_envelope_request(context,proposal.get('request',''),proposal.get('clarifications'))
        context['part_graph']=current_impact(document_id,proposal,source,context)
        context['root_target_ids']=proposal.get('root_target_ids',[]);context['root_bom_refs']=proposal.get('root_bom_refs',[])
        from cad.measured_features import index
        context['source_features']=index(context,context['part_graph'])
        return assess_plan(proposal,context,preview=not proposal.get('execution_available') and bool(proposal.get('checked_preview_plan')))
    except (ValueError,OSError,KeyError,TypeError) as error:
        return decision('plan',[check('source_preflight','blocked',str(error))],binding=dict(document_id=document_id,plan_id=plan_id))


def audit(document_id,result,action,revision_id=None):
    from backend.services.account_service import ACTOR
    folder=storage.folder(document_id)/'edit-gate-audit';folder.mkdir(exist_ok=True)
    value=dict(id=uuid.uuid4().hex,created_at=time.time(),action=action,actor=ACTOR.get(),revision_id=revision_id,decision=result)
    storage.write_json(folder/(value['id']+'.json'),value)
    return value['id']


def require_plan(document_id,proposal,context,*,preview=False,validated=False):
    result=assess_plan(proposal,context,preview=preview,validated=validated)
    result['audit_id']=audit(document_id,result,'apply_checked_preview' if preview else 'apply')
    if result['mode']=='BLOCK' or not result['preview_allowed']:
        detail=' '.join(c['detail'] for c in result['checks'] if c['status']=='blocked') or 'Chưa có thao tác đã kiểm để tạo bản sửa.'
        raise ValueError('DWG Edit Gate '+result['mode']+': '+detail)
    return result


def revision_review(document_id,revision_id,*,base=None):
    from backend.services import release_review_service as release,revision_service as revisions
    path,data=revisions.read_revision(document_id,revision_id)
    base=base or release.review(document_id,revision_id,include_gate=False)
    source_checks={c['id']:c for c in base['checks']};checks=[]
    for key in ('geometry','source_preservation'):
        item=source_checks[key];checks.append(check(key,'passed' if item['status']=='passed' else 'blocked',item['detail']))
    for key in ('coverage','approval','native_reopen','certification'):
        item=source_checks[key];status='passed' if item['status']=='passed' else 'review'
        if key=='native_reopen' and data.get('dwg_validation',{}).get('status')=='validated_roundtrip' and data['dwg_validation'].get('scope')=='document' and status!='passed':status='blocked'
        if key=='approval' and data.get('approval_kind')=='certified_auto':status='review'
        checks.append(check('manual_approval' if key=='approval' else key,status,item['detail']))
    pending=bool(data.get('pending_dependencies'))
    checks.append(check('dependency_confirmation','review' if pending else 'passed','Còn quan hệ cần xác nhận.' if pending else 'Các phụ thuộc cần xác nhận đã được giải quyết.'))
    ambiguities=data.get('relationship_evidence') or data.get('edit_gate',{}).get('relationship_evidence',[])
    ambiguity_status='blocked' if any(item.get('status')=='blocked' for item in ambiguities) else 'review' if ambiguities else 'passed'
    checks.append(check('relationship_evidence',ambiguity_status,
        'Có entity/hình học sửa nhưng chưa xác định được chủ sở hữu duy nhất.' if ambiguity_status=='blocked' else
        'Có quan hệ nguồn chưa đủ bằng chứng; revision cần kỹ sư đối chiếu.' if ambiguities else
        'Không có bằng chứng quan hệ mơ hồ được lưu trong phạm vi revision.'))
    request=data.get('request_review') or {};fulfillment=data.get('fulfillment_review') or {}
    incomplete=request.get('status','complete')!='complete' or fulfillment.get('status','complete') not in ('complete','matched')
    checks.append(check('request_fulfillment','review' if incomplete else 'passed','Còn phần yêu cầu chưa hoàn tất.' if incomplete else 'Hồ sơ không báo yêu cầu còn thiếu.'))
    binding=dict(document_id=document_id,revision_id=revision_id,source_hash=data['validation'].get('source_hash'),
                 output_hash=data['validation'].get('output_hash'),dwg_hash=data.get('dwg_validation',{}).get('dwg_hash'))
    certificate=base.get('certificate')
    manual=all(c['status']=='passed' for c in checks if c['id']!='certification')
    return decision('release',checks,preview_allowed=True,manual_release_allowed=manual,certificate=certificate,binding=binding)


def require_artifact(document_id,revision_id,*,production=False):
    result=revision_review(document_id,revision_id)
    if result['mode']=='BLOCK' or (production and not (result['manual_release_allowed'] or result['auto_release_allowed'])):
        raise ValueError('DWG Edit Gate '+result['mode']+': '+' '.join(c['detail'] for c in result['checks'] if c['status']!='passed'))
    return result


def preflight_revision(document_id,revision_id):
    """Cheap integrity guard, including legacy preview/export paths."""
    from backend.services.revision_service import read_revision
    path,data=read_revision(document_id,revision_id);folder=storage.folder(document_id)
    if digest(path/'modified.dxf')!=data['validation']['output_hash']:raise ValueError('DWG Edit Gate BLOCK: bản sửa đã đổi sau kiểm chứng.')
    if data['validation'].get('source_hash'):
        source=folder/storage.read_status(document_id)['dxf']
        if digest(source)!=data['validation']['source_hash']:
            raise ValueError('DWG Edit Gate BLOCK: nguồn CAD đã đổi.')
    for entry in data.get('source_preservation',{}).get('files',[]):
        candidate=(folder/entry['filename']).resolve()
        if not candidate.is_relative_to(folder.resolve()) or digest(candidate)!=entry['sha256']:
            raise ValueError('DWG Edit Gate BLOCK: file gốc không còn khớp hash.')
    if data.get('approval_kind')=='certified_auto':
        current=revision_review(document_id,revision_id)
        released=data.get('automatic_release',{})
        if (not current['auto_release_allowed'] or current['certificate']['id']!=released.get('certificate_id') or
                current['binding']['output_hash']!=released.get('output_hash') or current['binding']['dwg_hash']!=released.get('dwg_hash')):
            raise ValueError('DWG Edit Gate REVIEW: chứng nhận phát hành tự động không còn phù hợp; cần kỹ sư duyệt lại.')
    return data


def auto_release(document_id,revision_id):
    from backend.services import revision_service as revisions
    path,data=revisions.read_revision(document_id,revision_id)
    result=revision_review(document_id,revision_id)
    aid=audit(document_id,result,'auto_release',revision_id)
    if not result['auto_release_allowed']:raise ValueError('DWG Edit Gate '+result['mode']+': chưa đủ điều kiện tự phát hành.')
    revisions.validate_current_process_coverage(document_id,data)
    if digest(path/'modified.dxf')!=result['binding']['output_hash'] or digest(path/'export/modified.dwg')!=result['binding']['dwg_hash']:
        raise ValueError('Artifact đã đổi trong lúc kiểm phát hành.')
    data.update(approval_kind='certified_auto',approved_hash=result['binding']['output_hash'],status='auto_released',
        automatic_release=dict(certificate_id=result['certificate']['id'],output_hash=result['binding']['output_hash'],
            dwg_hash=result['binding']['dwg_hash'],audit_id=aid,released_at=time.time()))
    storage.write_json(path/'revision.json',data)
    return dict(revision_id=revision_id,mode='AUTO',production_release=True,certificate=result['certificate'],audit_id=aid)
