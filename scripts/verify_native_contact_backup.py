"""Real DWG roundtrip of a different-part contact dependency, outside user docs."""
import json
import os
from pathlib import Path
import runpy
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from cad.converter import converter_path,DWGConverter
from cad.edit_engine import digest
from cad.sheets import SHEET_VERSION
from backend.services import catalog_service as storage
from backend.services.change_service import plan_change,context_for,DrawingChangePlan
from backend.services.revision_service import apply_plan,export_dwg,read_revision
from graph.drawing_sync import require_assembly_sync


def main():
    os.environ.update(AI_PROVIDER='native',AI_OFFLINE='1',CAD_DWG_ENABLED='1')
    base=Path(__file__).resolve().parents[1]/'storage/validation-fixtures/native-contact-backup'/uuid.uuid4().hex
    authored=base/'authored';authored.mkdir(parents=True)
    fixture=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tests/test_native_contacts.py'))['contact_fixture']
    source,initial,_,_,_,_,_=fixture(authored)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(authored),str(base/'input-dwg'))
    dwg=base/'input-dwg/contacts.dwg';original=digest(dwg)
    storage.ROOT=base/'documents';storage.ROOT.mkdir()
    with dwg.open('rb') as stream:status=storage.create_document('planar-contact-assembly.dwg',stream)
    doc_id=status['id'];deadline=time.monotonic()+120
    while status['status'] in ('queued','reading') and time.monotonic()<deadline:
        time.sleep(.2);status=storage.read_status(doc_id)
    if status['status']!='ready':raise RuntimeError(status)
    path=storage.folder(doc_id);source=path/status['dxf'];source_hash=digest(source)
    targets=initial['targets'];storage.write_json(path/'sheets-v3.json',dict(version=SHEET_VERSION,items=targets))
    storage.write_json(path/'exclusions-v1.json',dict(regions=[],ids=[]))
    proposal=plan_change(doc_id,[targets[0]],'Chi tiết số 1 chiều cao từ 100 thành 80 mm, giữ đầu dưới')
    if not proposal['execution_available']:raise RuntimeError(proposal['plan']['questions'])
    context=context_for(source,proposal['targets']);context['part_graph']=proposal['impact_graph']
    require_assembly_sync(DrawingChangePlan.model_validate(proposal['plan']),context)
    revision=apply_plan(doc_id,proposal['id'],preview_only=True)
    backup=export_dwg(doc_id,revision['id'],require_approval=False,scope='selection')
    revision_path,revision=read_revision(doc_id,revision['id'])
    reopened=revision_path/'reopen-selection/modified.dxf';after=context_for(reopened,targets)
    moved=[e for e in after['entities'] if e['type']=='INSERT' and e['name']=='PART-B' and abs(e['position'][0]-600)<1e-6]
    assert len(moved)==1 and abs(moved[0]['position'][1]-80)<1e-6
    total=[e for e in after['entities'] if e['type']=='DIMENSION' and e['coordinate_frame']=='layout:Model' and e.get('scaled_measurement')==180]
    assert len(total)==1
    rows=[r for e in after['entities'] for r in e.get('bom',{}).get('rows',[])]
    assert next(r for r in rows if r['part_code']=='PART-A')['description']=='Bas 2x20x80'
    assert next(r for r in rows if r['part_code']=='PART-B')['description']=='Bas 2x20x100'
    assert digest(source)==source_hash and digest(dwg)==original
    receipt=dict(fixture=True,model_used=False,source_unchanged=True,planner=proposal['planner'],
        dependencies=proposal['plan']['dependencies'],drawing_sync=revision['drawing_sync'],
        moved_part='PART-B',moved_y=80,overall_height=180,source_part_height=80,
        roundtrip=revision['scoped_dwg_validation']['status'],dwg=str(backup),dwg_hash=digest(backup),approved=False)
    if '--repeat' in sys.argv:
        with backup.open('rb') as stream:again=storage.create_document('contact-backup-reopened.dwg',stream)
        deadline=time.monotonic()+120
        while again['status'] in ('queued','reading') and time.monotonic()<deadline:
            time.sleep(.2);again=storage.read_status(again['id'])
        if again['status']!='ready':raise RuntimeError(again)
        again_path=storage.folder(again['id'])
        storage.write_json(again_path/'sheets-v3.json',dict(version=SHEET_VERSION,items=targets))
        storage.write_json(again_path/'exclusions-v1.json',dict(regions=[],ids=[]))
        p2=plan_change(again['id'],[targets[0]],'Chi tiết số 1 chiều cao từ 80 thành 70 mm, giữ đầu dưới')
        if not p2['execution_available']:raise RuntimeError(p2['plan']['questions'])
        r2=apply_plan(again['id'],p2['id'],preview_only=True)
        b2=export_dwg(again['id'],r2['id'],require_approval=False,scope='selection')
        rpath,r2=read_revision(again['id'],r2['id']);c2=context_for(rpath/'reopen-selection/modified.dxf',targets)
        assert len([e for e in c2['entities'] if e['type']=='DIMENSION' and e.get('scaled_measurement')==70])==2
        assert len([e for e in c2['entities'] if e['type']=='DIMENSION' and e.get('scaled_measurement')==170])==1
        receipt['repeat_edit']=dict(passed=True,source_part_height=70,overall_height=170,roundtrip=r2['scoped_dwg_validation']['status'],dwg=str(b2),dwg_hash=digest(b2))
    (base/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
