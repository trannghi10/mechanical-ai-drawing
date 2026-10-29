# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.abspath('.'))

from backend.services.document_request_service import prepare, resolve

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
val, jid = prepare(doc_id)
req = 'Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm'
res = resolve(val, jid, req)

output = {
    'status': res['status'],
    'message': res.get('message'),
    'part_codes': res.get('part_codes'),
    'targets_count': len(res.get('targets', [])),
    'candidates_count': len(res.get('candidates', []))
}

with open(r'd:\mechanical-ai-drawing\scratch\resolve_output.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print('Saved to resolve_output.json')
