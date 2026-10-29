"""Real local DWG upload/edit/export/readback with source packing clearances."""
import json
import os
import runpy
import sys
import time
import uuid
import argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from cad.converter import converter_path,DWGConverter
from cad.edit_engine import digest
from cad.sheets import SHEET_VERSION
from backend.services import catalog_service as storage
from backend.services.change_service import plan_change,context_for,DrawingChangePlan
from backend.services.revision_service import apply_plan,export_dwg,read_revision,validate_current_process_coverage
from graph.packaging_fit import require_complete


def customer_roundtrip(document_id, plan_id):
    """Re-run a real stored request; never approve or overwrite its source."""
    from backend.services.revision_service import safe_id
    from backend.services.checked_preview_service import apply as apply_preview
    folder=storage.folder(safe_id(document_id))
    proposal=json.loads((folder/'change-plans'/(safe_id(plan_id)+'.json')).read_text(encoding='utf8'))
    source=folder/storage.read_status(document_id)['dxf']
    inputs={str(p):digest(p) for p in (source,folder/'original.dwg',folder/'original.dxf') if p.is_file()}
    print('Checking stored customer request against current CAD rules',flush=True)
    # This CLI owns the synchronous conversion/readback below. Do not launch
    # a second background conversion of the same large revision meanwhile.
    auto_export=os.environ.get('CAD_AUTO_PRE_EXPORT')
    os.environ['CAD_AUTO_PRE_EXPORT']='0'
    try:
        revision=(apply_plan(document_id,plan_id,preview_only=True) if proposal.get('execution_available')
                  else apply_preview(document_id,plan_id))
    finally:
        if auto_export is None:os.environ.pop('CAD_AUTO_PRE_EXPORT',None)
        else:os.environ['CAD_AUTO_PRE_EXPORT']=auto_export
    print('Created revision '+revision['id'],flush=True)
    backup=export_dwg(document_id,revision['id'],require_approval=False,scope='selection')
    _,revision=read_revision(document_id,revision['id'])
    assert all(digest(Path(p))==h for p,h in inputs.items()),'Original CAD changed'
    receipt=dict(fixture=False,document_id=document_id,plan_id=plan_id,revision_id=revision['id'],
        approved=False,complete_product_backup=revision['complete_product_backup'],source_unchanged=True,source_hashes=inputs,
        dwg=str(backup),dwg_hash=digest(backup),packaging_review=revision['packaging_review'],
        drawing_sync=revision['drawing_sync'],roundtrip=revision['scoped_dwg_validation'])
    destination=Path(__file__).resolve().parents[1]/'storage/validation-fixtures/packaging-backup'/revision['id']
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(receipt=str(destination/'receipt.json'),dwg=str(backup),
        complete_product_backup=receipt['complete_product_backup'],roundtrip=receipt['roundtrip']['status']),ensure_ascii=False),flush=True)


def main():
    sys.stdout.reconfigure(encoding='utf8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pads',action='store_true')
    parser.add_argument('--document',help='Existing uploaded customer document ID')
    parser.add_argument('--plan',help='Stored request/plan ID in that document')
    args=parser.parse_args()
    if bool(args.document)!=bool(args.plan):parser.error('--document and --plan are required together')
    if args.document:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=True,encoding='utf-8-sig')
        customer_roundtrip(args.document,args.plan)
        return
    os.environ.update(AI_PROVIDER='native',AI_OFFLINE='1',CAD_DWG_ENABLED='1')
    base=Path(__file__).resolve().parents[1]/'storage/validation-fixtures/packaging-backup'/uuid.uuid4().hex
    authored=base/'authored';authored.mkdir(parents=True)
    fixture=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tests/test_packaging.py'))['packaging_fixture']
    padded=args.pads
    _,initial,_,_,_=fixture(authored,pads=padded)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(authored),str(base/'input-dwg'))
    dwg=base/'input-dwg/packaging.dwg';original=digest(dwg)
    storage.ROOT=base/'documents';storage.ROOT.mkdir()
    with dwg.open('rb') as stream:status=storage.create_document('product-carton-source.dwg',stream)
    deadline=time.monotonic()+120
    while status['status'] in ('queued','reading') and time.monotonic()<deadline:
        time.sleep(.2);status=storage.read_status(status['id'])
    if status['status']!='ready':raise RuntimeError(status)
    doc_id=status['id'];path=storage.folder(doc_id);source=path/status['dxf'];source_hash=digest(source)
    targets=initial['targets'];storage.write_json(path/'sheets-v3.json',dict(version=SHEET_VERSION,items=targets))
    storage.write_json(path/'exclusions-v1.json',dict(regions=[],ids=[]))
    proposal=plan_change(doc_id,[targets[0]],'Chi tiết số 1 chiều cao từ 100 thành 80 mm, giữ đầu dưới')
    if not proposal['execution_available']:raise RuntimeError(proposal['plan']['questions'])
    context=context_for(source,proposal['targets']);context['part_graph']=proposal['impact_graph']
    require_complete(DrawingChangePlan.model_validate(proposal['plan']),context)
    revision=apply_plan(doc_id,proposal['id'],preview_only=True)
    validate_current_process_coverage(doc_id,revision)
    backup=export_dwg(doc_id,revision['id'],require_approval=False,scope='selection')
    rpath,revision=read_revision(doc_id,revision['id']);after=context_for(rpath/'reopen-selection/modified.dxf',targets)
    assert len([e for e in after['entities'] if e['type']=='DIMENSION' and abs(e.get('scaled_measurement',0)-80)<1e-6])==2
    assert len([e for e in after['entities'] if e['type']=='DIMENSION' and abs(e.get('scaled_measurement',0)-100)<1e-6])==(4 if padded else 2)
    rows=[r for e in after['entities'] for r in e.get('bom',{}).get('rows',[])]
    assert next(r for r in rows if r['part_code']=='BOX-A')['description']=='Thùng carton 5 lớp 40x40x100mm'
    if padded:
        assert next(r for r in rows if r['part_code']=='PAD-S')['description']=='Xốp tấm 5x10x100mm'
        assert next(r for r in rows if r['part_code']=='PAD-H')['description']=='Xốp tấm 5x10x20mm'
        assert any(e['type']=='INSERT' and e.get('name')=='PAD-H' and abs(e['position'][1]-90)<1e-6 for e in after['entities'])
    assert digest(source)==source_hash and digest(dwg)==original
    receipt=dict(fixture=True,customer_dauphine=False,model_used=False,source_unchanged=True,
        product_height_before=100,product_height_after=80,carton_height_before=120,carton_height_after=100,
        each_end_gap_mm=10,foam_stack=padded,packaging_review=revision['packaging_review'],
        related_frames=[t['id'] for t in proposal['targets']],roundtrip=revision['scoped_dwg_validation']['status'],
        dwg=str(backup),dwg_hash=digest(backup),approved=False)
    (base/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
