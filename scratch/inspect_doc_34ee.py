# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.abspath('.'))

from backend.services.document_request_service import prepare, resolve
from bom.reader import normalized

doc_id = '34ee84f35e1a44fb81c56044397a0fff'
val, jid = prepare(doc_id)
req = 'Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm'
res = resolve(val, jid, req)

parts = val['parts']
sheet_parts = []
for p in parts:
    descs = p.get('descriptions', [])
    for d in descs:
        if '1.5' in d or 'sat tam' in normalized(d):
            sheet_parts.append({'code': p['part_code'], 'desc': d})

result_data = {
    'status': res['status'],
    'message': res.get('message'),
    'total_parts': len(parts),
    'sheet_parts_count': len(sheet_parts),
    'sheet_parts': sheet_parts
}

with open(r'd:\mechanical-ai-drawing\scratch\doc_34ee_result.json', 'w', encoding='utf-8') as f:
    json.dump(result_data, f, ensure_ascii=False, indent=2)

print('Done!')
