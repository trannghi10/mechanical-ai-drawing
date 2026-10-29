import json
from pathlib import Path
doc_dir = Path('storage/documents')
docs = []
for d in doc_dir.iterdir():
    if d.is_dir() and (d / 'status.json').exists():
        try:
            s = json.loads((d / 'status.json').read_text(encoding='utf-8'))
            docs.append((d.name[:8], s.get('filename'), s.get('status')))
        except Exception:
            pass
for d in sorted(docs, key=lambda x: str(x[1])):
    print(f"{d[0]}: {d[1]} ({d[2]})")
