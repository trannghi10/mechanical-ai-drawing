import json
from pathlib import Path

for rev_id in ['5f87b84ede6345c88ccf3596bfe75ac7', '2efaca3e05e84897ab397625b296c6dc']:
    p = Path(f'storage/documents/5a1955b75d4345b69d19d38b7cfaf75c/revisions/{rev_id}/download-jobs')
    print(f'=== Jobs for {rev_id[:8]} ===')
    if p.exists():
        for f in p.glob('*.json'):
            d = json.loads(f.read_text(encoding='utf-8'))
            print('Job:', f.name, 'scope:', d.get('scope'), 'file:', d.get('file'), 'size:', (p.parent / d.get('file','')).stat().st_size if (p.parent / d.get('file','')).exists() else 'MISSING')
