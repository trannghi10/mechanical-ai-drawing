"""Actual local DWG upload, curve edit, scoped export and ODA readback."""
import json
import os
from pathlib import Path
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
sys.stdout.reconfigure(encoding='utf8')
from test_profiles import curved_profiles_fixture as fixture
from cad.converter import converter_path,DWGConverter
from cad.edit_engine import digest
from cad.sheets import SHEET_VERSION
from cad.measured_features import index
from backend.services import catalog_service as storage
from backend.services.change_service import plan_change,context_for
from backend.services.revision_service import apply_plan,export_dwg,read_revision,validate_current_process_coverage


def main():
    os.environ.update(AI_PROVIDER='native',AI_OFFLINE='1',CAD_DWG_ENABLED='1')
    base=ROOT/'storage/validation-fixtures/curved-backup'/uuid.uuid4().hex
    authored=base/'authored';authored.mkdir(parents=True)
    polyline='--polyline' in sys.argv
    _,initial,_,_,_=fixture(authored,polyline=polyline,rotation=30,scale=.5,radial=True)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(authored),str(base/'input-dwg'))
    dwg=base/'input-dwg/source.dwg';original=digest(dwg)
    storage.ROOT=base/'documents';storage.ROOT.mkdir()
    with dwg.open('rb') as stream:status=storage.create_document('rotated-curved-part.dwg',stream)
    deadline=time.monotonic()+180
    while status['status'] in ('queued','reading') and time.monotonic()<deadline:
        time.sleep(.2);status=storage.read_status(status['id'])
    if status['status']!='ready':raise RuntimeError(status)
    did=status['id'];folder=storage.folder(did);source=folder/status['dxf'];source_hash=digest(source)
    targets=initial['targets']
    storage.write_json(folder/'sheets-v3.json',dict(version=SHEET_VERSION,items=targets))
    storage.write_json(folder/'exclusions-v1.json',dict(regions=[],ids=[]))
    proposal=plan_change(did,targets,'Chi tiết số 1 chiều dài từ 100 thành 76 mm, giữ đầu trái')
    if not proposal['execution_available']:raise RuntimeError(proposal['plan']['questions'])
    revision=apply_plan(did,proposal['id'],preview_only=True)
    validate_current_process_coverage(did,revision)
    backup=export_dwg(did,revision['id'],require_approval=False,scope='selection')
    path,revision=read_revision(did,revision['id']);actual=context_for(path/'reopen-selection/modified.dxf',targets)
    features=index(actual,proposal['impact_graph'])
    curved=[f for f in features['features'] if f['kind']=='measured_curved_profile']
    assert len(curved)==1 and any(abs(d['measurement']-76)<1e-6 for d in curved[0]['dimensions'])
    assert [r['description'] for e in actual['entities'] for r in e.get('bom',{}).get('rows',[])]==['Bas 2x20x76']
    assert all(e['geometry']['radius']==2 for e in actual['entities'] if e['type']=='CIRCLE')
    if polyline:
        assert [p[4] for e in actual['entities'] if e['type']=='LWPOLYLINE' for p in e['geometry']['points']]==[0,1,0,1]
    else:assert all(e['geometry']['radius']==10 for e in actual['entities'] if e['type']=='ARC')
    assert digest(source)==source_hash and digest(dwg)==original
    receipt=dict(fixture=True,customer_dauphine=False,approved=False,source_unchanged=True,polyline=polyline,
        rotation_degrees=30,scale=.5,before_mm=100,after_mm=76,curve_radius_mm=10,hole_radius_mm=2,
        roundtrip=revision['scoped_dwg_validation']['status'],dwg=str(backup),dwg_hash=digest(backup),
        document_id=did,plan_id=proposal['id'],revision_id=revision['id'])
    storage.write_json(base/'receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
