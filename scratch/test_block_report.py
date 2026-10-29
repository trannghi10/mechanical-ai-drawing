import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")
import json
from pathlib import Path
from backend.services.inspection_service import reading_report

cat_path = Path("storage/documents/8565af68196b40a6acc853d9d9eead87/catalog.json")
data = json.loads(cat_path.read_text(encoding='utf-8'))
items = data.get('items', [])
sample_block = next(i for i in items if i['kind'] == 'block' and i.get('category') == 'mechanical_part')
print("Sample block target:", sample_block['id'], sample_block['name'], sample_block['layout'])

source, report = reading_report("8565af68196b40a6acc853d9d9eead87", [sample_block])
print("Report selected_entity_count:", report['selected_entity_count'])
print("Report selected_entity_types:", report['selected_entity_types'])
print("Report facts count:", len(report['facts']))
print("Facts:", report['facts'][:10])
