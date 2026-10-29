import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from backend.services.catalog_service import read_status
from backend.services.change_service import context_for, plan as plan_service

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
status = read_status(doc_id)
source = Path(status['dxf'])
targets = status['targets']
request_text = "đổi chi tiết số 6 481.5mm thành 480mm"

res = plan_service(doc_id, request_text)
plan = res.get('plan')
ops = plan.get('operations', [])
print(f"Total operations in plan: {len(ops)}")
for i, op in enumerate(ops):
    ref = getattr(op, 'ref', None) or op.get('ref')
    action = getattr(op, 'action', None) or op.get('action')
    before = getattr(op, 'before', None) or op.get('before')
    after = getattr(op, 'after', None) or op.get('after')
    reason = getattr(op, 'reason', None) or op.get('reason')
    print(f"[{i+1}] ref={ref} action={action}")
    print(f"     reason: {reason}")
    if action in ('replace_geometry', 'line_end'):
        print(f"     before: {before[:80] if before else ''}")
        print(f"     after:  {after[:80] if after else ''}")
    else:
        print(f"     before: {before}")
        print(f"     after:  {after}")
