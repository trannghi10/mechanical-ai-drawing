"""Resumable planning jobs: source-bound proposals, never implicit apply."""
import hashlib
import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from backend.services import catalog_service as storage
from backend.services.planning_control import Control,CURRENT,Cancelled

import sys
if not hasattr(sys, '_cad_planning_pool'):
    sys._cad_planning_pool = ThreadPoolExecutor(max_workers=2)
POOL = sys._cad_planning_pool

if not hasattr(sys, '_cad_planning_lock'):
    sys._cad_planning_lock = threading.RLock()
LOCK = sys._cad_planning_lock

if not hasattr(sys, '_cad_planning_active'):
    sys._cad_planning_active = {}
ACTIVE = sys._cad_planning_active


def job_path(document_id,job_id):
    from backend.services.revision_service import safe_id
    return storage.folder(document_id)/'planning-jobs'/(safe_id(job_id)+'.json')


def public(data):
    result={k:v for k,v in data.items() if k not in ('targets','key','source_signature')}
    result['elapsed_seconds']=round((data.get('finished_at') or time.time())-data['created_at'])
    return result


def read(document_id,job_id):
    with LOCK:
        data=json.loads(job_path(document_id,job_id).read_text(encoding='utf8'))
        if data['status'] in ('queued','running') and (document_id,job_id) not in ACTIVE:
            # Only consider abandoned if no active worker and created more than 5 minutes ago
            if time.time() - data.get('created_at', 0) > 300:
                data.update(status='failed',finished_at=time.time(),message='Tác vụ phân tích đã dừng hoặc server khởi động lại. Bấm phân tích lại; file gốc giữ nguyên.')
                storage.write_json(job_path(document_id,job_id),data)
        return public(data)


def submit(document_id,targets,request,part_selection=None,whole_document=False,target_choice=None):
    if whole_document and (targets or part_selection):
        raise ValueError('Tìm trong toàn file không nhận khung hoặc lựa chọn hình cũ.')
    if target_choice and not whole_document: raise ValueError('Lựa chọn hồ sơ cần chế độ toàn file.')
    if part_selection:
        from backend.services.design_model_service import resolve_part_selection
        part_selection=resolve_part_selection(document_id,targets,part_selection,request)
    folder=storage.folder(document_id);source=folder/storage.read_status(document_id)['dxf'];stat=source.stat()
    signature=[stat.st_mtime_ns,stat.st_size]
    key=hashlib.sha256(json.dumps([document_id,sorted(t['id'] for t in targets),request,signature,part_selection,whole_document,target_choice]).encode()).hexdigest()
    with LOCK:
        for (did,jid),control in ACTIVE.items():
            if did!=document_id:continue
            previous=json.loads(job_path(did,jid).read_text(encoding='utf8'))
            if previous['key']==key and previous['status'] in ('queued','running'):return public(previous)
        jid=uuid.uuid4().hex
        data=dict(id=jid,document_id=document_id,status='queued',phase='queued',message='Đang chờ lượt phân tích trên máy.',
            created_at=time.time(),request=request,target_ids=[t['id'] for t in targets],targets=targets,key=key,source_signature=signature,
            whole_document=whole_document,target_choice=target_choice)
        if part_selection:data['part_selection']=part_selection
        path=job_path(document_id,jid);path.parent.mkdir(exist_ok=True);storage.write_json(path,data)
        def update(phase,message,**details):
            with LOCK:
                current=json.loads(path.read_text(encoding='utf8'))
                if current['status']=='cancelled':return
                current.update(status='running',phase=phase,message=message,**details);storage.write_json(path,current)
        control=Control(update);ACTIVE[(document_id,jid)]=control
        from backend.services.job_context import submit as submit_worker
        submit_worker(POOL,run,document_id,jid,control)
        return public(data)


