"""Actual shell stages: bottom-anchored height plus wall thickness, not full product."""
import json
import re
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf8')
from backend.services import catalog_service as storage
from backend.services.change_service import context_for,DrawingChangePlan,EditProposal,validate_plan
from backend.services.part_graph_service import document_graph
from backend.services.parametric_service import compile_recipes
from backend.services.design_choices import attach
from cad.curved_wall import CurvedWallResize
from cad.parametric import LinearResize
from cad.measured_features import index
from cad.frame_geometry import world
from cad.edit_engine import Operation,apply_patch,digest
from cad.converter import DWGConverter,converter_path
from cad.scoped_export import select_entities
from cad.sheets import render_sheet
from cad.vision import rasterize_svg
from bom.operations import cell_operations


def main():
    folder=storage.folder('34ee84f35e1a44fb81c56044397a0fff');source=folder/storage.read_status(folder.name)['dxf'];original=digest(source)
    ids={'3B8A74','3B8B05','3B8B98','3B8C84','3D337A'}
    targets=[t for t in json.loads((folder/'sheets-v3.json').read_text(encoding='utf8'))['items'] if t['id'] in ids]
    c=attach(context_for(source,targets),folder);c['part_graph']=document_graph(folder.name);c['source_features']=index(c,c['part_graph'])
    anchor=next(v for v in c['design_choices']['confirmed_choices'] if v['key']=='height_anchor')
    assert anchor['anchor']=='bottom' and anchor['delta_mm']==-27
    by={e['ref']:e for e in c['entities']};code='8.1.05417.258'
    refs=['3E1394','3E1398','3E1399','3E139A','3E139B','3E139E','3E139F','3E13A0']
    wall=CurvedWallResize(part_code=code,outer_arc_ref='3E139A',inner_arc_ref='3E139E',outline_refs=refs,new_thickness=1,evidence_refs=refs)
    plan=DrawingChangePlan(summary='Tấm ốp cung: giữ đáy, cao 724 → 697 mm; tấm 1,5 → 1 mm; giữ R406,5 ngoài.',target_part=code,
        edits=[],dependencies=[],questions=[],warnings=[],curved_wall_recipes=[wall])
    height_refs=[];thin_refs=[]
    for f in c['source_features']['features']:
        if f['part_code']!=code:continue
        for d in f['dimensions']:
            if abs(d['measurement']-724)<1e-5 and abs(d['axis'][1])>1-1e-7:
                geometry=world(by[d['ref']])['geometry'];fixed='first' if geometry['defpoint2'][1]<geometry['defpoint3'][1] else 'second'
                plan.resize_recipes.append(LinearResize(part_code=code,dimension_ref=d['ref'],new_measurement=697,outline_refs=f['refs'],hole_refs=[],anchor=fixed,evidence_refs=f['evidence_refs']))
                height_refs.append(d['ref'])
            elif abs(d['measurement']-1.5)<1e-5 and f['kind']=='measured_straight_profile':
                geometry=world(by[d['ref']])['geometry'];fixed='first' if geometry['defpoint2'][0]<geometry['defpoint3'][0] else 'second'
                plan.resize_recipes.append(LinearResize(part_code=code,dimension_ref=d['ref'],new_measurement=1,outline_refs=f['refs'],hole_refs=[],anchor=fixed,evidence_refs=f['evidence_refs']))
                thin_refs.extend(f['refs'])
    assert len(height_refs)==3 and thin_refs
    def add(op,purpose):
        plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose=purpose,before=op.before,after=op.after,reason=op.reason))
    spec='1.5x382x724x812';stock=next(v for v in c['design_choices']['confirmed_choices'] if v['key']=='sheet_stock_code')
    cells=set()
    for table in c['entities']:
        for row in table.get('bom',{}).get('rows',[]):
            cells.update(v.get('mirror_ref') for v in row.get('cells',{}).values())
            if row['part_code']!=code:continue
            cell=row['cells']['description'];raw=cell['raw_text'];assert spec in raw
            for op in cell_operations(table,cell,raw.replace(spec,'1x382x697x812'),by,'Đồng bộ tấm ốp cao 697 và dày 1 trong BOM'):add(op,'bom')
    for e in c['entities']:
        if e['type'] not in ('TEXT','MTEXT') or e['ref'] in cells:continue
        raw=e.get('raw_text',e.get('text',''));after=raw
        if spec in raw and set(e.get('source_sheet_ids',[]))& (ids-{'3D337A'}):after=raw.replace(spec,'1x382x697x812')
        if '3.1.01820' in raw and re.search(r'vat tu\s*:',__import__('bom.reader',fromlist=['normalized']).normalized(raw)):
            after=re.sub(r'3\.1\.01820\s+Sắt tấm 1\.5x1220x2500mm',stock['after_description'],raw)
        if after!=raw:add(Operation(ref=e['ref'],action='replace_text',before=raw,after=after,xyz=[],reason='Đồng bộ quy cách và ghi chờ cấp mã nguyên liệu nguồn'),'annotation')
    plan=compile_recipes(plan,c);validate_plan(plan,c)
    out=Path('storage/validation-fixtures/dauphine-height-wall')/uuid.uuid4().hex
    authored=out/'authored';authored.mkdir(parents=True)
    modified=out/'full-source-copy.dxf';report=apply_patch(source,modified,plan.operations,set(by),original)
    selected=authored/'Dauphine-PREVIEW-tam-op-cao697-day1.dxf'
    scope=select_entities(modified,selected,{r.split('/')[0] for r in by if not r.startswith('graphic-table:')})
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(authored),str(out/'dwg'));converter.convert_dwg_to_dxf(str(out/'dwg'),str(out/'reopened'))
    actual=context_for(out/'reopened'/selected.name,targets);ab={e['ref']:e for e in actual['entities']}
    assert all(abs(ab[r]['scaled_measurement']-697)<1e-5 for r in height_refs)
    for ref in thin_refs:
        points=world(ab[ref])['geometry']['points'];assert abs(max(p[1] for p in points)-min(p[1] for p in points)-697)<1e-5
        assert abs(max(p[0] for p in points)-min(p[0] for p in points)-1)<1e-5
    assert abs(ab['3E139A']['geometry']['radius']-406.5)<1e-6 and abs(ab['3E139E']['geometry']['radius']-405.5)<1e-6
    assert abs(ab['3E139C']['geometry']['radius']-406.5)<1e-6 and abs(ab['3E13E7']['geometry']['radius']-405.5)<1e-6
    assert abs(ab['3E13E8']['scaled_measurement']-1)<1e-5
    cut_points=[]
    for e in actual['entities']:
        if not e['ref'].startswith('3B9117/') or e['type'] not in ('LINE','LWPOLYLINE'):continue
        g=world(e)['geometry']
        cut_points.extend([g['start'],g['end']] if e['type']=='LINE' else [[p[0],p[1],g['elevation']] for p in g['points']])
    assert abs(max(p[1] for p in cut_points)-min(p[1] for p in cut_points)-697)<1e-5
    assert abs(ab['3B8BB9']['scaled_measurement']-37)<1e-5 and abs(ab['3B8BE3']['scaled_measurement']-486)<1e-5
    side_features=[f for f in c['source_features']['features'] if f['part_code']==code and f['kind']=='measured_straight_profile' and '3B8C84' in f['sheet_ids'] and any(abs(d['measurement']-381.5)<1e-5 for d in f['dimensions'])]
    assert len(side_features)==1
    side_points=[]
    for ref in side_features[0]['refs']:
        g=world(ab[ref])['geometry'];side_points.extend([g['start'],g['end']] if 'start' in g else [[p[0],p[1],g['elevation']] for p in g['points']])
    assert abs(max(p[1] for p in side_points)-min(p[1] for p in side_points)-697)<1e-5
    angle_refs=[o.ref for o in plan.operations if by[o.ref]['type']=='DIMENSION' and by[o.ref].get('dimension_type')==2]
    from cad.geometry import near
    assert angle_refs and all(near(ab[r]['geometry'],json.loads(next(o.after for o in plan.operations if o.ref==r)),1e-6) for r in angle_refs)
    import ezdxf
    opened=ezdxf.readfile(out/'reopened'/selected.name)
    def display(ref):
        dimension=opened.entitydb[ref]
        return ' '.join(e.plain_text() for e in opened.blocks[dimension.dxf.geometry].query('MTEXT'))
    assert display('3E13E8')=='1'
    assert all('90' in display(r) and '270' not in display(r) for r in angle_refs)
    for e in actual['entities']:
        for row in e.get('bom',{}).get('rows',[]):
            if row['part_code']==code:assert '1x382x697x812' in row['description']
    for sid in ('3B8A74','3B8B05','3B8B98','3B8C84'):
        t=next(t for t in targets if t['id']==sid);svg=render_sheet(out/'reopened'/selected.name,t)
        (out/(sid+'-after.svg')).write_text(svg,encoding='utf8');(out/(sid+'-after.png')).write_bytes(rasterize_svg(svg,width=1600))
    assert digest(source)==original
    dwg=out/'dwg'/selected.with_suffix('.dwg').name
    receipt=dict(customer_dauphine=True,fixture=False,source_hash=original,source_unchanged=True,approved=False,complete_product_backup=False,
        height_before_mm=724,height_after_mm=697,height_anchor='bottom',thickness_after_mm=1,outer_radius_mm=406.5,inner_radius_mm=405.5,
        source_height_dimensions=height_refs,thin_section_refs=thin_refs,changed_entities=len(plan.operations),roundtrip='passed',dwg=str(dwg.resolve()),dwg_hash=digest(dwg),
        curved_sections=2,side_view_height_mm=697,cut_blank_height_mm=697,cut_top_gap_mm=37,cut_bottom_gap_mm=486,regenerated_angular_dimensions=angle_refs,
        remaining=['Phôi chiều dài sau uốn chưa kiểm chứng','Chưa đồng bộ toàn bộ cụm, 12 vật tư laser và đóng gói'])
    storage.write_json(out/'receipt.json',receipt);storage.write_json(out/'plan.json',plan.model_dump());print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
