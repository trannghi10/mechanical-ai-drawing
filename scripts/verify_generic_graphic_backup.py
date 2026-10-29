"""Exercise the real upload/plan/revision/DWG pipeline with a new 2D fixture.

All artifacts live outside the user's document list. This is a regression
fixture, not evidence that arbitrary engineering connections can be inferred.
Run from the project root: python scripts/verify_generic_graphic_backup.py
"""
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cad.converter import converter_path, DWGConverter
from cad.edit_engine import digest
from backend.services import catalog_service as storage
from backend.services.change_service import plan_change, context_for
from backend.services.revision_service import apply_plan, export_dwg, read_revision
from backend.services.comparison_service import material_review
from cad.sheets import SHEET_VERSION


def main():
    sys.stdout.reconfigure(encoding='utf8')
    model_plan='--model-plan' in sys.argv
    # Force the vision route only when explicitly testing the actual model.
    if '--vision-intent' in sys.argv:
        from backend.services import relative_planner
        relative_planner.compile_plan=lambda *args:None
    inset=float(sys.argv[sys.argv.index('--inset')+1]) if '--inset' in sys.argv else 24
    if not 0<inset<40:raise ValueError('Regression inset must be between 0 and 40 mm')
    expected=100-inset if model_plan else 76
    os.environ['AI_PROVIDER']='native'
    os.environ['AI_OFFLINE']='1'
    os.environ['CAD_DWG_ENABLED']='1'
    base=Path(__file__).resolve().parents[1]/'storage'/'validation-fixtures'/'generic-graphic-backup'/uuid.uuid4().hex
    authored=base/'authored';authored.mkdir(parents=True)
    if '--vision-intent' in sys.argv:
        from backend.services import ai_provider
        real_generate=ai_provider.generate_plan
        def traced_generate(prompt,parts,schema):
            if schema.__name__!='ResizeIntent':raise RuntimeError('Vision intent not compiled; see intent-attempt.json. Full planning was not tested.')
            value=real_generate(prompt,parts,schema)
            (base/'intent-attempt.json').write_text(json.dumps(value.model_dump(),ensure_ascii=False,indent=2),encoding='utf8')
            return value
        ai_provider.generate_plan=traced_generate
    fixture=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tests'/'test_bom.py'))['editable_fixture']
    source,initial,_,_,_,_,_=fixture(authored,True)
    converter=DWGConverter(converter_path())
    converter.convert_dxf_to_dwg(str(authored),str(base/'input-dwg'))
    dwg=base/'input-dwg'/'generic.dwg'
    original_hash=digest(dwg)
    storage.ROOT=base/'documents';storage.ROOT.mkdir()
    with dwg.open('rb') as stream:status=storage.create_document('generic-part-attributes.dwg',stream)
    doc_id=status['id'];deadline=time.monotonic()+180
    while status['status'] in ('queued','reading') and time.monotonic()<deadline:
        time.sleep(.2);status=storage.read_status(doc_id)
    if status['status']!='ready':raise RuntimeError(status)
    path=storage.folder(doc_id);source=path/status['dxf'];source_hash=digest(source)
    targets=initial['targets']
    storage.write_json(path/'sheets-v3.json',dict(version=SHEET_VERSION,items=targets))
    storage.write_json(path/'exclusions-v1.json',dict(regions=[],ids=[]))
    request=(f'Chi tiết số 1: đưa cạnh phải vào {inset:g} mm so với hiện tại, giữ đầu trái. Giữ đường kính lỗ và đồng bộ bảng kê.'
             if model_plan else 'Chi tiết số 1 giảm chiều dài từ 100 mm thành 76 mm, giữ đầu trái')
    proposal=plan_change(doc_id,[targets[0]],request)
    if not proposal['execution_available']:raise RuntimeError(proposal['plan']['questions'])
    revision=apply_plan(doc_id,proposal['id'],preview_only=True)
    backup=export_dwg(doc_id,revision['id'],require_approval=False,scope='selection')
    revision_path,revision=read_revision(doc_id,revision['id'])
    reopened=revision_path/'reopen-selection'/'modified.dxf'
    context=context_for(reopened,targets)
    rows=[r for e in context['entities'] for r in e.get('bom',{}).get('rows',[])]
    dimensions=[e['scaled_measurement'] for e in context['entities'] if e['type']=='DIMENSION']
    shapes=[e['geometry']['points'] for e in context['entities'] if e['type']=='LWPOLYLINE']
    assert len(rows)==2 and all(r['description']==f'Bas 2x20x{expected:g}' for r in rows)
    assert dimensions==[expected,expected] and len(shapes)==2 and all(max(p[0] for p in ps)==expected for ps in shapes)
    materials=material_review(doc_id,revision['id'],'S')
    assert materials['changed_count']==1
    assert digest(source)==source_hash and digest(dwg)==original_hash
    copy=base/'generic-2d-graphic-bom-PREVIEW.dwg';shutil.copy2(backup,copy)
    receipt=dict(fixture=True,document_id=doc_id,revision_id=revision['id'],planner=proposal.get('planner','vision_model'),
        model_plan=proposal.get('planner')=='vision_intent_checked_rectangular_resize',
        request_style='relative' if model_plan else 'explicit',forced_vision='--vision-intent' in sys.argv,
        request=request,expected_length=expected,interpreted_intent=proposal.get('interpreted_intent'),
        source_dwg_hash=original_hash,source_dxf_hash=source_hash,source_unchanged=True,
        selected_target='S',revision_targets=[t['id'] for t in revision['targets']],
        operations=len(proposal['plan']['operations']),bom_descriptions=[r['description'] for r in rows],
        measured_dimensions=dimensions,dwg_path=str(copy),dwg_hash=digest(copy),bytes=copy.stat().st_size,
        roundtrip=revision['scoped_dwg_validation']['status'],approved=False)
    (base/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
