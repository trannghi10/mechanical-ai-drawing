"""Durable export receipts: conversion survives a closed browser tab."""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from backend.services import catalog_service as storage
from backend.services.revision_service import read_revision, safe_id, require_solid_check
from cad.catalog import CAD_LOCK
from cad.edit_engine import digest

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cad-export')
_lock = threading.RLock()
_active = set()


def _folder(document_id, revision_id):
    return read_revision(document_id, revision_id)[0] / 'download-jobs'


def _read(document_id, revision_id, job_id):
    file = _folder(document_id, revision_id) / (safe_id(job_id) + '.json')
    return file, json.loads(file.read_text(encoding='utf8'))


def _public(document_id, revision_id, data):
    result = {k: v for k, v in data.items() if k not in ('file', 'file_hash', 'output_hash')}
    result['download_url'] = (
        f'/documents/{document_id}/revisions/{revision_id}/exports/{data["id"]}/download'
        if data['status'] == 'ready' else None)
    return result


def _check_revision(document_id, revision_id, preview):
    path, data = read_revision(document_id, revision_id)
    from backend.services.edit_gate_service import preflight_revision
    preflight_revision(document_id,revision_id)
    require_solid_check(data)
    if digest(path / 'modified.dxf') != data['validation']['output_hash']:
        raise ValueError('Bản sửa đã đổi sau kiểm chứng; cần tạo lại bản sửa.')
    if data['validation'].get('source_hash'):
        source = storage.folder(document_id) / storage.read_status(document_id)['dxf']
        if digest(source) != data['validation']['source_hash']:
            raise ValueError('Nguồn CAD đã đổi; cần phân tích và tạo lại bản sửa.')
    if not preview and (data.get('complete_product_backup') is False or
                        data.get('approved_hash') != data['validation']['output_hash']):
        raise ValueError('Chưa duyệt bản sửa hoàn chỉnh; chỉ có thể tải bản xem trước.')
    return path, data


def prepare_aps(document_id,revision_id,scope,preview):
    """Do remote waiting before taking the CAD lock for final validation.

export_dwg reuses this source-hash-bound cloud result while holding CAD_LOCK;
it still performs all existing geometry/DIM/BOM/approval readback checks.
"""
    import os
    backend=os.getenv('CAD_DWG_BACKEND','oda')
    if backend not in ('aps','autocad'):return
    from backend.services.revision_service import export_source,validate_current_process_coverage
    from backend.services.aps_jobs import convert_revision
    with CAD_LOCK:
        path,data=_check_revision(document_id,revision_id,preview)
        if not preview:validate_current_process_coverage(document_id,data)
        source,manifest=export_source(document_id,revision_id,data,scope)
        output=path/('export-selection' if manifest else 'export')
        check=path/('reopen-selection' if manifest else 'reopen')
        output.mkdir(exist_ok=True);check.mkdir(exist_ok=True)
    # Network calls/polling must never hold the shared renderer/edit lock.
    return convert_revision(document_id,revision_id,source,output,check,**({'provider':'autocad'} if backend=='autocad' else {}))


def start(document_id, revision_id, format='dwg', scope='document', preview=True):
    import os
    backend=os.getenv('CAD_DWG_BACKEND','oda') if format=='dwg' else 'native_dxf'
    if backend=='aps':
        from backend.services.aps_client import Settings
        Settings.load().check()
    if backend=='autocad':
        from backend.services.autocad_host import ready
        ready()
    if format not in ('dwg', 'dxf') or scope not in ('selection', 'document'):
        raise ValueError('Định dạng hoặc phạm vi xuất không hợp lệ.')
    path, revision = _check_revision(document_id, revision_id, preview)
    folder = path / 'download-jobs'
    folder.mkdir(exist_ok=True)
    with _lock:
        from cad.scoped_export import POLICY_VERSION
        scope_policy=POLICY_VERSION if scope=='selection' else None
        for file in sorted(folder.glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True):
            data = json.loads(file.read_text(encoding='utf8'))
            if data.get('backend','oda' if format=='dwg' else 'native_dxf')!=backend:continue
            if data.get('scope_policy_version')!=scope_policy:continue
            if any(data.get(k) != v for k, v in dict(format=format, scope=scope, preview=preview,
                    output_hash=revision['validation']['output_hash']).items()):
                continue
            if data['status'] == 'ready':
                try:
                    download(document_id, revision_id, data['id'])
                    return _public(document_id, revision_id, data)
                except (ValueError, FileNotFoundError):
                    pass
            if data['id'] in _active:
                return _public(document_id, revision_id, data)
        job_id = uuid.uuid4().hex
        data = dict(id=job_id, status='queued', format=format, scope=scope, preview=preview,backend=backend,
                    output_hash=revision['validation']['output_hash'],scope_policy_version=scope_policy,message='Đang chờ xuất CAD.')
        storage.write_json(folder / (job_id + '.json'), data)
        _active.add(job_id)
        from backend.services.job_context import submit
        submit(_pool, _run, document_id, revision_id, job_id)
        return _public(document_id, revision_id, data)


