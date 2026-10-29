"""Validate a batch of independent CenterMark translations on a native-import copy."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import httpx
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_id');parser.add_argument('selection_id');parser.add_argument('--count',type=int,required=True)
    parser.add_argument('--vary-deltas',action='store_true');parser.add_argument('--output',required=True)
    parser.add_argument('--reject-second-action-handle',help='Developer-only negative check below the API: use a wrong action on pair two.')
    args=parser.parse_args();output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    if (output/'started.json').exists():raise ValueError('Inspect the saved job before starting another audit in this directory.')
    base=f'/documents/{args.document_id}';source=storage.folder(args.document_id)/'original.dwg';source_hash=digest(source)
    with httpx.Client(base_url='http://127.0.0.1:8765',timeout=120,trust_env=False) as client:
        def request(method,path,**kw):
            response=client.request(method,path,**kw)
            if response.is_error:raise RuntimeError(f'{response.status_code}: {response.text[:1000]}')
            return response.json()
        def wait(job):
            deadline=time.monotonic()+300
            while job['status'] not in ('ready','failed'):
                if time.monotonic()>deadline:raise RuntimeError('Job remains active: '+job['id'])
                time.sleep(1);job=request('GET',base+'/autocad/jobs/'+job['id'])
            if job['status']!='ready':raise RuntimeError(job)
            return job
        context=request('POST',base+'/autocad/context',json=dict(ids=[args.selection_id]))
        inspection=request('POST',base+'/autocad/centermark-inspections',json=dict(ids=[args.selection_id]))
        storage.write_json(output/'started.json',dict(inspection_id=inspection['id'],document_id=args.document_id,source_hash=source_hash))
        inspection=wait(inspection)
        found=request('GET',base+'/autocad/jobs/'+inspection['id']+'/centermark-candidates')
        assert found['source_hash']==context['original_source_hash']==source_hash and 1<=args.count<=min(16,len(found['items']))
        pairs=found['items'][:args.count];ops=[]
        for index,pair in enumerate(pairs):
            before=pair['source_center'];dx=1.25+(index*.125 if args.vary_deltas else 0);dy=-.75
            ops.append(dict(action='translate_centermark',handle=pair['circle_handle'],mark_handle=pair['mark_handle'],action_handle=pair['action_handle'],owner_handle=pair['owner_handle'],expected_type='CIRCLE',before=json.dumps(before),after=json.dumps([before[0]+dx,before[1]+dy,before[2]])))
        body=dict(inspection_id=context['inspection_id'],dependency_inspection_id=inspection['id'],source_hash=source_hash,ids=[args.selection_id],operations=ops)
        storage.write_json(output/'request.json',body)
        duplicate=client.post(base+'/autocad/native-edits',json=dict(body,operations=[ops[0],ops[0]]))
        assert duplicate.status_code==422,duplicate.text
        if args.reject_second_action_handle:
            assert len(ops)>=2
            from dotenv import load_dotenv
            load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
            from backend.services import aps_jobs,aps_repository
            from backend.services.aps_client import APSError
            ops[1]['action_handle']=args.reject_second_action_handle
            storage.write_json(output/'negative-request.json',body)
            scopes={op[key] for op in ops for key in ('handle','mark_handle')}
            # Deliberately test the native preflight below the stricter API binding.
            job=aps_jobs.start(args.document_id,provider='autocad',mode='edit',operations=ops,scope_handles=scopes,expected_source_hash=source_hash)
            storage.write_json(output/'edit-started.json',job)
            try:
                aps_jobs.wait(args.document_id,job['id'],timeout=300)
            except APSError:
                record=aps_repository.read(args.document_id,job['id'])
                job_folder=storage.folder(args.document_id)/'aps-jobs'/job['id']
                error=json.loads((job_folder/'autocad-plugin-error.json').read_text(encoding='utf8'))
                assert record['status']=='failed' and error['message']=='CenterMark contract dependency/owner mismatch'
                assert not (job_folder/'result').exists() and digest(source)==source_hash
                report=dict(status='validated_native_batch_rejection',edit_id=job['id'],pair_count=len(ops),
                            wrong_pair_index=1,reason=error['message'],accepted_result_created=False,source_unchanged=True,customer_revision_created=False)
                storage.write_json(output/'receipt.json',report);print(json.dumps(report),flush=True);return
            raise AssertionError('Native batch unexpectedly accepted a wrong second action')
        job=request('POST',base+'/autocad/native-edits',json=body)
        storage.write_json(output/'edit-started.json',job);job=wait(job)
        receipt=request('GET',base+'/autocad/jobs/'+job['id']+'/files/receipt.json')
        effects=job['native_summary']['centermark_effects']
        assert receipt['applied_operations']==len(ops) and len(effects)==len(ops) and all(e['selected_pair_count']==len(ops) and e['persisted_state_verified_before_evaluation'] and e['reopened_evaluation_stable'] for e in effects)
        assert digest(source)==source_hash
        report=dict(status='validated_native_centermark_batch',document_id=args.document_id,edit_id=job['id'],inspection_id=inspection['id'],
                    pair_count=len(ops),varying_deltas=args.vary_deltas,output_hash=receipt['hashes']['modified.dwg'],source_hash=source_hash,
                    unselected_inventory_entries_verified=effects[0]['unselected_inventory_entries_verified'],duplicate_rejected_http=422,
                    source_unchanged=True,customer_revision_created=False,complete_product_backup=False)
        storage.write_json(output/'receipt.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
