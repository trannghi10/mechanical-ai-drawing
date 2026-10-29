from fastapi import FastAPI
from fastapi import UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, Response, RedirectResponse
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=True, encoding='utf-8-sig')
import os
os.environ.setdefault('CAD_ALLOW_REMOTE', '1')
from backend.services import catalog_service as service
from cad.catalog import preview, CAD_LOCK
from cad.sheets import discover_sheets, render_sheet, excluded_regions, discarded, geometry_index
from cad.catalog import load_document
from backend.aps_routes import router as aps_router, documents as aps_documents
from backend.autocad_routes import router as autocad_router
from backend.atlas_routes import router as atlas_router
from backend.dataset_routes import router as dataset_router
from backend.account_routes import router as account_router
from backend.release_routes import router as release_router
from backend.edit_gate_routes import router as edit_gate_router

app = FastAPI(
    title="Mechanical AI Drawing",
    description="AI system for understanding and modifying mechanical DWG drawings",
    version="0.1.0"
)

app.include_router(aps_router)
app.include_router(aps_documents)
app.include_router(autocad_router)
app.include_router(atlas_router)
app.include_router(dataset_router)
app.include_router(account_router)
app.include_router(release_router)
app.include_router(edit_gate_router)


@app.on_event('startup')
def recover_relationship_jobs():
    from backend.services.relationship_revision_service import recover_interrupted
    recover_interrupted()


@app.middleware('http')
async def protect_cloud_actions(request: Request, call_next):
    # Reading document lists/previews/downloads needs the same boundary as
    # writes. Host validation also covers DNS rebinding with no Origin header.
    from backend.local_access import denial
    reason=denial(request)
    if reason:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':reason},status_code=403)
    from backend.services import account_service as accounts
    from starlette.concurrency import run_in_threadpool
    from fastapi.responses import JSONResponse,RedirectResponse
    from urllib.parse import quote
    import uuid
    user=None
    public_paths={'/login','/accounts','/accounts.js','/workspace.css','/auth/status','/auth/setup','/auth/login','/auth/logout'}
    if accounts.required():
        try:user=await run_in_threadpool(accounts.current,request.cookies.get(accounts.COOKIE))
        except Exception:return JSONResponse({'detail':'Không kiểm tra được tài khoản; chưa cho phép truy cập dữ liệu.'},status_code=503)
        if request.url.path not in public_paths:
            if not user:
                if request.method=='GET' and request.url.path in ('/','/explorer','/help','/dataset','/relationship-review','/release-review'):
                    target=request.url.path+('?' + request.url.query if request.url.query else '')
                    return RedirectResponse('/login?next='+quote(target,safe=''),status_code=303)
                return JSONResponse({'detail':'Cần đăng nhập để truy cập bản vẽ.','login_required':True},status_code=401)
            if not accounts.permitted(user,request.method,request.url.path):
                return JSONResponse({'detail':'Vai trò hiện tại không cho phép thao tác này.'},status_code=403)
    request.state.actor=user
    request_id=uuid.uuid4().hex
    token=accounts.ACTOR.set(dict(user,request_id=request_id) if user else None)
    mutation=bool(user and request.method not in ('GET','HEAD','OPTIONS'))
    try:
        if mutation:
            try:await run_in_threadpool(accounts.audit,user,request.method,request.url.path,102,request_id)
            except Exception:return JSONResponse({'detail':'Không ghi được nhật ký; chưa thực hiện thao tác.'},status_code=503)
        response=await call_next(request)
        response.headers['X-Request-ID']=request_id
        if user or request.url.path.startswith('/auth/'):
            response.headers['Cache-Control']='no-store'
        if mutation:
            try:await run_in_threadpool(accounts.finish_audit,request_id,response.status_code)
            except Exception:pass # The durable started record remains recoverable.
        return response
    finally:accounts.ACTOR.reset(token)


@app.get("/")
@app.get("/explorer")
def workspace():
    return FileResponse(Path(__file__).resolve().parents[1] / 'frontend' / 'index.html')


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.get('/database/status')
def database_status():
    from backend.services.database_service import status
    return status()


@app.get('/database/health')
def database_health(request:Request):
    from backend.services.database_service import status
    result=status();actor=getattr(request.state,'actor',None)
    summary={key:result[key] for key in ('backend','ready','documents','revisions','message') if key in result}
    summary['details_allowed']=actor is None or actor['role']=='admin'
    return summary


@app.get('/workspace.css',include_in_schema=False)
def workspace_styles():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/workspace.css',media_type='text/css')


@app.get('/rectangle-ui.js',include_in_schema=False)
def rectangle_ui_script():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/rectangle-ui.js',media_type='application/javascript')


@app.get('/workspace-ui.js',include_in_schema=False)
def workspace_ui():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/workspace-ui.js',media_type='application/javascript')


@app.get('/document-request.js',include_in_schema=False)
def document_request_script():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/document-request.js',media_type='application/javascript')


@app.get('/help',include_in_schema=False)
def user_help():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/help.html',media_type='text/html')