def run(document_id,jid,control):
    path=job_path(document_id,jid);token=CURRENT.set(control)
    try:
        control.check();control.started=time.monotonic()
        with LOCK:
            data=json.loads(path.read_text(encoding='utf8'))
        source=storage.folder(document_id)/storage.read_status(document_id)['dxf'];stat=source.stat()
        if [stat.st_mtime_ns,stat.st_size]!=data['source_signature']:raise ValueError('File nguồn đã thay đổi; cần chọn lại bản vẽ.')
        control.progress('cad','Đang đọc phạm vi CAD và liên kết nguồn.')
        import sys, importlib
        for mod_name in ['cad.closed_profiles', 'cad.curved_profiles', 'cad.measured_features', 'graph.impact_validation', 'graph.part_graph', 'backend.services.size_commands', 'backend.services.measured_profile_planner', 'backend.services.rectangular_planner', 'backend.services.sheet_thickness_planner', 'backend.services.tube_planner', 'backend.services.compound_planner', 'backend.services.edit_gate_service', 'backend.services.change_service', 'backend.services.document_request_service', 'backend.services.ai_provider']:
            if mod_name in sys.modules:
                try: importlib.reload(sys.modules[mod_name])
                except Exception: pass
        from backend.services.change_service import plan_change
        kwargs={'part_selection':data['part_selection']} if data.get('part_selection') else {}
        if data.get('whole_document'):
            from backend.services.document_request_service import resolve_request
            from backend.services import document_atlas_service as atlas
            resolution=resolve_request(document_id,data['request'],data.get('target_choice'));control.check()
            if resolution['status']!='resolved':
                with LOCK:
                    current=json.loads(path.read_text(encoding='utf8'));control.check()
                    current.update(status=resolution['status'],phase='target',finished_at=time.time(),
                                   message=resolution['message'],target_resolution=resolution)
                    storage.write_json(path,current)
                return
            data['targets']=resolution['targets']
            # Bind the primary target code to request for compilers.
            selected_parts = resolution.get('evidence', {}).get('selected_parts', [])
            primary_code = resolution['part_codes'][0] if resolution.get('part_codes') else ''
            req_lower = data['request'].lower()
            matched_p = None
            for p in selected_parts:
                p_code = p.get('part_code', '')
                if p_code and p_code.lower() in req_lower:
                    matched_p = p
                    break
                for occ in p.get('bom_occurrences', []):
                    p_num = str(occ.get('part_number', '')).strip().lower()
                    if p_num and (f'so {p_num}' in req_lower or f'số {p_num}' in req_lower or f'ct{p_num}' in req_lower or f'ct {p_num}' in req_lower):
                        matched_p = p
                        break
                if matched_p:
                    break
            if matched_p:
                primary_code = matched_p['part_code']
            else:
                for p in selected_parts:
                    if p.get('detail_sheet_ids'):
                        primary_code = p['part_code']
                        break
            from backend.services.sheet_thickness_planner import command as sheet_command
            from bom.reader import normalized
            is_batch = bool(sheet_command(data['request']) or re.search(r'\b(?:tat ca|toan bo|dong loat|hang loat)\b', normalized(data['request'])))
            if is_batch or not primary_code:
                effective = data['request']
            elif primary_code in data['request'] or data['request'].strip().lower().startswith('mã '):
                effective = data['request']
            else:
                effective = f"Mã {primary_code}: {data['request']}"
            kwargs['document_reading']=resolution['evidence']
            control.progress('target','Đã tìm '+', '.join(resolution['part_codes'])+'; đang kiểm tra hình học và liên kết.',
                             target_ids=[t['id'] for t in data['targets']],target_resolution={k:v for k,v in resolution.items() if k not in ('targets','evidence')})
            # report() checks CAD/detection identity immediately before planning.
            atlas.report(document_id,resolution['atlas_id'])
        else: effective=data['request']
        plan=plan_change(document_id,data['targets'],effective,**kwargs);control.check()
        if data.get('whole_document'):
            atlas.report(document_id,resolution['atlas_id'])
            plan.update(user_request=data['request'],whole_document=True,target_resolution={k:v for k,v in resolution.items() if k not in ('targets','evidence')})
            storage.write_json(storage.folder(document_id)/'change-plans'/(plan['id']+'.json'),plan)
        # The large checked snapshot remains in the plan store, not each poll.
        with LOCK:
            data=json.loads(path.read_text(encoding='utf8'));control.check()
            data.update(status='ready',phase='ready',finished_at=time.time(),plan_id=plan['id'],
                message='Đã lập kế hoạch. Xem kết quả và các liên kết cần bổ sung trước khi tạo bản sửa.')
            storage.write_json(path,data)
    except Cancelled:pass  # cancel() already saved the terminal state
    except Exception as error:
        import traceback
        traceback.print_exc()
        with LOCK:
            data=json.loads(path.read_text(encoding='utf8'))
            if data['status']!='cancelled':
                from backend.services.gemini_service import AIError
                message=str(error) if isinstance(error,(ValueError,AIError)) else f'Lỗi phân tích nội bộ: {error}'
                data.update(status='failed',phase='failed',finished_at=time.time(),message=message)
                storage.write_json(path,data)
    finally:
        CURRENT.reset(token)
        with LOCK:ACTIVE.pop((document_id,jid),None)


def cancel(document_id,jid):
    with LOCK:
        data=json.loads(job_path(document_id,jid).read_text(encoding='utf8'))
        if data['status'] in ('queued','running'):
            data.update(status='cancelled',phase='cancelled',finished_at=time.time(),message='Đã hủy phân tích. Chưa tạo bản sửa; file gốc giữ nguyên.')
            storage.write_json(job_path(document_id,jid),data)
            control=ACTIVE.get((document_id,jid))
            if control:control.cancel()
        return public(data)
