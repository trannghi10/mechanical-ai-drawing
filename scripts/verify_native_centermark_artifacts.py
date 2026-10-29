"""Revalidate persisted single or batch CenterMark jobs, including independent DXF."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    from backend.services import aps_jobs,catalog_service as storage
    from cad.edit_engine import digest
    from cad.native_centermark import verify_results
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('document_id')
    parser.add_argument('--job',action='append',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    source=storage.folder(args.document_id)/'original.dwg';source_hash=digest(source);rows=[]
    for job_id in args.job:
        folder=storage.folder(args.document_id)/'aps-jobs'/job_id
        files={name:aps_jobs.artifact(args.document_id,job_id,name) for name in aps_jobs.ARTIFACTS}
        receipt=json.loads(files['receipt.json'].read_text(encoding='utf8'))
        commands=json.loads((folder/'commands.json').read_text(encoding='utf8'))
        assert digest(folder/'commands.json')==receipt['commands_sha256']
        assert source_hash==receipt['source_sha256']==commands['source_sha256']
        assert receipt['status']=='validated' and receipt['mode']=='edit' and receipt['applied_operations']==len(commands['operations'])
        output_hash=digest(files['modified.dwg']);assert output_hash==receipt['hashes']['modified.dwg']
        inventory=json.loads(files['inventory.json'].read_text(encoding='utf8'))
        verify_results(commands['operations'],inventory,files['roundtrip.dxf'],source_hash,output_hash)
        rows.append(dict(job_id=job_id,pair_count=len(commands['operations']),output_hash=output_hash))
        print(json.dumps(dict(job_id=job_id,persisted_artifacts_verified=True)),flush=True)
    assert digest(source)==source_hash
    report=dict(status='verified_persisted_centermark_jobs',document_id=args.document_id,source_hash=source_hash,items=rows,
                source_unchanged=True,customer_revision_created=False)
    storage.write_json(Path(args.output),report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
