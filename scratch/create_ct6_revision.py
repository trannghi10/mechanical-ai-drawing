import sys
sys.path.insert(0, '.')
import json
from pathlib import Path
from backend.services.catalog_service import read_status, write_json, folder
from cad.sheets import discover_sheets
from backend.services.change_service import plan_change
from backend.services.revision_service import apply_plan, safe_id

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
status = read_status(doc_id)
source = Path('storage/documents') / doc_id / status['dxf']
targets = discover_sheets(source)
request_text = "Mã 8.1.00499.008: đổi chi tiết số 6 481.5mm thành 480mm"

print("1. Planning change...")
res = plan_change(doc_id, targets, request_text)
plan_id = res['id']
print(f"Plan ID: {plan_id}, operations count: {len(res['plan']['operations'])}")

# Save proposal to disk so apply_plan can read it
proposal_path = folder(doc_id) / 'change-plans' / f"{safe_id(plan_id)}.json"
proposal_path.parent.mkdir(exist_ok=True)
write_json(proposal_path, res)

print("2. Applying plan to create revision...")
rev = apply_plan(doc_id, plan_id, preview_only=False)
rev_id = rev['id']
print(f"SUCCESS! Created Revision ID: {rev_id}")
print(f"Status: {rev.get('status')}")
print(f"Validation changes count: {len(rev.get('validation', {}).get('changes', []))}")

with open('scratch/created_revision.json', 'w', encoding='utf8') as f:
    json.dump({'revision_id': rev_id, 'plan_id': plan_id}, f)
