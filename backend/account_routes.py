from pathlib import Path
from fastapi import APIRouter,HTTPException,Request,Response
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ConfigDict
from typing import Literal
from backend.services import account_service as accounts

router=APIRouter()
ROOT=Path(__file__).resolve().parents[1]/'frontend'


class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(min_length=1,max_length=64)
    password:str=Field(min_length=1,max_length=128)


class NewUser(Credentials):
    display_name:str=Field(min_length=1,max_length=120)
    role:Literal['viewer','operator','engineer','admin']='viewer'


class UserUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    role:Literal['viewer','operator','engineer','admin']
    active:bool
    password:str|None=Field(default=None,min_length=12,max_length=128)


class PasswordChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    old_password:str=Field(min_length=1,max_length=128)
    new_password:str=Field(min_length=12,max_length=128)


def execute(function,*args):
    try:return function(*args)
    except accounts.AccountError as error:raise HTTPException(error.status,str(error))
    except Exception:raise HTTPException(503,'Không truy cập được dữ liệu tài khoản. Kiểm tra database trên máy chủ.') from None


def actor(request,admin=False):
    user=getattr(request.state,'actor',None)
    if not user:raise HTTPException(401,'Cần đăng nhập.')
    if admin and user['role']!='admin':raise HTTPException(403,'Chức năng dành cho quản trị viên.')
    return user


def cookie(response,token,request):
    response.set_cookie(accounts.COOKIE,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=accounts.SESSION_SECONDS,path='/')
    response.headers['Cache-Control']='no-store'


@router.get('/login',include_in_schema=False)
@router.get('/accounts',include_in_schema=False)
def page():return FileResponse(ROOT/'accounts.html',headers={'Cache-Control':'no-store'})


@router.get('/accounts.js',include_in_schema=False)
def script():return FileResponse(ROOT/'accounts.js',media_type='application/javascript')


@router.get('/auth/status')
def status(request:Request,response:Response):
    response.headers['Cache-Control']='no-store'
    return execute(accounts.status,request.cookies.get(accounts.COOKIE))


@router.post('/auth/setup',status_code=201)
def setup(body:NewUser,request:Request,response:Response):
    if body.role!='admin':raise HTTPException(422,'Tài khoản đầu tiên phải là quản trị viên.')
    user,token=execute(accounts.setup,body.username,body.display_name,body.password)
    cookie(response,token,request)
    return dict(user=user)


@router.post('/auth/login')
def login(body:Credentials,request:Request,response:Response):
    user,token=execute(accounts.login,body.username,body.password,request.client.host)
    cookie(response,token,request)
    return dict(user=user)


@router.post('/auth/logout')
def logout(request:Request,response:Response):
    execute(accounts.logout,request.cookies.get(accounts.COOKIE));response.delete_cookie(accounts.COOKIE,path='/')
    response.headers['Cache-Control']='no-store'
    return dict(logged_out=True)


@router.post('/auth/password')
def password(body:PasswordChange,request:Request,response:Response):
    token=execute(accounts.change_password,actor(request),body.old_password,body.new_password)
    cookie(response,token,request)
    return dict(changed=True)


@router.get('/auth/users')
def users(request:Request):actor(request,True);return dict(items=execute(accounts.users))


@router.post('/auth/users',status_code=201)
def create(body:NewUser,request:Request):
    actor(request,True)
    return execute(accounts.create_user,body.username,body.display_name,body.password,body.role)


@router.patch('/auth/users/{user_id}')
def update(user_id:str,body:UserUpdate,request:Request):
    actor(request,True);execute(accounts.update_user,user_id,body.role,body.active,body.password)
    return dict(updated=True)


@router.get('/auth/audit')
def audit(request:Request,limit:int=100):
    actor(request,True)
    if not 1<=limit<=200:raise HTTPException(422,'Giới hạn từ 1 đến 200 bản ghi.')
    return dict(items=execute(accounts.audit_rows,limit))
