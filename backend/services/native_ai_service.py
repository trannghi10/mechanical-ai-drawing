"""Offline llama.cpp vision runtime. All CAD remains on loopback."""
import os
import asyncio
import time
from urllib.parse import urlsplit
import httpx
from backend.services.gemini_service import AIError


class ContextBudgetExceeded(AIError):
    """A view can be repaged; never increase the runtime slot or drop source."""
    pass


STARTUP_TIMEOUT=60


def start_for_request(base):
    """Start only the installed pinned loopback runtime, never another model."""
    from backend.services.local_runtime_service import start
    if base!=settings()[0]:raise AIError(503,'Địa chỉ AI đã đổi; hãy phân tích lại yêu cầu.')
    from backend.services.planning_control import progress,remaining
    remaining();progress('runtime','AI nội bộ chưa chạy; đang khởi động model trên máy. Có thể hủy phân tích.')
    try:return start()
    except (ValueError,OSError) as error:raise AIError(503,'Không khởi động được AI nội bộ: '+str(error)) from error


def startup_wait(deadline):
    from backend.services.planning_control import remaining
    left=min(deadline-time.monotonic(),remaining())
    if left<=0:raise AIError(503,'AI nội bộ chưa nạp xong sau 60 giây. Kiểm tra storage/runtime/native.stderr.log rồi bấm Khởi động AI; chưa gửi CAD cho model.')
    return min(.25,left)


def inspect_ready_model(client,base):
    from backend.services.planning_control import remaining,progress
    deadline=time.monotonic()+min(STARTUP_TIMEOUT,remaining());started=False;notified=False
    while True:
        try:return inspect_model(client,base)
        except httpx.ConnectError:
            if not started:start_for_request(base);started=True
        except AIError as error:
            if error.status!=503 or 'nạp model' not in str(error):raise
            if not notified:progress('runtime','Đang nạp AI nội bộ trên máy; chưa gửi CAD cho model.');notified=True
        time.sleep(startup_wait(deadline))


async def inspect_ready_model_async(client,base):
    from backend.services.planning_control import remaining,progress
    deadline=time.monotonic()+min(STARTUP_TIMEOUT,remaining());started=False;notified=False
    while True:
        try:
            health=await client.get(base+'/health',timeout=5)
            if health.status_code!=200:raise AIError(503,'AI nội bộ đang nạp model hoặc chưa chạy.')
            props=await client.get(base+'/props',timeout=5)
            if props.status_code!=200:raise AIError(503,'Không đọc được cấu hình AI nội bộ.')
            return check_model(props.json())
        except httpx.ConnectError:
            if not started:await asyncio.to_thread(start_for_request,base);started=True
        except AIError as error:
            if error.status!=503 or 'nạp model' not in str(error):raise
            if not notified:progress('runtime','Đang nạp AI nội bộ trên máy; chưa gửi CAD cho model.');notified=True
        await asyncio.sleep(startup_wait(deadline))


def settings():
    base=os.environ.get('LOCAL_AI_BASE_URL','http://127.0.0.1:11436').rstrip('/')
    u=urlsplit(base)
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError('AI nội bộ chỉ được kết nối localhost.')
    return base,'qwen3-vl:4b-instruct'


def inspect_model(client,base):
    health=client.get(base+'/health',timeout=5)
    if health.status_code!=200:raise AIError(503,'AI nội bộ đang nạp model hoặc chưa chạy.')
    r=client.get(base+'/props',timeout=5)
    if r.status_code!=200:raise AIError(503,'Không đọc được cấu hình AI nội bộ.')
    d=r.json()
    return check_model(d)


def check_model(d):
    if not d.get('modalities',{}).get('vision'):raise AIError(422,'Model nội bộ không hỗ trợ đọc ảnh.')
    # This launcher uses a pinned local model file, never a remote URL.
    from backend.services.local_runtime_service import MODEL_FILES
    if str(d.get('model_path','')).replace('\\','/').rsplit('/',1)[-1] not in MODEL_FILES:
        raise AIError(403,'Runtime không dùng đúng model nội bộ đã kiểm tra; đã chặn CAD.')
    return d


def status():
    base,model=settings()
    try:
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=5) as c:inspect_model(c,base)
        return dict(provider='native',model=model,local_only=True,ready=True,state='ready',message='AI đọc ảnh chạy nội bộ trên máy; không gửi CAD ra ngoài.')
    except AIError as error:
        loading='nạp model' in str(error)
        return dict(provider='native',model=model,local_only=True,ready=False,state='loading' if loading else 'blocked',message=str(error))
    except (httpx.RequestError,ValueError):
        from backend.services.local_runtime_service import installed_files
        try:
            installed_files()
            message='AI nội bộ chưa chạy; sẽ tự khởi động khi phân tích. Có thể bấm Khởi động AI để nạp trước.'
        except ValueError as error:message=str(error)
        return dict(provider='native',model=model,local_only=True,ready=False,state='stopped',message=message)


