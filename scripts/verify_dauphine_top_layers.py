"""Recompile and export customer preview; independently measure ODA readback."""
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
from graph.packaging_fit import synchronize, review as packing_review
from graph.drawing_sync import assembly_sync_review
from backend.services.curved_wall_service import review as forming_review
from cad.edit_engine import digest
from cad.geometry import snapshot, near


def main():
    started = time.monotonic()
    doc = '34ee84f35e1a44fb81c56044397a0fff'
    source, c = context()
    folder = storage.folder(doc)
    base = json.loads((folder/'change-plans/e29ee929e88246deaded6ce39c0a2b46.json').read_text(encoding='utf8'))
    assert base['source_hash'] == c['source_hash']
    c['root_target_ids'] = base['root_target_ids']
    c['root_bom_refs'] = base['root_bom_refs']
    plan = DrawingChangePlan.model_validate(base['checked_preview_plan'])
    before_count = len(plan.operations)
    plan = synchronize(plan, c)
    validate_plan(plan, c)
    expected = {'3E5DE0', '3E5DDE', '3E5DDF', '3E5DDD'}
    assert len(plan.operations) >= before_count+4
    assert expected <= {o.ref for o in plan.operations}
    packing = packing_review(plan, c)
    stacks = [s for r in packing for envelope in r['updated_envelopes'] for s in envelope['top_layer_bindings']]
    assert len(stacks) == 1 and stacks[0]['delta_mm'] == -27
    assert stacks[0]['product_gap_mm'] == 6 and stacks[0]['carton_gap_mm'] == 8.5
    proposal = dict(base, id=uuid.uuid4().hex, checked_preview_plan=plan.model_dump(), packaging_review=packing)
    storage.write_json(folder/'change-plans'/(proposal['id']+'.json'), proposal)
    export_checked_preview(doc, proposal['id'], source, c, plan, base['request_review'], assembly_sync_review(plan, c),
        packing, forming_review(plan, c), started, backup_name='Dauphine-PREVIEW-dem-tren-va-lien-ket-moi.dwg')
    # Resolve the newly created revision by its unique plan receipt.
    receipts = [p for p in (Path('storage/validation-fixtures/dauphine-combined')).glob('*/receipt.json')
                if json.loads(p.read_text(encoding='utf8')).get('plan_id') == proposal['id']]
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding='utf8'))
    import ezdxf
    reopened = folder/'revisions'/receipt['revision_id']/'reopen-selection/modified.dxf'
    doc_after = ezdxf.readfile(reopened)
    ops = {o.ref:o for o in plan.operations}
    for ref in expected:
        assert near(snapshot(doc_after.entitydb[ref]), json.loads(ops[ref].after), 1e-5), ref
    assert near(doc_after.entitydb['3E5DF3'].get_measurement(), 823)
    assert near(doc_after.entitydb['3E5E00'].get_measurement(), 953)
    assert digest(source) == c['source_hash']
    proof = dict(revision_id=receipt['revision_id'], plan_id=proposal['id'], dwg=receipt['dwg'], dwg_hash=receipt['dwg_hash'],
        native_pad_and_hatch_readback='passed', stacks=stacks, source_unchanged=True,
        complete_product_backup=False, complete_packaging=False, changed_entities=len(plan.operations))
    storage.write_json(receipts[0].parent/'top-layers-readback.json', proof)
    print(json.dumps(proof, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--refresh-review':
        # Re-evaluate newly discovered fit warnings without rewriting validated
        # CAD or historical export receipts. Native operations must be equal.
        from backend.services.revision_service import read_revision
        source, c = context()
        doc = '34ee84f35e1a44fb81c56044397a0fff'
        path, revision = read_revision(doc, sys.argv[2])
        assert revision['complete_product_backup'] is False
        assert digest(path/'modified.dxf') == revision['validation']['output_hash']
        proposal_path = storage.folder(doc)/'change-plans'/(revision['plan_id']+'.json')
        proposal = json.loads(proposal_path.read_text(encoding='utf8'))
        assert digest(source) == proposal['source_hash']
        c['root_target_ids'], c['root_bom_refs'] = proposal['root_target_ids'], proposal['root_bom_refs']
        original = DrawingChangePlan.model_validate(proposal['checked_preview_plan'])
        plan = synchronize(original.model_copy(deep=True), c)
        assert [o.model_dump() for o in original.operations] == [o.model_dump() for o in plan.operations]
        validate_plan(plan, c)
        review = packing_review(plan, c)
        proposal['checked_preview_plan'] = plan.model_dump()
        proposal['packaging_review'] = revision['packaging_review'] = review
        storage.write_json(proposal_path, proposal)
        storage.write_json(path/'revision.json', revision)
        report = dict(revision_id=revision['id'], cad_unchanged=True, complete_packaging=False,
                      packaging_review=review, warnings=plan.warnings)
        out = Path('storage/validation-fixtures/dauphine-combined')/revision['id']/'top-layers-intersections.json'
        storage.write_json(out, report)
        print(str(out.resolve()), flush=True)
    else:
        main()
