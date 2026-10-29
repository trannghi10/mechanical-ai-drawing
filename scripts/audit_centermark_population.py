"""Validate newly discovered CenterMark pairs individually through production HTTP jobs.

Each output is an isolated validation copy. No revision or mating decision is created.
"""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import httpx
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_id');parser.add_argument('selection_id');parser.add_argument('dependency_inspection_id')
    parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    if (output/'started.json').exists():raise ValueError('Audit output already exists; inspect saved job IDs before resuming.')
    base=f'/documents/{args.document_id}';source=storage.folder(args.document_id)/'original.dwg';source_hash=digest(source)
    rows=[]
    with httpx.Client(base_url='http://127.0.0.1:8765',trust_env=False,timeout=120) as client:
        def request(method,path,**kw):
            response=client.request(method,path,**kw);response.raise_for_status();return response.json()
        context=request('POST',base+'/autocad/context',json=dict(ids=[args.selection_id]))
        found=request('GET',base+'/autocad/jobs/'+args.dependency_inspection_id+'/centermark-candidates')
        assert found['source_hash']==context['original_source_hash']==source_hash
        pairs=[p for p in found['items'] if p['circle_handle'] not in ('3B7FD1','3B7FF1')]
        storage.write_json(output/'started.json',dict(document_id=args.document_id,source_hash=source_hash,pairs=pairs))
        for index,pair in enumerate(pairs):
            before=pair['source_center'];delta=[(index+1)*.125,-.25,0];after=[a+b for a,b in zip(before,delta)]
            operation=dict(action='translate_centermark',handle=pair['circle_handle'],mark_handle=pair['mark_handle'],
                action_handle=pair['action_handle'],owner_handle=pair['owner_handle'],expected_type='CIRCLE',before=json.dumps(before),after=json.dumps(after))
            body=dict(inspection_id=context['inspection_id'],dependency_inspection_id=args.dependency_inspection_id,
                      source_hash=source_hash,ids=[args.selection_id],operations=[operation])
            job=request('POST',base+'/autocad/native-edits',json=body)
            row=dict(circle_handle=pair['circle_handle'],mark_handle=pair['mark_handle'],job_id=job['id'],delta=delta,status=job['status'])
            rows.append(row);storage.write_json(output/'progress.json',dict(items=rows))
            deadline=time.monotonic()+300
            while job['status'] not in ('ready','failed'):
                if time.monotonic()>deadline:raise RuntimeError('Job remains active; audit its saved ID: '+job['id'])
                time.sleep(1);job=request('GET',base+'/autocad/jobs/'+job['id'])
            row.update(status=job['status'],message=job['message'])
            if job['status']=='ready':
                receipt=request('GET',base+'/autocad/jobs/'+job['id']+'/files/receipt.json')
                effect,=job['native_summary']['centermark_effects']
                assert receipt['source_sha256']==source_hash and effect['persisted_state_verified_before_evaluation'] is True and effect['reopened_evaluation_stable'] is True
                row.update(output_hash=receipt['hashes']['modified.dwg'],unselected_inventory_entries_verified=effect['unselected_inventory_entries_verified'])
            else:
                error_path=storage.folder(args.document_id)/'aps-jobs'/job['id']/'autocad-plugin-error.json'
                if error_path.exists():row['native_error']=json.loads(error_path.read_text(encoding='utf8'))['message']
            assert digest(source)==source_hash
            storage.write_json(output/'progress.json',dict(items=rows))
            print(json.dumps(row,ensure_ascii=True),flush=True)
    report=dict(status='completed_centermark_population_audit',items=rows,passed=sum(r['status']=='ready' for r in rows),
                failed=sum(r['status']=='failed' for r in rows),source_hash=source_hash,source_unchanged=digest(source)==source_hash,
                customer_revision_created=False,complete_product_backup=False)
    storage.write_json(output/'receipt.json',report);print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()
