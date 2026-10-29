import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

for p in Path('.').rglob('*.py'):
    if 'venv' in str(p) or '.git' in str(p) or 'scratch' in str(p): continue
    try:
        txt = p.read_text(encoding='utf-8')
        for i, line in enumerate(txt.splitlines(), 1):
            if 'khung' in line and ('chưa' in line or 'hợp lệ' in line or 'nguồn' in line):
                print(f'{p}:{i}: {line.strip()}')
    except Exception:
        pass
