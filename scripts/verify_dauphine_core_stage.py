"""Export a checked partial revision; reopen its actual DWG and measure it."""
import contextlib,io,json,math,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_dauphine_combined import export_checked_preview
from verify_dauphine_inner_panel import readback as panel_readback
from backend.services import catalog_service as storage
from backend.services.change_service import DrawingChangePlan
from backend.services.parametric_service import compile_recipes
from graph.confirmed_inner_tubes import proofs as cut_proofs
from graph.corner_wall_contacts import proofs as detail_proofs,operations as detail_operations
from graph.core_stack_views import proofs as core_proofs,operations as core_operations
from graph.laminar_stage_gauges import proofs as stage_proofs,expected_operations as stage_operations
from graph.packaging_fit import review as packing_review
from graph.drawing_sync import assembly_sync_review
from backend.services.curved_wall_service import review as forming_review
from cad.geometry import near,snapshot
from cad.edit_engine import digest
sys.stdout.reconfigure(encoding='utf8')


def readback(receipt_file,source,c,plan):
    import ezdxf
    receipt=json.loads(receipt_file.read_text(encoding='utf8'));folder=storage.folder(receipt['document_id'])/'revisions'/receipt['revision_id']
    revision=json.loads((folder/'revision.json').read_text(encoding='utf8'));dxf=folder/'reopen-selection/modified.dxf';doc=ezdxf.readfile(dxf)
    mapping={ref:o['ref'] for o in revision['validation']['changes'] for ref in o.get('original_refs',[o['ref']])}
    entity=lambda ref:doc.entitydb[mapping.get(ref,ref).split('/')[-1]]
    with contextlib.redirect_stdout(io.StringIO()):panel_readback(receipt_file,source,c,plan)
    native_ops=[]
    from graph.packing_detail_lengths import bindings as packing_length_bindings
    packing_lengths=packing_length_bindings(plan,c)
    for proof in packing_lengths:native_ops.extend(proof['operations'])
    for proof in core_proofs(plan,c):native_ops.extend(core_operations(proof,c))
    for proof in detail_proofs(plan,c):native_ops.extend(detail_operations(proof,c))
    for proof in stage_proofs(plan,c):native_ops.extend(stage_operations(proof,c))
    for op in native_ops:
        if op.action=='replace_geometry':assert near(snapshot(entity(op.ref)),json.loads(op.after),1e-5),op.ref
        elif op.action=='move_insert':assert near(list(entity(op.ref).dxf.insert),op.xyz,1e-5),op.ref
        elif op.action=='move_text':
            from cad.text_motion import anchor
            assert near(anchor(entity(op.ref)),op.xyz,1e-5),op.ref
            assert (entity(op.ref).text if entity(op.ref).dxftype()=='MTEXT' else entity(op.ref).dxf.text)==json.loads(op.before)['text']
        elif op.action=='replace_text':
            e=entity(op.ref);assert (e.text if e.dxftype()=='MTEXT' else e.dxf.text)==op.after,op.ref
        elif op.action=='table_cell':
            from cad.table_data import table_cells
            cell=next(v for v in table_cells(dxf)[mapping.get(op.ref,op.ref)] if v['index']==op.cell_index)
            assert cell['raw_text']==op.after,op.ref
    angle_checks=[]
    for proof in core_proofs(plan,c):
        for op in core_operations(proof,c):
            e=entity(op.ref)
            if e.dxftype()!='DIMENSION' or e.dxf.dimtype & 15!=2:continue
            text=' '.join(t.text if t.dxftype()=='MTEXT' else t.dxf.text for t in doc.blocks[e.dxf.geometry] if t.dxftype() in ('TEXT','MTEXT'))
            assert '90' in text and '270' not in text,(op.ref,text)
            assert near(e.dxf.actual_measurement,math.pi/2,1e-6),(op.ref,e.dxf.actual_measurement)
            angle_checks.append(op.ref)
    cuts=[]
    from cad.dimensions import native_tolerance,text_side,dimension_snapshot
    source_doc=ezdxf.readfile(source)
    for proof in packing_lengths:
        for detail in proof['details']:
            assert all(near(entity(ref).get_measurement()*abs(entity(ref).override().get('dimlfac',1)),proof['after_spec_mm'][-1],1e-5) for ref in detail['dimension_refs'])
            for ref in detail['stationary_refs']:assert near(snapshot(entity(ref)),snapshot(source_doc.entitydb[ref.split('/')[-1]]),1e-5),ref
    for proof in core_proofs(plan,c):
        if proof['status']!='measured_symmetric_core_front':continue
        before=source_doc.entitydb[proof['height_dimension_ref']];after=entity(proof['height_dimension_ref'])
        side0=text_side(before,dimension_snapshot(before));side1=text_side(after,dimension_snapshot(after))
        assert side0 and side1 and side0[1]*side1[1]>0,'Nhãn chiều cao đổi phía so với bản nguồn'
    side_checks=[]
    for proof in core_proofs(plan,c):
        if proof['status']!='measured_paired_core_side':continue
        def level(i):
            g=snapshot(entity(proof['face_evidence_refs'][i][0]))
            return g['start'][1] if 'start' in g else g['points'][0][1]
        actual_height=level(5)-level(0);middle_gauge=level(3)-level(2)
        assert near(actual_height,proof['core_height_after_mm'],1e-5) and near(middle_gauge,1,1e-5)
        side_checks.append(dict(width_dimension_ref=proof['width_dimension_ref'],height_mm=actual_height,middle_gauge_mm=middle_gauge,
            checked_operations=len(core_operations(proof,c))))
    for proof in cut_proofs(plan,c):
        e=entity(proof['dimension_ref']);before=source_doc.entitydb[proof['dimension_ref']]
        assert near(snapshot(e),proof['after'],1e-5) and near(e.get_measurement(),proof['native_measured_span_mm'],1e-5)
        assert e.override().get('dimlfac',1)==1 and near(native_tolerance(e),native_tolerance(before),1e-8)
        rendered=' '.join(t.text if t.dxftype()=='MTEXT' else t.dxf.text for t in doc.blocks[e.dxf.geometry] if t.dxftype() in ('TEXT','MTEXT'))
        assert rendered.count('0.5')==1,(proof['dimension_ref'],rendered)
        cuts.append(dict(part_code=proof['part_code'],cut_length_mm=proof['target_nominal_mm'],native_cropped_span_mm=e.get_measurement(),tolerance_rendered_once=True))
    from cad.table_data import table_cells
    from cad.broken_tube import tube_spec
    from backend.services.design_choices import sheet_spec
    cells=table_cells(dxf);verified_rows=[];cut_codes={p['part_code']:p['target_nominal_mm'] for p in cut_proofs(plan,c)};stage_codes={p['part_code']:p['after_mm'] for p in stage_proofs(plan,c)}
    for t in c['entities']:
        for row in t.get('bom',{}).get('rows',[]):
            code=row['part_code']
            if code not in cut_codes and code not in stage_codes:continue
            cell=row['cells']['description'];text=next(v['raw_text'] for v in cells[mapping.get(t['ref'],t['ref'])] if v['index']==cell['index'])
            if code in cut_codes:assert near(tube_spec(text)[-1],cut_codes[code],1e-5)
            else:assert near(sheet_spec(text)[0],stage_codes[code],1e-5)
            qty=row['cells']['quantity'];quantity=next(v['raw_text'] for v in cells[mapping.get(t['ref'],t['ref'])] if v['index']==qty['index'])
            assert quantity==qty['raw_text'];verified_rows.append(dict(table_ref=t['ref'],part_code=code,quantity=quantity))
    # Struck historical labels are preserved; they are not live gauge DIMs.
    for ref in ('3E1C0E','3F6238'):
        assert entity(ref).text==source_doc.entitydb[ref].text
    assert digest(source)==c['source_hash']
    from backend.services.revision_service import revision_preview
    from cad.vision import rasterize_svg
    for sid,name in [('3ADF05','core-front-after'),('3B3987','weld-details-after'),('3A1991','member4-cut-after'),('3A1D79','member5-cut-after')]:
        svg=revision_preview(receipt['document_id'],receipt['revision_id'],sid);(receipt_file.parent/(name+'.svg')).write_text(svg,encoding='utf8');(receipt_file.parent/(name+'.png')).write_bytes(rasterize_svg(svg,width=1600))
    result=dict(revision_id=receipt['revision_id'],plan_id=receipt['plan_id'],dwg=receipt['dwg'],dwg_hash=receipt['dwg_hash'],
        core_front_height_mm=695,core_side_readback=side_checks,core_front_member_length_mm=692,core_end_clearances_mm=[.5,.5],laminar_stage_gauge_mm=1,
        detail_D_wall_mm=1.2,detail_D_plate_gauges_mm=[1,1],verified_new_native_operations=len(native_ops),cuts=cuts,native_bom_checks=verified_rows,
        native_quarter_sectors_verified=angle_checks,
        source_height_annotation_side_preserved=True,
        packing_cut_lengths=[{k:v for k,v in p.items() if k not in ('operations','edits')} for p in packing_lengths],
        source_unchanged=True,complete_product_backup=False,complete_packaging=False,
        remaining=['Còn hình cụm phối cảnh và các mặt lắp chưa xác định của C4','Còn chi tiết lắp cạnh cung Detail C','Còn các hình tách rời/đóng gói chưa gắn đủ'])
    storage.write_json(receipt_file.parent/'core-stage-readback.json',result);print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


