"""Export and reopen the customer revision after confirmed inner-panel fitting."""
import json, sys, time, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_dauphine_laser_group import context
from verify_dauphine_combined import export_checked_preview
from backend.services import catalog_service as storage
from backend.services.change_service import DrawingChangePlan, validate_plan
from graph.confirmed_inner_panels import proofs, window_operations, window_captions
from graph.packaging_fit import review as packing_review
from graph.drawing_sync import assembly_sync_review
from backend.services.curved_wall_service import review as forming_review
from cad.edit_engine import digest
from cad.geometry import snapshot, near

sys.stdout.reconfigure(encoding='utf8')

def readback(receipt_file, source, c, plan):
    import ezdxf
    receipt = json.loads(receipt_file.read_text(encoding='utf8'))
    folder = storage.folder(receipt['document_id'])/'revisions'/receipt['revision_id']
    revision = json.loads((folder/'revision.json').read_text(encoding='utf8'))
    after = ezdxf.readfile(folder/'reopen-selection/modified.dxf')
    mapping = {ref:op['ref'] for op in revision['validation']['changes'] for ref in op.get('original_refs',[op['ref']])}
    def entity(ref): return after.entitydb[mapping.get(ref,ref).split('/')[-1]]
    proof, = proofs(plan,c)
    expected = window_operations(proof,c)
    panel_refs = {d['dimension_ref'] for d in proof['recipe_data']}|{ref for r in plan.resize_recipes if r.part_code==proof['part_code'] for ref in r.outline_refs}
    expected += [o for o in plan.operations if o.action=='replace_geometry' and o.ref in panel_refs]
    for op in expected:
        assert near(snapshot(entity(op.ref)),json.loads(op.after),1e-5),op.ref
    for op in window_captions(proof,c):
        e=entity(op.ref); assert (e.text if e.dxftype()=='MTEXT' else e.dxf.text)==op.after
    for data in proof['recipe_data']:
        assert near(entity(data['dimension_ref']).get_measurement(),data['new_measurement'],1e-5)
    assert near(entity(proof['source_windows'][0]['dimension_ref']).get_measurement(),697,1e-5)
    from cad.table_data import table_cells
    from backend.services.design_choices import sheet_spec
    cells = table_cells(folder/'reopen-selection/modified.dxf')
    records={e['ref']:e for e in c['entities']}
    checked_bom = 0
    for t in records.values():
        for row in t.get('bom',{}).get('rows',[]):
            if row['part_code'] != proof['part_code']: continue
            cell=row['cells']['description']; actual=next(v['raw_text'] for v in cells[mapping.get(t['ref'],t['ref'])] if v['index']==cell['index'])
            assert near(list(sheet_spec(actual)),[1,695,809.002],1e-5)
            checked_bom += 1
    assert checked_bom > 0 and digest(source)==c['source_hash']
    from backend.services.revision_service import revision_preview
    from cad.vision import rasterize_svg
    for sid,name in [('3C41A7','inner-panel-after'),('3B3987','weld-window-after')]:
        svg=revision_preview(receipt['document_id'],receipt['revision_id'],sid)
        (receipt_file.parent/(name+'.svg')).write_text(svg,encoding='utf8')
        (receipt_file.parent/(name+'.png')).write_bytes(rasterize_svg(svg,width=1400))
    result=dict(revision_id=receipt['revision_id'],plan_id=receipt['plan_id'],dwg=receipt['dwg'],dwg_hash=receipt['dwg_hash'],
        panel_native_dimensions_mm=[695,809.002],panel_gauge_bom_mm=1,verified_native_bom_rows=checked_bom,
        weld_frame_native_height_mm=697,confirmed_inner_fit=proof,source_unchanged=True,
        complete_product_backup=False,complete_packaging=False)
    storage.write_json(receipt_file.parent/'inner-panel-readback.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

def main():
    started=time.monotonic(); source,c=context(); folder=storage.folder('34ee84f35e1a44fb81c56044397a0fff')
    base=json.loads((folder/'change-plans/e29ee929e88246deaded6ce39c0a2b46.json').read_text(encoding='utf8'))
    c['root_target_ids'],c['root_bom_refs']=base['root_target_ids'],base['root_bom_refs']
    plan=DrawingChangePlan.model_validate(json.loads((folder/'inner-panel-probe.json').read_text(encoding='utf8')))
    assert len(plan.operations)==254 and proofs(plan,c)
    validate_plan(plan,c)
    packing=packing_review(plan,c); assembly=assembly_sync_review(plan,c); forming=forming_review(plan,c)
    proposal=dict(base,id=uuid.uuid4().hex,checked_preview_plan=plan.model_dump(),packaging_review=packing,drawing_sync=assembly,forming_review=forming)
    storage.write_json(folder/'change-plans'/(proposal['id']+'.json'),proposal)
    export_checked_preview(base['document_id'],proposal['id'],source,c,plan,base['request_review'],assembly,packing,forming,started,
                           backup_name='Dauphine-PREVIEW-tam-21-va-cua-lap.dwg')
    receipts=[p for p in Path('storage/validation-fixtures/dauphine-combined').glob('*/receipt.json') if json.loads(p.read_text(encoding='utf8')).get('plan_id')==proposal['id']]
    assert len(receipts)==1
    readback(receipts[0],source,c,plan)

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--readback':
        source,c=context(); path=Path('storage/validation-fixtures/dauphine-combined')/sys.argv[2]/'receipt.json'
        r=json.loads(path.read_text(encoding='utf8')); proposal=json.loads((storage.folder(r['document_id'])/'change-plans'/(r['plan_id']+'.json')).read_text(encoding='utf8'))
        readback(path,source,c,DrawingChangePlan.model_validate(proposal['checked_preview_plan']))
    else: main()
