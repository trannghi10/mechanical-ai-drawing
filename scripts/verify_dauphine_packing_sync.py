"""Roundtrip the real customer's checked shell and measured packing envelope.

Records this as a partial revision, never as a completed product backup.
"""
import json
import shutil
import sys
import uuid
import faulthandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf8')
from backend.services import catalog_service as storage
from backend.services.change_service import context_for, DrawingChangePlan, validate_plan
from backend.services.design_choices import attach
from backend.services.part_graph_service import document_graph
from cad.edit_engine import apply_patch, digest
from cad.frame_geometry import world
from cad.measured_features import index
from cad.converter import DWGConverter, converter_path
from cad.scoped_export import select_entities
from cad.sheets import render_sheet
from cad.vision import rasterize_svg
from graph.packing_envelope_sync import synchronize, bindings


def main():
    faulthandler.dump_traceback_later(30, repeat=True)
    document_id = '34ee84f35e1a44fb81c56044397a0fff'
    folder = storage.folder(document_id)
    source = folder / storage.read_status(document_id)['dxf']
    original = digest(source)
    ids = {'3B8A74', '3B8B05', '3B8B98', '3B8C84', '3D337A', '3E5E8C', '3E5F1D'}
    from backend.main import get_sheets
    print('Reading active sheets', flush=True)
    targets = [s for s in get_sheets(document_id)['items'] if s['id'] in ids]
    assert {s['id'] for s in targets} == ids
    print('Reading source context', flush=True)
    context = attach(context_for(source, targets), folder)
    context['part_graph'] = document_graph(document_id)
    context['root_target_ids'] = ['3B8C84']
    print('Indexing measured features', flush=True)
    context['source_features'] = index(context, context['part_graph'])
    shell = Path('storage/validation-fixtures/dauphine-height-wall/15dba9a530c640a4b4d56a1e0352ad66/plan.json')
    plan = DrawingChangePlan.model_validate(json.loads(shell.read_text(encoding='utf8')))
    before = len(plan.operations)
    print('Synchronizing packing', flush=True)
    plan = synchronize(plan, context)
    proof = bindings(plan, context)
    assert len(proof) == 1 and proof[0][0]['carton_target_mm'] == 823
    assert len(plan.operations) > before
    print('Validating plan', flush=True)
    validate_plan(plan, context)
    output = Path('storage/validation-fixtures/dauphine-packing-sync') / uuid.uuid4().hex
    authored = output/'authored'
    authored.mkdir(parents=True)
    receipt = apply_patch(source, output/'full-source-copy.dxf', plan.operations,
        {e['ref'] for e in context['entities']}, original)
    name = 'Dauphine-PREVIEW-tam-op697-day1-thung823.dxf'
    scoped = authored/name
    select_entities(output/'full-source-copy.dxf', scoped,
        {e['ref'].split('/')[0] for e in context['entities'] if not e['ref'].startswith('graphic-table:')})
    converter = DWGConverter(converter_path())
    converter.convert_dxf_to_dwg(str(authored), str(output/'dwg'))
    converter.convert_dwg_to_dxf(str(output/'dwg'), str(output/'reopened'))
    reopened = output/'reopened'/name
    actual = context_for(reopened, targets)
    by = {e['ref']: e for e in actual['entities']}
    mapped = {r: change['ref'] for change in receipt['changes'] for r in change.get('original_refs', [change['ref']])}
    def points(ref):
        return world(by[mapped.get(ref, ref)])['geometry']['points']
    def ends(ref):
        return [min(p[1] for p in points(ref)), max(p[1] for p in points(ref))]
    proof = proof[0][0]
    sections = sorted(proof['product_section_refs'], key=lambda r: ends(r)[0])
    body, cap = sections
    b0, b1 = ends(body)
    c0, c1 = ends(cap)
    x0, x1 = ends(proof['carton_outline_ref'])
    assert abs(b1-b0-697) < 1e-5
    assert abs(c1-c0-3) < 1e-5 and abs(c0-b1) < 1e-5
    assert abs(c1-b0-700) < 1e-5 and abs(x1-x0-823) < 1e-5
    assert abs(b0-x0-61.5) < 1e-5 and abs(x1-c1-61.5) < 1e-5
    assert abs(by[proof['carton_dimension_ref']]['scaled_measurement']-823) < 1e-5
    rows = [r for e in actual['entities'] for r in e.get('bom', {}).get('rows', []) if r['part_code'] == proof['carton_code']]
    assert rows and all('925x925x823' in row['description'] for row in rows)
    svg = render_sheet(reopened, next(s for s in targets if s['id'] == proof['sheet_id']))
    (output/'packing-after.svg').write_text(svg, encoding='utf8')
    (output/'packing-after.png').write_bytes(rasterize_svg(svg, width=1500))
    dwg = output/'dwg'/Path(name).with_suffix('.dwg')
    result = dict(source_hash=original, source_unchanged=digest(source) == original,
        complete_product_backup=False, complete_packaging=False, changed_entities=len(plan.operations),
        new_packing_entities=len(plan.operations)-before, shell_height_mm=697, product_envelope_height_mm=700,
        cap_height_mm=3, carton_height_mm=823, clearances_mm=[61.5, 61.5],
        dwg=str(dwg.resolve()), dwg_hash=digest(dwg), roundtrip='passed', proof=proof,
        remaining=['Chưa kiểm chứng toàn bộ 12 vật tư laser, hình cụm và phôi uốn',
            'Chưa đồng bộ lớp đệm và các hình tách rời đóng gói'])
    storage.write_json(output/'receipt.json', result)
    storage.write_json(output/'plan.json', plan.model_dump())
    backup = Path('storage/backups')/dwg.name
    backup.parent.mkdir(exist_ok=True)
    shutil.copy2(dwg, backup)
    result['preview_copy'] = str(backup.resolve())
    storage.write_json(output/'receipt.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
