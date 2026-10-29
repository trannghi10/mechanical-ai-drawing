"""Bind requested heights to physical source dimensions, separately from CAD validity."""
import json
import math
import re

from bom.reader import normalized
from cad.geometry import near


OVERALL = re.compile(r'chieu cao\s+(?:tong the|thanh pham|san pham)\s*(?:san pham\s*)?(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|con|->|→)\s*(\d+(?:[.,]\d+)?)')
PART_HEIGHT = re.compile(r'chieu cao\s*(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|con|->|→)\s*(\d+(?:[.,]\d+)?)')


def fixed_sides(text):
    words = re.findall(r'(?:giu|co dinh)\s*(?:nguyen\s*|co dinh\s*)?(?:dau\s*|canh\s*|mat\s*)?(trai|phai|tren|duoi|tam|day|chan|dinh)\b', normalized(text))
    mapping = dict(trai='left', phai='right', tren='top', duoi='bottom', tam='center', day='bottom', chan='bottom', dinh='top')
    return {mapping[word] for word in words}


def stored_anchor(context):
    choices = context.get('design_choices', {})
    if not context.get('source_hash') or choices.get('source_hash') != context['source_hash']:
        return None
    anchors = [c for c in choices.get('confirmed_choices', []) if c.get('key') == 'height_anchor']
    if len(anchors) != 1 or anchors[0].get('anchor') not in ('bottom', 'top'):
        return None
    product = anchors[0].get('product_code')
    roots = set(context.get('root_target_ids', []))
    if product and not any(t['id'] in roots and product in t.get('texts', []) for t in context.get('targets', [])):
        return None
    return anchors[0]['anchor']


def overall_goal(context, request, clarifications=None):
    """A saved answer may disambiguate frame vs finished height, never override a new datum."""
    match = OVERALL.search(normalized(request))
    if not match:
        return None
    old, new = [float(v.replace(',', '.')) for v in match.groups()]
    choices = context.get('design_choices', {})
    height = [c for c in choices.get('confirmed_choices', []) if c.get('key') == 'overall_height']
    anchor = stored_anchor(context)
    if len(height) != 1 or anchor is None:
        raise ValueError('Chưa gắn chiều cao thành phẩm, chiều cao khung và mốc giữ với đúng nguồn CAD; không được coi chiều cao tổng thể là chiều cao một chi tiết.')
    height = height[0]
    d = choices.get('derived_values', {})
    before, after, stack = [d.get(k) for k in ('frame_height_before_mm', 'frame_height_target_mm', 'top_stack_mm')]
    values = [old, new, before, after, stack, height.get('before_mm'), height.get('target_mm')]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        raise ValueError('Thiếu số đo nguồn hoặc số đo đích để phân biệt khung và thành phẩm.')
    if min(before, after, old, new) <= 0 or stack < 0 or not near(before + stack, height['before_mm']) or not near(after + stack, height['target_mm']):
        raise ValueError('Chiều cao khung và phần chênh thành phẩm không khớp quyết định nguồn.')
    delta = next(c.get('delta_mm') for c in choices['confirmed_choices'] if c.get('key') == 'height_anchor')
    if not isinstance(delta, (int, float)) or not math.isfinite(delta) or not near(after - before, delta):
        raise ValueError('Độ dịch mặt trên/dưới không khớp chiều cao đã chốt.')
    if not near(new, height['target_mm']) or not any(near(old, v) for v in (before, height['before_mm'])):
        raise ValueError('Số đo trong yêu cầu mới khác mục tiêu đã chốt; không được dùng mục tiêu cũ để sửa yêu cầu mới.')
    sides = fixed_sides(request + ' ' + ' '.join(c.get('answer', '') for c in clarifications or []))
    if sides and sides != {anchor}:
        raise ValueError('Mốc giữ trong yêu cầu mới khác mốc chiều cao đã chốt; chưa được dùng mốc cũ để dịch các chi tiết liên quan.')
    return dict(kind='overall_height', before_mm=height['before_mm'], target_mm=new,
                frame_before_mm=before, frame_target_mm=after, retained_stack_mm=stack,
                fixed_side=anchor, source_hash=context['source_hash'],
                request_source_role='frame' if near(old, before) else 'finished_product',
                note='Giữ phần chênh khung/thành phẩm theo nguồn; không gán số đo thành phẩm cho mọi chi tiết.')


