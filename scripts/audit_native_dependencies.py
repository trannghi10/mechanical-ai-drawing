"""Inspect selected object dependencies in native AutoCAD; do not edit CAD."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import requests
from backend.services import catalog_service as storage
from cad.edit_engine import digest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('document_id');p.add_argument('--handle',action='append',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    folder=storage.folder(args.document_id);source=folder/'original.dwg';before=digest(source)
    session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765'
    route=f'/documents/{args.document_id}/autocad/jobs';r=session.post(base+route,json=dict(handles=args.handle),timeout=30);r.raise_for_status();job=r.json();deadline=time.monotonic()+300
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True);storage.write_json(output/'started.json',job)
    while job['status'] not in ('ready','failed'):
        if time.monotonic()>deadline:raise RuntimeError('Native inspection still active: '+job['id'])
        time.sleep(1);r=session.get(base+route+'/'+job['id'],timeout=30);r.raise_for_status();job=r.json()
    if job['status']!='ready':raise RuntimeError(job)
    r=session.get(base+route+'/'+job['id']+'/files/inventory.json',timeout=60);r.raise_for_status();inventory=r.json();storage.write_json(output/'inventory.json',inventory)
    graph=inventory['native_dependencies'];assert graph['requested_roots']==sorted(set(args.handle)),graph
    assert before==digest(source)
    receipt=dict(document_id=args.document_id,job_id=job['id'],mode='inspect',provider='autocad',original_dwg_hash=before,source_unchanged=True,
        native_dependency_status=graph['status'],node_count=len(graph['nodes']),edge_count=len(graph['edges']),errors=graph['errors'],truncated=graph['truncated'],
        customer_revision_created=False,edit_authorization=False)
    storage.write_json(output/'receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=True))


if __name__=='__main__':main()
