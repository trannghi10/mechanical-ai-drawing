"""Read a customer proposal's production context; never alter its CAD or plan."""
import argparse,json,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from dotenv import load_dotenv
from backend.services import catalog_service as storage
from backend.services.change_service import DrawingChangePlan
from verify_dauphine_core_stage import checked_context
from cad.edit_engine import digest
from cad.cuboid_projection import components
from graph.cuboid_projections import inventory,bindings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_id');parser.add_argument('plan_id');parser.add_argument('--output',required=True)
    args=parser.parse_args();load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig');started=time.monotonic()
    folder=storage.folder(args.document_id);source=folder/storage.read_status(args.document_id)['dxf'];original=digest(source)
    proposal=json.loads((folder/'change-plans'/(args.plan_id+'.json')).read_text(encoding='utf8'))
    context=checked_context(source,proposal);plan=DrawingChangePlan.model_validate(proposal.get('checked_preview_plan') or proposal['plan'])
    rejected=[];identified=inventory(context,rejected);applied=bindings(plan,context)
    result=dict(customer_document=True,document_id=args.document_id,plan_id=args.plan_id,source_hash=original,source_unchanged=digest(source)==original,
        complete_wire_candidates=len(components(context['entities'])),identified_cuboids=[{k:v for k,v in b.items() if k!='maps'} for b in identified],
        rejected_overlapping_bodies=rejected,executable_bindings=[{k:v for k,v in p.items() if k!='operations'} for p in applied],
        new_operation_count=sum(len(p['operations']) for p in applied),complete_product_backup=False,
        remaining=['Occluded labelled pad and complete unlabelled counterpart require independent correspondence and a fixed datum.',
                   'Unmapped product assembly faces, mating details and other packaging remain incomplete.'],seconds=round(time.monotonic()-started,2))
    assert result['source_unchanged'];storage.write_json(Path(args.output),result)
    print(json.dumps(result,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
