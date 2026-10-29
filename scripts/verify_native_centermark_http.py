"""Exercise selection, scoped inspection and native edit over the local HTTP API."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import httpx
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_id');parser.add_argument('selection_id')
    parser.add_argument('circle_handle');parser.add_argument('mark_handle');parser.add_argument('--output',required=True)
    parser.add_argument('--discover-selection',action='store_true',help='Use the same automatic scope discovery as the CenterMark UI.')
    args=parser.parse_args();output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    base=f'/documents/{args.document_id}'
    source=storage.folder(args.document_id)/'original.dwg';source_hash=digest(source)
    with httpx.Client(base_url='http://127.0.0.1:8765',trust_env=False,timeout=120) as client:
        def request(method,path,**kw):
            response=client.request(method,path,**kw)
            if response.is_error:raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:1000]}')
            return response.json()
        def wait_job(job):
            storage.write_json(output/('started-'+job['id']+'.json'),job)
            deadline=time.monotonic()+300
            while job['status'] not in ('ready','failed'):
                if time.monotonic()>deadline:raise RuntimeError('Job remains active: '+job['id'])
                time.sleep(1);job=request('GET',base+'/autocad/jobs/'+job['id'])
            if job['status']!='ready':raise RuntimeError(job)
            return job
        state=request('GET',base)
        assert state['status']=='ready' and state['read_backend']=='autocad'
        context=request('POST',base+'/autocad/context',json=dict(ids=[args.selection_id]))
        assert context['inspection_id']==state['native_import_job_id'] and context['original_source_hash']==source_hash
        inspected=wait_job(request('POST',base+'/autocad/centermark-inspections',json=dict(ids=[args.selection_id])) if args.discover_selection else request('POST',base+'/autocad/jobs',json=dict(handles=[args.circle_handle,args.mark_handle])))
        found=request('GET',base+'/autocad/jobs/'+inspected['id']+'/centermark-candidates')
        pair,=[p for p in found['items'] if p['circle_handle']==args.circle_handle and p['mark_handle']==args.mark_handle]
        before=pair['source_center'];after=[before[0]+3,before[1]-2,before[2]]
        op=dict(action='translate_centermark',handle=args.circle_handle,mark_handle=args.mark_handle,action_handle=pair['action_handle'],
                owner_handle=pair['owner_handle'],expected_type='CIRCLE',before=json.dumps(before),after=json.dumps(after))
        body=dict(inspection_id=context['inspection_id'],dependency_inspection_id=inspected['id'],source_hash=source_hash,
                  ids=[args.selection_id],operations=[op])
        # Invalid source center must fail at API validation without creating a CAD job.
        wrong=dict(body,operations=[dict(op,before=json.dumps([before[0]+1,before[1],before[2]]))])
        rejected=client.post(base+'/autocad/native-edits',json=wrong)
        assert rejected.status_code==422,rejected.text
        job=wait_job(request('POST',base+'/autocad/native-edits',json=body))
        receipt=request('GET',base+'/autocad/jobs/'+job['id']+'/files/receipt.json')
        assert receipt['source_sha256']==source_hash and receipt['applied_operations']==1
        assert digest(source)==source_hash
        report=dict(status='validated_native_centermark_http',document_id=args.document_id,selection_id=args.selection_id,
                    import_inspection_id=context['inspection_id'],dependency_inspection_id=inspected['id'],edit_id=job['id'],
                    source_hash=source_hash,output_hash=receipt['hashes']['modified.dwg'],wrong_center_rejected_http=422,
                    automatic_selection_discovery=args.discover_selection,
                    source_unchanged=True,customer_revision_created=False,complete_product_backup=False)
        storage.write_json(output/'receipt.json',report);storage.write_json(output/'request.json',body)
        print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()
