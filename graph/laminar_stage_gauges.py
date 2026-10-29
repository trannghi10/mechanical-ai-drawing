"""Update a flat welded sheet stage only when every native BOM member agrees.

Assembly edges alone locate the stage. A measured constant-gauge profile,
complete native member table, common material and executed child gauge DIMs
prove this limited propagation. It does not certify assembly projections.
"""
import json
from cad.geometry import near
from cad.parametric import LinearResize
from backend.services.design_choices import sheet_spec
from bom.stage_links import physical_spec
from cad.edit_engine import Operation

TOL=1e-5


def proofs(plan,context):
    choices=context.get('design_choices',{})
    if context.get('units')!=4 or choices.get('source_hash')!=context.get('source_hash'):return []
    anchors=[v for v in choices.get('confirmed_choices',[]) if v.get('key')=='sheet_thickness_anchor' and v.get('process_id')=='cut_laser' and v.get('fallback_anchor')=='center']
    if len(anchors)!=1:return []
    anchor=anchors[0];old,new=anchor['before_thickness_mm'],anchor['target_thickness_mm']
    records={e['ref']:e for e in context['entities']};ops={o.ref:o for o in plan.operations if o.action=='replace_geometry'}
    changed=set()
    from graph.fit_constraints import measurement
    for r in plan.resize_recipes:
        d=records.get(r.dimension_ref,{});op=ops.get(r.dimension_ref)
        if op and near(d.get('scaled_measurement'),old,TOL) and near(r.new_measurement,new,TOL) and near(json.loads(op.before),d.get('geometry'),TOL) and near(measurement(d,json.loads(op.after)),new,TOL):changed.add(r.part_code)
    graph=context.get('part_graph',{});features=context.get('source_features',{}).get('features',[]);result=[]
    for node in graph.get('nodes',[]):
        code=node['code'];edges=[e for e in graph.get('edges',[]) if e.get('kind')=='assembly_bom' and e['target']==code]
        children={e['source'] for e in edges}
        if not children or not children<=changed:continue
        tables={v['table_ref'] for e in edges for v in e.get('evidence',[]) if v.get('table_ref')}
        if not tables or any(t not in records or records[t].get('bom',{}).get('status')!='verified_template' for t in tables):continue
        member_rows=[r for t in tables for r in records[t]['bom']['rows']]
        # Every member must be one of those driven sheet parts. A fastener,
        # tube, spacer or unidentified BOM row prevents this inference.
        if {r['part_code'] for r in member_rows}!=children:continue
        if any(not sheet_spec(r['description']) or not near(sheet_spec(r['description'])[0],old,TOL) for r in member_rows):continue
        parents=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
        if not parents or any(t['bom'].get('status')!='verified_template' or not sheet_spec(r['description']) or not near(sheet_spec(r['description'])[0],old,TOL) for t,r in parents):continue
        materials={r['material'] for r in member_rows}|{r['material'] for t,r in parents}
        if len(materials)!=1 or not next(iter(materials)):continue
        recipes=[]
        for f in features:
            if f.get('part_code')!=code or f.get('ownership_proof') not in ('native_part_identity','unique_source_detail_sheet'):continue
            for d in f['dimensions']:
                if not near(d['measurement'],old,TOL):continue
                axis=d['axis'];cross=[-axis[1],axis[0],0]
                spans=[sum(a*b for a,b in zip(p,cross)) for p in f['points']]
                if max(spans)-min(spans)<=old+TOL:continue
                recipes.append(LinearResize(part_code=code,dimension_ref=d['ref'],new_measurement=new,outline_refs=f['refs'],hole_refs=[],anchor='center',evidence_refs=f['evidence_refs']))
        if not recipes:continue
        result.append(dict(part_code=code,children=sorted(children),member_tables=sorted(tables),before_mm=old,after_mm=new,recipe_data=[r.model_dump() for r in recipes],
                           status='native_members_and_measured_laminar_gauge'))
    return result


def text_operations(proof,context):
    from backend.services.sheet_thickness_planner import _replace_gauge
    from bom.operations import cell_operations
    records={e['ref']:e for e in context['entities']};code=proof['part_code'];result=[]
    rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
    for t,r in rows:
        cell=r['cells']['description'];result.extend(cell_operations(t,cell,_replace_gauge(cell['raw_text'],proof['before_mm'],proof['after_mm']),records,'Đồng bộ cụm tấm theo toàn bộ vật tư và mặt cắt công đoạn đo thật'))
    specs={physical_spec(r['description']) for t,r in rows}
    sheets={s for n in context['part_graph']['nodes'] if n['code']==code for s in n.get('detail_sheets',[])}
    mirrors={o.ref for o in result}
    for e in records.values():
        raw=e.get('raw_text',e.get('text',''))
        if e['type'] in ('TEXT','MTEXT') and e['ref'] not in mirrors and sheets.intersection(e.get('source_sheet_ids',[])) and physical_spec(raw) in specs:
            result.append(Operation(ref=e['ref'],action='replace_text',before=raw,after=_replace_gauge(raw,proof['before_mm'],proof['after_mm']),xyz=[],reason='Đồng bộ độ dày tên cụm tại công đoạn nguồn'))
    return result


def expected_operations(proof,context):
    from cad.multi_resize import resize_many
    recipes=[LinearResize.model_validate(v) for v in proof['recipe_data']]
    return text_operations(proof,context)+resize_many(recipes,context,{r.dimension_ref:r.new_measurement for r in recipes})


def synchronize(plan,context):
    checks=proofs(plan,context)
    if not checks:return plan
    from backend.services.change_service import EditProposal
    from backend.services.compound_planner import operation_key,same_operation
    result=plan.model_copy(deep=True);ops={operation_key(o):o for o in result.operations};recipes={r.dimension_ref:r for r in result.resize_recipes}
    for proof in checks:
        for data in proof['recipe_data']:
            r=LinearResize.model_validate(data)
            if r.dimension_ref in recipes and recipes[r.dimension_ref].model_dump()!=r.model_dump():raise ValueError('Mặt cắt cụm tấm có recipe xung đột')
            if r.dimension_ref not in recipes:result.resize_recipes.append(r);recipes[r.dimension_ref]=r
        for op in expected_operations(proof,context):
            key=operation_key(op)
            if key in ops and not same_operation(ops[key],op):raise ValueError('Cụm tấm có thay đổi xung đột: '+op.ref)
            ops[key]=op;result.edits=[e for e in result.edits if not (e.entity_ref==op.ref and e.before==op.before)]
            result.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['part_code'],purpose='geometry' if op.action=='replace_geometry' else 'bom' if op.action=='table_cell' else 'annotation',before=op.before,after=op.after,reason=op.reason))
    result.operations=list(ops.values());validate(result,context);return result


def validate(plan,context):
    from backend.services.compound_planner import operation_key,same_operation
    actual={operation_key(o):o for o in plan.operations}
    for proof in proofs(plan,context):
        for expected in expected_operations(proof,context):
            if operation_key(expected) not in actual or not same_operation(expected,actual[operation_key(expected)]):raise ValueError('Cụm tấm/công đoạn chưa đồng bộ theo độ dày vật tư con')
