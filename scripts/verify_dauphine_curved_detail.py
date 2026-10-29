"""Export a partial Dauphine revision with source-bound Detail C gauges.

Uses normal apply/validation/export gates; never marks it a full backup.
"""
import json,sys,time,uuid,subprocess,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_dauphine_laser_group import context
from verify_dauphine_combined import export_checked_preview
from backend.services import catalog_service as storage
from backend.services.change_service import DrawingChangePlan,validate_plan
from backend.services.parametric_service import compile_recipes
from graph.curved_detail_contacts import proofs,expected_operations
from graph.packaging_fit import review as packing_review
from graph.drawing_sync import assembly_sync_review
from backend.services.curved_wall_service import review as forming_review
from cad.geometry import near,snapshot
from cad.edit_engine import digest
sys.stdout.reconfigure(encoding='utf8')


def readback(receipt_path,source,c,plan):
    import ezdxf
    receipt=json.loads(receipt_path.read_text(encoding='utf8'));folder=storage.folder(receipt['document_id'])/'revisions'/receipt['revision_id']
    revision=json.loads((folder/'revision.json').read_text(encoding='utf8'));doc=ezdxf.readfile(folder/'reopen-selection/modified.dxf');original=ezdxf.readfile(source)
    mapping={ref:o['ref'] for o in revision['validation']['changes'] for ref in o.get('original_refs',[o['ref']])}
    entity=lambda ref:doc.entitydb[mapping.get(ref,ref).split('/')[-1]]
    evidence=[]
    for proof in proofs(plan,c):
        for op in expected_operations(proof,c):assert near(snapshot(entity(op.ref)),json.loads(op.after),1e-5),op.ref
        for ref in (proof['circle_ref'],proof['outer_arc_ref'],proof['outer_leg_ref']):assert near(snapshot(entity(ref)),snapshot(original.entitydb[ref]),1e-5),ref
        dims=[]
        for key in ('radial_dimension','leg_dimension'):
            e=entity(proof['bindings'][key]);factor=e.override().get('dimlfac',1)
            # Aligned source DIMs can have optional angle=0. ezdxf's generic
            # measurement tool projects along that angle; native CAD measures
            # the extension endpoints. Verify both those points and group 42.
            measured=math.dist(e.dxf.defpoint2,e.dxf.defpoint3) if e.dxf.dimtype & 15==1 else e.get_measurement()
            value=measured*factor
            assert near(value,1,1e-5) and e.dxf.text=='<>'
            assert near(e.dxf.actual_measurement*factor,value,1e-5)
            rendered=[t.text if t.dxftype()=='MTEXT' else t.dxf.text for t in doc.blocks[e.dxf.geometry] if t.dxftype() in ('TEXT','MTEXT')]
            assert rendered==['1'],rendered
            dims.append(dict(ref=proof['bindings'][key],measured_mm=value))
        g=dict(outer=snapshot(entity(proof['outer_arc_ref'])),inner=snapshot(entity(proof['bindings']['inner_arc'])),
            outer_leg=snapshot(entity(proof['outer_leg_ref'])),inner_leg=snapshot(entity(proof['bindings']['inner_leg'])),clip=snapshot(entity(proof['circle_ref'])))
        assert near((g['outer']['radius']-g['inner']['radius'])*.2,1,1e-5)
        input_path=receipt_path.parent/'detail-c-exported-kernel-input.json';output_path=receipt_path.parent/'detail-c-occ.json'
        storage.write_json(input_path,g)
        completed=subprocess.run([r'C:\Program Files\FreeCAD 1.1\bin\python.exe',str(Path('scripts/check_clipped_curve_kernel.py').resolve()),str(input_path.resolve()),str(output_path.resolve())],capture_output=True,text=True,timeout=45)
        assert completed.returncode==0,(completed.stdout,completed.stderr)
        kernel=json.loads(output_path.read_text(encoding='utf8'));assert kernel['closed'] and kernel['valid_face']
        evidence.append(dict(sheet_ids=proof['sheet_ids'],bindings=proof['bindings'],dimensions=dims,exterior_radius_mm=g['outer']['radius']*.2,inner_radius_mm=g['inner']['radius']*.2,independent_kernel=kernel))
    assert evidence and digest(source)==c['source_hash'] and revision['complete_product_backup'] is False
    assembly=assembly_sync_review(plan,c)
    coverage=next(r for r in assembly if r['sheet_id']=='3B3987')
    assert coverage['status']=='unverified_projection_mapping'
    assert any(v['view'].startswith('Detail cong:') for v in coverage['verified_views'])
    # Refresh derived coverage only, with native readback/source guards above;
    # geometry hashes and the partial/full-backup gate remain unchanged.
    revision['drawing_sync']=assembly;storage.write_json(folder/'revision.json',revision)
    proposal_path=storage.folder(receipt['document_id'])/'change-plans'/(receipt['plan_id']+'.json')
    proposal=json.loads(proposal_path.read_text(encoding='utf8'));proposal['drawing_sync']=assembly;storage.write_json(proposal_path,proposal)
    from backend.services.revision_service import revision_preview
    from cad.vision import rasterize_svg
    svg=revision_preview(receipt['document_id'],receipt['revision_id'],'3B3987')
    (receipt_path.parent/'weld-detail-c-after.svg').write_text(svg,encoding='utf8')
    (receipt_path.parent/'weld-detail-c-after.png').write_bytes(rasterize_svg(svg,width=1800))
    result=dict(document_id=receipt['document_id'],revision_id=receipt['revision_id'],plan_id=receipt['plan_id'],dwg=receipt['dwg'],dwg_hash=receipt['dwg_hash'],changed_entities=len(plan.operations),detail_c=evidence,
        source_unchanged=True,complete_product_backup=False,complete_packaging=False,
        remaining=['Hình cạnh/phối cảnh C4 và các hình cụm/công đoạn còn thiếu liên kết','Một số đệm góc/hình đóng gói chưa được gắn đủ'])
    storage.write_json(receipt_path.parent/'curved-detail-readback.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


def main():
    started=time.monotonic();source,c=context();folder=storage.folder('34ee84f35e1a44fb81c56044397a0fff')
    base=json.loads((folder/'change-plans/a7c123c47b0a49ac90a6429b62afd838.json').read_text(encoding='utf8'))
    c['root_target_ids'],c['root_bom_refs']=base['root_target_ids'],base['root_bom_refs']
    plan=compile_recipes(DrawingChangePlan.model_validate(json.loads((folder/'corner-detail-probe.json').read_text(encoding='utf8'))),c)
    assert len(proofs(plan,c))==1;validate_plan(plan,c)
    print('Compiled',len(plan.operations),'checked operations including curved Detail C',flush=True)
    packing,assembly,forming=packing_review(plan,c),assembly_sync_review(plan,c),forming_review(plan,c)
    proposal=dict(base,id=uuid.uuid4().hex,checked_preview_plan=plan.model_dump(),packaging_review=packing,drawing_sync=assembly,forming_review=forming)
    proposal['plan']=dict(base['plan'],summary='Bản xem trước đồng bộ thêm cung trong, chân thẳng và DIM độ dày của Detail C.',questions=[
        'Còn hình cạnh/phối cảnh C4 và các hình cụm/công đoạn thiếu liên kết.',
        'Còn các đệm góc/hình đóng gói chưa được gắn đủ.'])
    proposal['message']='Detail C đã được tính theo DIM nguồn; vẫn là DWG xem trước một phần, chưa phải backup toàn sản phẩm.'
    storage.write_json(folder/'change-plans'/(proposal['id']+'.json'),proposal)
    export_checked_preview(base['document_id'],proposal['id'],source,c,plan,base['request_review'],assembly,packing,forming,started,backup_name='Dauphine-PREVIEW-cum-xuong-thanh692-DetailCD.dwg')
    receipts=[p for p in Path('storage/validation-fixtures/dauphine-combined').glob('*/receipt.json') if json.loads(p.read_text(encoding='utf8')).get('plan_id')==proposal['id']]
    assert len(receipts)==1;readback(receipts[0],source,c,plan)


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--readback':
        source,c=context();path=Path('storage/validation-fixtures/dauphine-combined')/sys.argv[2]/'receipt.json';r=json.loads(path.read_text(encoding='utf8'))
        p=json.loads((storage.folder(r['document_id'])/'change-plans'/(r['plan_id']+'.json')).read_text(encoding='utf8'))
        readback(path,source,c,DrawingChangePlan.model_validate(p['checked_preview_plan']))
    else:main()
