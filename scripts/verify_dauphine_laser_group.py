"""Compile source-measured laser material edits against the real cached CAD.

The cache is hash checked; every operation is recompiled against native source
snapshots before it can be used. This is not a complete assembly backup.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf8')
from backend.services import catalog_service as storage
from backend.services.change_service import validate_plan, context_for
from backend.services.design_choices import attach
from backend.services.part_graph_service import document_graph
from backend.services.sheet_thickness_planner import compile_plan
from cad.edit_engine import digest
from cad.measured_features import index


def context():
    folder = storage.folder('34ee84f35e1a44fb81c56044397a0fff')
    source = folder/storage.read_status(folder.name)['dxf']
    from backend.main import get_sheets
    active = {s['id']: s for s in get_sheets(folder.name)['items']}
    cache = Path('storage/validation-fixtures/dauphine-laser-group/current-context.json')
    signature = dict(source_hash=digest(source), active_ids=sorted(active), parser_reference_version=5)
    saved = json.loads(cache.read_text(encoding='utf8')) if cache.exists() else {}
    if saved.get('signature') == signature:
        c = saved['context']
    else:
        print('Reading all active source frames', flush=True)
        c = context_for(source, list(active.values()))
        graph = document_graph(folder.name)
        print('Indexing all source measurements', flush=True)
        c['source_features'] = index(c, graph)
        cache.parent.mkdir(parents=True, exist_ok=True)
        storage.write_json(cache, dict(signature=signature, context=c))
    c['part_graph'] = document_graph(folder.name)
    c['root_target_ids'] = ['3D3E83']
    c['root_bom_refs'] = [e['ref'] for e in c['entities'] if '3D3E83' in e.get('source_sheet_ids', []) and e.get('bom')]
    c['root_bom_refs'].extend(c['part_graph'].get('bom_continuations', {}).get('3D3E83', {}).get('table_refs', []))
    assert c['root_bom_refs']
    return source, attach(c, folder)


def main():
    start = time.monotonic()
    source, c = context()
    print('Compiling all laser sheet materials', flush=True)
    plan = compile_plan(c, 'Tất cả liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1 mm')
    assert plan is not None
    out = Path('storage/validation-fixtures/dauphine-laser-group')
    out.mkdir(parents=True, exist_ok=True)
    storage.write_json(out/'plan.json', plan.model_dump())
    report = dict(source_hash=digest(source), questions=plan.questions, changed_entities=len(plan.operations),
        measured_sections=len(plan.resize_recipes), curved_sections=len(plan.curved_wall_recipes),
        part_codes=sorted({r.part_code for r in plan.resize_recipes}), complete_product_backup=False,
        compile_seconds=round(time.monotonic()-start, 3))
    if not plan.questions:
        validate_plan(plan, c)
        report['plan_validation'] = 'passed'
    storage.write_json(out/'receipt.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
