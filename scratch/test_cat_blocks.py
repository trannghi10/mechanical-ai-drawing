import json
from pathlib import Path

cat_path = Path("storage/documents/8565af68196b40a6acc853d9d9eead87/catalog.json")
data = json.loads(cat_path.read_text(encoding='utf-8'))
items = data.get('items', [])
print(f"Total items in catalog: {len(items)}")

blocks = [i for i in items if i['kind'] == 'block']
print(f"Total block items: {len(blocks)}")
table_blocks = [i for i in blocks if i.get('layout') == 'BlockTable']
print(f"BlockTable items: {len(table_blocks)}")
print("Sample BlockTable items:")
for b in table_blocks[:5]:
    print(b)