@app.get('/relationship-review',include_in_schema=False)
def relationship_review_page():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/relationship-review.html',media_type='text/html')


@app.get('/relationship-review.js',include_in_schema=False)
def relationship_review_script():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/relationship-review.js',media_type='application/javascript')


@app.get('/ai/status')
def ai_status():
    from backend.services.ai_provider import settings
    try:
        provider,model=settings()
        if provider=='native':
            from backend.services.native_ai_service import status
            return dict(status(),checked_engine_available=True)
        if provider=='ollama':
            from backend.services.ollama_service import status
            return status()
        return {'provider':provider,'model':model,'local_only':False,'ready':True,
                'message':('Chế độ OpenAI: ảnh và dữ liệu CAD được gửi đến OpenAI khi phân tích.' if provider=='openai' else 'Chế độ Gemini: dữ liệu được gửi đến Google khi phân tích.')}
    except ValueError as error:
        return {'provider':'blocked','local_only':True,'ready':False,'message':str(error)}


@app.post('/ai/start')
def start_local_ai(request: Request):
    if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Chỉ khởi động AI từ máy nội bộ.')
    from backend.services.ai_provider import settings
    from backend.services.local_runtime_service import start
    try:
        if settings()[0]!='native':raise ValueError('Khởi động này chỉ dành cho AI nội bộ native.')
        return start()
    except ValueError as error:raise HTTPException(422,str(error))


@app.get('/documents')
def list_documents(include_auxiliary: bool = False, current: str = ''):
    return service.list_documents(include_auxiliary=include_auxiliary,current=current)


@app.post('/documents', status_code=202)
def upload(file: UploadFile):
    try:
        return service.create_document(file.filename or '', file.file)
    except ValueError as error:
        raise HTTPException(400, str(error))
    finally:
        file.file.close()


@app.get('/documents/{document_id}/cad-capabilities')
def cad_capabilities(document_id:str,offset:int=0,limit:int=50):
    if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Phân trang CAD không hợp lệ')
    from backend.services.capability_service import get
    try:return get(document_id,offset,limit)
    except FileNotFoundError as error:raise HTTPException(404,str(error))
    except ValueError as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/block-assembly')
def block_assembly(document_id: str):
    from backend.services.block_assembly_service import get_block_assembly
    try:
        return get_block_assembly(document_id)
    except FileNotFoundError as error:
        raise HTTPException(404, str(error))
    except ValueError as error:
        raise HTTPException(422, str(error))



@app.get('/documents/{document_id}')
def status(document_id: str):
    try:
        return service.read_status(document_id)
    except FileNotFoundError:
        raise HTTPException(404, 'Document không tồn tại')


@app.get('/documents/{document_id}/catalog')
def get_catalog(document_id: str):
    try:
        data=service.catalog(document_id)
        try:
            from backend.services.exclusion_service import exclusions as read_exclusions
            ex=read_exclusions(document_id,data['items'])
            ids=set(ex.get('ids',[]))
            data['items']=[i for i in data['items'] if i['id'] not in ids]
            data['excluded_count']=len(ids)
        except Exception:
            data['excluded_count']=0
        return data
    except FileNotFoundError:
        raise HTTPException(404, 'Document không tồn tại')
    except ValueError as error:
        raise HTTPException(409, str(error))


class Selection(BaseModel):
    ids: list[str]


class ParameterLinkRequest(Selection):
    source_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    rule:dict
    confirmed:Literal[True]


@app.get('/documents/{document_id}/parameter-links')
def get_parameter_links(document_id:str):
    from backend.services.parameter_link_service import get
    try:return get(document_id)
    except FileNotFoundError as error:raise HTTPException(404,str(error))
    except ValueError as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/parameter-links')
def save_parameter_link(document_id:str,body:ParameterLinkRequest):
    from backend.services.parameter_link_service import save
    targets=reading_targets(document_id,body.ids)
    try:return save(document_id,targets,body.source_hash,body.rule)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.delete('/documents/{document_id}/parameter-links/{link_id}')
def remove_parameter_link(document_id:str,link_id:str,source_hash:str):
    from backend.services.parameter_link_service import remove
    try:return remove(document_id,link_id,source_hash)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


class CuboidCandidatesRequest(Selection):
    source_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    dimension_ref:str=Field(min_length=1,max_length=256)


class CuboidLinkRequest(BaseModel):
    candidate_id:str=Field(pattern=r'^[0-9a-f]{24}$')
    body_id:str=Field(pattern=r'^[0-9a-f]{24}$')
    source_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    anchor:Literal['center','vertex']
    vertex:Literal['A','B','C','D','E','F','G','H']|None=None
    confirmed:Literal[True]


