import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

for p in Path('backend').rglob('*.py'):
    txt = p.read_text(encoding='utf-8')
    if 'khung' in txt:
        for i, l in enumerate(txt.splitlines(), 1):
            if 'chưa' in l and 'khung' in l:
                print(f'{p}:{i}: {l.strip()}')
