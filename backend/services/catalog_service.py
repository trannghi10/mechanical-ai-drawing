import json
import os
import subprocess
import threading
import uuid
import hashlib
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from cad.catalog import discover

ROOT = Path(__file__).resolve().parents[2] / 'storage' / 'documents'
ROOT.mkdir(parents=True, exist_ok=True)
POOL = ThreadPoolExecutor(max_workers=3)
LOCK = threading.Lock()
UPLOAD_FAILURES = {}
PROCESS_TASKS = {}
TASK_LOCK = threading.RLock()
LOG = logging.getLogger(__name__)


def folder(document_id):
    if len(document_id) != 32 or any(c not in '0123456789abcdef' for c in document_id):
        raise FileNotFoundError('Document không tồn tại')
    path = ROOT / document_id
    if not path.exists():
        raise FileNotFoundError('Document không tồn tại')
    return path


def write_json(path, data):
    from backend.services.account_service import ACTOR
    actor=ACTOR.get()
    with LOCK:
        tracked=isinstance(data,dict) and (path.name in ('status.json','revision.json','relationship-history.json') or
            path.parent.name in ('change-plans','planning-jobs','download-jobs') or
            (path.name=='job.json' and path.parent.parent.name=='document-atlas'))
        if tracked:
            if path.exists():
                previous=json.loads(path.read_text(encoding='utf8'))
                for key in ('created_by','updated_by'):
                    if key in previous:data[key]=previous[key]
                    else:data.pop(key,None)
            elif actor:
                data['created_by']=dict(actor)
            else:
                # Old or system-created receipts have no inferred human owner.
                data.pop('created_by',None);data.pop('updated_by',None)
            if actor:data['updated_by']=dict(actor)
        # Readers/antivirus can briefly hold the destination on Windows.
        # Keep JSON atomic and retry sharing conflicts with a private sibling.
        # Keep the basename short: export receipts live in deep directories,
        # and Windows hosts may still enforce the legacy path-length limit.
        temp = path.with_name(uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            for attempt in range(7):
                try:
                    temp.replace(path)
                    break
                except PermissionError:
                    if attempt==6:raise
                    time.sleep(.025*2**attempt)
        finally:
            temp.unlink(missing_ok=True)
    try:
        from backend.services.database_service import index_json
        index_json(path,data)
    except Exception:
        # Keep an already-written CAD/revision receipt recoverable if DB indexing
        # is down. setup_postgres.py index retries; never log DSNs/passwords.
        LOG.warning('Database metadata index failed; local receipt retained for reindex.')


def read_status(document_id):
    document_folder=folder(document_id)
    result=json.loads((document_folder / 'status.json').read_text(encoding='utf-8'))
    with LOCK:failure=UPLOAD_FAILURES.get(str(document_folder.resolve()))
    if failure:result.update(status='failed',error=failure)
    return result


def _upload_finished(document_id,document_folder,task):
    """Expose worker failures even when committing the status file failed."""
    try:task.result()
    except Exception as error:
        with LOCK:UPLOAD_FAILURES[str(document_folder.resolve())]='Không hoàn tất đọc CAD: '+str(error)
        LOG.exception('Upload processing failed for %s',document_id)


def source_fingerprint(path):
    """Content identity, independent of upload name. Cache only while stat agrees."""
    source=next((p for p in (path/'original.dwg',path/'original.dxf') if p.is_file()),None)
    if source is None:return None
    stat=source.stat(); cache=path/'source-fingerprint.json'
    if cache.exists():
        data=json.loads(cache.read_text(encoding='utf8'))
        if data.get('size')==stat.st_size and data.get('mtime_ns')==stat.st_mtime_ns:
            return data['sha256']
    hasher=hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):hasher.update(chunk)
    value=hasher.hexdigest()
    write_json(cache,dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=value))
    return value


def auxiliary_name(filename):
    name = Path(filename).name.lower()
    if any(k in name for k in ('synthetic', 'validation', 'benchmark', 'test_', 'test-', '_test',
                               'sample_recover', 'sample-recover', 'parametric-demo', 'unseen', 'new-hole')):
        return True
    return name in ('test_upload.dwg', 'test.dwg', 'test.dxf') or bool(re.search(r'synthetic|validation|dimassoc|rectangle-api', name))


