"""Revalidate persisted artifacts behind a completed CenterMark population audit."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    from backend.services import aps_jobs,catalog_service as storage
    from cad.edit_engine import digest
    from cad.native_centermark import verify_result
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('audit_directory');args=parser.parse_args()
    folder=Path(args.audit_directory)
    start=json.loads((folder/'started.json').read_text(encoding='utf8'))
    report=json.loads((folder/'receipt.json').read_text(encoding='utf8'))
    document_id=start['document_id'];source=storage.folder(document_id)/'original.dwg'
    assert report['status']=='completed_centermark_population_audit' and report['failed']==0
    assert digest(source)==start['source_hash']==report['source_hash']
    assert {p['circle_handle'] for p in start['pairs']}=={r['circle_handle'] for r in report['items']}
    verified=[]
    for row in report['items']:
        assert row['status']=='ready'
        job_folder=storage.folder(document_id)/'aps-jobs'/row['job_id']
        commands=json.loads((job_folder/'commands.json').read_text(encoding='utf8'))
        artifacts={name:aps_jobs.artifact(document_id,row['job_id'],name) for name in aps_jobs.ARTIFACTS}
        receipt=json.loads(artifacts['receipt.json'].read_text(encoding='utf8'))
        assert digest(job_folder/'commands.json')==receipt['commands_sha256']
        assert receipt['status']=='validated' and receipt['mode']=='edit' and receipt['applied_operations']==1
        assert len(commands['operations'])==1 and commands['source_sha256']==report['source_hash']
        op=commands['operations'][0]
        assert op['action']=='translate_centermark' and receipt['source_sha256']==report['source_hash']
        assert op['handle']==row['circle_handle'] and op['mark_handle']==row['mark_handle']
        assert digest(artifacts['modified.dwg'])==row['output_hash']==receipt['hashes']['modified.dwg']
        inventory=json.loads(artifacts['inventory.json'].read_text(encoding='utf8'))
        verify_result(op,inventory,artifacts['roundtrip.dxf'],report['source_hash'],row['output_hash'])
        verified.append(dict(circle_handle=row['circle_handle'],job_id=row['job_id'],output_hash=row['output_hash']))
        print(json.dumps(dict(circle_handle=row['circle_handle'],persisted_artifacts_verified=True)),flush=True)
    result=dict(status='verified_persisted_population_artifacts',document_id=document_id,source_hash=report['source_hash'],
                count=len(verified),items=verified,source_unchanged=digest(source)==report['source_hash'],customer_revision_created=False)
    assert result['source_unchanged']
    storage.write_json(folder/'artifact-verification.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