def generate_plan(prompt,parts,schema):
    base,_=settings();content=[]
    for part in parts:
        if 'text' in part:content.append(dict(type='text',text=part['text']))
        elif 'inlineData' in part and part['inlineData'].get('mimeType')=='image/png':
            content.append(dict(type='image_url',image_url=dict(url='data:image/png;base64,'+part['inlineData']['data'])))
        else:raise ValueError('AI nội bộ chỉ nhận text và ảnh PNG tạo từ CAD.')
    body={'messages':[dict(role='system',content=prompt),dict(role='user',content=content)],
          'temperature':0,'stream':False,'chat_template_kwargs':{'enable_thinking':False},
          'response_format':{'type':'json_object','schema':schema.model_json_schema()}}
    from backend.services.planning_control import CURRENT,remaining,progress
    control=CURRENT.get()
    if control:
        return asyncio.run(control.run(generate_async(base,body,schema)))
    try:
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(remaining(),connect=5)) as c:
            props=inspect_ready_model(c,base)
            count=c.post(base+'/v1/chat/completions/input_tokens',json=body)
            if count.status_code!=200:raise AIError(422,'Không kiểm tra được độ dài phạm vi CAD; chưa tạo bản sửa.')
            n=count.json().get('input_tokens')
            token_budget(body,n,props)
            r=c.post(base+'/v1/chat/completions',json=body)
    except httpx.TimeoutException as e:raise AIError(504,'AI nội bộ quá thời gian xử lý trên CPU; chưa tạo bản sửa.') from e
    except httpx.RequestError as e:raise AIError(503,'Không kết nối được AI nội bộ; không chuyển sang cloud.') from e
    return parse_response(r,schema)


def token_budget(body,n,props):
    # Match the running slot, not just an environment value from an older
    # 32k launcher. Context overflow and CPU overload are distinct checks.
    budget=min(8192,int(os.environ.get('LOCAL_AI_NUM_CTX','8192')))
    actual=props.get('default_generation_settings',{}).get('n_ctx')
    if isinstance(actual,int) and actual>0:budget=min(budget,actual)
    if not isinstance(n,int) or n<0 or n+512>=budget:
        raise ContextBudgetExceeded(422,f'Phạm vi CAD ({n} tokens) vượt bộ nhớ model nội bộ ({budget}); cần chia trang dữ liệu trước khi phân tích.')
    env_max = int(os.environ.get('LOCAL_AI_MAX_INPUT_TOKENS', '7168'))
    ceiling = min(budget - 512, max(512, env_max))
    if n > ceiling:
        raise ContextBudgetExceeded(422, f'Phạm vi phân tích gồm {n} tokens, vượt ngân sách CPU {ceiling}; cần chia trang dữ liệu trước khi phân tích.')
    body['max_tokens'] = min(2048, budget - n - 256)


async def generate_async(base,body,schema):
    from backend.services.planning_control import remaining,progress
    try:
        async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(remaining(),connect=5)) as c:
            data=await inspect_ready_model_async(c,base)
            count=await c.post(base+'/v1/chat/completions/input_tokens',json=body)
            if count.status_code!=200:raise AIError(422,'Không kiểm tra được độ dài phạm vi CAD; chưa tạo bản sửa.')
            n=count.json().get('input_tokens')
            progress('budget','Đang kiểm tra ngân sách CPU trước khi gọi AI.',input_tokens=n)
            token_budget(body,n,data)
            progress('model',f'AI nội bộ đang phân tích {n} tokens; có thể hủy hoặc tải lại trang.',input_tokens=n)
            r=await c.post(base+'/v1/chat/completions',json=body,timeout=remaining())
            return parse_response(r,schema)
    except (httpx.TimeoutException,asyncio.TimeoutError) as e:raise AIError(504,'AI nội bộ đã hết ngân sách thời gian; chưa tạo bản sửa.') from e
    except httpx.RequestError as e:raise AIError(503,'Không kết nối được AI nội bộ; không chuyển sang cloud.') from e


def parse_response(r,schema):
    if r.status_code!=200:raise AIError(422,'Runtime nội bộ từ chối yêu cầu; chưa tạo bản sửa.')
    try:
        choice=r.json()['choices'][0]
        if choice.get('finish_reason')!='stop':raise ValueError('AI trả kế hoạch chưa đầy đủ; chưa tạo bản sửa.')
        return schema.model_validate_json(choice['message']['content'])
    except (KeyError,IndexError,TypeError) as e:raise ValueError('AI trả kế hoạch không hợp lệ; chưa tạo bản sửa.') from e
