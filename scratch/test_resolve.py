import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
from backend.services.document_request_service import resolve_request

doc_id = '8565af68196b40a6acc853d9d9eead87'
req = 'đổi chiều dài từ 1115mm thành 1110mm'

res = resolve_request(doc_id, req)
print('STATUS:', res['status'])
print('MESSAGE:', res.get('message'))
print('CANDIDATES:', res.get('candidates'))
