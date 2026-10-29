import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

target = 'khung nguồn hợp lệ'

for p in Path('.').rglob('*'):
    if p.is_file() and not p.name.endswith('.json') and not p.name.endswith('.tmp'):
        try:
            content = p.read_text(encoding='utf-8')
            if target in content:
                print(f'{p}: found!')
        except Exception:
            pass
