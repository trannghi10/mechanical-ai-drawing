import json, time
from pathlib import Path

doc_dir = Path('storage/documents')
t0 = time.time()
scanned = []

for d in doc_dir.iterdir():
    status_file = d / 'status.json'
    if d.is_dir() and status_file.exists():
        try:
            st = json.loads(status_file.read_text(encoding='utf-8'))
            if st.get('status') == 'ready':
                cat_file = d / 'catalog.json'
                sheets_file = d / 'sheets-v3.json'
                scanned.append({
                    'id': d.name,
                    'filename': st.get('filename'),
                    'has_cat': cat_file.exists(),
                    'has_sheets': sheets_file.exists()
                })
        except Exception:
            pass

print(f"Scanned {len(scanned)} ready documents in {time.time()-t0:.2f}s")
for s in scanned[:10]:
    print(f"  {s['id'][:8]}: {s['filename']}")
