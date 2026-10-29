"""Exercise the local/cloud rectangle API with real native jobs and downloadable DWG."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services import catalog_service as storage,aps_jobs
    from cad.edit_engine import digest
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--provider',choices=['autocad','aps'],default='autocad');parser.add_argument('--target',type=float,default=120);args=parser.parse_args()
    if args.output.exists():raise ValueError('New evidence directory required')
    args.output.mkdir(parents=True);source_hash=digest(args.source)
    with args.source.open('rb') as stream:state=storage.create_document('synthetic-rectangle-api.dwg',stream,read_backend_override=args.provider)
    storage.write_json(args.output/'import-started.json',state);deadline=time.monotonic()+300
    while state['status'] not in ('ready','failed'):
        if time.monotonic()>deadline:raise TimeoutError(state['id'])
        time.sleep(1);state=storage.read_status(state['id'])
    assert state['status']=='ready',state
    document_id=state['id'];client=TestClient(app)
    body=dict(inspection_id=state['native_import_job_id'],polyline_handle='2F',dimension_handle='30',target_width_mm=args.target,source_hash=source_hash)
    url=f'/documents/{document_id}/{args.provider}/rectangle-stretch'
    response=client.post(url,json=body);assert response.status_code==202,response.text
    started=response.json();storage.write_json(args.output/'edit-started.json',started)
    job=aps_jobs.wait(document_id,started['id'],timeout=300)
    status=client.get(f'/documents/{document_id}/{args.provider}/jobs/{job["id"]}');assert status.status_code==200 and status.json()['status']=='ready',status.text
    download=client.get(status.json()['download_url']);assert download.status_code==200
    dwg=aps_jobs.artifact(document_id,job['id'],'modified.dwg')
    assert download.content==dwg.read_bytes()
    again=client.post(url,json=body);assert again.status_code==202 and again.json()['id']==job['id'],again.text
    wrong=client.post(url,json=dict(body,source_hash='0'*64));assert wrong.status_code==422,wrong.text
    for name in ('modified.dwg','roundtrip.dxf','inventory.json','receipt.json'):
        (args.output/name).write_bytes(aps_jobs.artifact(document_id,job['id'],name).read_bytes())
    assert digest(args.source)==source_hash and digest(storage.folder(document_id)/'original.dwg')==source_hash
    report=dict(status='validated_cloud_rectangle_stretch_api' if args.provider=='aps' else 'validated_local_rectangle_stretch_api',document_id=document_id,inspection_id=body['inspection_id'],edit_id=job['id'],source_sha256=source_hash,output_sha256=digest(dwg),download_verified=True,retry_deduplicated=True,stale_source_rejected=True,source_unchanged=True,solver_summary=started['solver_summary'],customer_revision_created=False,aps_cloud_verified=args.provider=='aps',provider=args.provider,target_width_mm=args.target)
    storage.write_json(args.output/'api-verification.json',report);print(json.dumps(report))


if __name__=='__main__':main()
