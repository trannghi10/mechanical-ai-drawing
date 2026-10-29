"""Real ODA round trip of an atomic two-part change; no customer files altered."""
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
sys.stdout.reconfigure(encoding='utf8')
from test_planning import compound_planner_fixture as fixture, COMPOUND_PLANNER_REQUEST as REQUEST
from cad.converter import converter_path,DWGConverter
from cad.edit_engine import digest
from cad.sheets import SHEET_VERSION
from backend.services import catalog_service as storage
from backend.services.change_service import plan_change,context_for
from backend.services.revision_service import apply_plan,export_dwg,read_revision,validate_current_process_coverage


def main():
    os.environ['AI_PROVIDER']='native';os.environ['AI_OFFLINE']='1';os.environ['CAD_DWG_ENABLED']='1'
    base=ROOT/'storage/validation-fixtures/compound-backup'/uuid.uuid4().hex
    authored=base/'authored';authored.mkdir(parents=True)
    source,initial=fixture(authored)
    converter=DWGConverter(converter_path())
    converter.convert_dxf_to_dwg(str(authored),str(base/'input-dwg'))
    dwg=base/'input-dwg/source.dwg';original=digest(dwg)
    storage.ROOT=base/'documents';storage.ROOT.mkdir()
    with dwg.open('rb') as stream:status=storage.create_document('two-part-compound.dwg',stream)
    did=status['id'];deadline=time.monotonic()+180
    while status['status'] in ('queued','reading') and time.monotonic()<deadline:
        time.sleep(.2);status=storage.read_status(did)
    if status['status']!='ready':raise RuntimeError(status)
    path=storage.folder(did);source=path/status['dxf'];source_hash=digest(source)
    targets=initial['targets']
    storage.write_json(path/'sheets-v3.json',dict(version=SHEET_VERSION,items=targets))
    storage.write_json(path/'exclusions-v1.json',dict(regions=[],ids=[]))
    proposal=plan_change(did,targets,REQUEST)
    assert proposal['execution_available'] and proposal['request_review']['status']=='complete'
    revision=apply_plan(did,proposal['id'],preview_only=True)
    validate_current_process_coverage(did,revision)
    backup=export_dwg(did,revision['id'],require_approval=False,scope='selection')
    revision_path,revision=read_revision(did,revision['id'])
    actual=context_for(revision_path/'reopen-selection/modified.dxf',targets)
    dimensions=sorted(e['scaled_measurement'] for e in actual['entities'] if e['type']=='DIMENSION')
    rows=[r['description'] for e in actual['entities'] for r in e.get('bom',{}).get('rows',[])]
    assert dimensions==[40,76] and rows==['Bas 2x20x76','Bas 2x20x40']
    assert digest(source)==source_hash and digest(dwg)==original
    receipt=dict(fixture=True,customer_dauphine=False,approved=False,request=REQUEST,
                 document_id=did,plan_id=proposal['id'],revision_id=revision['id'],
                 request_review=proposal['request_review'],source_unchanged=True,
                 measured_dimensions=dimensions,bom_descriptions=rows,
                 dwg=str(backup),dwg_hash=digest(backup),validation=revision['validation']['status'])
    storage.write_json(base/'receipt.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
