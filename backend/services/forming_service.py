"""Bind an authorized source forming rule to owned sections and measured blanks."""
import json
from bom.reader import normalized
from cad.geometry import near
from cad.parametric import LinearResize


def authorized(context, code):
    choices=context.get('design_choices',{})
    return choices.get('source_hash')==context.get('source_hash') and any(
        c.get('key')=='forming_rule' and c.get('part_code')==code and c.get('policy')=='source_calibrated_neutral_axis'
        for c in choices.get('confirmed_choices',[]))


def expected(plan, context, code):
    """Reconstruct from source on every compile/review; never trust model K values."""
    if not authorized(context,code):raise ValueError('Chưa chốt quy tắc uốn hiệu chỉnh từ bản nguồn')
    records={e['ref']:e for e in context['entities']}
    walls=[r for r in plan.curved_wall_recipes if r.part_code==code and len(r.outline_refs)==8]
    if len(walls)!=1:raise ValueError('Cần một mặt cắt nguồn trước chặt đủ hai chân uốn')
    wall=walls[0]
    nodes=[n for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==code]
    owned=set(s for n in nodes for s in n.get('detail_sheets',[]))
    other=set(s for n in context.get('part_graph',{}).get('nodes',[]) if n['code']!=code for s in n.get('detail_sheets',[]))
    owned-=other
    def stage(sids, first, second):
        return any(first in text and second in text and text.index(first)<text.index(second) for e in records.values()
            if set(e.get('source_sheet_ids',[]))&set(sids)&owned
            for text in [normalized(e.get('text',''))] if text.startswith('hdcv:'))
    sids=set.intersection(*(set(records[r].get('source_sheet_ids',[])) for r in wall.outline_refs))
    if not stage(sids,'uon','chat'):raise ValueError('Mặt cắt chưa có công đoạn uốn trước chặt được xác định')
    from cad.curved_wall import resize
    from cad.forming_calibration import calibrate, neutral_length
    before=[records[r] for r in wall.outline_refs]
    changes={op.ref:json.loads(op.after) for op in resize(wall,context)[0]}
    after=[dict(e,geometry=changes.get(e['ref'],e['geometry'])) for e in before]
    minimum, maximum=neutral_length(before,0),neutral_length(before,1)
    candidates=[]
    for feature in context.get('source_features',{}).get('features',[]):
        if feature.get('part_code')!=code or feature.get('ownership_proof') not in ('unique_source_detail_sheet','native_part_identity'):
            continue
        if not stage(feature.get('sheet_ids',[]),'cat laser','uon'):continue
        for dimension in feature.get('dimensions',[]):
            if minimum-1e-5 <= dimension['measurement'] <= maximum+1e-5 and near(dimension.get('linear_factor',1),1):
                candidates.append((feature,dimension))
    if len(candidates)!=1:raise ValueError('Chưa tìm được duy nhất phôi phẳng có DIM liên kết công đoạn uốn')
    feature, dimension=candidates[0]; dim=records[dimension['ref']]
    proof=calibrate(before,after,dimension['measurement'],dim.get('dimension_tolerance',{}))
    # The first cut datum is explicit in the measured source. Keep its position;
    # the independent cut-layout fit review below must also pass.
    recipe=LinearResize(part_code=code,dimension_ref=dimension['ref'],new_measurement=proof['target_nominal_mm'],
        outline_refs=feature['refs'],hole_refs=[],anchor='first',evidence_refs=feature['evidence_refs'])
    proof.update(part_code=code,dimension_ref=dimension['ref'],formed_outline_refs=wall.outline_refs,
                 flat_outline_refs=feature['refs'],source_hash=context['source_hash'])
    return recipe,proof


def compile_recipes(plan,context):
    for code in sorted({r.part_code for r in plan.curved_wall_recipes}):
        if not authorized(context,code):continue
        recipe,proof=expected(plan,context,code)
        previous=next((r for r in plan.resize_recipes if r.dimension_ref==recipe.dimension_ref),None)
        if previous and previous.model_dump()!=recipe.model_dump():
            raise ValueError('Recipe phôi uốn xung đột với quy tắc hiệu chỉnh nguồn')
        if not previous:plan.resize_recipes.append(recipe)
        warning='Phôi uốn '+code+': dùng quy tắc trung hòa hiệu chỉnh từ nguồn, giữ dung sai DIM; chưa thay thế kiểm tra công nghệ uốn tại xưởng.'
        if warning not in plan.warnings:plan.warnings.append(warning)
    return plan


