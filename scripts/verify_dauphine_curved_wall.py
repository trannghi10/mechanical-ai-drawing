"""Actual Dauphine formed-shell preview; explicitly not a full product backup."""
import json
from pathlib import Path
import re
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf8')
from backend.services import catalog_service as storage
from backend.services.change_service import context_for,DrawingChangePlan,EditProposal,validate_plan
from backend.services.part_graph_service import document_graph
from backend.services.parametric_service import compile_recipes
from backend.services.design_choices import attach
from backend.services.curved_wall_service import require_developed_blanks
from cad.curved_wall import CurvedWallResize
from cad.curved_profiles import profile_from
from cad.edit_engine import apply_patch,digest,Operation
from cad.catalog import load_document
from cad.converter import DWGConverter,converter_path
from cad.scoped_export import select_entities
from cad.sheets import render_sheet
from cad.vision import rasterize_svg
from bom.operations import cell_operations


def main():
    root=Path(__file__).resolve().parents[1];did='34ee84f35e1a44fb81c56044397a0fff';folder=storage.folder(did)
    source=folder/storage.read_status(did)['dxf'];original=digest(source)
    sheets=json.loads((folder/'sheets-v3.json').read_text(encoding='utf8'))['items']
    targets=[t for t in sheets if t['id'] in ('3B8B98','3D337A')]
    context=attach(context_for(source,targets),folder);context['part_graph']=document_graph(did)
    code='8.1.05417.258'
    choice=next(c for c in context['design_choices']['confirmed_choices'] if c['key']=='curved_shell_anchor' and c['part_code']==code)
    assert choice['anchor']=='outer' and choice['outer_radius_mm']==406.5
    refs=['3E1394','3E1398','3E1399','3E139A','3E139B','3E139E','3E139F','3E13A0']
    from backend.services.compound_planner import checked_one
    plan,planner=checked_one(context,'Chi tiết 8.1.05417.258: đổi độ dày từ 1.5 mm thành 1 mm')
    assert plan is not None and planner=='checked_curved_wall'
    assert set(plan.curved_wall_recipes[0].outline_refs)==set(refs)
    validate_plan(plan,context)
    changed_rows=[dict(before=o.before,after=o.after) for o in plan.operations if o.action=='table_cell']
    assert changed_rows
    pattern=re.compile(r'(?<![\d.])1[.,]5(?=\s*[x×])')
    try:require_developed_blanks(plan,context)
    except ValueError as error:incomplete_reason=str(error)
    else:raise AssertionError('Source forming blank must retain its incomplete gate')
    out=root/'storage/validation-fixtures/dauphine-curved-wall'/uuid.uuid4().hex
    authored=out/'authored';authored.mkdir(parents=True)
    modified=out/'full-source-copy.dxf'
    validation=apply_patch(source,modified,plan.operations,{e['ref'] for e in context['entities']},original)
    keep={e['ref'].split('/')[0] for e in context['entities'] if e['type']!='GRAPHIC_TABLE'}
    selected=authored/'Dauphine-PREVIEW-mat-cat-tam-op-cung-t1.dxf'
    scope=select_entities(modified,selected,keep)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(authored),str(out/'dwg'))
    converter.convert_dwg_to_dxf(str(out/'dwg'),str(out/'reopened'))
    reopened=out/'reopened'/selected.name
    actual=context_for(reopened,targets);records={e['ref']:e for e in actual['entities']}
    assert abs(records['3E139A']['geometry']['radius']-406.5)<1e-6
    assert abs(records['3E139E']['geometry']['radius']-405.5)<1e-6
    assert profile_from([records[r] for r in refs])
    row=next(r for e in actual['entities'] for r in e.get('bom',{}).get('rows',[]) if r['part_code']==code)
    assert pattern.search(row['description']) is None
    # Full height remains 724 in this thickness-only preview; no inferred datum.
    assert abs(records['3B8BF1']['scaled_measurement']-724)<1e-6
    assert digest(source)==original
    target=next(t for t in targets if t['id']=='3B8B98')
    for name,path in [('before',source),('after',reopened)]:
        svg=render_sheet(path,target);(out/(name+'.svg')).write_text(svg,encoding='utf8')
        (out/(name+'.png')).write_bytes(rasterize_svg(svg,width=1600))
    dwg=out/'dwg'/selected.with_suffix('.dwg').name
    receipt=dict(customer_dauphine=True,fixture=False,approved=False,complete_product_backup=False,
        source_unchanged=True,source_hash=original,source_part_code=code,outer_radius_mm=406.5,inner_radius_mm=405.5,
        thickness_before_mm=1.5,thickness_after_mm=1,height_mm=724,closed_contour=True,roundtrip='passed',
        planner=planner,changed_rows=changed_rows,changed_entities=len(plan.operations),unresolved=incomplete_reason,dwg=str(dwg),dwg_hash=digest(dwg))
    storage.write_json(out/'receipt.json',receipt);storage.write_json(out/'plan.json',plan.model_dump())
    print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
