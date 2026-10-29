import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")
import json
from pathlib import Path
from graph.part_graph import build_part_graph

doc_dir = Path("storage/documents/8565af68196b40a6acc853d9d9eead87")
sheets_data = json.loads((doc_dir / "sheets-v3.json").read_text(encoding='utf-8'))
sheets = sheets_data['items']

# Load tables from existing part-graph or table data
old_graph = json.loads((doc_dir / "part-graph-v1.json").read_text(encoding='utf-8'))
# In old_graph, what were tables?
# Let's inspect old_graph nodes
for node in old_graph['nodes']:
    print(f"Old Part {node['code']}: detail_sheets={node.get('detail_sheets')}")

# Now let's see what build_part_graph produces for these sheets and occurrences
# Let's recreate tables from bom occurrences in old_graph
tables = []
seen_tables = set()
for node in old_graph['nodes']:
    for occ in node.get('bom_occurrences', []):
        t_ref = occ['table_ref']
        if t_ref not in seen_tables:
            seen_tables.add(t_ref)
            # Reconstruct table object
            rows = []
            for n in old_graph['nodes']:
                for o in n.get('bom_occurrences', []):
                    if o['table_ref'] == t_ref:
                        rows.append({
                            'part_number': o['part_number'],
                            'part_code': n['code'],
                            'description': o['description'],
                            'material': o['material'],
                            'cells': {'description': o.get('description_cell', {})}
                        })
            tables.append({
                'ref': t_ref,
                'bom': {'status': 'verified_template', 'rows': rows}
            })

new_graph = build_part_graph(tables, sheets)
print("\n--- NEW GRAPH WITH OUR FIX ---")
for node in new_graph['nodes']:
    print(f"New Part {node['code']}: detail_sheets={node.get('detail_sheets')}")
