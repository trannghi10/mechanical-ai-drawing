import sys
sys.path.insert(0, '.')
from pathlib import Path
from backend.services.catalog_service import read_status
from cad.sheets import discover_sheets
from backend.services.change_service import plan_change

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
status = read_status(doc_id)
source = Path('storage/documents') / doc_id / status['dxf']
targets = discover_sheets(source)
request_text = "Mã 8.1.00499.008: đổi chi tiết số 6 481.5mm thành 480mm"

res = plan_change(doc_id, targets, request_text)
plan = res.get('plan') or {}
ops = plan.get('operations', [])

with open('scratch/plan_output.txt', 'w', encoding='utf8') as f:
    f.write(f"Status: {res.get('status')}\n")
    f.write(f"Plan summary: {plan.get('summary')}\n")
    f.write(f"Total operations in plan: {len(ops)}\n")
    for i, op in enumerate(ops):
        ref = getattr(op, 'ref', None) or (op.get('ref') if isinstance(op, dict) else '')
        action = getattr(op, 'action', None) or (op.get('action') if isinstance(op, dict) else '')
        reason = getattr(op, 'reason', None) or (op.get('reason') if isinstance(op, dict) else '')
        f.write(f"[{i+1}] ref={ref} action={action} reason={reason}\n")
print("Done writing to scratch/plan_output.txt")
