# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.abspath('.'))

from backend.services.change_service import context_for
from backend.services.sheet_thickness_planner import compile_plan as sheets
from backend.services.design_choices import attach
from backend.services.part_graph_service import document_graph
from cad.measured_features import index
from cad.edit_engine import digest
from backend.services import catalog_service as storage
from pathlib import Path

doc_id = '34ee84f35e1a44fb81c56044397a0fff'
folder = storage.folder(doc_id)
source = folder / storage.read_status(doc_id)['dxf']

from backend.main import get_sheets
active = {s['id']: s for s in get_sheets(doc_id)['items']}

cache = Path('storage/validation-fixtures/dauphine-laser-group/current-context.json')
if cache.exists():
    c = json.loads(cache.read_text(encoding='utf8'))['context']
else:
    c = context_for(source, list(active.values()))
    c['source_features'] = index(c, document_graph(doc_id))

c['part_graph'] = document_graph(doc_id)
c['root_target_ids'] = ['3D3E83']
c['root_bom_refs'] = [e['ref'] for e in c['entities'] if '3D3E83' in e.get('source_sheet_ids', []) and e.get('bom')]
c['root_bom_refs'].extend(c['part_graph'].get('bom_continuations', {}).get('3D3E83', {}).get('table_refs', []))

c = attach(c, folder)

req = 'Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm'
plan = sheets(c, req)
print('plan summary:', plan.summary if plan else None)
if plan:
    print('operations count:', len(plan.operations))
    print('edits count:', len(plan.edits))
    print('questions:', plan.questions)
    print('warnings:', plan.warnings)
    print('resize_recipes count:', len(plan.resize_recipes))
    print('curved_wall_recipes count:', len(plan.curved_wall_recipes))
