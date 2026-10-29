import sys
sys.path.insert(0, 'd:/mechanical-ai-drawing')
from backend.services.compound_planner import compile_bundle, checked_one
from backend.services.change_service import context_for
from backend.services import catalog_service as storage
import json

doc_id = 'baf461e9c2764a5ba9000a48772f846c'
folder = storage.folder(doc_id)
source = folder / storage.read_status(doc_id)['dxf']
sheet_cache = folder / 'sheets-v3.json'
sheets = json.loads(sheet_cache.read_text(encoding='utf-8'))['items']

requests = [
    'thay doi chieu dai chi tiet 6 thanh 600mm giu nguyen dau trai',
    'thay doi chieu dai chi tiet 5 thanh 500mm',
    'thay doi hop 30x60 thanh hop 30x50',
    'doi tam day 2mm thanh 1.5mm',
    'thay doi kich thuoc 571.5 thanh 600mm'
]

target = next(s for s in sheets if s['id'] == '43BAB5')
ctx = context_for(source, [target])

for req in requests:
    plan, review = compile_bundle(ctx, req, None)
    one, planner = checked_one(ctx, req, None)
    print(f'Req: "{req}"')
    print(f'  compile_bundle: plan={bool(plan)}, review={review}')
    print(f'  checked_one: plan={bool(one)}, planner={planner}')
