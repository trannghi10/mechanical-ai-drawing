"""Validate the production native job contract on an isolated CAD output.

This creates inspection/edit validation jobs, never a customer revision or mating confirmation.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    from backend.services import aps_jobs, catalog_service as storage
    from cad.native_centermark import candidates
    from cad.edit_engine import digest
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_id');parser.add_argument('circle_handle');parser.add_argument('mark_handle')
    parser.add_argument('--dx',type=float,default=3);parser.add_argument('--dy',type=float,default=-2)
    parser.add_argument('--reject-action-handle',help='Negative native preflight check: deliberately supply a wrong action handle.')
    args=parser.parse_args()
    source=storage.folder(args.document_id)/'original.dwg';source_hash=digest(source)
    scope=[args.circle_handle,args.mark_handle]
    inspection=aps_jobs.start(args.document_id,provider='autocad',scope_handles=scope,expected_source_hash=source_hash)
    aps_jobs.wait(args.document_id,inspection['id'],timeout=300)
    inventory=json.loads(aps_jobs.artifact(args.document_id,inspection['id'],'inventory.json').read_text(encoding='utf8'))
    pair,=[p for p in candidates(inventory) if p['circle_handle']==args.circle_handle and p['mark_handle']==args.mark_handle]
    before=pair['source_center'];after=[before[0]+args.dx,before[1]+args.dy,before[2]]
    operation=dict(action='translate_centermark',handle=args.circle_handle,mark_handle=args.mark_handle,
                   action_handle=pair['action_handle'],owner_handle=pair['owner_handle'],expected_type='CIRCLE',
                   before=json.dumps(before),after=json.dumps(after))
    if args.reject_action_handle:
        operation['action_handle']=args.reject_action_handle
    job=aps_jobs.start(args.document_id,provider='autocad',mode='edit',operations=[operation],scope_handles=scope,expected_source_hash=source_hash)
    if args.reject_action_handle:
        from backend.services.aps_client import APSError
        from backend.services import aps_repository
        try:
            aps_jobs.wait(args.document_id,job['id'],timeout=300)
        except APSError:
            record=aps_repository.read(args.document_id,job['id'])
            job_folder=storage.folder(args.document_id)/'aps-jobs'/job['id']
            error=json.loads((job_folder/'autocad-plugin-error.json').read_text(encoding='utf8'))
            assert record['status']=='failed' and error['message']=='CenterMark contract dependency/owner mismatch'
            assert not (job_folder/'result').exists() and digest(source)==source_hash
            report=dict(status='validated_native_centermark_rejection',edit_id=job['id'],source_hash=source_hash,
                        reason=error['message'],source_unchanged=True,customer_revision_created=False)
            folder=ROOT/'storage/validation-fixtures'/('native-centermark-rejection-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True)
            storage.write_json(folder/'receipt.json',report);print(json.dumps(dict(report,evidence=str(folder)),ensure_ascii=True));return
        raise AssertionError('Native preflight unexpectedly accepted the wrong action handle')
    aps_jobs.wait(args.document_id,job['id'],timeout=300)
    output=aps_jobs.artifact(args.document_id,job['id'],'modified.dwg')
    assert digest(source)==source_hash
    report=dict(status='validated_native_centermark_job',inspection_id=inspection['id'],edit_id=job['id'],
                source_hash=source_hash,output_hash=digest(output),output=str(output),operation=operation,
                customer_revision_created=False,complete_product_backup=False)
    folder=ROOT/'storage/validation-fixtures'/('native-centermark-job-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True)
    storage.write_json(folder/'receipt.json',report)
    print(json.dumps(dict(report,evidence=str(folder)),ensure_ascii=True))


if __name__=='__main__':main()
