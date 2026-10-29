"""A material/process-wide gauge change compiled from source BOM and DIMs.

No drawing handles, product names or replacement coordinates are built in.
Mechanical contacts and assembly/formed/packing coverage remain separate gates.
"""
import math
import re
from collections import defaultdict

from bom.reader import normalized
from bom.processes import process_tags
from bom.stage_links import physical_spec
from bom.operations import cell_operations
from cad.edit_engine import Operation
from cad.geometry import near
from cad.measured_features import index
from cad.parametric import LinearResize

NUMBER = r'(\d+(?:[.,]\d+)?)'


def command(request):
    text = normalized(request)
    if 'hop' in text or 'ong' in text:
        return None
    if not ('sat tam' in text or 'tam' in text or re.search(r'\b(?:do|be)\s*day\b', text)):
        return None
    # A global thickness compiler must not consume a height/width change too.
    if re.search(r'chieu\s+(?:cao|rong|dai)|duong kinh|ban kinh|them lo|bo lo', text):
        return None
    matches = list(re.finditer(r'(?:day\s*)?(?:tu\s*)?'+NUMBER+r'\s*(?:mm\s*)?(?:thanh|xuong|sang|->|→)\s*(?:day\s*)?'+NUMBER+r'\s*(?:mm)?', text))
    if len(matches) != 1:
        return None
    old, new = [float(v.replace(',', '.')) for v in matches[0].groups()]
    if not all(math.isfinite(v) and v > 0 for v in (old, new)) or near(old, new):
        return None
    return old, new


def _gauge(text):
    m = re.search(r'sat tam\s*'+NUMBER+r'\s*[x×]', normalized(text))
    return float(m[1].replace(',', '.')) if m else None


def _replace_gauge(raw, old, new):
    # Do not replace the same number in stock codes, tolerances or length fields.
    pattern = re.compile(r'(?i)(Sắt\s+tấm\s*)'+NUMBER+r'(?=\s*[x×])')
    matches = list(pattern.finditer(raw))
    if len(matches) != 1 or not near(float(matches[0][2].replace(',', '.')), old, 1e-5):
        raise ValueError('Không xác định duy nhất độ dày sắt tấm trong mô tả nguồn')
    m = matches[0]
    return raw[:m.start(2)] + f'{new:g}' + raw[m.end(2):]


