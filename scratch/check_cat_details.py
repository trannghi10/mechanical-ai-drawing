import json
from collections import Counter
from pathlib import Path

cat_path = Path("storage/documents/8565af68196b40a6acc853d9d9eead87/catalog.json")
data = json.loads(cat_path.read_text(encoding='utf-8'))
items = data.get('items', [])
cats = Counter(i.get('category') for i in items)
print("Categories:", cats)
names = Counter(i.get('name') for i in items)
print("Top 15 block names:", names.most_common(15))

# Check sample item
print("\nSample item:", items[0])
