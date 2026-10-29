from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from cad.catalog import CAD_LOCK
from backend.services import edit_gate_service as gate,edit_certification_service as certificates,account_service as accounts

router=APIRouter()


def execute(function,*args):
    try:
        with CAD_LOCK:return function(*args)
    except accounts.AccountError as error:raise HTTPException(error.status,str(error))
    except (ValueError,OSError,KeyError,TypeError) as error:raise HTTPException(422,str(error))
    except Exception:raise HTTPException(503,'Chưa kiểm được bằng chứng DWG hiện tại; không tự phát hành.') from None


@router.get('/documents/{document_id}/change-plans/{plan_id}/edit-gate')
def plan(document_id:str,plan_id:str):return execute(gate.plan_review,document_id,plan_id)


@router.get('/documents/{document_id}/revisions/{revision_id}/edit-gate')
def revision(document_id:str,revision_id:str):return execute(gate.revision_review,document_id,revision_id)


@router.post('/documents/{document_id}/revisions/{revision_id}/auto-release')
def auto_release(document_id:str,revision_id:str):return execute(gate.auto_release,document_id,revision_id)


@router.get('/edit-certifications')
def listing():return dict(items=execute(certificates.listing))


@router.post('/edit-certifications',status_code=201)
def issue(body:certificates.CertificateRequest):return execute(certificates.issue,body)


class Revocation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason:str=Field(min_length=8,max_length=2000)


@router.post('/edit-certifications/{certificate_id}/revoke')
def revoke(certificate_id:str,body:Revocation):return execute(certificates.revoke,certificate_id,body.reason)
