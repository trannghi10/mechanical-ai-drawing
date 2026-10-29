"""Export the next partial customer revision and measure actual reopened DWG."""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding='utf8')
from verify_dauphine_laser_group import context
from verify_dauphine_combined import export_checked_preview
from backend.services import catalog_service as storage
from backend.services.change_service import DrawingChangePlan, validate_plan
from graph.packaging_fit import synchronize, review
from graph.drawing_sync import assembly_sync_review
from backend.services.curved_wall_service import review as forming_review
from cad.edit_engine import digest
from cad.geometry import snapshot, near


def main():
    started = time.monotonic()
    doc_id = '34ee84f35e1a44fb81c56044397a0fff'
    source, c = context()
    folder = storage.folder(doc_id)
    base = json.loads((folder/'change-plans/e29ee929e88246deaded6ce39c0a2b46.json').read_text(encoding='utf8'))
    assert c['source_hash'] == base['source_hash']
    c['root_target_ids'], c['root_bom_refs'] = base['root_target_ids'], base['root_bom_refs']
    plan = synchronize(DrawingChangePlan.model_validate(base['checked_preview_plan']), c)
    validate_plan(plan, c)
    packing = review(plan, c)
    envelope = next(e for r in packing for e in r['updated_envelopes'] if e['sheet_id'] == '3E5E8C')
    assert envelope['top_layer_bindings'][0]['unresolved_intersections'] == []
    side = envelope['side_layer_bindings'][0]
    assert side['nominal_after_mm'] == 718
    assert sorted(s['after_mm'] for s in side['side_views']) == [716, 718]
    assert envelope['carton_inset_binding']['after_height_mm'] == 809
    assert len(plan.operations) == 239
    proposal = dict(base, id=uuid.uuid4().hex, checked_preview_plan=plan.model_dump(), packaging_review=packing)
    storage.write_json(folder/'change-plans'/(proposal['id']+'.json'), proposal)
    export_checked_preview(doc_id, proposal['id'], source, c, plan, base['request_review'], assembly_sync_review(plan, c),
        packing, forming_review(plan, c), started, backup_name='Dauphine-PREVIEW-xop-ben-hong-va-long-thung.dwg')
    receipts = [p for p in Path('storage/validation-fixtures/dauphine-combined').glob('*/receipt.json')
                if json.loads(p.read_text(encoding='utf8')).get('plan_id') == proposal['id']]
    assert len(receipts) == 1
    verify_readback(receipts[0], source, c, plan)


def verify_readback(receipt_path, source, c, plan):
    doc_id = '34ee84f35e1a44fb81c56044397a0fff'
    folder = storage.folder(doc_id)
    receipt = json.loads(receipt_path.read_text(encoding='utf8'))
    side = next(s for group in receipt['packaging_review'] for envelope in group['updated_envelopes']
                for s in envelope['side_layer_bindings'])
    import ezdxf
    reopened = folder/'revisions'/receipt['revision_id']/'reopen-selection/modified.dxf'
    after = ezdxf.readfile(reopened)
    ops = {o.ref:o for o in plan.operations if o.action == 'replace_geometry'}
    for ref in ('3E5DEA', '3E5DEC', '3E5DE9', '3E5DEB', '3E6B8A', '3DFA5C'):
        assert near(snapshot(after.entitydb[ref]), json.loads(ops[ref].after), 1e-5), ref
    assert type(after.entitydb['3E5DEB'].paths[0]).__name__ == 'EdgePath'
    assert near(after.entitydb['3DFA60'].get_measurement(), 718)
    from cad.table_data import table_cells
    values = table_cells(reopened)['3E5E9B']
    from bom.reader import read_bom
    from cad.table_bindings import bind_cells
    rows = read_bom(values, bind_cells(after.entitydb['3E5E9B'], values, after))['rows']
    assert any(r['part_code'] == '3.8.01312' and '40x635x718' in r['description'] for r in rows)
    assert any(r['part_code'] == '3.8.02293' and '925x925x823' in r['description'] for r in rows)
    assert digest(source) == c['source_hash']
    from backend.services.revision_service import revision_preview
    from cad.vision import rasterize_svg
    svg = revision_preview(doc_id, receipt['revision_id'], '3E007F')
    (receipt_path.parent/'side-pad-detail-after.png').write_bytes(rasterize_svg(svg, width=1400))
    proof = dict(revision_id=receipt['revision_id'], plan_id=receipt['plan_id'], dwg=receipt['dwg'], dwg_hash=receipt['dwg_hash'],
        side_pad_bom_and_dimension_mm=718, source_top_gaps_mm=[s['top_gap_mm'] for s in side['side_views']],
        side_projection_heights_mm=[s['after_mm'] for s in side['side_views']], carton_inset_height_mm=809,
        source_unchanged=True, former_four_intersections_resolved=True, native_hatch_edge_type_preserved=True,
        complete_packaging=False, complete_product_backup=False)
    storage.write_json(receipt_path.parent/'side-layers-readback.json', proof)
    print(json.dumps(proof, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--readback':
        source, c = context()
        path = Path('storage/validation-fixtures/dauphine-combined')/sys.argv[2]/'receipt.json'
        receipt = json.loads(path.read_text(encoding='utf8'))
        proposal = json.loads((storage.folder(receipt['document_id'])/'change-plans'/(receipt['plan_id']+'.json')).read_text(encoding='utf8'))
        assert c['source_hash'] == proposal['source_hash']
        verify_readback(path, source, c, DrawingChangePlan.model_validate(proposal['checked_preview_plan']))
    else:
        main()
