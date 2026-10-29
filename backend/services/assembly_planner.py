"""Assembly and sub-assembly level dimension planner.

Handles requests targeting assemblies (e.g. Khung chân C1, Cụm La trên C2)
and initializes the change plan so that synchronous propagation reaches all
constituent child parts, stage sheets, and BOM tables.
"""
import json
import re
from bom.reader import normalized
from cad.edit_engine import Operation
from backend.services.change_service import DrawingChangePlan

def compile_plan(context, request, clarifications=None):
    text = normalized(request)

    # 1. Skip if request is specifically for hole operations or sheet thickness
    from backend.services.sheet_thickness_planner import command as sheet_command
    if sheet_command(request) is not None:
        return None
    if any(w in text for w in ('do day', 'day tam', 'sat tam', 'tam lo', 'them lo', 'xoa lo', 'khoang cach lo')):
        return None

    old_val = None
    new_val = None
    # 1. Explicit range with 'tu' or arrow
    m = re.search(r'(?:\btu\s+|(?<![a-zA-Z\d]))(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:->|→)\s*(\d+(?:[.,]\d+)?)', text)
    if not m:
        m = re.search(r'\btu\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|sang|xuong|len|con)\s*(\d+(?:[.,]\d+)?)', text)
    if not m:
        m = re.search(r'(?<![a-zA-Z\d])(\d+(?:[.,]\d+)?)\s*mm\s*(?:thanh|sang|xuong|len|con)\s*(\d+(?:[.,]\d+)?)', text)
    if m:
        old_val = float(m.group(1).replace(',', '.'))
        new_val = float(m.group(2).replace(',', '.'))
    else:
        m2 = re.search(r'(?:thanh|sang|xuong|len|con|cao|dai|rong)\s*(\d+(?:[.,]\d+)?)', text)
        if m2:
            new_val = float(m2.group(1).replace(',', '.'))
        else:
            nums = re.findall(r'\b\d+(?:[.,]\d+)?\b', text)
            if nums:
                new_val = float(nums[-1].replace(',', '.'))

    graph = context.get('part_graph', {})
    seeds = graph.get('seed_codes', [])
    entities = context.get('entities', [])

    # 2. Resolve target_code
    target_code = None
    if seeds:
        target_code = seeds[0]
    if not target_code:
        from graph.part_graph import seed_codes
        found = seed_codes(context, request, graph)
        if found:
            target_code = next(iter(found))
    if not target_code and graph:
        from graph.part_graph import requested_numbers, part_number_key
        req_nums = [part_number_key(n) for n in requested_numbers(request)]
        if req_nums:
            for n in graph.get('nodes', []):
                if any(part_number_key(o.get('part_number', '')) in req_nums for o in n.get('bom_occurrences', [])):
                    target_code = n['code']
                    break
        if not target_code:
            for n in graph.get('nodes', []):
                if n.get('code') and re.search(r'(?<![\w.])' + re.escape(n['code']) + r'(?![\w.])', request):
                    target_code = n['code']
                    break

    if not target_code:
        return None

    # 3. Resolve old_val if user only supplied new_val
    if old_val is None and new_val is not None:
        for n in graph.get('nodes', []):
            if n.get('code') == target_code:
                from backend.services.size_commands import parse_part_dimensions
                for o in n.get('bom_occurrences', []):
                    pdims = parse_part_dimensions(o.get('description', ''))
                    # Collect dimension candidates
                    cands = [v for k, v in pdims.items() if k in ('dai', 'cao', 'rong') and v > 0]
                    if cands:
                        if any(w in text for w in ('cao', 'chieu cao', 'dung')) and 'cao' in pdims:
                            old_val = pdims['cao']
                        elif any(w in text for w in ('rong', 'chieu rong', 'bemat', 'ngang')) and 'rong' in pdims:
                            old_val = pdims['rong']
                        elif any(w in text for w in ('dai', 'chieu dai')) and 'dai' in pdims:
                            old_val = pdims['dai']
                        else:
                            old_val = min(cands, key=lambda v: abs(v - new_val))
                        break
                if old_val:
                    break

    if old_val is None and new_val is not None:
        dims = [e.get('scaled_measurement') or e.get('measurement', 0) for e in entities if e.get('type') == 'DIMENSION']
        if len(dims) == 1:
            old_val = dims[0]

    if old_val is None or new_val is None or abs(old_val - new_val) < 1e-6:
        return None

    delta = new_val - old_val
    old_str = f'{old_val:g}'
    new_str = f'{new_val:g}'

    # 4. Find anchor operations
    ops = []

    # 4a. Match DIMENSION
    for e in entities:
        if e.get('type') == 'DIMENSION':
            m_val = e.get('scaled_measurement') or e.get('measurement', 0)
            if abs(m_val - old_val) < 1.0:
                g = e.get('geometry', {})
                dp2 = list(g.get('defpoint2', [0, 0, 0]))
                dp3 = list(g.get('defpoint3', [0, 0, 0]))
                g_before = {"defpoint": list(g.get('defpoint', dp2)), "defpoint2": dp2, "defpoint3": dp3, "angle": g.get('angle', 0), "text": g.get('text', '<>')}
                g_after = dict(g_before)
                dx = abs(dp3[0] - dp2[0])
                dy = abs(dp3[1] - dp2[1])
                if dy >= dx:
                    g_after['defpoint3'] = [dp3[0], dp3[1] + delta, dp3[2]]
                else:
                    g_after['defpoint3'] = [dp3[0] + delta, dp3[1], dp3[2]]
                ops.append(Operation(ref=e['ref'], action='replace_geometry', before=json.dumps(g_before), after=json.dumps(g_after), xyz=[], reason=f'Đổi kích thước {target_code} {old_str} -> {new_str} mm'))
                break

    # 4b. Match TEXT / MTEXT
    if not ops:
        for e in entities:
            if e.get('type') in ('TEXT', 'MTEXT'):
                raw = e.get('raw_text', e.get('text', ''))
                if f'{old_str}mm' in raw or f'{old_str} mm' in raw:
                    after = raw.replace(f'{old_str}mm', f'{new_str}mm').replace(f'{old_str} mm', f'{new_str} mm')
                    ops.append(Operation(ref=e['ref'], action='replace_text', before=raw, after=after, xyz=[], reason=f'Đổi quy cách {target_code} {old_str} -> {new_str} mm'))
                    break
                elif re.search(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', raw):
                    after = re.sub(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', new_str, raw)
                    if after != raw:
                        ops.append(Operation(ref=e['ref'], action='replace_text', before=raw, after=after, xyz=[], reason=f'Đổi quy cách {target_code} {old_str} -> {new_str} mm'))
                        break

    # 4c. Match BOM Table cell
    if not ops:
        by_ref = {e['ref']: e for e in entities}
        for e in entities:
            bom = e.get('bom', {})
            for r in bom.get('rows', []):
                if r.get('part_code') == target_code:
                    desc_cell = r.get('cells', {}).get('description', {})
                    raw = desc_cell.get('raw_text', '')
                    idx = desc_cell.get('index', -1)
                    mirror = desc_cell.get('mirror_ref', '')
                    if raw and idx >= 0 and (f'{old_str}mm' in raw or f'{old_str} mm' in raw or re.search(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', raw)):
                        new_raw = re.sub(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', new_str, raw)
                        if new_raw != raw:
                            if desc_cell.get('storage') != 'text':
                                ops.append(Operation(ref=e['ref'], action='table_cell', cell_index=idx,
                                                     mirror_ref=mirror, before=raw, after=new_raw, xyz=[],
                                                     reason=f'Đổi quy cách bảng kê {target_code} {old_str} -> {new_str} mm'))
                            if mirror and mirror in by_ref:
                                m_rec = by_ref[mirror]
                                m_raw = m_rec.get('raw_text', m_rec.get('text', ''))
                                m_after = re.sub(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', new_str, m_raw)
                                if m_after != m_raw:
                                    ops.append(Operation(ref=mirror, action='replace_text',
                                                         before=m_raw, after=m_after, xyz=[],
                                                         reason=f'Đồng bộ text bảng kê {target_code} {old_str} -> {new_str} mm'))
                            break
            if ops:
                break

    if not ops:
        return None

    plan = DrawingChangePlan(
        summary=f'Chỉnh sửa kích thước {target_code} từ {old_str}mm thành {new_str}mm',
        target_part=target_code,
        operations=ops
    )
    return plan
