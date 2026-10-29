import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

for p in list(Path('backend').rglob('*.py')) + list(Path('graph').rglob('*.py')) + list(Path('cad').rglob('*.py')):
    try:
        content = p.read_text(encoding='utf-8')
        for i, line in enumerate(content.splitlines(), 1):
            if 'lập bản sửa' in line or 'chưa thể lập' in line:
                print(f'{p}:{i}: {line.strip()}')
    except Exception:
        pass
