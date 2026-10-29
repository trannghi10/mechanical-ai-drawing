import sys
sys.path.insert(0, '.')
from pathlib import Path
import json
from backend.services.catalog_service import read_status
from cad.sheets import discover_sheets
from backend.services.change_service import plan_change
from cad.edit_engine import apply_patch, Operation
from backend.services.revision_service import digest

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
status = read_status(doc_id)
source = Path('storage/documents') / doc_id / status['dxf']
targets = discover_sheets(source)
request_text = "Mã 8.1.00499.008: đổi chi tiết số 6 481.5mm thành 480mm"

res = plan_change(doc_id, targets, request_text)
plan = res.get('plan') or {}
ops = [Operation.model_validate(o) for o in plan.get('operations', [])]
allowed_refs = {o.ref for o in ops}
source_hash = digest(source)
test_dest = Path('scratch/test_revision_apply.dxf')

print(f"Trying to apply {len(ops)} operations...")
try:
    report = apply_patch(source, test_dest, ops, allowed_refs, source_hash)
    print("SUCCESS! Output hash:", report.get('output_hash'))
except Exception as e:
    print("FAILED with error:", type(e), e)
