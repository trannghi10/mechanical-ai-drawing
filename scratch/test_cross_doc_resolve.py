import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json, time
from pathlib import Path
from backend.services.document_request_service import resolve_request

doc_dir = Path('storage/documents')
req = "đổi chi tiết số 6 481.5mm thành 480mm"
print(f"Searching for request across documents: '{req}'")

matched = []
for d in doc_dir.iterdir():
    status_file = d / 'status.json'
    if not (d.is_dir() and status_file.exists()): continue
    try:
        st = json.loads(status_file.read_text(encoding='utf-8'))
        if st.get('status') != 'ready': continue
        res = resolve_request(d.name, req)
        if res.get('status') == 'resolved':
            matched.append({
                'id': d.name,
                'filename': st.get('filename'),
                'targets': len(res.get('targets', [])),
                'part_codes': res.get('part_codes', [])
            })
    except Exception as e:
        pass

print(f"Matched {len(matched)} documents:")
for m in matched:
    print(f"  [{m['id'][:8]}] {m['filename']}: targets={m['targets']}, parts={m['part_codes']}")
