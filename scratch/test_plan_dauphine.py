# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.abspath('.'))

from backend.services.change_service import plan_change
from backend.services import catalog_service as storage
from backend.main import get_sheets

doc_id = '34ee84f35e1a44fb81c56044397a0fff'
sheets = get_sheets(doc_id)['items']
req = 'Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm'

plan = plan_change(doc_id, sheets, req)
with open(r'd:\mechanical-ai-drawing\scratch\dauphine_plan.json', 'w', encoding='utf-8') as f:
    json.dump(plan, f, ensure_ascii=False, indent=2, default=str)

print('Saved dauphine_plan.json')