def review(context, request, clarifications=None):
    from backend.services.compound_planner import clauses
    result = []
    for clause in clauses(request):
        if not OVERALL.search(normalized(clause)):
            continue
        try:
            goal = overall_goal(context, clause, clarifications)
            result.append(dict(goal, status='resolved', clause=clause))
        except ValueError as error:
            result.append(dict(kind='overall_height', status='unresolved', clause=clause, reason=str(error)))
    return result


def verify(plan, context, request, clarifications=None):
    """Check the user goal again for saved/model plans, before either kind of apply."""
    if plan.questions or not plan.operations:
        return
    from backend.services.compound_planner import clauses
    from cad.frame_geometry import world
    from cad.dimensions import linear_axis
    from graph.fit_constraints import measurement
    records = {e['ref']: e for e in context['entities']}
    operations = {o.ref: o for o in plan.operations}
    for clause in clauses(request):
        overall = OVERALL.search(normalized(clause))
        command = PART_HEIGHT.search(normalized(clause)) if not overall else None
        if overall:
            goal = overall_goal(context, clause, clarifications)
            old, new, side = goal['frame_before_mm'], goal['frame_target_mm'], goal['fixed_side']
            if not plan.requires_complete_product_review:
                raise ValueError('Sửa chiều cao tổng thể phải kiểm tra toàn sản phẩm; không được chứng nhận chỉ một chi tiết.')
            codes = None
        elif command:
            old, new = [float(v.replace(',', '.')) for v in command.groups()]
            from graph.part_graph import seed_codes
            codes = seed_codes(context, clause, context.get('part_graph'))
            if len(codes) != 1:
                continue
            sides = fixed_sides(clause + ' ' + ' '.join(c.get('answer', '') for c in clarifications or []))
            if len(sides) > 1:
                raise ValueError('Yêu cầu chiều cao có nhiều mốc giữ trái nhau.')
            side = next(iter(sides), None) or stored_anchor(context)
        else:
            continue
        primary = []
        for recipe in plan.resize_recipes:
            if codes is not None and recipe.part_code not in codes:
                continue
            record = records.get(recipe.dimension_ref, {})
            if not near(record.get('scaled_measurement', -1), old):
                continue
            drawing_record = world(record)
            g = drawing_record['geometry']
            a, b = g['defpoint2'], g['defpoint3']
            axis = linear_axis(drawing_record)
            if abs(axis[0]) > 1e-5 or abs(axis[1]) < 1 - 1e-5 or abs(a[1] - b[1]) < 1e-5:
                continue
            primary.append(recipe)
            if recipe.new_measurement is None or not near(recipe.new_measurement, new, 1e-6):
                raise ValueError('Kích thước recipe khác chiều cao yêu cầu: ' + recipe.dimension_ref)
            if side:
                expected = 'center' if side == 'center' else 'first' if ((a[1] < b[1]) == (side == 'bottom')) else 'second'
                if side not in ('top', 'bottom', 'center') or recipe.anchor != expected:
                    raise ValueError('Mốc giữ recipe khác yêu cầu chiều cao: ' + recipe.dimension_ref)
            op = operations.get(recipe.dimension_ref)
            if not op or op.action != 'replace_geometry' or not near(measurement(record, json.loads(op.after)), new, 1e-6):
                raise ValueError('DIM sau sửa không đạt chiều cao yêu cầu: ' + recipe.dimension_ref)
        if not primary:
            raise ValueError('Không có DIM chiều cao đo thật và recipe đúng chủ sở hữu để thực hiện yêu cầu.')
