import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")
import json
from pathlib import Path
from graph.part_graph import build_part_graph

doc_dir = Path("storage/documents/8565af68196b40a6acc853d9d9eead87")
cache_path = doc_dir / "part-graph-v1.json"
sheets_data = json.loads((doc_dir / "sheets-v3.json").read_text(encoding='utf-8'))
sheets = sheets_data['items']

graph = json.loads(cache_path.read_text(encoding='utf-8'))
tables = []
seen_tables = set()
for node in graph['nodes']:
    for occ in node.get('bom_occurrences', []):
        t_ref = occ['table_ref']
        if t_ref not in seen_tables:
            seen_tables.add(t_ref)
            rows = []
            for n in graph['nodes']:
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
# Update nodes in existing graph
node_map = {n['code']: n for n in new_graph['nodes']}
for node in graph['nodes']:
    if node['code'] in node_map:
        node['detail_sheets'] = node_map[node['code']]['detail_sheets']

graph['version'] = 35

# Cache updated

cache_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf-8')
print("Successfully updated part-graph-v1.json with version 35 and populated detail_sheets!")
