import json
from pathlib import Path

doc_dir = Path('storage/documents/5a1955b75d4345b69d19d38b7cfaf75c/revisions')
for rev in doc_dir.iterdir():
    if not rev.is_dir(): continue
    jobs_dir = rev / 'download-jobs'
    if not jobs_dir.exists(): continue
    for jf in jobs_dir.glob('*.json'):
        try:
            d = json.loads(jf.read_text(encoding='utf-8'))
            if d.get('scope') == 'selection' or 'export-selection' in d.get('file', ''):
                print(f"Rev {rev.name[:8]}: Job {jf.name} -> scope={d.get('scope')}, file={d.get('file')}")
        except Exception:
            pass