@app.post('/documents/{document_id}/cuboid-candidates')
def inspect_cuboid_candidates(document_id:str,body:CuboidCandidatesRequest):
    from backend.services.cuboid_link_service import candidates
    targets=reading_targets(document_id,body.ids)
    try:
        result=candidates(document_id,targets,body.dimension_ref)
        if result['source_hash']!=body.source_hash:raise ValueError('Nguồn CAD đã thay đổi; cần đọc lại hồ sơ')
        return result
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/cuboid-candidates/{candidate_id}/{body_id}/preview')
def cuboid_candidate_preview(document_id:str,candidate_id:str,body_id:str,source_hash:str):
    from backend.services.cuboid_link_service import preview
    try:return Response(preview(document_id,candidate_id,body_id,source_hash),media_type='image/svg+xml',headers={'Cache-Control':'no-store'})
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/cuboid-links')
def get_cuboid_links(document_id:str):
    from backend.services.cuboid_link_service import get
    try:return get(document_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/cuboid-links')
def confirm_cuboid_link(document_id:str,body:CuboidLinkRequest):
    from backend.services.cuboid_link_service import save
    try:return save(document_id,body.candidate_id,body.body_id,body.source_hash,body.anchor,body.vertex)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.delete('/documents/{document_id}/cuboid-links/{body_id}')
def remove_cuboid_link(document_id:str,body_id:str,source_hash:str):
    from backend.services.cuboid_link_service import remove
    try:return remove(document_id,body_id,source_hash)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


class PartSelection(BaseModel):
    map_id:str=Field(pattern=r'^[a-f0-9]{24}$')
    view_id:str=Field(min_length=1,max_length=80)
    source_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    part_code:str=Field(min_length=1,max_length=128)


class DocumentTargetChoice(BaseModel):
    atlas_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    source_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    part_code:str=Field(min_length=1,max_length=128)


class ChangeRequest(BaseModel):
    ids: list[str]=Field(default_factory=list)
    request: str
    part_selection:PartSelection|None=None
    whole_document:bool=False
    target_choice:DocumentTargetChoice|None=None


class InspectionRequest(BaseModel):
    ids: list[str]
    request: str = Field(default='',max_length=4000)


def reading_targets(document_id,ids):
    all_items=get_catalog(document_id)['items']+get_sheets(document_id)['items']
    chosen=set(ids)
    if not chosen or len(chosen)>4 or not chosen<={i['id'] for i in all_items}:
        raise HTTPException(400,'Chọn từ 1 đến 4 khung, block hoặc bảng CAD hợp lệ để đọc')
    return [item for item in all_items if item['id'] in chosen]


@app.post('/documents/{document_id}/reading-report')
def get_reading_report(document_id:str,body:Selection):
    from backend.services.inspection_service import reading_report
    targets=reading_targets(document_id,body.ids)
    try:return reading_report(document_id,targets)[1]
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/design-model')
def get_design_model(document_id:str,body:Selection):
    from backend.services.design_model_service import get
    targets=reading_targets(document_id,body.ids)
    try:return get(document_id,targets)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


class PartMapRequest(Selection):
    include_related: bool = True


@app.post('/documents/{document_id}/part-map')
def recognize_parts(document_id:str,body:PartMapRequest):
    from backend.services.design_model_service import part_map
    targets=reading_targets(document_id,body.ids)
    try:return part_map(document_id,targets,body.include_related)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/part-map/{map_id}/views/{view_id}/preview')
def recognized_part_preview(document_id:str,map_id:str,view_id:str,source_hash:str):
    from backend.services.design_model_service import part_view_preview
    try:
        content=part_view_preview(document_id,map_id,view_id,source_hash)
        return Response(content,media_type='image/svg+xml',headers={'Cache-Control':'no-store'})
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/inspect')
def inspect_drawing(document_id:str,body:InspectionRequest):
    from backend.services.inspection_service import inspect_selection
    from backend.services.gemini_service import AIError
    targets=reading_targets(document_id,body.ids)
    try:return inspect_selection(document_id,targets,body.request.strip())
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))
    except AIError as error:raise HTTPException(error.status,str(error))


@app.get('/documents/{document_id}/inspections/{inspection_id}')
def get_inspection(document_id:str,inspection_id:str):
    import hashlib,json
    from backend.services.revision_service import safe_id
    try:
        path=service.folder(document_id)
        result=json.loads((path/'inspections'/(safe_id(inspection_id)+'.json')).read_text(encoding='utf8'))
        source=path/service.read_status(document_id)['dxf']
        if result['source_hash']!=hashlib.sha256(source.read_bytes()).hexdigest():
            raise HTTPException(409,'Kết quả đọc thuộc phiên bản CAD cũ; hãy đọc lại.')
        from backend.services.inspection_service import ground_reading,GROUNDING_VERSION
        result['readings']=[reading if reading.get('grounding_version')==GROUNDING_VERSION else ground_reading(reading,result['facts']) for reading in result.get('readings',[])]
        return result
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Kết quả đọc không tồn tại')


class Clarifications(BaseModel):
    answers: list[str]


class DependencyConfirmation(BaseModel):
    confirmed_dependencies: list[int] = Field(default_factory=list)
    preview_only: bool = False


def public_change_plan(data):
    # The checked snapshot is server-side execution evidence. The viewer only
    # needs its availability flag, not a second huge copy of CAD operations.
    return {k:v for k,v in data.items() if k!='checked_preview_plan'}


