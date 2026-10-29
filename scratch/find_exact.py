import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

target = "Chi tiết chưa có khung nguồn hợp lệ"
for p in Path('.').rglob('*'):
    if 'venv' in str(p) or '.git' in str(p) or 'storage' in str(p): continue
    if p.is_file():
        try:
            txt = p.read_text(encoding='utf-8')
            if target in txt:
                print(f'{p}')
        except Exception:
            pass
