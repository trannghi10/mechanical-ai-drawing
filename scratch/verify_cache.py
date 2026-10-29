import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
from pathlib import Path

data = json.loads(Path("storage/documents/8565af68196b40a6acc853d9d9eead87/part-graph-v1.json").read_text(encoding='utf-8'))
for n in data['nodes']:
    if n.get('detail_sheets'):
        print(f"Node {n['code']}: detail_sheets={n['detail_sheets']}")