def review(plan,context,code):
    recipe,proof=expected(plan,context,code)
    actual=next((r for r in plan.resize_recipes if r.dimension_ref==recipe.dimension_ref),None)
    if not actual or actual.model_dump()!=recipe.model_dump():raise ValueError('Thiếu recipe chiều dài phôi uốn đã hiệu chỉnh')
    operations={op.ref:op for op in plan.operations}
    op=operations.get(recipe.dimension_ref)
    if not op or op.action!='replace_geometry':raise ValueError('Thiếu thao tác DIM chiều dài phôi uốn')
    from graph.fit_constraints import measurement
    records={e['ref']:e for e in context['entities']}
    if not near(measurement(records[op.ref],json.loads(op.after)),recipe.new_measurement,1e-6):
        raise ValueError('Chiều dài phôi uốn không khớp quy tắc hiệu chỉnh')
    proof['cut_layouts']=cut_layouts(recipe,plan,context)
    return dict(proof,status='verified_source_calibrated_blank',reason='Phôi uốn và các bản cắt native tương ứng khớp quy tắc nguồn, dung sai và khổ tấm.')


def cut_layouts(recipe,plan,context):
    """Check complete native receiving blanks against measured rectangular stock.

    This verifies containment of the changed blank only, not arbitrary nesting.
    Other pieces and nesting clearance remain separate assembly/cutting checks.
    """
    import copy
    from cad.frame_geometry import world
    from graph.native_instances import equivalent_flat_refs
    from cad.closed_profiles import polygon_from
    records={e['ref']:e for e in context['entities']};ops={o.ref:o for o in plan.operations}
    roots={r.rsplit('/',1)[0] for r in recipe.outline_refs if '/' in r}
    if len(roots)!=1:raise ValueError('Phôi uốn chưa có định nghĩa native đầy đủ để đối chiếu bản cắt')
    root=next(iter(roots));reports=[]
    owned={s for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==recipe.part_code for s in n.get('detail_sheets',[])}
    ambiguous={s for n in context.get('part_graph',{}).get('nodes',[]) if n['code']!=recipe.part_code for s in n.get('detail_sheets',[])}
    owned-=ambiguous
    def updated(ref):
        record=copy.deepcopy(records[ref]);op=ops.get(ref)
        if op:
            if op.action!='replace_geometry':raise ValueError('Bản cắt có thao tác không xác định được hình học')
            record['geometry']=json.loads(op.after)
        return world(record)
    for target,e in records.items():
        if e['type']!='INSERT' or target==root or e.get('review_only') or not owned.intersection(e.get('source_sheet_ids',[])):continue
        mapping=equivalent_flat_refs(records,root,target)
        if not mapping:continue
        refs=[mapping[r] for r in recipe.outline_refs]
        # Copy completeness is checked independently of containment. A shorter
        # stale cut blank could otherwise pass the stock-bounds check.
        for source,received in mapping.items():
            if source in ops and (received not in ops or ops[received].action!=ops[source].action or
                    not near(json.loads(ops[received].after),json.loads(ops[source].after),1e-6)):
                raise ValueError('Bản cắt thiếu đồng bộ hình học phôi uốn: '+received)
        polygon=polygon_from([updated(r) for r in refs])
        stocks=[]
        for f in context.get('source_features',{}).get('features',[]):
            if not set(f.get('sheet_ids',[]))&set(e.get('source_sheet_ids',[])) or set(f['refs'])&set(refs) or len(f.get('dimensions',[]))!=2:continue
            from cad.measured_features import rectangle
            stock=rectangle(f.get('points',[]))
            from shapely.geometry import Polygon
            if stock and all(abs(p[2]-polygon[0][2])<1e-5 for p in stock['points']) and \
                    Polygon([p[:2] for p in stock['points']]).buffer(1e-5).covers(Polygon([p[:2] for p in polygon])):
                stocks.append(f)
        if len(stocks)!=1:raise ValueError('Phôi uốn sau sửa chưa nằm trong duy nhất khổ tấm có DIM nguồn')
        stock=stocks[0]
        if any(r in ops for r in stock['refs']):raise ValueError('Không được thay khổ tấm để hợp thức hóa phôi uốn')
        reports.append(dict(instance_ref=target,stock_refs=stock['refs'],contained=True,full_native_copy=True))
    if not reports:raise ValueError('Chưa xác minh được bản cắt native của phôi uốn')
    return reports