def _run(document_id, revision_id, job_id):
    file, data = _read(document_id, revision_id, job_id)
    try:
        import os
        if data.get('backend','oda' if data['format']=='dwg' else 'native_dxf') != (os.getenv('CAD_DWG_BACKEND','oda') if data['format']=='dwg' else 'native_dxf'):
            raise ValueError('CAD backend đã đổi sau khi xếp hàng; tạo tác vụ xuất mới.')
        data.update(status='running', message='Đang chuyển đổi CAD và kiểm tra lại hình học, kích thước, bảng kê.')
        storage.write_json(file, data)
        from backend.services.revision_service import export_dwg, export_dxf
        if data['format']=='dwg':prepare_aps(document_id,revision_id,data['scope'],data['preview'])
        with CAD_LOCK:
            path, _ = _check_revision(document_id, revision_id, data['preview'])
            exporter = export_dwg if data['format'] == 'dwg' else export_dxf
            result = exporter(document_id, revision_id, require_approval=not data['preview'], scope=data['scope'])
            data.update(file=str(result.resolve().relative_to(path.resolve())), file_hash=digest(result))
        data.update(status='ready', message='File đã kiểm chứng và sẵn sàng tải.')
    except Exception as error:
        message = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else 'Xuất CAD thất bại; bản sửa vẫn được lưu, hãy thử lại.'
        data.update(status='failed', message=message)
    finally:
        with _lock:
            storage.write_json(file, data)
            _active.discard(job_id)


def status(document_id, revision_id, job_id):
    with _lock:
        file, data = _read(document_id, revision_id, job_id)
        if data['status'] in ('queued', 'running') and job_id not in _active:
            data.update(status='failed', message='Server đã khởi động lại trong lúc xuất; bấm tạo file lại.')
            storage.write_json(file, data)
        if data['status']=='ready':
            try:download(document_id,revision_id,job_id)
            except (ValueError,FileNotFoundError) as error:
                data.update(status='failed',message=str(error)+' Bấm tạo file lại nếu bản sửa vẫn còn hợp lệ.')
                storage.write_json(file,data)
        return _public(document_id, revision_id, data)


def list_jobs(document_id, revision_id):
    folder = _folder(document_id, revision_id)
    items = [status(document_id, revision_id, f.stem) for f in
             sorted(folder.glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True)]
    items.sort(key=lambda j: 0 if j.get('scope') == 'document' else 1)
    return {'items': items}


def download(document_id, revision_id, job_id):
    _, data = _read(document_id, revision_id, job_id)
    if data['status'] != 'ready':
        raise ValueError(data.get('message', 'File chưa sẵn sàng tải.'))
    path, revision = _check_revision(document_id, revision_id, data['preview'])
    if not data['preview'] and data['format']=='dwg' and data['scope']=='document':
        from backend.services.edit_gate_service import require_artifact
        require_artifact(document_id,revision_id,production=True)
    if data.get('backend')=='autocad' and data['format']=='dwg':
        from backend.services.autocad_dxf_input import valid_receipt
        checked=revision.get('scoped_dwg_validation' if data['scope']=='selection' else 'dwg_validation',{})
        if not valid_receipt(checked):raise ValueError('Bản xuất cũ chưa kiểm đủ payload OLE; cần xuất lại bằng luồng hiện tại.')
    if revision['validation']['output_hash'] != data['output_hash']:
        raise ValueError('File tải thuộc phiên bản CAD cũ.')
    result = (path / data['file']).resolve()
    if not result.is_relative_to(path.resolve()) or result.suffix.lower() != '.' + data['format']:
        raise ValueError('Đường dẫn file xuất không hợp lệ.')
    if not result.is_file() or digest(result) != data['file_hash']:
        raise ValueError('File xuất đã thay đổi hoặc không còn; hãy xuất lại.')
    return result, ('PREVIEW-backup-' if data['preview'] else 'drawing-backup-') + revision_id[:8] + '.' + data['format']