def list_documents(include_auxiliary=False,current=''):
    results = []
    if ROOT.exists():
        for d in sorted(ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir() and len(d.name) == 32 and (d / 'status.json').exists():
                try:
                    st = json.loads((d / 'status.json').read_text(encoding='utf-8'))
                    st['id'] = st.get('id') or d.name
                    st['source_hash']=source_fingerprint(d)
                    st['auxiliary']=st.get('auxiliary') is True or auxiliary_name(st.get('filename','')) or st.get('synthetic_test') is True
                    st['history_count']=sum(1 for group in ('revisions','change-plans','inspections') for _ in (d/group).glob('*.json'))
                    sheet_file = d / 'sheets-v3.json'
                    if sheet_file.exists():
                        try:
                            from cad.sheets import SHEET_VERSION
                            cached=json.loads(sheet_file.read_text(encoding='utf-8'))
                            if cached.get('version')==SHEET_VERSION:
                                st['sheet_count'] = len(cached.get('items', []))
                        except Exception:
                            pass
                    catalog_file = d / 'catalog.json'
                    if 'count' not in st and catalog_file.exists():
                        try:
                            st['count'] = len(json.loads(catalog_file.read_text(encoding='utf-8')).get('items', []))
                        except Exception:
                            pass
                    results.append(st)
                except Exception:
                    continue
    groups={}
    for result in results:groups.setdefault(result.get('source_hash') or result['id'],[]).append(result)
    visible=[]
    for group in groups.values():
        primary=max(group,key=lambda s:(not s['auxiliary'],s['history_count'],s.get('status')=='ready',s['id']))
        # Keep an explicitly opened upload and its history selected.
        representative=next((s for s in group if s['id']==current),primary)
        for row in group:
            row['duplicate_count']=len(group)-1
            row['duplicate_of']=primary['id'] if row['id']!=primary['id'] else None
            if include_auxiliary or (row is representative and (not row['auxiliary'] or row['id']==current)):
                visible.append(row)
    visible.sort(key=lambda s:(s['auxiliary'],s.get('filename','').casefold(),s['id']))
    versions={}
    for row in visible:
        versions.setdefault(row.get('filename','').casefold(),set()).add(row.get('source_hash') or row['id'])
    for row in visible:
        row['content_variant']=(row.get('source_hash') or row['id'])[:6] if len(versions[row.get('filename','').casefold()])>1 else None
    return {'items':visible,'hidden_count':len(results)-len(visible),'total_uploads':len(results)}


def create_document(filename, stream, *, read_backend_override=None):
    from backend.services.aps_client import read_backend,Settings
    backend=read_backend_override or read_backend()
    if backend not in ('oda','aps','autocad'):raise ValueError('Backend đọc CAD không hợp lệ.')
    if backend=='aps':Settings.load().check()
    if backend=='autocad':
        from backend.services.autocad_host import ready
        ready()
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.dwg', '.dxf'):
        raise ValueError('Chỉ nhận DWG hoặc DXF')
    document_id = uuid.uuid4().hex
    path = ROOT / document_id
    path.mkdir()
    source = path / ('original' + suffix)
    size = 0
    try:
        with source.open('wb') as target:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > 200 * 1024 * 1024:
                    raise ValueError('File vượt giới hạn 200 MB')
                target.write(chunk)
        if not size:
            raise ValueError('File rỗng')
    except Exception:
        source.unlink(missing_ok=True)
        path.rmdir()
        raise
    write_json(path / 'status.json', dict(id=document_id, filename=Path(filename).name, status='queued',read_backend=backend))
    queue_process(document_id,source)
    return read_status(document_id)


def queue_process(document_id,source):
    with TASK_LOCK:
        previous=PROCESS_TASKS.get(document_id)
        if previous and not previous.done():return
        from backend.services.job_context import submit
        task=submit(POOL,process,document_id,source)
        PROCESS_TASKS[document_id]=task
        def finished(future):
            _upload_finished(document_id,source.parent,future)
            with TASK_LOCK:
                if PROCESS_TASKS.get(document_id) is future:PROCESS_TASKS.pop(document_id,None)
        task.add_done_callback(finished)


def resume_native_import(document_id):
    from backend.services.aps_client import Settings
    path=folder(document_id);status=read_status(document_id)
    provider=status.get('read_backend')
    if provider not in ('aps','autocad'):raise ValueError('Tài liệu này không dùng luồng đọc native.')
    if provider=='aps':Settings.load().check()
    else:
        from backend.services.autocad_host import ready
        ready()
    if status['status']=='ready':return status
    source=next((p for p in (path/'original.dwg',path/'original.dxf') if p.is_file()),None)
    if source is None:raise FileNotFoundError('Không có CAD nguồn để tiếp tục đọc.')
    with TASK_LOCK:
        task=PROCESS_TASKS.get(document_id)
        if task is None or task.done():
            status.update(status='queued',message='Đang tiếp tục tác vụ đọc AutoCAD local đã lưu.' if provider=='autocad' else 'Đang tiếp tục tác vụ đọc APS đã lưu.')
            status.pop('error',None);UPLOAD_FAILURES.pop(document_id,None)
            write_json(path/'status.json',status)
            queue_process(document_id,source)
    return read_status(document_id)


def process(document_id, source):
    path = source.parent
    status = read_status(document_id)
    try:
        status['status'] = 'reading'
        write_json(path / 'status.json', status)
        from backend.services.aps_client import read_backend
        configured_backend = read_backend()
        backend = configured_backend if status.get('status') != 'ready' else (status.get('read_backend') or configured_backend)
        native_ok = False
        if backend in ('aps','autocad'):
            try:
                from backend.services.aps_jobs import import_source
                def progress(job_id):
                    status.update(native_import_job_id=job_id,message='AutoCAD đang đọc CAD trên máy.' if backend=='autocad' else 'AutoCAD cloud đang đọc CAD; có thể mở lại trang để theo dõi.')
                    write_json(path/'status.json',status)
                source,job_id=import_source(document_id,source,progress=progress,**({'provider':'autocad'} if backend=='autocad' else {}))
                from cad.edit_engine import digest
                status.update(read_backend=backend,native_import_job_id=job_id,native_dxf_hash=digest(source))
                native_ok = True
            except Exception as native_err:
                if source.suffix == '.dwg':
                    LOG.warning('Native backend %s failed (%s); falling back to ODA converter', backend, native_err)
                else:
                    raise
        if not native_ok and source.suffix == '.dwg':
            if os.environ.get('CAD_FREE_MODE','0')=='1' and os.environ.get('CAD_DWG_ENABLED','0')!='1':
                raise ValueError('Chế độ miễn phí nhận DXF. Hãy xuất DXF từ phần mềm CAD của bạn rồi tải lên; DWG đã chuyển trước đó vẫn xem được.')
            converter = (os.environ.get('ODA_CONVERTER') or '').strip('\'"')
            if not converter or not Path(converter).is_file():
                candidates = list(Path('C:/Program Files/ODA').glob('ODAFileConverter */ODAFileConverter.exe'))
                converter = str(sorted(candidates)[-1]) if candidates else None
            if not converter or not Path(converter).is_file():
                raise ValueError('Cần cấu hình ODA_CONVERTER tới ODAFileConverter.exe')
            output = path / 'converted'
            output.mkdir(exist_ok=True)
            result = subprocess.run([converter, str(path), str(output), 'ACAD2018', 'DXF', '0', '1', '*.dwg'],
                                    capture_output=True, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if (output / 'original.dxf').is_file():
                source = output / 'original.dxf'
            else:
                dxf_candidate = next((p for p in output.iterdir() if p.suffix.lower() == '.dxf'), None)
                if dxf_candidate:
                    source = dxf_candidate
                else:
                    raise ValueError('Chuyển đổi DWG không tạo ra file DXF')
        catalog = discover(source)
        write_json(path / 'catalog.json', catalog)
        try:
            from cad.sheets import discover_sheets, SHEET_VERSION
            from cad.catalog import CAD_LOCK
            from cad.edit_engine import digest
            with CAD_LOCK:
                sheet_items = discover_sheets(source)
            write_json(path / 'sheets-v3.json', {'items': sheet_items, 'version': SHEET_VERSION, 'source_hash': digest(source)})
        except Exception as sheet_err:
            LOG.warning('Sheet pre-cache deferred: %s', sheet_err)
        status.update(status='ready', dxf=str(source.relative_to(path)), count=len(catalog['items']))
        write_json(path / 'status.json', status)

        def _calc_capabilities():
            try:
                from cad.capabilities import report as capability_report
                capabilities = capability_report(source)
                write_json(path / 'cad-capabilities-v1.json', capabilities)
                cur = read_status(document_id)
                cur['capability_status'] = 'ready'
                write_json(path / 'status.json', cur)
            except Exception as error:
                cur = read_status(document_id)
                cur.update(capability_status='failed', capability_error=str(error))
                write_json(path / 'status.json', cur)
            try:
                from backend.services import document_atlas_service as atlas
                atlas.submit(document_id)
            except Exception as atlas_err:
                LOG.warning('Atlas pre-warm deferred: %s', atlas_err)

        POOL.submit(_calc_capabilities)
        return
    except Exception as error:
        status.update(status='failed', error=str(error))
    write_json(path / 'status.json', status)


def catalog(document_id):
    path = folder(document_id)
    if read_status(document_id)['status'] != 'ready':
        raise ValueError('Danh mục chưa sẵn sàng')
    cat_file = path / 'catalog.json'
    result = json.loads(cat_file.read_text(encoding='utf-8'))
    items = result.get('items', [])
    if items and not any(i.get('category') == 'mechanical_part' for i in items):
        try:
            status = read_status(document_id)
            dxf_rel = status.get('dxf')
            if dxf_rel:
                source = path / dxf_rel
                if source.is_file():
                    result = discover(source)
                    write_json(cat_file, result)
        except Exception as e:
            LOG.warning('Catalog refresh failed: %s', e)
    for item in result.get('items',[]):
        if item.get('kind')=='table':
            item['read_status']='preview_available'
            item['warning']='Bấm Đọc dữ liệu CAD để kiểm tra ô native, tiêu đề cột và các dòng vật tư trong bảng này.'
    return result
