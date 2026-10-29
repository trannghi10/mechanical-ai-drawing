"""Reopen a real DWG and verify confirmed tube cuts without fake DIM scale."""
import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_dauphine_laser_group import context
from verify_dauphine_combined import export_checked_preview
from verify_dauphine_inner_panel import readback as panel_readback
from backend.services import catalog_service as storage
from backend.services.change_service import DrawingChangePlan,validate_plan
from graph.confirmed_inner_tubes import proofs,validate
from graph.packaging_fit import review as packing_review
from graph.drawing_sync import assembly_sync_review
from backend.services.curved_wall_service import review as forming_review
from cad.geometry import near,snapshot
from cad.edit_engine import digest
sys.stdout.reconfigure(encoding='utf8')

def readback(receipt_file,source,c,plan):
    import ezdxf
    panel_readback(receipt_file,source,c,plan)
    receipt=json.loads(receipt_file.read_text(encoding='utf8'))
    folder=storage.folder(receipt['document_id'])/'revisions'/receipt['revision_id']
    revision=json.loads((folder/'revision.json').read_text(encoding='utf8'))
    after=ezdxf.readfile(folder/'reopen-selection/modified.dxf')
    binding,=proofs(plan,c);ref=binding['dimension_ref'];e=after.entitydb[ref]
    assert near(snapshot(e),binding['after'],1e-5)
    assert e.dxf.text=='695%%P0.5'
    assert near(e.get_measurement(),binding['native_measured_span_mm'],1e-5)
    assert e.override().get('dimlfac',1)==1
    records={e['ref']:e for e in c['entities']}
    for ref in binding['break_refs']+binding['section_refs']+binding['end_cap_refs']+binding['joined_edge_refs']:
        assert near(snapshot(after.entitydb[ref]),records[ref]['geometry'],1e-5),ref
    from cad.table_data import table_cells
    from cad.broken_tube import tube_spec
    cells=table_cells(folder/'reopen-selection/modified.dxf')
    qty_checks=[]
    for t in c['entities']:
        for row in t.get('bom',{}).get('rows',[]):
            if row['part_code']!=binding['part_code']:continue
            desc=row['cells']['description'];text=next(v['raw_text'] for v in cells[t['ref']] if v['index']==desc['index'])
            assert tube_spec(text)==(14,14,1.2,695)
            qty=row['cells']['quantity'];quantity=next(v['raw_text'] for v in cells[t['ref']] if v['index']==qty['index'])
            assert quantity=='12';qty_checks.append(t['ref'])
    assert len(qty_checks)==2 and digest(source)==c['source_hash']
    from backend.services.revision_service import revision_preview
    from cad.vision import rasterize_svg
    svg=revision_preview(receipt['document_id'],receipt['revision_id'],'3A1D79')
    (receipt_file.parent/'tube5-after.svg').write_text(svg,encoding='utf8')
    (receipt_file.parent/'tube5-after.png').write_bytes(rasterize_svg(svg,width=1400))
    result=dict(revision_id=receipt['revision_id'],plan_id=receipt['plan_id'],dwg=receipt['dwg'],dwg_hash=receipt['dwg_hash'],
        cut_nominal_before_mm=721,cut_nominal_after_mm=695,nominal_tolerance_mm=.5,quantity=12,unchanged_stock_cross_section_mm=[14,14,1.2],
        native_cropped_span_mm=binding['native_measured_span_mm'],unchanged_native_dimension_scale=1,source_break_markers_preserved=True,
        verified_native_bom_tables=qty_checks,source_unchanged=True,complete_product_backup=False,complete_packaging=False)
    storage.write_json(receipt_file.parent/'tube5-readback.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

def main():
    started=time.monotonic();source,c=context();folder=storage.folder('34ee84f35e1a44fb81c56044397a0fff')
    base=json.loads((folder/'change-plans/e29ee929e88246deaded6ce39c0a2b46.json').read_text(encoding='utf8'))
    c['root_target_ids'],c['root_bom_refs']=base['root_target_ids'],base['root_bom_refs']
    plan=DrawingChangePlan.model_validate(json.loads((folder/'inner-tube-probe.json').read_text(encoding='utf8')))
    assert len(plan.operations)==260 and validate(plan,c)
    validate_plan(plan,c)
    packing=packing_review(plan,c);assembly=assembly_sync_review(plan,c);forming=forming_review(plan,c)
    proposal=dict(base,id=uuid.uuid4().hex,checked_preview_plan=plan.model_dump(),packaging_review=packing,drawing_sync=assembly,forming_review=forming)
    storage.write_json(folder/'change-plans'/(proposal['id']+'.json'),proposal)
    export_checked_preview(base['document_id'],proposal['id'],source,c,plan,base['request_review'],assembly,packing,forming,started,
        backup_name='Dauphine-PREVIEW-tam-21-thanh-5-va-cua-lap.dwg')
    receipts=[p for p in Path('storage/validation-fixtures/dauphine-combined').glob('*/receipt.json') if json.loads(p.read_text(encoding='utf8')).get('plan_id')==proposal['id']]
    assert len(receipts)==1;readback(receipts[0],source,c,plan)

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--readback':
        source,c=context();path=Path('storage/validation-fixtures/dauphine-combined')/sys.argv[2]/'receipt.json'
        r=json.loads(path.read_text(encoding='utf8'));proposal=json.loads((storage.folder(r['document_id'])/'change-plans'/(r['plan_id']+'.json')).read_text(encoding='utf8'))
        readback(path,source,c,DrawingChangePlan.model_validate(proposal['checked_preview_plan']))
    else:main()
