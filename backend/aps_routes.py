"""Cloud actions are explicit; ordinary document upload remains local."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse,Response
from pathlib import Path
from pydantic import BaseModel, Field

from backend.services import aps_jobs, aps_repository
from backend.services.aps_client import status, APSClient, APSError, check_connection
import httpx
from backend.services import catalog_service as storage

router = APIRouter(prefix='/aps', tags=['Autodesk Platform Services'])
documents = APIRouter(prefix='/documents', tags=['Autodesk Platform Services'])


@router.get('/status')
def aps_status():
    return status()


@router.post('/connection')
def aps_connection():
    """Check credentials and the deployed contract without sending any CAD."""
    client = None
    try:
        client = APSClient()
        return check_connection(client)
    except (APSError, ValueError) as error:
        raise HTTPException(422, str(error))
    except (httpx.HTTPError, KeyError, TypeError):
        # Transport exceptions can contain URLs or authentication details.
        raise HTTPException(502, 'Không kiểm tra được kết nối Autodesk; thử lại hoặc kiểm tra mạng server.')
    finally:
        if client is not None:
            client.close()


@router.get('/ui.js', include_in_schema=False)
def ui_script():
    return FileResponse(Path(__file__).resolve().parents[1] / 'frontend' / 'aps.js', media_type='application/javascript')


class NativeEditRequest(BaseModel):
    inspection_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    ids: list[str] = Field(min_length=1, max_length=4)
    operations: list[aps_jobs.NativeOperation] = Field(min_length=1, max_length=200)
    dependency_inspection_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')


class NativeContextRequest(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=4)
    parameter_offset:int|None=Field(default=None,ge=0,le=100000)


@documents.post('/{document_id}/aps/context')
def selected_native_context(document_id:str,body:NativeContextRequest):
    from backend.main import reading_targets
    from backend.services.change_service import context_for
    try:
        targets=reading_targets(document_id,body.ids)
        source=storage.folder(document_id)/storage.read_status(document_id)['dxf']
        context=context_for(source,targets)
        if body.parameter_offset is not None:
            from backend.services.aps_context import attach
            context=attach(context,source,parameter_offset=body.parameter_offset)
        result=context.get('aps_native')
        if not result:raise ValueError('Chưa có dữ liệu CAD native khớp nguồn. Mở bản sao bằng bộ xử lý đang chọn trước.')
        return dict(result,scope_ids=body.ids)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@documents.post('/{document_id}/aps/native-edits', status_code=202)
def native_edit(document_id: str, body: NativeEditRequest):
    return edit_native(document_id,body,'aps')


def edit_native(document_id,body,provider):
    """Explicit native operations grounded in a prior native inspection and local selection.

