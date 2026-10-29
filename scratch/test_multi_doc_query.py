import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json, time
from pathlib import Path
from backend.services import document_atlas_service as atlas
from backend.services.document_request_service import resolve

doc_dir = Path('storage/documents')

# Let's test 3 representative documents
test_docs = [
    '5a1955b75d4345b69d19d38b7cfaf75c',  # HW-09-042L-PBL (has Ct6 481.5mm)
    '34ee84f35e1a44fb81c56044397a0fff',  # Dauphine 32 rnd
    'baf461e9f19e4871aa9bf31a7c5c00e5',  # LEG6949
]

req = "đổi chi tiết số 6 481.5mm thành 480mm"
print(f"Testing Multi-DWG analysis for: '{req}'")

for doc_id in test_docs:
    path = doc_dir / doc_id
    st = json.loads((path / 'status.json').read_text(encoding='utf-8'))
    fname = st.get('filename')
    try:
        job = atlas.submit(doc_id)
        # wait ready
        for _ in range(20):
            rep = atlas.read(doc_id, job['id'])
            if rep['status'] in ('ready', 'failed'): break
            time.sleep(0.1)
        if rep['status'] == 'ready':
            data = atlas.report(doc_id, job['id'])
            res = resolve(data, job['id'], req)
            status = res.get('status')
            msg = res.get('message', '')
            print(f"-> [{doc_id[:8]}] {fname}: {status} - {msg}")
        else:
            print(f"-> [{doc_id[:8]}] {fname}: atlas {rep['status']}")
    except Exception as e:
        print(f"-> [{doc_id[:8]}] {fname}: error {e}")
