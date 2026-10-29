"""Local vision + structured planning; never redirect or use a remote model."""
import os
import re
from urllib.parse import urlsplit
import httpx
from backend.services.gemini_service import AIError


def settings():
    base=os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11435').strip().rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','::1','localhost') or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('AI nội bộ chỉ được kết nối địa chỉ localhost; không cho phép URL bên ngoài.')
    model=os.environ.get('OLLAMA_MODEL','qwen3-vl:4b-instruct').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.:/-]+',model) or 'cloud' in model.lower() or '/' in model:
        raise ValueError('Chỉ dùng tên model đã cài trên máy; không dùng model cloud/registry từ xa.')
    return base,model


def inspect_model(client,base,model):
    response=client.post(base+'/api/show',json={'model':model})
    if response.status_code==404:raise AIError(503,'Model AI nội bộ chưa được cài trên máy.')
    if response.status_code!=200:raise AIError(503,'Không đọc được cấu hình model AI nội bộ.')
    data=response.json()
    if data.get('remote_host') or data.get('remote_model'):
        raise AIError(403,'Model trỏ đến máy chủ từ xa; đã chặn gửi dữ liệu CAD.')
    if 'vision' not in data.get('capabilities',[]):
        raise AIError(422,'Model nội bộ không hỗ trợ đọc ảnh CAD. Cần model có vision.')
    return data


def status():
    base,model=settings()
    try:
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=5) as client:
            inspect_model(client,base,model)
        return {'provider':'ollama','model':model,'local_only':True,'ready':True,'message':'AI đọc ảnh chạy trên máy; không gửi CAD đến Gemini.'}
    except (httpx.RequestError,AIError,ValueError) as error:
        message=str(error) if isinstance(error,AIError) else 'Chưa kết nối được AI nội bộ. Chạy start-local-ai.ps1.'
        return {'provider':'ollama','model':model,'local_only':True,'ready':False,'message':message}


def generate_plan(prompt,parts,schema):
    base,model=settings()
    content=[];images=[]
    for part in parts:
        if 'text' in part:content.append(part['text'])
        elif 'inlineData' in part:
            if part['inlineData'].get('mimeType')!='image/png':raise ValueError('AI nội bộ chỉ nhận preview PNG được tạo từ CAD.')
            images.append(part['inlineData']['data'])
        else:raise ValueError('Loại nội dung AI không được hỗ trợ')
    try:
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(900,connect=5)) as client:
            inspect_model(client,base,model)  # Inspect before sending ANY CAD data.
            body={'model':model,'stream':False,'think':False,'truncate':False,'shift':False,
                  'messages':[{'role':'system','content':prompt},
                              {'role':'user','content':'\n'.join(content),'images':images}],
                  'format':schema.model_json_schema(),
                  'options':{'temperature':0,'use_mmap':True,'num_ctx':int(os.environ.get('OLLAMA_NUM_CTX','16384')),
                             'num_predict':int(os.environ.get('OLLAMA_NUM_PREDICT','8192'))},'keep_alive':'10m'}
            response=client.post(base+'/api/chat',json=body)
    except httpx.TimeoutException as error:
        raise AIError(504,'AI nội bộ quá thời gian xử lý; chưa tạo bản sửa. CPU có thể chậm với bản vẽ lớn.') from error
    except httpx.RequestError as error:
        raise AIError(503,'Không kết nối được AI nội bộ. Chạy start-local-ai.ps1; không chuyển sang Gemini.') from error
    if response.status_code!=200:
        if response.status_code==400:
            raise AIError(422,'AI nội bộ từ chối yêu cầu hoặc phạm vi vượt context. Không cắt bỏ dữ liệu CAD; chưa tạo bản sửa.')
        raise AIError(503,'AI nội bộ không xử lý được yêu cầu; không chuyển dữ liệu sang dịch vụ khác.')
    try:
        data=response.json()
        if data.get('done') is not True or data.get('done_reason')!='stop':
            raise ValueError('AI nội bộ chưa trả kế hoạch đầy đủ; chưa tạo bản sửa.')
        return schema.model_validate_json(data['message']['content'])
    except (KeyError,TypeError) as error:
        raise ValueError('AI nội bộ trả dữ liệu không hợp lệ; chưa tạo bản sửa.') from error
