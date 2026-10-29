"""OpenAI Responses adapter for vision and validated CAD plans."""
import os
import re
import httpx
from backend.services.gemini_service import AIError


def settings():
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if not key or key=='replace_with_your_api_key':
        raise ValueError('Chưa cấu hình OPENAI_API_KEY hợp lệ trong .env trên server')
    model=os.environ.get('OPENAI_MODEL','gpt-6-astra').strip()
    if not re.fullmatch(r'gpt-[A-Za-z0-9._-]+',model):
        raise ValueError('OPENAI_MODEL không hợp lệ')
    return key,model


def strict_schema(value):
    if isinstance(value,list):return [strict_schema(item) for item in value]
    if not isinstance(value,dict):return value
    result={key:strict_schema(item) for key,item in value.items() if key!='default'}
    if result.get('type')=='object' or 'properties' in result:
        result['additionalProperties']=False
        result['required']=list(result.get('properties',{}))
    return result


def generate_plan(prompt,parts,schema):
    if os.environ.get('AI_OFFLINE','1').lower() not in ('0','false','no'):
        raise ValueError('Chế độ nội bộ đang bật; đã chặn gửi dữ liệu đến OpenAI.')
    key,model=settings()
    content=[]
    for part in parts:
        if 'text' in part:content.append({'type':'input_text','text':part['text']})
        elif 'inlineData' in part:
            data=part['inlineData']
            if data.get('mimeType') not in ('image/png','image/jpeg','image/webp'):
                raise ValueError('Định dạng ảnh CAD không được hỗ trợ')
            content.append({'type':'input_image','image_url':f"data:{data['mimeType']};base64,{data['data']}",'detail':'high'})
        else:raise ValueError('Nội dung CAD gửi đến OpenAI không hợp lệ')
    body={'model':model,'instructions':prompt,'input':[{'role':'user','content':content}],
          'store':False,'truncation':'disabled','reasoning':{'effort':'high'},'max_output_tokens':32768,
          'text':{'format':{'type':'json_schema','name':'cad_change_plan','strict':True,
                            'schema':strict_schema(schema.model_json_schema())}}}
    try:
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(600,connect=20)) as client:
            response=client.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {key}'},json=body)
    except httpx.TimeoutException as error:
        raise AIError(504,'OpenAI hết thời gian chờ. Chưa tạo bản sửa; thử lại sau.') from error
    except httpx.RequestError as error:
        raise AIError(502,'Không kết nối được OpenAI. Kiểm tra mạng trên server.') from error
    if response.status_code!=200:
        messages={400:'OpenAI từ chối cấu hình model hoặc schema yêu cầu.',401:'OPENAI_API_KEY không hợp lệ; cập nhật .env trên server.',
                  403:'OpenAI từ chối quyền truy cập model.',404:'Không tìm thấy model OpenAI hoặc tài khoản chưa có quyền sử dụng.',
                  429:'OpenAI hết hạn mức hoặc vượt giới hạn tốc độ. Kiểm tra tài khoản API.',
                  500:'OpenAI gặp lỗi xử lý; thử lại sau.',503:'OpenAI tạm không khả dụng; thử lại sau.'}
        raise AIError(response.status_code if response.status_code in messages else 502,messages.get(response.status_code,'OpenAI không xử lý được yêu cầu. Chưa tạo bản sửa.'))
    try:
        data=response.json()
        if data.get('status')!='completed' or data.get('error') or data.get('incomplete_details'):
            raise ValueError('OpenAI chưa trả kế hoạch đầy đủ. Chưa tạo bản sửa.')
        output=[]
        for item in data.get('output',[]):
            if item.get('type')!='message':continue
            for item_content in item.get('content',[]):
                if item_content.get('type')=='refusal':raise ValueError('OpenAI từ chối phân tích. Chưa tạo bản sửa.')
                if item_content.get('type')=='output_text':output.append(item_content['text'])
        return schema.model_validate_json(''.join(output))
    except (KeyError,TypeError) as error:
        raise ValueError('OpenAI trả dữ liệu không hợp lệ. Chưa tạo bản sửa.') from error
