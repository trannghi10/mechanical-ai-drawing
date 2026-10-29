"""Local AutoCAD proof: whole-file identity -> linked edit -> saved/reopened DWG.

Synthetic authored engineering expectations; no customer file is modified or
sent to a cloud provider. Detection uses drawn borders, not seeded sheet IDs.
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=True,encoding='utf-8-sig')
os.environ.update(AI_PROVIDER='native',AI_OFFLINE='1',CAD_READ_BACKEND='autocad',CAD_DWG_BACKEND='autocad')
import ezdxf
import requests
from test_native_contacts import contact_fixture
from backend.services import catalog_service as storage, aps_jobs
from backend.services.change_service import context_for
from cad.edit_engine import digest
from cad.geometry import snapshot, near

BASE='http://127.0.0.1:8765'
ROOT=Path(__file__).resolve().parents[1]


def api(method,path,**kwargs):
    response=requests.request(method,BASE+path,timeout=180,**kwargs)
    if not response.ok:raise RuntimeError(f'{path}: {response.status_code} {response.text[:1500]}')
    return response.json()


def wait_read(did):
    deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        state=api('GET',f'/documents/{did}')
        if state['status']=='ready':return state
        if state['status']=='failed':raise RuntimeError(state.get('error',state))
        time.sleep(1)
    raise RuntimeError('Timed out reading local DWG')


def main():
    base=ROOT/'storage/validation-fixtures'/('whole-file-edit-'+uuid.uuid4().hex[:12]);base.mkdir(parents=True)
    source,initial,_,_,_,_,outside=contact_fixture(base)
    doc=ezdxf.readfile(source);space=doc.modelspace()
    # Actual source borders, title and unrelated line are part of the fixture.
    for i,t in enumerate(initial['targets']):
        a,b,c,d=t['bbox'];space.add_lwpolyline([(a,b),(c,b),(c,d),(a,d)],close=True)
        space.add_text('BẢN VẼ KIỂM THỬ TOÀN FILE '+str(i),dxfattribs=dict(insert=(a+4,b+4),height=2))
    unrelated=space.add_line((1600,500),(1700,525));doc.saveas(source)
    authored_hash=digest(source)
    # Fixed local native adapter creates the initial DWG from the authored DXF.
    with source.open('rb') as stream:bootstrap=storage.create_document('whole-file-bootstrap.dxf',stream,read_backend_override='autocad')
    folder=storage.folder(bootstrap['id']);status=storage.read_status(bootstrap['id']);status.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',status)
    deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        state=storage.read_status(bootstrap['id'])
        if state['status']=='ready':break
        if state['status']=='failed':raise RuntimeError(state)
        time.sleep(1)
    assert state['status']=='ready',state
    state.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',state)
    native=aps_jobs.artifact(bootstrap['id'],state['native_import_job_id'],'modified.dwg')
    source_dwg=base/'before.dwg';source_dwg.write_bytes(native.read_bytes());before_hash=digest(source_dwg)
    with source_dwg.open('rb') as stream:uploaded=api('POST','/documents',files={'file':('whole-file-linked-edit.dwg',stream,'application/octet-stream')})
    did=uploaded['id'];folder=storage.folder(did)
    status=storage.read_status(did);status.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',status)
    state=wait_read(did);source_dxf=folder/state['dxf'];dxf_hash=digest(source_dxf)
    state.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',state)
    # These API calls discover all source frames and BOM/native identities.
    catalog=api('GET',f'/documents/{did}/catalog');frames=api('GET',f'/documents/{did}/sheets')['items']
    print(json.dumps(dict(stage='imported',document_id=did,frames=len(frames),local_only=True)),flush=True)
    request='Chi tiết số 1 chiều cao từ 100 thành 120 mm, giữ đầu dưới; đồng bộ hình chi tiết và cụm lắp'
    job=api('POST',f'/documents/{did}/planning-jobs',json=dict(request=request,whole_document=True))
    deadline=time.monotonic()+300;last=None
    while time.monotonic()<deadline:
        job=api('GET',f'/documents/{did}/planning-jobs/{job["id"]}')
        current=(job['status'],job['phase'])
        if current!=last:print(json.dumps(dict(stage='planning',status=job['status'],phase=job['phase'],message=job['message']),ensure_ascii=True),flush=True);last=current
        if job['status'] not in ('running','queued'):break
        time.sleep(1)
    assert job['status']=='ready',job
    plan=api('GET',f'/documents/{did}/change-plans/{job["plan_id"]}')
    assert plan['execution_available'],plan['plan']['questions']
    assert plan['whole_document'] and plan['target_resolution']['part_codes']==['PART-A']
    assert plan['document_reading']['status']=='ready' and plan['document_reading']['traversal_complete']
    assert plan['user_request']==request and len(plan['target_ids'])>=2
    revision=api('POST',f'/documents/{did}/change-plans/{plan["id"]}/apply',json=dict(preview_only=True))
    rid=revision['id'];revroot=f'/documents/{did}/revisions/{rid}'
    export=api('POST',revroot+'/exports',json=dict(format='dwg',scope='document',preview=True))
    deadline=time.monotonic()+300
    while export['status'] not in ('ready','failed') and time.monotonic()<deadline:
        time.sleep(1);export=api('GET',revroot+'/exports/'+export['id'])
    assert export['status']=='ready',export
    response=requests.get(BASE+export['download_url'],timeout=60);response.raise_for_status()
    output=base/'after.dwg';output.write_bytes(response.content)
    assert output.read_bytes()[:6]==b'AC1032'
    revision_path=folder/'revisions'/rid;reopened=revision_path/'reopen/modified.dxf'
    assert reopened.is_file()
    after=context_for(reopened,frames)
    before=ezdxf.readfile(source_dxf)
    roots={e.dxf.handle for e in before.modelspace().query('INSERT') if e.dxf.name=='PART-A'}
    part_a=[e for e in after['entities'] if e['type']=='DIMENSION' and e['ref'].split('/')[0] in roots]
    assert len(part_a)>=2 and all(abs(e['scaled_measurement']-120)<1e-6 for e in part_a)
    profiles=[e for e in after['entities'] if e['type']=='LWPOLYLINE' and e['ref'].split('/')[0] in roots]
    assert len(profiles)==2
    for profile in profiles:
        points=profile['geometry']['points'];ys=[point[1] for point in points]
        assert abs(max(ys)-min(ys)-120)<1e-6
        assert abs(min(ys))<1e-6,'Fixed lower edge moved'
    moved=[e for e in after['entities'] if e['type']=='INSERT' and e.get('name')=='PART-B' and abs(e['position'][0]-600)<1e-6]
    assert len(moved)==1 and abs(moved[0]['position'][1]-120)<1e-6
    assert any(e['type']=='DIMENSION' and abs(e.get('scaled_measurement',0)-220)<1e-6 for e in after['entities'])
    rows={r['part_code']:r['description'] for e in after['entities'] for r in e.get('bom',{}).get('rows',[])}
    assert rows['PART-A']=='Bas 2x20x120' and rows['PART-B']=='Bas 2x20x100',rows
    original=ezdxf.readfile(source_dxf);again=ezdxf.readfile(reopened)
    outside_before=[e for e in original.modelspace().query('INSERT') if abs(e.dxf.insert.x-2000)<1e-6]
    assert len(outside_before)==1
    for entity in outside_before:
        actual=again.entitydb[entity.dxf.handle]
        assert actual.dxftype()=='INSERT' and actual.dxf.name==entity.dxf.name
        assert actual.dxf.insert.isclose(entity.dxf.insert,abs_tol=1e-6)
        for key in ('rotation','xscale','yscale','zscale'):
            assert abs(actual.dxf.get(key,0 if key=='rotation' else 1)-entity.dxf.get(key,0 if key=='rotation' else 1))<1e-6
        original_block=original.blocks[entity.dxf.name];actual_block=again.blocks[actual.dxf.name]
        assert len(original_block)==len(actual_block)
        for old,new in zip(original_block,actual_block):
            assert old.dxftype()==new.dxftype()
            if old.dxftype()=='LWPOLYLINE':assert near(snapshot(old),snapshot(new),1e-6)
            if old.dxftype()=='DIMENSION':assert abs(old.get_measurement()-new.get_measurement())<1e-6
    assert near(snapshot(original.entitydb[unrelated.dxf.handle]),snapshot(again.entitydb[unrelated.dxf.handle]),1e-6)
    assert digest(source_dwg)==before_hash and digest(source_dxf)==dxf_hash and digest(source)==authored_hash
    rdata=json.loads((revision_path/'revision.json').read_text(encoding='utf8'))
    assert rdata['dwg_validation']['status']=='validated_roundtrip'
    receipt=dict(status='passed',synthetic_authored_expectations=True,cloud_used=False,document_id=did,planning_job_id=job['id'],
                 atlas_id=plan['document_reading']['atlas_id'],plan_id=plan['id'],revision_id=rid,
                 native_read_backend=state.get('read_backend'),native_export_converter=rdata['dwg_validation']['converter'],
                 detected_frames=len(frames),selected_part='PART-A',root_target_ids=plan['root_target_ids'],expanded_target_ids=plan['target_ids'],
                 before_height_mm=100,after_height_mm=120,assembly_receiver_y_mm=120,overall_height_mm=220,
                 source_part_dimension_count=len(part_a),bom=rows,outside_instances_unchanged=True,outside_line_unchanged=True,
                 source_unchanged=True,before_dwg_sha256=before_hash,after_dwg_sha256=digest(output),
                 roundtrip=rdata['dwg_validation']['status'],after_dwg=str(output.relative_to(ROOT)),
                 production_release=False,engineer_accepted=False)
    (base/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=True,indent=2),flush=True)


def verify_saved(receipt_path):
    """Import the downloaded bytes again, independent of export's readback."""
    receipt_path=Path(receipt_path).resolve();receipt=json.loads(receipt_path.read_text(encoding='utf8'))
    source=ROOT/receipt['after_dwg'];before_hash=digest(source)
    assert before_hash==receipt['after_dwg_sha256'] and receipt['status']=='passed'
    with source.open('rb') as stream:uploaded=api('POST','/documents',files={'file':('whole-file-saved-reopened.dwg',stream,'application/octet-stream')})
    did=uploaded['id'];status=wait_read(did);folder=storage.folder(did)
    assert status['read_backend']=='autocad'
    status.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',status)
    frames=api('GET',f'/documents/{did}/sheets')['items']
    context=context_for(folder/status['dxf'],frames)
    from cad.part_identity import record_identity
    roots={e['ref'] for e in context['entities'] if record_identity(e,{'PART-A'})=='PART-A'}
    assert len(roots)==2,'Saved cloned blocks lost source identity'
    dimensions=[e for e in context['entities'] if e['type']=='DIMENSION' and e['ref'].split('/')[0] in roots]
    profiles=[e for e in context['entities'] if e['type']=='LWPOLYLINE' and e['ref'].split('/')[0] in roots]
    assert len(dimensions)==len(profiles)==2
    assert all(abs(e['scaled_measurement']-120)<1e-6 for e in dimensions)
    assert all(abs(max(p[1] for p in e['geometry']['points'])-min(p[1] for p in e['geometry']['points'])-120)<1e-6 for e in profiles)
    assert all(abs(min(p[1] for p in e['geometry']['points']))<1e-6 for e in profiles)
    moved=[e for e in context['entities'] if e['type']=='INSERT' and record_identity(e,{'PART-B'})=='PART-B' and abs(e['position'][0]-600)<1e-6]
    assert len(moved)==1 and abs(moved[0]['position'][1]-120)<1e-6
    assert any(e['type']=='DIMENSION' and abs(e.get('scaled_measurement',0)-220)<1e-6 for e in context['entities'])
    job=api('POST',f'/documents/{did}/planning-jobs',json=dict(whole_document=True,request='Mã PART-A chiều cao từ 120 thành 110 mm, giữ đầu dưới'))
    deadline=time.monotonic()+180
    while job['status'] in ('queued','running') and time.monotonic()<deadline:
        time.sleep(1);job=api('GET',f'/documents/{did}/planning-jobs/{job["id"]}')
    assert job['status']=='ready',job
    plan=api('GET',f'/documents/{did}/change-plans/{job["plan_id"]}')
    assert plan['execution_available'],plan['plan']['questions']
    assert plan['target_resolution']['part_codes']==['PART-A']
    assert digest(source)==before_hash
    proof=dict(status='passed',independent_native_open=True,read_backend=status['read_backend'],document_id=did,
               dwg_sha256=before_hash,dimension_measurements_mm=[e['scaled_measurement'] for e in dimensions],
               physical_profile_heights_mm=[max(p[1] for p in e['geometry']['points'])-min(p[1] for p in e['geometry']['points']) for e in profiles],
               fixed_lower_edge_y_mm=[min(p[1] for p in e['geometry']['points']) for e in profiles],receiver_y_mm=120,overall_height_mm=220,
               source_identity_preserved=True,repeat_planning_available=True,repeat_plan_id=plan['id'],
               repeat_plan_applied=False,source_unchanged=True,cloud_used=False,engineer_accepted=False)
    (receipt_path.parent/'independent-reopen.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(proof,ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--reopen':verify_saved(sys.argv[2])
    else:main()
