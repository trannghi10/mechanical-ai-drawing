"""Local AutoCAD has separate endpoints; none of these call Autodesk cloud."""
import os
import json
from typing import Annotated,Literal
from pydantic import BaseModel,Field,ConfigDict
from fastapi import APIRouter,HTTPException
from backend import aps_routes
from backend.services import aps_jobs,aps_repository,catalog_service as storage,autocad_host

router=APIRouter(tags=['AutoCAD local'])


class RelationshipProposalRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    inspection_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    polyline_handle:str=Field(pattern=r'^[A-Fa-f0-9]{1,16}$')
    source_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    adapter:Literal['legacy','native_pointrefs']='legacy'
    base_revision_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')


class RelationshipHistoryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=0)


@router.post('/documents/{document_id}/autocad/relationship-proposals/{proposal_id}/apply',status_code=202)
def apply_relationship_proposal(document_id:str,proposal_id:str,body:RelationshipHistoryRequest):
    from backend.services.relationship_revision_service import start
    try:return start(document_id,proposal_id,body.expected_version)
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/relationship-history')
def relationship_history(document_id:str):
    from backend.services.relationship_revision_service import history
    try:return history(document_id)
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.post('/documents/{document_id}/autocad/relationship-history/{direction}')
def move_relationship_history(document_id:str,direction:str,body:RelationshipHistoryRequest):
    from backend.services.relationship_revision_service import move
    try:return move(document_id,direction,body.expected_version)
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/relationship-revisions/{revision_id}')
def relationship_revision(document_id:str,revision_id:str):
    from backend.services.relationship_revision_service import read
    try:return read(document_id,revision_id)
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/relationship-revisions/{revision_id}/files/{name}')
def relationship_revision_file(document_id:str,revision_id:str,name:str):
    from backend.services.relationship_revision_service import artifact
    from fastapi.responses import FileResponse
    try:return FileResponse(artifact(document_id,revision_id,name),filename='RELATIONSHIP-PREVIEW-'+revision_id[:8]+'.'+name.rsplit('.',1)[-1],headers={'Cache-Control':'no-store'})
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/relationship-revisions/{revision_id}/preview')
def relationship_revision_preview(document_id:str,revision_id:str):
    from backend.services.relationship_revision_service import preview
    from fastapi.responses import Response
    try:return Response(preview(document_id,revision_id),media_type='image/svg+xml',headers={'Cache-Control':'no-store'})
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.post('/documents/{document_id}/autocad/relationship-proposals',status_code=201)
def propose_relationship_repair(document_id:str,body:RelationshipProposalRequest):
    from backend.services.relationship_repair_service import create
    try:return create(document_id,body.inspection_id,body.polyline_handle,body.source_hash,body.adapter,body.base_revision_id)
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/relationship-proposals/{proposal_id}')
def relationship_proposal(document_id:str,proposal_id:str):
    from backend.services.relationship_repair_service import read
    try:return read(document_id,proposal_id)[0]
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/relationship-proposals/{proposal_id}/preview')
def relationship_proposal_preview(document_id:str,proposal_id:str):
    from fastapi.responses import Response
    from backend.services.relationship_repair_service import preview
    try:return Response(preview(document_id,proposal_id),media_type='image/svg+xml',headers={'Cache-Control':'no-store'})
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


class NativeInspectRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    handles:list[Annotated[str,Field(pattern=r'^[0-9A-Fa-f]{1,16}(?:/[0-9A-Fa-f]{1,16}){0,7}$',max_length=143)]]=Field(default_factory=list,max_length=64)


from backend.rectangle_models import RectangleStretchRequest


@router.post('/documents/{document_id}/autocad/rectangle-stretch',status_code=202)
def stretch_rectangle(document_id:str,body:RectangleStretchRequest):
    from backend.services.rectangle_stretch_service import start
    try:return start(document_id,body.inspection_id,body.polyline_handle,body.dimension_handle,body.target_width_mm,body.source_hash)
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/autocad/status')
def status():
    return dict(autocad_host.status(),backend=os.getenv('CAD_DWG_BACKEND','oda'),
                read_backend=os.getenv('CAD_READ_BACKEND') or os.getenv('CAD_DWG_BACKEND','oda'),missing=[],
                cloud_disclosure='Đọc/sửa CAD bằng AutoCAD trên máy; adapter này không gửi file ra cloud.')


def local_job(document_id,job_id):
    job=aps_repository.read(document_id,job_id)
    if job.get('provider')!='autocad':raise FileNotFoundError('Không có tác vụ AutoCAD local này.')
    return job


