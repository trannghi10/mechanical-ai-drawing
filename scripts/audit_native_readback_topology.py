"""Compare native topology metadata against the same job's readback DXF."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    from backend.services import aps_jobs,catalog_service as storage
    from cad.edit_engine import digest
    from cad.native_topology import compare
    import ezdxf
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('document_id');parser.add_argument('job_id');parser.add_argument('--output',required=True);args=parser.parse_args()
    inventory_path=aps_jobs.artifact(args.document_id,args.job_id,'inventory.json')
    dxf_path=aps_jobs.artifact(args.document_id,args.job_id,'roundtrip.dxf')
    inventory=json.loads(inventory_path.read_text(encoding='utf8'));doc=ezdxf.readfile(dxf_path)
    report=compare(inventory,doc)
    report.update(document_id=args.document_id,job_id=args.job_id,inventory_hash=digest(inventory_path),dxf_hash=digest(dxf_path),customer_revision_created=False)
    storage.write_json(Path(args.output),report)
    print(json.dumps({k:v for k,v in report.items() if k!='differences'}),flush=True)


if __name__=='__main__':main()