def checked_context(source,proposal):
    # Use precisely the context rebuilt by the production apply endpoint,
    # rather than an older all-frame feature cache.
    from backend.services.change_service import context_for
    from backend.services.revision_service import current_impact
    from backend.services.design_choices import attach
    from cad.measured_features import index
    c=context_for(source,proposal['targets']);attach(c,storage.folder(proposal['document_id']))
    c['root_target_ids'],c['root_bom_refs']=proposal['root_target_ids'],proposal['root_bom_refs']
    c['part_graph']=current_impact(proposal['document_id'],proposal,source,c);c['source_features']=index(c,c['part_graph'])
    return c


def main():
    started=time.monotonic();folder=storage.folder('34ee84f35e1a44fb81c56044397a0fff');source=folder/storage.read_status(folder.name)['dxf']
    base=json.loads((folder/'change-plans/a7c123c47b0a49ac90a6429b62afd838.json').read_text(encoding='utf8'));c=checked_context(source,base)
    from backend.services.compound_planner import compile_bundle
    from graph.packaging_fit import synchronize as sync_packing
    print('Compiling current request against the production scope',flush=True)
    plan,audit=compile_bundle(c,base['request'],base.get('clarifications'))
    assert plan is not None and not plan.questions,audit
    plan=sync_packing(plan,c)
    storage.write_json(Path('storage/validation-fixtures/c4-mount-links-2026-10-20/recompiled-plan.json'),plan.model_dump())
    assert len(core_proofs(plan,c))==2 and len(stage_proofs(plan,c))==3 and len(cut_proofs(plan,c))==2 and len(detail_proofs(plan,c))==1
    print('Compiled',len(plan.operations),'checked operations',flush=True)
    packing=packing_review(plan,c);assembly=assembly_sync_review(plan,c);forming=forming_review(plan,c)
    proposal=dict(base,id=uuid.uuid4().hex,checked_preview_plan=plan.model_dump(),request_review=audit,impact_graph=c['part_graph'],packaging_review=packing,drawing_sync=assembly,forming_review=forming)
    proposal['plan']=dict(base['plan'],summary='Bản xem trước đã nối hình đứng/cạnh C4, lót góc 758 mm, bản chi tiết và BOM đóng gói.',questions=[
        'Còn phối cảnh và các mặt lắp chưa xác định của C4 cùng các hình cụm/công đoạn khác.',
        'Còn chi tiết lắp cạnh cung Detail C và các lớp đệm/góc đóng gói chưa gắn đủ liên kết; cung trong và DIM độ dày đã có kiểm chứng riêng.'])
    proposal['message']='Đã mở rộng phần sửa được kiểm chứng; đây vẫn là DWG xem trước một phần, chưa phải backup toàn sản phẩm.'
    storage.write_json(folder/'change-plans'/(proposal['id']+'.json'),proposal)
    export_checked_preview(base['document_id'],proposal['id'],source,c,plan,audit,assembly,packing,forming,started,backup_name='Dauphine-PREVIEW-C4-lot-goc758-2026-10-20.dwg')
    receipts=[p for p in Path('storage/validation-fixtures/dauphine-combined').glob('*/receipt.json') if json.loads(p.read_text(encoding='utf8')).get('plan_id')==proposal['id']]
    assert len(receipts)==1;readback(receipts[0],source,c,plan)


if __name__=='__main__':
    from dotenv import load_dotenv
    load_dotenv('.env',override=True,encoding='utf-8-sig')
    if len(sys.argv)==3 and sys.argv[1]=='--readback':
        path=Path('storage/validation-fixtures/dauphine-combined')/sys.argv[2]/'receipt.json';r=json.loads(path.read_text(encoding='utf8'));folder=storage.folder(r['document_id']);source=folder/storage.read_status(r['document_id'])['dxf'];p=json.loads((folder/'change-plans'/(r['plan_id']+'.json')).read_text(encoding='utf8'));c=checked_context(source,p)
        readback(path,source,c,DrawingChangePlan.model_validate(p['checked_preview_plan']))
    else:main()