This is an adapter API, not an LLM code execution endpoint or a full-product approval.
"""
    import json
    from backend.main import reading_targets
    from backend.services.change_service import context_for
    try:
        inspection = aps_repository.read(document_id, body.inspection_id)
        if inspection['mode'] != 'inspect' or inspection['source_hash'] != body.source_hash:
            raise ValueError('Kết quả đọc không khớp nguồn native đã chọn.')
        inventory = json.loads(aps_jobs.artifact(document_id, body.inspection_id, 'inventory.json').read_text(encoding='utf-8-sig'))
        native = {row['handle']: row for row in inventory['entities']}
        targets = reading_targets(document_id, body.ids)
        source = storage.folder(document_id) / storage.read_status(document_id)['dxf']
        context = context_for(source, targets)
        bound=context.get('aps_native')
        if not bound or bound['inspection_id']!=body.inspection_id or bound['original_source_hash']!=body.source_hash or bound.get('provider','aps')!=provider:
            raise ValueError('Dữ liệu native không còn khớp bản vẽ đang chọn; mở bản sao và đọc lại tham số.')
        nested_refs={'/'.join(op.instance_path) for op in body.operations if op.instance_path}
        if nested_refs-set(r['ref'] for r in bound.get('records',[])):
            from backend.services.aps_context import attach
            context=attach(context,source,record_refs=nested_refs)
            bound=context.get('aps_native')
            if not bound or bound['inspection_id']!=body.inspection_id or bound['original_source_hash']!=body.source_hash:
                raise ValueError('Nguồn đã đổi khi truy xuất nhánh block; đọc lại CAD trước khi sửa.')
        allowed = {row['ref'] for row in context['entities'] if not row.get('review_only')}
        bound_records={r['ref']:r for r in bound.get('records',[])}
        for op in body.operations:
            row = native.get(op.handle, {})
            ref='/'.join(op.instance_path) if op.instance_path else op.handle
            if ref not in allowed or row.get('owner_handle') != op.owner_handle or row.get('type') != op.expected_type:
                raise ValueError('Lệnh native không khớp entity/phạm vi/chủ sở hữu CAD đã đọc.')
            if op.instance_path:
                facts=bound_records.get(ref,{})
                chain=[native.get(handle,{}) for handle in op.instance_path]
                if (not facts.get('nested_editable') or facts.get('handle')!=op.handle or not chain[0].get('is_layout')
                        or any(parent.get('type')!='INSERT' or parent.get('dynamic') or
                            child.get('owner_handle')!=parent.get('block_handle') for parent,child in zip(chain,chain[1:]))):
                    raise ValueError('Nhánh block lồng chưa xác minh quyền cô lập instance; đọc lại CAD nguồn.')
            elif not row.get('is_layout'):
                raise ValueError('Đối tượng trong định nghĩa dùng chung cần đường dẫn instance đã xác minh.')
            if op.action=='set_dynamic_property':
                from backend.services.native_parameters import validate_parameter
                validate_parameter(row,op)
            if op.action=='translate_centermark':
                from cad.native_centermark import candidates
                import math
                if provider!='autocad' or not body.dependency_inspection_id:
                    raise ValueError('Cần inspection dependency local cho các cặp CenterMark.')
                dependency_job=aps_repository.read(document_id,body.dependency_inspection_id)
                if (dependency_job.get('provider')!='autocad' or dependency_job.get('mode')!='inspect' or
                        dependency_job.get('source_hash')!=body.source_hash):
                    raise ValueError('Inspection dependency không khớp nguồn local.')
                dependency_inventory=json.loads(aps_jobs.artifact(document_id,body.dependency_inspection_id,'inventory.json').read_text(encoding='utf-8-sig'))
                pairs=[p for p in candidates(dependency_inventory) if p['circle_handle']==op.handle and p['mark_handle']==op.mark_handle and p['action_handle']==op.action_handle and p['owner_handle']==op.owner_handle]
                if len(pairs)!=1 or op.mark_handle not in allowed or math.dist(pairs[0]['source_center'],json.loads(op.before))>1e-6:
                    raise ValueError('Cặp CenterMark hoặc tâm nguồn không khớp phạm vi/dependency đã đọc.')
        return aps_jobs.start(document_id, mode='edit', operations=[op.model_dump() for op in body.operations], scope_handles=allowed, expected_source_hash=body.source_hash,target_ids=body.ids,provider=provider)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(422, str(error))


@documents.post('/{document_id}/aps/jobs', status_code=202)
def inspect_native(document_id: str):
    try:
        return aps_jobs.start(document_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(422, str(error))


@documents.post('/{document_id}/aps/import',status_code=202)
def import_cloud_copy(document_id:str):
    return import_native_copy(document_id,'aps')


def import_native_copy(document_id,provider):
    """New native-imported document; old working sources/revisions stay intact."""
    try:
        from backend.services.aps_client import Settings
        if provider=='aps':Settings.load().check()
        else:
            from backend.services.autocad_host import ready
            ready()
        path=storage.folder(document_id);status=storage.read_status(document_id)
        if status.get('read_backend')==provider:return storage.resume_native_import(document_id)
        source=next((p for p in (path/'original.dwg',path/'original.dxf') if p.is_file()),None)
        if source is None:raise FileNotFoundError('Không có CAD nguồn.')
        with source.open('rb') as stream:
            return storage.create_document(status.get('filename',source.name),stream,read_backend_override=provider)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@documents.get('/{document_id}/aps/jobs')
def jobs(document_id: str):
    try:
        storage.folder(document_id)
        return {'items': [aps_jobs.public(job) for job in aps_repository.list_jobs(document_id) if job.get('provider','aps')=='aps']}
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, str(error))


@documents.get('/{document_id}/aps/jobs/{job_id}')
def job_status(document_id: str, job_id: str):
    try:
        return aps_jobs.read(document_id, job_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, str(error))


@documents.post('/{document_id}/aps/jobs/{job_id}/derivative')
def refresh_metadata(document_id:str,job_id:str):
    try:return aps_jobs.refresh_derivative(document_id,job_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@documents.get('/{document_id}/aps/jobs/{job_id}/preview/{target_id}')
def preview_native(document_id:str,job_id:str,target_id:str):
    from backend.main import reading_targets
    from cad.catalog import CAD_LOCK,preview
    from cad.sheets import render_sheet
    try:
        job=aps_repository.read(document_id,job_id)
        if target_id not in job.get('target_ids',[]):raise ValueError('Bản vẽ không thuộc phạm vi bản sửa native này.')
        source=aps_jobs.artifact(document_id,job_id,'roundtrip.dxf')
        target=reading_targets(document_id,[target_id])[0]
        with CAD_LOCK:
            content=render_sheet(source,target) if target['kind']=='sheet' else preview(source,target_id)
        return Response(content,media_type='image/svg+xml')
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@documents.get('/{document_id}/aps/jobs/{job_id}/files/{name}')
def download(document_id: str, job_id: str, name: str):
    try:
        file = aps_jobs.artifact(document_id, job_id, name)
        filename = 'APS-PREVIEW-' + job_id[:8] + '.dwg' if name == 'modified.dwg' else name
        return FileResponse(file, filename=filename)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(422, str(error))


from backend.rectangle_models import RectangleStretchRequest


@documents.post('/{document_id}/aps/rectangle-stretch',status_code=202)
def stretch_rectangle_cloud(document_id:str,body:RectangleStretchRequest):
    from backend.services.rectangle_stretch_service import start
    try:return start(document_id,body.inspection_id,body.polyline_handle,body.dimension_handle,body.target_width_mm,body.source_hash,provider='aps')
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@documents.get('/{document_id}/aps/jobs/{job_id}/rectangle-candidates')
def rectangle_candidates_cloud(document_id:str,job_id:str):
    from backend.services.rectangle_stretch_service import candidates
    try:return candidates(document_id,job_id,provider='aps')
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


def preview_rectangle(document_id,job_id,polyline_handle,dimension_handle,*,provider):
    import re
    from backend.services.rectangle_stretch_service import preview
    try:
        if any(not re.fullmatch('[0-9A-F]{1,16}',h) for h in (polyline_handle,dimension_handle)):raise ValueError('Invalid rectangle handles')
        return Response(preview(document_id,job_id,polyline_handle,dimension_handle,provider=provider),media_type='image/svg+xml',headers={'Cache-Control':'no-store'})
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@documents.get('/{document_id}/aps/jobs/{job_id}/rectangle-preview')
def rectangle_preview_cloud(document_id:str,job_id:str,polyline_handle:str,dimension_handle:str):
    return preview_rectangle(document_id,job_id,polyline_handle,dimension_handle,provider='aps')
