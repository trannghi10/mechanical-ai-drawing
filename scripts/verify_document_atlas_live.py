"""Read existing local documents only; preserve source hashes in a receipt."""
import json
import time
from pathlib import Path
import requests
from cad.edit_engine import digest

ROOT=Path(__file__).resolve().parents[1]
DOCUMENTS=('51ec94944c4443b19fb8d5bd7930a6dd','1c7d831296ff402bb1a838479063a99d',
           '17466fcb1c59489985408c027ef56611','baf461e9c2764a5ba9000a48772f846c')
BASE='http://127.0.0.1:8765'


def response(method,path,**kwargs):
    result=requests.request(method,BASE+path,timeout=60,**kwargs);result.raise_for_status();return result.json()


def main():
    evidence=ROOT/'storage/validation-fixtures/document-atlas-2026-10-22';evidence.mkdir(parents=True,exist_ok=True)
    jobs=[]
    for did in DOCUMENTS:
        folder=ROOT/'storage/documents'/did
        source=next(p for p in (folder/'original.dwg',folder/'original.dxf') if p.is_file())
        before=digest(source);job=response('POST',f'/documents/{did}/atlas')
        jobs.append(dict(document_id=did,id=job['id'],source=str(source.relative_to(ROOT)),source_sha256=before))
        print(json.dumps(dict(document_id=did,job_id=job['id'],status=job['status'])),flush=True)
    states={};deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        pending=False
        for entry in jobs:
            did=entry['document_id'];job=response('GET',f'/documents/{did}/atlas/{entry["id"]}')
            state=(job['status'],job.get('phase'))
            if states.get(did)!=state:
                states[did]=state;print(json.dumps(dict(document_id=did,status=job['status'],phase=job.get('phase'))),flush=True)
            pending|=job['status'] in ('queued','running')
            entry['status']=job['status']
        if not pending:break
        time.sleep(2)
    for entry in jobs:
        did=entry['document_id'];jid=entry['id']
        assert entry['status']=='ready',entry
        report=response('GET',f'/documents/{did}/atlas/{jid}/report')
        pages=report['pages'];folder=ROOT/'storage/documents'/did/'document-atlas'/jid
        assert all(digest(folder/page['file'])==page['sha256'] for page in pages)
        assert sum(page['count'] for page in pages)==report['placed_record_count']
        dim_page=response('GET',f'/documents/{did}/atlas/{jid}/entities',params={'kind':'DIMENSION','limit':2})
        entry.update({key:report[key] for key in ('placed_record_count','traversal_complete','all_placed_data_read','metadata_only_types','partial_types','gap_count','graph_error')})
        entry.update(part_count=len(report['parts']),frame_count=len(report['frames']),verified_pages=len(pages),dimension_count=dim_page['match_count'],
                     source_unchanged=digest(ROOT/entry['source'])==entry['source_sha256'])
        assert entry['source_unchanged']
    (evidence/'verification.json').write_text(json.dumps(dict(documents=jobs,customer_data_sent_to_cloud=False),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(jobs,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
