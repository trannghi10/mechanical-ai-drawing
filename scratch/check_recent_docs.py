import json
from pathlib import Path

docs_dir = Path(r'd:\mechanical-ai-drawing\storage\documents')
docs = []
for p in docs_dir.iterdir():
    if p.is_dir() and (p / 'status.json').exists():
        try:
            stat = json.loads((p / 'status.json').read_text(encoding='utf-8'))
            mtime = (p / 'status.json').stat().st_mtime
            docs.append((mtime, p.name, stat))
        except Exception:
            pass

docs.sort(key=lambda x: x[0], reverse=True)
for mtime, did, stat in docs[:10]:
    import datetime
    dt = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
    print(f"{dt} [{did}] {stat.get('filename')} (status: {stat.get('status')})")