@app.post('/documents/{document_id}/change-plans/{plan_id}/refine')
def refine_plan(document_id: str,plan_id: str,body: Clarifications):
    from backend.services.change_service import refine_change
    try:
        from backend.services.planning_control import bounded
        with bounded():return public_change_plan(refine_change(document_id,plan_id,body.answers))
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))
    except Exception as error:
        from backend.services.gemini_service import AIError
        if isinstance(error,AIError):raise HTTPException(error.status,str(error))
        raise HTTPException(502,'Không lập lại được kế hoạch AI. Chưa tạo bản sửa.')



@app.post('/documents/{document_id}/change-plans')
def create_change_plan(document_id: str, body: ChangeRequest):
    from backend.services.change_service import plan_change
    from backend.services.gemini_service import AIError
    if body.whole_document or body.target_choice:
        raise HTTPException(400,'Dùng tác vụ phân tích toàn file tại planning-jobs để theo dõi quá trình đọc và tìm chi tiết.')
    all_items=get_catalog(document_id)['items']+get_sheets(document_id)['items']
    ids=set(body.ids)
    if not ids or not ids <= {i['id'] for i in all_items}:
        raise HTTPException(400,'Chọn bản vẽ hoặc block hợp lệ trước khi nhập yêu cầu')
    if not body.request.strip() or len(body.request)>4000:
        raise HTTPException(400,'Yêu cầu phải có từ 1 đến 4000 ký tự')
    targets=[i for i in all_items if i['id'] in ids]
    try:
        from backend.services.planning_control import bounded
        with bounded():return public_change_plan(plan_change(document_id,targets,body.request.strip(),**({'part_selection':body.part_selection} if body.part_selection else {})))
    except ValueError as error:
        raise HTTPException(422,str(error))
    except AIError as error:
        raise HTTPException(error.status,str(error))
    except Exception:
        raise HTTPException(500,'Lỗi xử lý nội bộ khi phân tích CAD. Chưa tạo bản sửa; cần kiểm tra context/schema trên server.')


@app.get('/documents/{document_id}/change-plans')
def list_change_plans(document_id: str, summary: bool = False):
    import json
    try:
        path=service.folder(document_id)/'change-plans'
        rows=[json.loads(p.read_text(encoding='utf8')) for p in sorted(path.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)]
        if summary:rows=[{k:r.get(k) for k in ('id','request')} for r in rows]
        return {'items':[public_change_plan(row) for row in rows]}
    except FileNotFoundError:raise HTTPException(404,'Document không tồn tại')


@app.post('/documents/{document_id}/planning-jobs',status_code=202)
def create_planning_job(document_id:str,body:ChangeRequest):
    from backend.services.planning_jobs import submit
    if not body.request.strip() or len(body.request)>4000:raise HTTPException(400,'Yêu cầu phải có từ 1 đến 4000 ký tự')
    if body.whole_document and (body.ids or body.part_selection):
        raise HTTPException(400,'Chế độ toàn file tự tìm khung nguồn; bỏ lựa chọn khung/hình cũ.')
    targets=[] if body.whole_document else reading_targets(document_id,body.ids)
    extra={}
    if body.part_selection:extra['part_selection']=body.part_selection
    if body.whole_document:extra['whole_document']=True
    if body.target_choice:extra['target_choice']=body.target_choice.model_dump()
    try:return submit(document_id,targets,body.request.strip(),**extra)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/planning-jobs/{job_id}')
def read_planning_job(document_id:str,job_id:str):
    from backend.services.planning_jobs import read
    try:return read(document_id,job_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,'Tác vụ không tồn tại trong file này.')


@app.delete('/documents/{document_id}/planning-jobs/{job_id}')
def cancel_planning_job(document_id:str,job_id:str):
    from backend.services.planning_jobs import cancel
    try:return cancel(document_id,job_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,'Tác vụ không tồn tại trong file này.')


@app.get('/documents/{document_id}/change-plans/{plan_id}')
def read_change_plan(document_id: str,plan_id: str):
    from backend.services.revision_service import safe_id, ensure_changed_targets
    import json
    try:
        file=service.folder(document_id)/'change-plans'/(safe_id(plan_id)+'.json')
        data=json.loads(file.read_text(encoding='utf8'))
        if not data.get('changed_targets'):
            try:
                source=service.folder(document_id)/service.read_status(document_id)['dxf']
                from backend.services.change_service import context_for
                ctx=context_for(source,data.get('targets',[]))
                ensure_changed_targets(data,ctx,data.get('targets',[]))
                service.write_json(file, data)
            except Exception:
                ensure_changed_targets(data,targets=data.get('targets',[]))
        return public_change_plan(data)
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Kế hoạch không tồn tại')


@app.get('/documents/{document_id}/revisions/{revision_id}')
def get_revision(document_id: str,revision_id: str, summary: bool = False):
    from backend.services.revision_service import read_revision
    try:
        result=read_revision(document_id,revision_id)[1]
        # The viewer does not need tens of thousands of raw audit snapshots.
        # Full receipts remain available through the default endpoint.
        if summary:result={k:v for k,v in result.items() if k!='validation'}
        return result
    except (ValueError,FileNotFoundError):raise HTTPException(404,'Revision không tồn tại')