def compile_plan(context, request, clarifications=None):
    parsed = command(request)
    if parsed is None or context.get('units') != 4:
        return None
    old, new = parsed
    text = normalized(request+' '+' '.join(c.get('answer', '') for c in clarifications or []))
    choices = context.get('design_choices', {})
    bound = choices.get('source_hash') == context.get('source_hash')
    anchor_choices = [c for c in choices.get('confirmed_choices', []) if bound and
        c.get('key') == 'sheet_thickness_anchor' and c.get('process_id') == 'cut_laser' and
        near(c.get('before_thickness_mm'), old, 1e-5) and near(c.get('target_thickness_mm'), new, 1e-5)]
    centered = bool(re.search(r'giu\s+(?:mat\s+(?:phang\s+)?)?(?:giua|tam)\b', text)) or (
        len(anchor_choices) == 1 and anchor_choices[0].get('fallback_anchor') == 'center')
    records = {e['ref']: e for e in context['entities']}
    roots = set(context.get('root_bom_refs', []))
    rows = [(t, r) for t in records.values() if t.get('bom', {}).get('status') == 'verified_template'
            for r in t['bom']['rows']]
    root_rows = [(t, r) for t, r in rows if not roots or t['ref'] in roots]
    codes = {r['part_code'] for t, r in root_rows if near(_gauge(r.get('description', '')), old, 1e-5)
             and any(p['id'] == 'cut_laser' for p in process_tags(r['description']))}
    if not codes:
        return None
    from backend.services.change_service import DrawingChangePlan, EditProposal
    plan = DrawingChangePlan(summary=f'Sắt tấm cắt laser: {old:g} → {new:g} mm cho {len(codes)} chi tiết.',
        target_part=', '.join(sorted(codes)), edits=[], dependencies=[], questions=[], warnings=[])
    if not centered:
        plan.questions.append('Cần chốt mặt giữ cho các tấm laser: giữ mặt giữa khi chưa có mốc lắp, hoặc chỉ định riêng từng chi tiết.')
        return plan
    features = (context.get('source_features') or index(context, context.get('part_graph')))['features']
    by_code = defaultdict(list)
    for f in features:
        if f.get('part_code') in codes and f.get('ownership_proof') in ('native_part_identity', 'unique_source_detail_sheet'):
            by_code[f['part_code']].append(f)
    curved = {}
    source_owners = defaultdict(set)
    for n in context.get('part_graph', {}).get('nodes', []):
        for sid in n.get('detail_sheets', []):
            source_owners[sid].add(n['code'])
    for code in sorted(codes):
        owned = {s for s, values in source_owners.items() if values == {code}}
        local = [e for e in records.values() if owned.intersection(e.get('source_sheet_ids', [])) and
                 e['type'] == 'ARC' and e.get('geometry') and not e.get('review_only')]
        # Curved shells need an explicit physical outer datum. An isolated
        # straight gauge view may be centered on its own page independently.
        curved_section = any(near(a['geometry']['center'], b['geometry']['center'], 1e-5)
            and near(abs(a['geometry']['radius']-b['geometry']['radius']), old, 1e-5)
            for i, a in enumerate(local) for b in local[i+1:])
        if curved_section:
            from backend.services.curved_wall_planner import compile_plan as wall_plan
            wall_context = dict(context, part_graph=dict(context.get('part_graph', {}), seed_codes=[code]))
            wall = wall_plan(wall_context, f'{code} độ dày từ {old:g} thành {new:g} mm')
            if wall is not None:
                curved[code] = wall.curved_wall_recipes
            else:
                plan.questions.append('Mặt cắt cong '+code+' cần mốc giữ và recipe đường bao nguồn trước khi đổi độ dày.')
    if plan.questions:
        return plan
    missing = []
    for code in sorted(codes):
        dims = set()
        for f in by_code[code]:
            for d in f['dimensions']:
                if not near(d['measurement'], old, 1e-5):
                    continue
                # The source contour, not a repeated numeric annotation,
                # must be a gauge section with a longer cross dimension.
                axis = d['axis']
                cross = [-axis[1], axis[0], 0]
                span = max(sum(p[k]*cross[k] for k in range(3)) for p in f['points']) - min(
                    sum(p[k]*cross[k] for k in range(3)) for p in f['points'])
                if span <= old + 1e-5 or d['ref'] in dims:
                    continue
                dims.add(d['ref'])
                plan.resize_recipes.append(LinearResize(part_code=code, dimension_ref=d['ref'], new_measurement=new,
                    outline_refs=f['refs'], hole_refs=[], anchor='center', evidence_refs=f['evidence_refs']))
        if not dims:
            missing.append(code)
        plan.curved_wall_recipes.extend(curved.get(code, []))
    if missing:
        plan.questions.append('Chưa mở/gắn được mặt cắt độ dày đo thật cho: '+', '.join(missing))
        return plan
    ops = {}
    def add(op, code, purpose):
        key = (op.ref, op.cell_index if op.action == 'table_cell' else -1)
        if key in ops:
            from backend.services.compound_planner import same_operation
            if not same_operation(ops[key], op):
                raise ValueError('Hai quy cách vật tư xung đột tại cùng ô CAD')
            return
        ops[key] = op
        plan.operations.append(op)
        plan.edits.append(EditProposal(entity_ref=op.ref, part_number=code, purpose=purpose,
            before=op.before, after=op.after, reason=op.reason))
    try:
        specs = defaultdict(set)
        cell_refs = {c.get('mirror_ref') for t, r in rows for c in r.get('cells', {}).values()}
        for table, row in rows:
            code = row['part_code']
            if code not in codes:
                continue
            specs[code].add(physical_spec(row['description']))
            cell = row.get('cells', {}).get('description', {})
            raw = cell.get('raw_text', '')
            after = _replace_gauge(raw, old, new)
            for op in cell_operations(table, cell, after, records, 'Đồng bộ độ dày sắt tấm cùng công đoạn laser'):
                add(op, code, 'bom')
        for e in records.values():
            if e['type'] not in ('TEXT', 'MTEXT') or e['ref'] in cell_refs:
                continue
            owners = set().union(*(source_owners[s] for s in e.get('source_sheet_ids', [])))
            if len(owners) != 1 or not owners <= codes:
                continue
            code = next(iter(owners))
            raw = e.get('raw_text', e.get('text', ''))
            if physical_spec(e.get('text', raw)) in specs[code]:
                add(Operation(ref=e['ref'], action='replace_text', before=raw, after=_replace_gauge(raw, old, new), xyz=[],
                    reason='Đồng bộ quy cách tấm trên bản chi tiết/công đoạn nguồn'), code, 'annotation')
            elif re.search(r'vat tu\s*:', normalized(raw)) and near(_gauge(raw), old, 1e-5):
                stock = [c for c in choices.get('confirmed_choices', []) if bound and c.get('key') == 'sheet_stock_code']
                if len(stock) != 1 or stock[0].get('after_code') is not None:
                    raise ValueError('Cần xác định mã nguyên liệu mới hoặc ghi chờ cấp mã')
                before_code = re.escape(stock[0]['before_code'])
                pattern = re.compile(before_code+r'\s+Sắt\s+tấm\s*\d+(?:[.,]\d+)?\s*[x×]\s*\d+\s*[x×]\s*\d+\s*(?:mm)?', re.I)
                if len(pattern.findall(raw)) != 1 or not near(_gauge(stock[0]['after_description']), new, 1e-5):
                    raise ValueError('Chưa khớp duy nhất ghi chú cấp mã nguyên liệu nguồn')
                add(Operation(ref=e['ref'], action='replace_text', before=raw, after=pattern.sub(lambda _: stock[0]['after_description'], raw),
                    xyz=[], reason='Đổi quy cách mua hàng; bỏ mã tấm cũ, ghi chờ cấp mã'), code, 'annotation')
        from backend.services.parametric_service import compile_recipes
        plan = compile_recipes(plan, context)
        plan.warnings.append('Mặt cắt rời giữ tâm trên trang; các mốc tiếp xúc đã có bằng chứng được kiểm tra riêng. Chưa suy độ bền hay chứng nhận mọi hình cụm/phôi uốn.')
        return plan
    except ValueError as error:
        plan.operations = []
        plan.edits = []
        plan.questions.append(str(error))
        return plan
