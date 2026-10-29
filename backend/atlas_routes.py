"""Whole-document reading API. No route here changes or publishes CAD."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend.services import document_atlas_service as atlas

router = APIRouter()


def call(action, *args, **kwargs):
    try: return action(*args, **kwargs)
    except FileNotFoundError: raise HTTPException(404, 'Tài liệu hoặc hồ sơ toàn file không tồn tại')
    except ValueError as error: raise HTTPException(422, str(error))


@router.get('/document-atlas.js', include_in_schema=False)
def script():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/document-atlas.js', media_type='application/javascript')


@router.post('/documents/{document_id}/atlas', status_code=202)
def submit(document_id: str):
    return call(atlas.submit, document_id)


@router.get('/documents/{document_id}/atlas/{job_id}')
def status(document_id: str, job_id: str):
    return call(atlas.read, document_id, job_id)


@router.get('/documents/{document_id}/atlas/{job_id}/report')
def report(document_id: str, job_id: str):
    return call(atlas.report, document_id, job_id)


@router.get('/documents/{document_id}/atlas/{job_id}/entities')
def entities(document_id: str, job_id: str, offset: int = 0, limit: int = 50,
             layout: str = '', kind: str = '', query: str = ''):
    return call(atlas.entities, document_id, job_id, offset=offset, limit=limit, layout=layout, kind=kind, query=query)
