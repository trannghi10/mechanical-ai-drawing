# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.abspath('.'))

from backend.services.document_request_service import prepare, resolve, _candidate
from backend.services.change_service import plan_change
from backend.services.sheet_thickness_planner import command as sheet_command

doc_id = '34ee84f35e1a44fb81c56044397a0fff'
val, jid = prepare(doc_id)
req = 'Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm'

# Monkey patch or test resolve logic
from bom.reader import normalized
import re
from backend.services.tube_planner import intent as tube_intent

t_intent = tube_intent(req)
is_batch = bool(sheet_command(req) or t_intent or re.search(r'\b(?:tat ca|toan bo|dong loat)\b', normalized(req)))
print('is_batch:', is_batch)

# If we get matches from resolve
parts = val['parts']
req_norm = normalized(req).replace(',', '.')
dim_candidates = re.findall(r'(?:tu|chieu\s+dai|dai|rong|cao|kich\s+thuoc|day)?\s*(\d+(?:\.\d+)?)\s*(?:mm\b|\s*(?:thanh|sang|len|xuong|con))', req_norm)
target_val = float(dim_candidates[0])
by_spec = []
for p in parts:
    for d in p.get('descriptions', []):
        d_norm = normalized(d).replace(',', '.')
        d_nums = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)', d_norm) if x]
        if any(abs(dn - target_val) < 1e-5 for dn in d_nums):
            if p not in by_spec:
                by_spec.append(p)

print('by_spec matches count:', len(by_spec))

frames = {f['id']: f for f in val['frames']}
targets = []
for p in by_spec:
    ids = (p.get('detail_sheet_ids', []) or []) + [f['id'] for f in p.get('frames', [])]
    for sid in ids:
        if sid in frames and frames[sid]['id'] not in {t['id'] for t in targets}:
            targets.append(frames[sid])

print('targets count:', len(targets))

# Now run plan_change!
print('Running plan_change with targets and req...')
plan = plan_change(doc_id, targets, req)
print('plan summary:', plan.get('summary'))
print('plan edits:', len(plan.get('edits', [])))
print('plan operations:', len(plan.get('operations', [])))
print('plan questions:', plan.get('questions'))
