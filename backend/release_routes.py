from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from cad.catalog import CAD_LOCK

router=APIRouter()
FRONTEND=Path(__file__).resolve().parents[1]/'frontend'


@router.get('/release-review',include_in_schema=False)
def page():return FileResponse(FRONTEND/'release-review.html',headers={'Cache-Control':'no-store'})


@router.get('/release-review.js',include_in_schema=False)
def script():return FileResponse(FRONTEND/'release-review.js',media_type='application/javascript')


@router.get('/documents/{document_id}/revisions/{revision_id}/release-review')
def review(document_id:str,revision_id:str):
    from backend.services.release_review_service import review
    try:
        with CAD_LOCK:return review(document_id,revision_id)
    except (ValueError,FileNotFoundError):raise HTTPException(422,'Không đọc được revision hiện tại; kiểm tra lại tài liệu và phiên bản.')
    except Exception:raise HTTPException(503,'Chưa kiểm được điều kiện phát hành. Chưa cho phép tự phát hành.') from None