@app.post('/documents/{document_id}/change-plans/{plan_id}/review-process')
def review_process_images(document_id:str,plan_id:str):
    from backend.services.process_vision_service import review_process
    from backend.services.gemini_service import AIError
    try:return review_process(document_id,plan_id)
    except AIError as error:raise HTTPException(error.status,str(error))
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/change-plans/{plan_id}/apply')
def apply_change(document_id: str,plan_id: str,confirmation: DependencyConfirmation | None = None):
    from backend.services.revision_service import apply_plan
    try:
        with CAD_LOCK:return apply_plan(document_id,plan_id,confirmation.confirmed_dependencies if confirmation else [],confirmation.preview_only if confirmation else False)
    except (ValueError,FileNotFoundError) as error:
        import logging; logging.getLogger(__name__).error(f"apply_plan failed: {error}", exc_info=True)
        raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/revisions')
def list_revisions(document_id: str, summary: bool = False):
    import json
    try:
        service.read_status(document_id)
        files=sorted((service.folder(document_id)/'revisions').glob('*/revision.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        rows=[json.loads(p.read_text(encoding='utf8')) for p in files]
        if summary:rows=[dict({k:r[k] for k in ('id','plan_id','status','complete_product_backup','preview_only_reason','root_target_ids','changed_targets') if k in r},document_id=document_id,
                             target_ids=[t['id'] for t in r.get('targets',[])]) for r in rows]
        return {'items':rows}
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,str(error))


@app.post('/documents/{document_id}/change-plans/{plan_id}/apply-checked-preview')
def apply_checked_preview(document_id: str, plan_id: str):
    from backend.services.checked_preview_service import apply
    try:
        with CAD_LOCK:return apply(document_id,plan_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/revisions/{revision_id}/sheets/{sheet_id}/preview')
def get_revision_preview(document_id: str,revision_id: str,sheet_id: str):
    from backend.services.revision_service import revision_preview
    try:
        with CAD_LOCK:content=revision_preview(document_id,revision_id,sheet_id)
        return Response(content,media_type='image/svg+xml',headers={'Cache-Control':'no-cache'})
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/revisions/{revision_id}/approve')
def approve_revision(document_id: str,revision_id: str,confirmation: DependencyConfirmation | None = None):
    from backend.services.revision_service import approve
    try:
        with CAD_LOCK:return approve(document_id,revision_id,confirmation.confirmed_dependencies if confirmation else [])
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/revisions/{revision_id}/materials')
def revision_materials(document_id: str, revision_id: str, root_id: str | None = None):
    from backend.services.comparison_service import material_review
    try:
        with CAD_LOCK:return material_review(document_id,revision_id,root_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/revisions/{revision_id}/sheets/{sheet_id}/comparison')
def revision_comparison(document_id: str, revision_id: str, sheet_id: str,
                        part_number: str | None = None, mode: str = 'overlay', part_code: str | None = None):
    from backend.services.comparison_service import comparison_preview
    try:
        with CAD_LOCK:content=comparison_preview(document_id,revision_id,sheet_id,part_number,mode,part_code)
        return Response(content,media_type='image/svg+xml',headers={'Cache-Control':'no-cache'})
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/revisions/{revision_id}/items/{handle}/preview')
def revision_item_preview(document_id: str,revision_id: str,handle: str):
    from backend.services.revision_service import item_preview
    try:
        with CAD_LOCK:content=item_preview(document_id,revision_id,handle)
        return Response(content,media_type='image/svg+xml',headers={'Cache-Control':'no-cache'})
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/revisions/{revision_id}/export')
def export_revision(document_id: str,revision_id: str,scope: Literal['document','selection']='document'):
    from backend.services.revision_service import export_dwg
    try:
        from backend.services.export_jobs import prepare_aps
        prepare_aps(document_id,revision_id,scope,False)
        with CAD_LOCK:dwg=export_dwg(document_id,revision_id,scope=scope)
        return FileResponse(dwg,filename='drawing-backup-'+revision_id[:8]+'.dwg',media_type='application/octet-stream')
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


class ExportRequest(BaseModel):
    format: Literal['dwg','dxf'] = 'dwg'
    scope: Literal['selection','document'] = 'document'
    preview: bool = True


@app.post('/documents/{document_id}/revisions/{revision_id}/exports', status_code=202)
def start_export_job(document_id: str, revision_id: str, body: ExportRequest):
    from backend.services import export_jobs
    try:return export_jobs.start(document_id,revision_id,**body.model_dump())
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/revisions/{revision_id}/exports')
def list_export_jobs(document_id: str, revision_id: str):
    from backend.services import export_jobs
    try:return export_jobs.list_jobs(document_id,revision_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,str(error))


@app.get('/documents/{document_id}/revisions/{revision_id}/exports/{job_id}')
def export_job_status(document_id: str, revision_id: str, job_id: str):
    from backend.services import export_jobs
    try:return export_jobs.status(document_id,revision_id,job_id)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(404,str(error))


@app.get('/documents/{document_id}/revisions/{revision_id}/exports/{job_id}/download')
def download_export_job(document_id: str, revision_id: str, job_id: str):
    from backend.services import export_jobs
    try:
        path,name=export_jobs.download(document_id,revision_id,job_id)
        return FileResponse(path,filename=name,media_type='application/octet-stream',headers={'Cache-Control':'no-store'})
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/revisions/{revision_id}/export-preview')
def export_revision_preview(document_id: str,revision_id: str,scope: Literal['document','selection']='document'):
    from backend.services.revision_service import export_dwg
    try:
        from backend.services.export_jobs import prepare_aps
        prepare_aps(document_id,revision_id,scope,True)
        with CAD_LOCK:dwg=export_dwg(document_id,revision_id,require_approval=False,scope=scope)
        return FileResponse(dwg,filename='PREVIEW-backup-'+revision_id[:8]+'.dwg',media_type='application/octet-stream')
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/selection')
def select(document_id: str, selection: Selection):
    data = get_catalog(document_id)
    data['items'] = data['items'] + get_sheets(document_id)['items']
    valid = {i['id'] for i in data['items']}
    if not set(selection.ids) <= valid:
        raise HTTPException(400, 'Có đối tượng không thuộc document')
    selected = list(dict.fromkeys(selection.ids))
    service.write_json(service.folder(document_id) / 'selection.json', {'ids': selected})
    return {'ids': selected, 'items': [i for i in data['items'] if i['id'] in selected]}


@app.get('/documents/{document_id}/sheets')
def get_sheets(document_id: str):
    get_catalog(document_id)
    path = service.folder(document_id)
    cache = path / 'sheets-v3.json'
    import json
    from cad.sheets import SHEET_VERSION
    from cad.edit_engine import digest
    source=path / service.read_status(document_id)['dxf']
    fingerprint=digest(source)
    cached=json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {}
    if cached.get('version') != SHEET_VERSION or cached.get('source_hash') != fingerprint:
        try:
            with CAD_LOCK:
                items = discover_sheets(source)
                if cached.get('items') and cached.get('version') is None and source.stat().st_mtime_ns<=cache.stat().st_mtime_ns:
                    from cad.sheets import preserve_legacy_sheets
                    items=preserve_legacy_sheets(cached['items'],items)
            service.write_json(cache, {'items': items,'version':SHEET_VERSION,'source_hash':fingerprint})
        except Exception as error:
            raise HTTPException(422, 'Không nhận diện được khung: ' + str(error))
    result=json.loads(cache.read_text(encoding='utf-8'))
    ex_file=path/'exclusions-v1.json'
    if not ex_file.exists():
        try:
            from backend.services.exclusion_service import exclusions as read_exclusions
            cat_data=get_catalog(document_id)
            read_exclusions(document_id,cat_data.get('items',[]))
        except Exception:
            pass
    regions=json.loads(ex_file.read_text(encoding='utf8'))['regions'] if ex_file.exists() else []
    if regions:
        result['items']=[s for s in result['items'] if not discarded(s['bbox'],s['layout'],regions)]
    return result


@app.get('/documents/{document_id}/sheets/{handle}/preview')
def sheet_preview(document_id: str, handle: str):
    sheet = next((i for i in get_sheets(document_id)['items'] if i['id']==handle), None)
    if sheet is None:
        from backend.services.part_graph_service import document_graph
        sheet=next((s for s in document_graph(document_id).get('linked_details',[]) if s['id']==handle),None)
    if sheet is None:
        raise HTTPException(404,'Khung không tồn tại')
    path = service.folder(document_id)
    source=path/service.read_status(document_id)['dxf']
    from cad.renderer_patch import render_cache_key,cached_svg
    cache = path / ('sheet-render-' + render_cache_key(source,sheet) + '.svg')
    try:
        with CAD_LOCK:content=cached_svg(cache,lambda:render_sheet(source,sheet))
        return Response(content,media_type='image/svg+xml',headers={'Cache-Control':'no-cache'})
    except Exception as error:
        raise HTTPException(422,'Không render được khung: '+str(error))


@app.get('/documents/{document_id}/selection')
def get_selection(document_id: str):
    get_catalog(document_id)
    path = service.folder(document_id) / 'selection.json'
    import json
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'ids': []}


@app.get('/documents/{document_id}/items/{handle}/preview')
def get_preview(document_id: str, handle: str):
    data = get_catalog(document_id)
    if handle not in {i['id'] for i in data['items']}:
        raise HTTPException(404, 'Đối tượng không tồn tại')
    path = service.folder(document_id)
    source=path/service.read_status(document_id)['dxf']
    from cad.renderer_patch import render_cache_key,cached_svg
    cache = path / ('block-render-' + render_cache_key(source,dict(id=handle)) + '.svg')
    try:
        with CAD_LOCK:content=cached_svg(cache,lambda:preview(source,handle))
        return Response(content, media_type='image/svg+xml',headers={'Cache-Control':'no-cache'})
    except Exception as error:
        raise HTTPException(422, 'Không render được đối tượng: ' + str(error))


@app.post('/documents/{document_id}/revisions/{revision_id}/export-dxf')
def export_revision_dxf(document_id: str,revision_id: str,scope: Literal['document','selection']='document'):
    from backend.services.revision_service import export_dxf
    try:
        with CAD_LOCK:output=export_dxf(document_id,revision_id,scope=scope)
        return FileResponse(output,filename='drawing-backup-'+revision_id[:8]+'.dxf')
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.post('/documents/{document_id}/revisions/{revision_id}/export-preview-dxf')
def export_revision_preview_dxf(document_id: str,revision_id: str,scope: Literal['document','selection']='document'):
    from backend.services.revision_service import export_dxf
    try:
        with CAD_LOCK:output=export_dxf(document_id,revision_id,require_approval=False,scope=scope)
        return FileResponse(output,filename='PREVIEW-backup-'+revision_id[:8]+'.dxf')
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/part-graph')
def get_part_graph(document_id: str):
    from backend.services.part_graph_service import document_graph
    try:
        get_catalog(document_id);get_sheets(document_id)
        return document_graph(document_id)
    except FileNotFoundError:raise HTTPException(404,'Document không tồn tại')
    except ValueError as error:raise HTTPException(422,str(error))


@app.get('/documents/{document_id}/row-groups')
def get_row_groups(document_id: str):
    graph=get_part_graph(document_id)
    return dict(document_id=document_id,source_hash=graph['source_hash'],drawing_rows=graph.get('drawing_rows',{}))


@app.get('/documents/{document_id}/block-assembly')
def get_block_assembly_endpoint(document_id: str):
    from backend.services.block_assembly_service import get_block_assembly
    try:
        get_catalog(document_id);get_sheets(document_id)
        return get_block_assembly(document_id)
    except FileNotFoundError:raise HTTPException(404,'Document không tồn tại')
    except ValueError as error:raise HTTPException(422,str(error))


class ProjectAnalyzeRequest(BaseModel):
    document_ids: list[str] | None = None
    request: str


class ProjectPlanRequest(BaseModel):
    document_ids: list[str] | None = None
    request: str


class ProjectApplyRequest(BaseModel):
    project_plan_id: str


@app.get('/project/documents')
def get_project_documents():
    from backend.services import multi_document_service
    return {'items': multi_document_service.list_project_documents()}


@app.post('/project/analyze')
def analyze_project_endpoint(body: ProjectAnalyzeRequest):
    from backend.services import multi_document_service
    if not body.request.strip():
        raise HTTPException(400, 'Yêu cầu không được để trống.')
    return multi_document_service.analyze_project(body.document_ids, body.request.strip())


@app.post('/project/plan')
def plan_project_endpoint(body: ProjectPlanRequest):
    from backend.services import multi_document_service
    if not body.request.strip():
        raise HTTPException(400, 'Yêu cầu không được để trống.')
    return multi_document_service.plan_project_changes(body.document_ids or [], body.request.strip())


@app.post('/project/apply')
def apply_project_endpoint(body: ProjectApplyRequest):
    from backend.services import multi_document_service
    try:
        return multi_document_service.apply_project_changes(body.project_plan_id)
    except Exception as e:
        raise HTTPException(422, str(e))


@app.get('/project/download-archive/{batch_id}')
def download_project_archive(batch_id: str):
    from backend.services import multi_document_service
    try:
        archive_path = multi_document_service.get_project_archive_path(batch_id)
        return FileResponse(archive_path, filename=archive_path.name, media_type='application/zip')
    except Exception as e:
        raise HTTPException(404, str(e))


@app.get('/project-ui.js', include_in_schema=False)
def project_ui_script():
    return FileResponse(Path(__file__).resolve().parents[1] / 'frontend' / 'project-ui.js', media_type='application/javascript')


@app.get('/cad/capabilities')
def cad_capabilities():
    from cad.converter import dwg_enabled
    from backend.services.solid_validation_service import runtime
    import os
    from backend.services.aps_client import status as aps_status
    cloud=aps_status();export_backend=os.getenv('CAD_DWG_BACKEND','oda')
    from backend.services.autocad_host import status as local_status
    local=local_status() if 'autocad' in (export_backend,cloud['read_backend']) else {'configured':False}
    export_ready=cloud['configured'] if export_backend=='aps' else local['configured'] if export_backend=='autocad' else dwg_enabled()
    cloud_enabled=export_backend=='aps' or cloud['read_backend']=='aps'
    return {'dwg_export':export_ready,'dxf_export':True,'local_only':not cloud_enabled,
            'dwg_import':cloud['configured'] if cloud['read_backend']=='aps' else local['configured'] if cloud['read_backend']=='autocad' else dwg_enabled(),
            'read_backend':cloud['read_backend'],'export_backend':export_backend,
            'compound_requests':{'policy':'atomic_all_clauses','saved_plan_recheck':True,
                                 'unsupported_clause':'blocks complete backup; never executes only the first clause'},
            'graphic_schedules':{'readable_columns':[4,5,6],'identity_policy':'no part code synthesized from description or row number'},
            'solid_kernel':{'engine':'FreeCAD/OpenCASCADE','installed':runtime() is not None,'scope':'measured planar profiles with holes, verified part solids and centered section fits; not full assembly reconstruction','planar_checks':['closed valid face','strictly internal nonoverlapping holes','source DIM scale in physical mm'],'policy_version':2},
            'edit_support':['rectangular and notched straight profiles','source-measured LINE/ARC contours and bulged polylines','clamped source NURBS and planar ellipse end curves','identical source definition views including anonymous blocks','circular holes','linear/aligned/radial dimensions','source-bound rounded plate fits','explicit coordinate constraints','measured linear equations','verified BOM template','checked rectangular tube wall'],
            'legacy_polyline':{'supported':'classic 2D POLYLINE with fixed VERTEX/SEQEND sequence; straight/bulged profiles and table grids','preserves':['entity type','vertex handles','widths/bulges','flags','vertex metadata'],'unsupported':['curve-fit/spline-fit','mesh/3D','unhandled native reactors/extensions']},
            'nested_blocks':{'ownership_and_bom_depth_limit':128,'cycle_policy':'explicit error; never silently truncate'},
            'native_contacts':{'scope':'source-owned straight closed profiles, including notches; actual axis-aligned end-face overlap required',
                               'multiple_drivers':'all source anchors must admit one consistent solution',
                               'checks':['actual boundary contact','polygon intersection','source vertex-bound assembly DIM'],
                               'unsupported':['hidden 3D contacts','uncoded or ambiguous ownership','general curve contacts']},
            'insert_motion':{'attributes':'native ATTRIB insertion/alignment points translated in parent WCS/attribute OCS',
                             'definition':'unchanged; no dynamic parameter editing or opaque association reevaluation',
                             'unsupported':['instance/attribute reactors or extension dictionaries','embedded MTEXT attributes']},
            'curved_profiles':{'curves':'native ARC, LWPOLYLINE/POLYLINE bulges, clamped positive-weight SPLINE degree 1-8 and planar ELLIPSE retained',
                               'spline_proof':'clamped quadratic Bezier spans with positive weights; homogeneous circle identity and rigid control-point motion',
                               'nurbs_proof':'exact knot insertion and rational Bezier convex hull locators bounded to 1e-6 drawing units; exact source/modified OCC face checks required',
                               'nurbs_limits':{'max_degree':8,'max_poles':257,'min_normalized_weight':1e-12,'periodic_or_fit_point_only':False},
                               'wall_thickness':'source-owned closed two-arc/six-line section; outer datum fixed; analytic inner boundary and real DIM updates',
                               'wall_planner':'single-part thickness command with confirmed outer datum; exact source closure and BOM required',
                               'forming_gate':'developed blank and bend allowance still require independent manufacturing evidence',
                               'resize':'rigid source end curves and straight bridges parallel to source DIM',
                               'view_sync':'same verified part, complete one-to-one local definition and bound DIM endpoints',
                               'unsupported':['nonrigid general spline/ellipse deformation','periodic/fit-point-only splines','tilted ellipse planes','inferred perspective projection','unproven assembly contacts','bend allowance without source rules']},
            'packaging':{'scope':'exact product code and packaging purpose; carton, foam, corner protectors and pallet',
                         'automatic':'source-measured native planar rectangular carton/product and foam pad fits',
                         'preserves':['individual source clearances','foam thickness/material','unmodified pallet dimensions'],
                         'unmapped':'incomplete packaging blocks final backup approval'},
            'message':('DWG dùng Autodesk APS; file được gửi lên cloud khi đọc/xuất.' if cloud['configured'] else cloud['message']) if cloud_enabled else local.get('message','AutoCAD xử lý DWG trên máy.') if 'autocad' in (export_backend,cloud['read_backend']) else ('DWG được chuyển đổi và kiểm tra lại trên máy.' if dwg_enabled() else 'Chưa bật bộ chuyển đổi DWG nội bộ; có thể xuất DXF.')}


if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time
    import os
    import subprocess

    # Tự động giải phóng cổng 8765 nếu có tiến trình cũ đang chiếm giữ
    try:
        out = subprocess.check_output('netstat -ano', shell=True).decode()
        current_pid = str(os.getpid())
        for line in out.splitlines():
            if ':8765 ' in line and 'LISTENING' in line:
                pid = line.strip().split()[-1]
                if pid != current_pid and pid != '0':
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                    time.sleep(0.5)
    except Exception:
        pass

    def _open():
        time.sleep(1.2)
        webbrowser.open("http://127.0.0.1:8765/")

    threading.Thread(target=_open, daemon=True).start()
    print("===================================================")
    print("  Mechanical AI Drawing is running at:")
    print("  http://127.0.0.1:8765/")
    print("  (Press Ctrl+C to stop server)")
    uvicorn.run(app, host="0.0.0.0", port=8765, proxy_headers=True, forwarded_allow_ips="*")