@router.post('/documents/{document_id}/autocad/jobs',status_code=202)
def inspect(document_id:str,body:NativeInspectRequest|None=None):
    try:return aps_jobs.start(document_id,provider='autocad',scope_handles=body.handles if body else [])
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@router.post('/documents/{document_id}/autocad/recover',status_code=202)
def recover_copy(document_id:str):
    try:return aps_jobs.start(document_id,provider='autocad',mode='recover')
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@router.post('/documents/{document_id}/autocad/import',status_code=202)
def import_copy(document_id:str):return aps_routes.import_native_copy(document_id,'autocad')


@router.post('/documents/{document_id}/autocad/context')
def context(document_id:str,body:aps_routes.NativeContextRequest):
    return aps_routes.selected_native_context(document_id,body)


@router.post('/documents/{document_id}/autocad/centermark-inspections',status_code=202)
def inspect_centermarks(document_id:str,body:aps_routes.NativeContextRequest):
    from backend.main import reading_targets
    from backend.services.change_service import context_for
    from cad.native_centermark import inspection_roots
    try:
        targets=reading_targets(document_id,body.ids)
        path=storage.folder(document_id)
        context=context_for(path/storage.read_status(document_id)['dxf'],targets)
        bound=context.get('aps_native')
        if not bound or bound.get('provider')!='autocad':
            raise ValueError('Mở bản sao bằng AutoCAD trên máy trước khi đọc dấu tâm.')
        inventory=json.loads(aps_jobs.artifact(document_id,bound['inspection_id'],'inventory.json').read_text(encoding='utf-8-sig'))
        allowed={row['ref'] for row in context['entities'] if not row.get('review_only') and '/' not in row['ref']}
        roots=inspection_roots(inventory,allowed)
        return aps_jobs.start(document_id,provider='autocad',scope_handles=roots,target_ids=body.ids,expected_source_hash=bound['original_source_hash'])
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@router.post('/documents/{document_id}/autocad/native-edits',status_code=202)
def edit(document_id:str,body:aps_routes.NativeEditRequest):
    return aps_routes.edit_native(document_id,body,'autocad')


@router.get('/documents/{document_id}/autocad/jobs')
def jobs(document_id:str):
    try:
        storage.folder(document_id)
        return {'items':[aps_jobs.public(job) for job in aps_repository.list_jobs(document_id) if job.get('provider')=='autocad']}
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,str(error))


@router.get('/documents/{document_id}/autocad/jobs/{job_id}')
def read(document_id:str,job_id:str):
    try:
        local_job(document_id,job_id)
        return aps_jobs.read(document_id,job_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,str(error))


@router.get('/documents/{document_id}/autocad/jobs/{job_id}/centermark-candidates')
def centermark_candidates(document_id:str,job_id:str):
    from cad.native_centermark import candidates
    from cad.edit_engine import digest
    try:
        job=local_job(document_id,job_id)
        if job.get('mode')!='inspect' or job.get('status')!='ready':
            raise ValueError('Cần tác vụ đọc native đã hoàn thành.')
        source=storage.folder(document_id)/'original.dwg'
        if digest(source)!=job['source_hash']:
            raise ValueError('Nguồn đã đổi; cần đọc lại dependency native.')
        inventory=json.loads(aps_jobs.artifact(document_id,job_id,'inventory.json').read_text(encoding='utf8'))
        return dict(inspection_id=job_id,source_hash=job['source_hash'],items=candidates(inventory),
                    edit_authorization=False,complete_mechanical_group=False)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/jobs/{job_id}/files/{name}')
def download(document_id:str,job_id:str,name:str):
    try:local_job(document_id,job_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,str(error))
    response=aps_routes.download(document_id,job_id,name)
    if name=='modified.dwg':
        prefix='RECOVERY-REVIEW' if local_job(document_id,job_id)['mode']=='recover' else 'AUTOCAD-PREVIEW'
        response.headers['content-disposition']=f'attachment; filename="{prefix}-{job_id[:8]}.dwg"'
    return response


@router.get('/documents/{document_id}/autocad/jobs/{job_id}/preview/{target_id}')
def preview(document_id:str,job_id:str,target_id:str):
    try:local_job(document_id,job_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,str(error))
    return aps_routes.preview_native(document_id,job_id,target_id)


@router.get('/documents/{document_id}/autocad/jobs/{job_id}/rectangle-candidates')
def rectangle_candidates(document_id:str,job_id:str):
    from backend.services.rectangle_stretch_service import candidates
    try:return candidates(document_id,job_id,provider='autocad')
    except (ValueError,FileNotFoundError,KeyError) as error:raise HTTPException(422,str(error))


@router.get('/documents/{document_id}/autocad/jobs/{job_id}/rectangle-preview')
def rectangle_preview(document_id:str,job_id:str,polyline_handle:str,dimension_handle:str):
    return aps_routes.preview_rectangle(document_id,job_id,polyline_handle,dimension_handle,provider='autocad')
