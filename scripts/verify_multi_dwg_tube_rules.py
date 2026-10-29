"""Local HTTP + AutoCAD regression for distinct, explicitly synthetic DWGs.

Uses the production planner/revision/export routes and an independently
authored coordinate oracle. These files are never counted as company samples.
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
os.environ.update(AI_PROVIDER='native',AI_OFFLINE='1',CAD_READ_BACKEND='autocad',CAD_DWG_BACKEND='autocad')
import ezdxf
from cad.edit_engine import digest
from cad.geometry import snapshot,near
from cad.frame_geometry import transform
from cad.tube_stock import parse
from backend.services import catalog_service as storage,aps_jobs
from backend.services.change_service import context_for
from test_tube_sections import tube_fixture
from verify_whole_file_edit_dwg import api,wait_read


def auxiliary(did):
    state=storage.read_status(did)
    state.update(synthetic_test=True,auxiliary=True)
    storage.write_json(storage.folder(did)/'status.json',state)


def verify_geometry(path,original,targets,refs,matrix,size,description):
    width,height,length,old,new,*_=size
    actual=ezdxf.readfile(path);source=ezdxf.readfile(original)
    inverse=matrix.copy();inverse.inverse()
    local=transform('LWPOLYLINE',snapshot(actual.entitydb[refs['inner']]),inverse)
    if not near([min(p[i] for p in local['points']) for i in (0,1)],[new,new],1e-6):raise ValueError('Inner minimum differs from authored oracle')
    if not near([max(p[i] for p in local['points']) for i in (0,1)],[width-new,height-new],1e-6):raise ValueError('Inner maximum differs from authored oracle')
    wall=abs(actual.entitydb[refs['wall']].get_measurement())
    longitudinal=abs(actual.entitydb[refs['length']].get_measurement())
    if abs(wall-new)>1e-6 or abs(longitudinal-length)>1e-6:raise ValueError('Measured native DIM differs from authored oracle')
    for ref in ('outer','outside'):
        if not near(snapshot(actual.entitydb[refs[ref]]),snapshot(source.entitydb[refs[ref]]),1e-6):raise ValueError('Untouched geometry changed: '+ref)
    context=context_for(path,targets)
    rows=[r['description'] for e in context['entities'] for r in e.get('bom',{}).get('rows',[])]
    expected='Sắt hộp '+parse(description,old).with_wall(new)+'mm'
    if rows!=[expected]:raise ValueError('BOM differs from authored expectation: '+str(rows))
    return dict(inner_bbox_mm=[new,new,width-new,height-new],wall_dimension_mm=wall,length_dimension_mm=longitudinal,
                outer_unchanged=True,outside_circle_unchanged=True,bom=rows)


def main():
    from scripts.verify_company_whole_file import require_local
    require_local()
    base=ROOT/'storage/validation-fixtures'/('multi-dwg-native-'+uuid.uuid4().hex[:12]);base.mkdir(parents=True)
    report=dict(status='running',synthetic=True,company_dwg=False,cloud_used=False,production_release=False,engineer_accepted=False,cases=[])
    receipt=base/'receipt.json'
    for name,size in [('rectangular-rotated-37',(40,80,215,3,2,37,False)),('square-horizontal',(14,14,321,1.2,1,90,True))]:
        case=base/name;source,targets,refs,matrix,request,description=tube_fixture(case,*size)
        source_hash=digest(source)
        with source.open('rb') as stream:bootstrap=storage.create_document(name+'-bootstrap.dxf',stream,read_backend_override='autocad')
        bid=bootstrap['id'];auxiliary(bid)
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            state=storage.read_status(bid)
            if state['status']=='ready':break
            if state['status']=='failed':raise ValueError(state.get('error',state))
            time.sleep(1)
        if state['status']!='ready':raise TimeoutError('Bootstrap native conversion')
        auxiliary(bid)
        native=aps_jobs.artifact(bid,state['native_import_job_id'],'modified.dwg')
        source_dwg=case/'before.dwg';source_dwg.write_bytes(native.read_bytes());before_hash=digest(source_dwg)
        with source_dwg.open('rb') as stream:uploaded=api('POST','/documents',files={'file':(name+'.dwg',stream,'application/octet-stream')})
        did=uploaded['id'];auxiliary(did);state=wait_read(did);auxiliary(did)
        if state['read_backend']!='autocad':raise ValueError('Native import required')
        original=storage.folder(did)/state['dxf'];native_hash=digest(original)
        frames=api('GET',f'/documents/{did}/sheets')['items']
        if not {t['id'] for t in targets}<={f['id'] for f in frames}:raise ValueError('Drawn source frames not discovered')
        print(json.dumps(dict(case=name,stage='native_imported',document_id=did,frames=len(frames))),flush=True)
        plan=api('POST',f'/documents/{did}/change-plans',json=dict(ids=[t['id'] for t in targets],request=request))
        if not plan['execution_available']:raise ValueError(plan['plan']['questions'])
        if not plan['planner'].startswith('checked_'):raise ValueError('Expected source-checked compiler')
        revision=api('POST',f'/documents/{did}/change-plans/{plan["id"]}/apply',json=dict(preview_only=True))
        rid=revision['id'];route=f'/documents/{did}/revisions/{rid}'
        job=api('POST',route+'/exports',json=dict(format='dwg',scope='document',preview=True))
        deadline=time.monotonic()+600
        while job['status'] not in ('ready','failed') and time.monotonic()<deadline:
            time.sleep(1);job=api('GET',route+'/exports/'+job['id'])
        if job['status']!='ready':raise ValueError(job)
        import requests
        response=requests.get('http://127.0.0.1:8765'+job['download_url'],timeout=60);response.raise_for_status()
        output=case/'after.dwg';output.write_bytes(response.content);output_hash=digest(output)
        native_check=storage.folder(did)/'revisions'/rid/'reopen/modified.dxf'
        verified=verify_geometry(native_check,original,targets,refs,matrix,size,description)
        with output.open('rb') as stream:reimported=api('POST','/documents',files={'file':(name+'-independent.dwg',stream,'application/octet-stream')})
        reopened_id=reimported['id'];auxiliary(reopened_id);again=wait_read(reopened_id);auxiliary(reopened_id)
        if again['read_backend']!='autocad':raise ValueError('Independent native reopen required')
        verified_again=verify_geometry(storage.folder(reopened_id)/again['dxf'],original,targets,refs,matrix,size,description)
        if digest(source)!=source_hash or digest(source_dwg)!=before_hash or digest(original)!=native_hash or digest(output)!=output_hash:raise ValueError('Source or output changed during verification')
        report['cases'].append(dict(name=name,status='passed',synthetic=True,company_dwg=False,document_id=did,
            plan_id=plan['id'],planner=plan['planner'],revision_id=rid,reopened_document_id=reopened_id,
            source_sha256=before_hash,output_sha256=output_hash,after_dwg=str(output.relative_to(ROOT)),
            dimensions=dict(width=size[0],height=size[1],length=size[2],old_wall=size[3],new_wall=size[4],rotation_degrees=size[5]),
            native_save_reopen=verified,independent_native_open=verified_again,source_unchanged=True))
        receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(dict(case=name,status='passed',independent_native_open=True,planner=plan['planner'])),flush=True)
    report['status']='passed';receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status='passed',cases=len(report['cases']),receipt=str(receipt.relative_to(ROOT)))),flush=True)


if __name__=='__main__':main()
