import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from backend.services.change_service import _context_for
from cad.catalog import discover

doc_id = '8565af68196b40a6acc853d9d9eead87'
source = Path(f'storage/documents/{doc_id}/converted/original.dxf')
cat = discover(source)

# Find a block definition item with layout == 'BlockTable'
block_item = next((i for i in cat['items'] if i['kind'] == 'block' and i['layout'] == 'BlockTable' and i['entity_count'] > 0), None)
print('Block item from catalog:', block_item['name'], block_item['id'], 'entity_count:', block_item['entity_count'])

if block_item:
    try:
        ctx = _context_for(source, [block_item])
        ents = ctx.get('entities', [])
        print('Context entities count for block:', len(ents))
        print('Entities:', [e['type'] for e in ents])
    except Exception as ex:
        print('Error reading block context:', type(ex).__name__, ex)
