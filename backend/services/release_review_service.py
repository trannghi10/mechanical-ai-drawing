"""Read-only, current-artifact checks; never approve or publish a revision."""
from backend.services import catalog_service as storage, revision_service as revisions
from cad.edit_engine import digest


def review(document_id,revision_id,*,include_gate=True):
    folder=storage.folder(document_id)
    path,data=revisions.read_revision(document_id,revision_id)
    checks=[]

    def check(key,label,operation):
        try:
            detail=operation()
            checks.append(dict(id=key,label=label,status='passed',detail=detail))
        except (ValueError,OSError,KeyError,TypeError):
            checks.append(dict(id=key,label=label,status='blocked',detail=messages[key]))

    def geometry():
        source=folder/storage.read_status(document_id)['dxf']
        if data['validation'].get('status')!='validated' or data['validation'].get('source_unchanged') is not True:
            raise ValueError('No validated edit receipt')
        if digest(path/'modified.dxf')!=data['validation']['output_hash']:
            raise ValueError('Output changed')
        if digest(source)!=data['validation']['source_hash']:
            raise ValueError('Source changed')
        revisions.require_solid_check(data)
        return 'Hash DXF nguồn và bản sửa khớp hồ sơ kiểm chứng hiện tại.'

    def preservation():
        proof=data.get('source_preservation',{})
        if proof.get('status')!='verified_unchanged' or not proof.get('files'):raise ValueError('Missing source proof')
        names=set()
        for entry in proof['files']:
            candidate=(folder/entry['filename']).resolve()
            if not candidate.is_relative_to(folder.resolve()) or digest(candidate)!=entry['sha256']:
                raise ValueError('Source changed')
            names.add(candidate)
        originals={f.resolve() for f in (folder/'original.dwg',folder/'original.dxf') if f.is_file()}
        if not originals or not originals<=names:raise ValueError('Missing original identity')
        return 'Các file nguồn gốc vẫn khớp SHA-256 đã lưu khi tạo revision.'

    def coverage():
        if data.get('complete_product_backup') is False:raise ValueError('Partial preview')
        proposal=folder/'change-plans'/(revisions.safe_id(data['plan_id'])+'.json')
        # Old receipts without a plan/detection cannot establish full coverage.
        if not proposal.is_file() or not (folder/'sheets-v3.json').is_file():raise ValueError('Missing coverage')
        revisions.validate_current_process_coverage(document_id,data)
        return 'Đạt kiểm phạm vi tác động theo các quy tắc hiện tại; chưa thay thế nghiệm thu kỹ sư.'

    def approval():
        output=data['validation']['output_hash']
        if data.get('complete_product_backup') is False or data.get('approved_hash')!=output or data.get('pending_dependencies'):
            raise ValueError('Unapproved')
        return 'Đã duyệt đúng hash bản sửa và giải quyết các phụ thuộc phải xác nhận.'

    def native():
        from backend.services import aps_jobs,aps_repository
        from backend.services.autocad_dxf_input import valid_receipt
        proof=data.get('dwg_validation',{})
        if (proof.get('status')!='validated_roundtrip' or proof.get('scope')!='document' or
                proof.get('dxf_hash')!=data['validation']['output_hash'] or
                proof.get('scope_hash')!=data['validation']['output_hash'] or not valid_receipt(proof)):
            raise ValueError('No full native readback')
        dwg=path/'export/modified.dwg'
        if digest(dwg)!=proof['dwg_hash']:raise ValueError('DWG changed')
        jid=proof['aps_job_id'];job=aps_repository.read(document_id,jid)
        if job['status']!='ready' or job.get('provider') not in ('autocad','aps'):
            raise ValueError('No native receipt')
        native_dwg=aps_jobs.artifact(document_id,jid,'modified.dwg')
        native_dxf=aps_jobs.artifact(document_id,jid,'roundtrip.dxf')
        if digest(native_dwg)!=proof['dwg_hash'] or digest(native_dxf)!=digest(path/'reopen/modified.dxf'):
            raise ValueError('Native evidence changed')
        return 'DWG toàn hồ sơ và DXF mở lại khớp artifact native đã kiểm hash.'

    messages=dict(
        geometry='Thiếu kiểm chứng hiện tại hoặc DXF nguồn/bản sửa đã thay đổi. Cần phân tích và kiểm lại.',
        source_preservation='Thiếu bằng chứng giữ nguyên file gốc hoặc hash nguồn không còn khớp.',
        coverage=data.get('preview_only_reason') or 'Chưa chứng minh đủ quan hệ toàn yêu cầu bằng quy tắc hiện tại.',
        approval='Chưa duyệt đúng revision hoặc còn phụ thuộc cần xác nhận; không dùng quyền tài khoản để bỏ qua.',
        native_reopen='Chưa có DWG toàn hồ sơ được mở lại bằng native với artifact hiện tại còn nguyên hash.')
    check('geometry','Hình học và phiên bản nguồn',geometry)
    check('source_preservation','Giữ nguyên file gốc',preservation)
    check('coverage','Phạm vi chi tiết liên quan',coverage)
    check('approval','Phê duyệt đúng revision',approval)
    check('native_reopen','Lưu và mở lại DWG toàn hồ sơ',native)
    certificate=None
    try:
        from backend.services import edit_certification_service as certificates
        if any(certificates.root().glob('*.json')):
            import json
            proposal=json.loads((folder/'change-plans'/(revisions.safe_id(data['plan_id'])+'.json')).read_text(encoding='utf8'))
            certificate=certificates.matching(proposal,certificates.source_context(document_id,proposal),data.get('dwg_validation',{}).get('converter','unknown'))
    except Exception:
        pass # Missing/unavailable registry never authorizes automatic release.
    checks.append(dict(id='certification',label='Chứng nhận loại sửa để tự phát hành',status='passed' if certificate else 'blocked',
        detail='Chứng nhận kỹ sư còn hiệu lực, đúng phiên bản bộ xử lý và khoảng áp dụng.' if certificate else
        'Chưa có chứng nhận kỹ sư phù hợp còn hiệu lực với phiên bản bộ xử lý và khoảng áp dụng hiện tại. Không tự phát hành.'))
    result=dict(document_id=document_id,revision_id=revision_id,auto_release_allowed=False,certificate=certificate,
                status='preview_only' if data.get('complete_product_backup') is False else 'needs_review',
                passed_count=sum(c['status']=='passed' for c in checks),checks=checks,
                engineer_accepted=False,production_release=False,
                policy='Báo cáo kiểm tra hiện trạng; không chỉnh CAD, phê duyệt hoặc tự phát hành.')
    if include_gate:
        from backend.services.edit_gate_service import revision_review
        result['edit_gate']=revision_review(document_id,revision_id,base=result)
        result['auto_release_allowed']=result['edit_gate']['auto_release_allowed']
        result['production_release']=bool(data.get('automatic_release') and result['auto_release_allowed'])
    return result
