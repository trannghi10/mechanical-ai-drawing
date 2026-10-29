"""Read-only scope injection for explicitly confirmed cuboid depictions.

These links never turn an assembly sheet into a part detail or assign a code
to an entire INSERT. Ownership is rechecked for the exact target LINE set.
"""
import copy,json
from pathlib import Path


def read(folder,source_hash):
    folder=Path(folder);file=folder/'design-decisions-v1.json'
    if not file.exists():return []
    data=json.loads(file.read_text(encoding='utf8'))
    if data.get('source_hash')!=source_hash:return []
    rows=[copy.deepcopy(c) for c in data.get('confirmed_choices',[]) if c.get('key')=='cuboid_projection_datum' and c.get('confirmation')=='user_confirmed_cuboid_identity_and_datum']
    excluded=folder/'exclusions-v1.json';ids=set(json.loads(excluded.read_text(encoding='utf8')).get('ids',[])) if excluded.exists() else set()
    for row in rows:row['unavailable_scope_ids']=sorted(ids.intersection(t['id'] for t in row.get('targets',[])))
    return rows


def inject(graph,rows):
    result=copy.deepcopy(graph);known={n['code'] for n in result['nodes']}
    links=[]
    for row in rows:
        if row['part_code'] not in known:raise ValueError('Mã của hình hộp đã gắn không còn trong BOM nguồn')
        links.append(dict(body_id=row['body_id'],part_code=row['part_code'],dimension_ref=row['dimension_ref'],
                          sheet_ids=[t['id'] for t in row.get('targets',[])],target_refs=row['target_refs'],unavailable_scope_ids=row.get('unavailable_scope_ids',[])))
    result['confirmed_representation_links']=links
    return result
