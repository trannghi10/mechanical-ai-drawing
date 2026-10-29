"""Link side-pad elevations to measured orthographic footprints and BOM.

Identity requires a measured top carton aligned with the side carton, a unique
foam specification, its complete footprint count and a separately owned DIM
detail. Source end gaps are measured and preserved, not called compression.
"""
import copy
import json
import math
import re

from bom.reader import normalized
from cad.edit_engine import Operation
from cad.frame_geometry import world, local_geometry
from cad.geometry import near
from cad.hatch_translation import follow_boundary
from graph.packing_top_layers import same_boundary

TOL = 1e-4


def rect(record):
    if record.get('review_only') or record.get('type') != 'LWPOLYLINE' or not record.get('geometry'):
        return None
    g = world(record)['geometry']
    if not g['closed'] or any(any(p[2:]) for p in g['points']):
        return None
    points = [p[:2] for p in g['points']]
    low = [min(p[i] for p in points) for i in (0, 1)]
    high = [max(p[i] for p in points) for i in (0, 1)]
    if min(high[i]-low[i] for i in (0, 1)) < TOL or not same_boundary(points,
            [[low[0], low[1]], [high[0], low[1]], [high[0], high[1]], [low[0], high[1]]]):
        return None
    return dict(ref=record['ref'], low=low, high=high, size=[high[i]-low[i] for i in (0, 1)], geometry=g)


def dim_bound(d, box, axis):
    if d.get('review_only') or d.get('type') != 'DIMENSION' or d.get('dimension_type') != 0 or not d.get('geometry'):
        return False
    w = world(d)
    g = w['geometry']
    a = [math.cos(math.radians(g['angle'])), math.sin(math.radians(g['angle']))]
    return (g.get('text') in ('', '<>') and near(abs(a[axis]), 1, TOL) and
        near(abs(w.get('linear_factor', 1)), 1, TOL) and near(d.get('scaled_measurement'), box['size'][axis], TOL) and
        near(sorted(g[k][axis] for k in ('defpoint2', 'defpoint3')), [box['low'][axis], box['high'][axis]], TOL) and
        all(any(near(g[k][:2], p[:2], TOL) for p in box['geometry']['points']) for k in ('defpoint2', 'defpoint3')))


def bound_hatches(context, outline, after):
    result = []
    for e in context['entities']:
        if e['type'] != 'HATCH' or e.get('review_only') or e.get('layout') != outline.get('layout') or e.get('coordinate_frame') != outline.get('coordinate_frame') or not set(e.get('source_sheet_ids', [])).intersection(outline.get('source_sheet_ids', [])):
            continue
        paths = (e.get('hatch_translation_geometry') or {}).get('paths') or e.get('read_only_geometry', {}).get('boundary_paths', [])
        if len(paths) != 1 or not same_boundary([p[:2] for p in outline['geometry']['points']],
                [p[:2] for p in paths[0].get('vertices', [])], TOL):
            continue
        old = e.get('hatch_translation_geometry')
        if not old:
            raise ValueError('Xốp có HATCH association/đường cong chưa hỗ trợ: '+e['ref'])
        new = follow_boundary(old, outline['geometry']['points'], after['points'])
        result.append(Operation(ref=e['ref'], action='replace_geometry', before=json.dumps(old), after=json.dumps(new),
            xyz=[], reason='Co/giãn HATCH xốp theo đường bao nguồn; giữ pattern và topology'))
    if len(result) > 1:
        raise ValueError('Xốp có HATCH trùng lặp cần kiểm tra: '+outline['ref'])
    return result


def bindings(context, envelope, top_stacks):
    if context.get('units') != 4 or len(top_stacks) != 1:
        return []
    stack = top_stacks[0][0]
    sid = envelope['sheet_id']
    group = next(g for g in context['part_graph']['packaging_groups'] if g['product_code'] == envelope['product_code'])
    records = {e['ref']:e for e in context['entities']}
    local = [e for e in records.values() if sid in e.get('source_sheet_ids', [])]
    shapes = [r for e in local if (r := rect(e)) is not None]
    box = rect(records[envelope['carton_outline_ref']])
    dims = [e for e in local if e['type'] == 'DIMENSION']
    carton_specs = set()
    foam_specs = {}
    for table in local:
        if table.get('bom', {}).get('status') != 'verified_template':
            continue
        for row in table['bom']['rows']:
            m = re.search(r'(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)', normalized(row['description']))
            if not m:
                continue
            spec = tuple(float(v.replace(',', '.')) for v in m.groups())
            if row['part_code'] == envelope['carton_code']:
                carton_specs.add(spec)
            elif row['part_code'] in group['package_codes'] and re.match(r'(?:xop tam|tam xop|foam)\b', normalized(row['description'])) and re.fullmatch(r'\d+', row.get('quantity_text', '')):
                foam_specs.setdefault(row['part_code'], set()).add((spec, int(row['quantity_text'])))
    if len(carton_specs) != 1:
        return []
    cw, depth, height = next(iter(carton_specs))
    if not near(box['size'], [cw, height], TOL):
        return []
    top_boxes = [r for r in shapes if near(r['size'], [cw, depth], TOL) and
        near([r['low'][0], r['high'][0]], [box['low'][0], box['high'][0]], TOL) and
        # Registration is established by matching X extents and two real
        # dimensions, not by whether the drafter put the plan above/below.
        (r['low'][1] > box['high'][1]+TOL or r['high'][1] < box['low'][1]-TOL) and
        all(any(dim_bound(d, r, axis) for d in dims) for axis in (0, 1))]
    if len(top_boxes) != 1:
        return []
    top = top_boxes[0]
    top_plane = min(l['low'] for l in stack['layers'])
    delta = stack['delta_mm']
    candidates = []
    for code, entries in foam_specs.items():
        if len(entries) != 1:
            continue
        (thickness, width, nominal), quantity = next(iter(entries))
        if not 0 < thickness < min(width, nominal):
            continue
        footprints = [r for r in shapes if r['ref'] != top['ref'] and
            all(r['low'][i] >= top['low'][i]-TOL and r['high'][i] <= top['high'][i]+TOL for i in (0, 1)) and
            (near(r['size'], [thickness, width], TOL) or near(r['size'], [width, thickness], TOL))]
        if len(footprints) != quantity or quantity < 2:
            continue
        sides = []
        for shape in shapes:
            if shape['ref'] in envelope['product_section_refs'] or not near(shape['size'][0], thickness, TOL) or shape['size'][1] <= thickness:
                continue
            if not all(shape['low'][i] >= box['low'][i]-TOL and shape['high'][i] <= box['high'][i]+TOL for i in (0, 1)):
                continue
            aligned = [f for f in footprints if near(f['size'], [thickness, width], TOL) and
                       near([shape['low'][0], shape['high'][0]], [f['low'][0], f['high'][0]], TOL)]
            if len(aligned) != 1 or shape['high'][1] > top_plane+TOL:
                continue
            top_contacts = [l for l in stack['layers'] if near(l['low'], top_plane, TOL) and
                min(max(p[0] for p in l['points']), shape['high'][0])-
                max(min(p[0] for p in l['points']), shape['low'][0]) > TOL]
            if len(top_contacts) != 1:
                continue
            # An actual stationary lower contact face closes the constraint.
            lower = [r for r in shapes if r['ref'] != shape['ref'] and near(r['high'][1], shape['low'][1], TOL) and
                r['size'][0] > r['size'][1] and r['high'][1] <= min(
                    p[1] for ref in envelope['product_section_refs'] for p in world(records[ref])['geometry']['points'])+TOL and
                min(r['high'][0], shape['high'][0])-max(r['low'][0], shape['low'][0]) > TOL]
            if len(lower) != 1:
                continue
            sides.append(dict(shape, footprint_ref=aligned[0]['ref'], bottom_contact_ref=lower[0]['ref'],
                              top_contact_ref=top_contacts[0]['ref'],
                              top_gap_mm=top_plane-shape['high'][1]))
        vertical = [f for f in footprints if near(f['size'], [thickness, width], TOL)]
        if not sides or len(sides) != len(vertical) or {s['footprint_ref'] for s in sides} != {f['ref'] for f in vertical} or not any(near(s['size'][1], nominal, TOL) and near(s['top_gap_mm'], 0, TOL) for s in sides):
            continue
        candidates.append((code, nominal, sides, footprints))
    # A projected side shape cannot belong to competing BOM specifications.
    counts = {}
    for _, _, sides, _ in candidates:
        for s in sides:
            counts[s['ref']] = counts.get(s['ref'], 0)+1
    results = []
    for code, nominal, sides, footprints in candidates:
        if any(counts[s['ref']] != 1 for s in sides) or nominal+delta <= 0:
            continue
        # A reused code with conflicting BOM specifications is not one part.
        # Never update every matching numeric token across such occurrences.
        local_spec = next(iter(foam_specs[code]))[0]
        occurrences = [(table, row) for table in records.values() for row in table.get('bom', {}).get('rows', [])
                       if row['part_code'] == code]
        consistent = bool(occurrences)
        for table, row in occurrences:
            value = normalized(row['description'])
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)', value)
            if table.get('bom', {}).get('status') != 'verified_template' or not re.match(r'(?:xop tam|tam xop|foam)\b', value) or not match or not near(
                    [float(v.replace(',', '.')) for v in match.groups()], local_spec, TOL):
                consistent = False
                break
        if not consistent:
            continue
        features = [f for f in context.get('source_features', {}).get('features', []) if f.get('part_code') == code and
            f.get('ownership_proof') in ('unique_source_detail_sheet', 'native_part_identity', 'local_bom_leader_profile') and
            any(near(d['measurement'], nominal, TOL) for d in f['dimensions'])]
        if not features:
            continue
        # Choose a driver, then require the measured-view compiler to prove
        # every other owned representation. Merely sharing a material code
        # or the same nominal dimension does not establish correspondence.
        features.sort(key=lambda f: (not bool(set(f['sheet_ids']).intersection(context.get('root_target_ids', []))), f['refs']))
        feature = features[0]
        measurements = [d for d in feature['dimensions'] if near(d['measurement'], nominal, TOL)]
        if len(measurements) != 1:
            continue
        axis = measurements[0]['axis']
        normal = [-axis[1], axis[0], 0]
        cross = [sum(p[i]*normal[i] for i in range(3)) for p in feature['points']]
        span = [sum(p[i]*axis[i] for i in range(3)) for p in feature['points']]
        kind = 'chiều dài' if max(span)-min(span) > max(cross)-min(cross)+TOL else 'chiều rộng'
        keep = 'trái' if abs(axis[0]) >= abs(axis[1]) else 'đáy'
        from backend.services.measured_profile_planner import compile_plan
        detail_context = dict(context, part_graph=dict(context['part_graph'], seed_codes=[code]),
                              root_target_ids=feature['sheet_ids'])
        detail = compile_plan(detail_context, f'Mã {code} {kind} từ {nominal:g} thành {nominal+delta:g} mm, giữ {keep}')
        if not detail or detail.questions or not detail.operations:
            continue
        if any(not any(r.part_code == code and set(r.outline_refs) == set(f['refs']) and
                       near(r.new_measurement, nominal+delta, TOL) and
                       any(d['ref'] == r.dimension_ref and near(d['measurement'], nominal, TOL) for d in f['dimensions'])
                       for r in detail.resize_recipes) for f in features):
            continue
        ops = []
        for side in sides:
            if side['size'][1]+delta <= TOL:
                raise ValueError('Xốp bên hông sau sửa không đủ chiều cao')
            e = records[side['ref']]
            g = copy.deepcopy(side['geometry'])
            for p in g['points']:
                if near(p[1], side['high'][1], TOL):
                    p[1] += delta
            after = local_geometry(e, g)
            ops.append(Operation(ref=e['ref'], action='replace_geometry', before=json.dumps(e['geometry']),
                after=json.dumps(after), xyz=[], reason='Giảm xốp bên hông theo mặt lót trên; giữ đáy, độ dày và khe hở nguồn'))
            ops.extend(bound_hatches(context, e, after))
        proof = dict(part_code=code, sheet_id=sid, top_carton_ref=top['ref'], footprint_refs=[f['ref'] for f in footprints],
            detail_dimension_refs=sorted({r.dimension_ref for r in detail.resize_recipes if r.part_code == code}),
            nominal_before_mm=nominal, nominal_after_mm=nominal+delta,
            side_views=[dict(ref=s['ref'], footprint_ref=s['footprint_ref'], bottom_contact_ref=s['bottom_contact_ref'],
                top_contact_ref=s['top_contact_ref'],
                before_mm=s['size'][1], after_mm=s['size'][1]+delta, top_gap_mm=s['top_gap_mm']) for s in sides],
            status='source_registered_orthographic_pads', complete_packaging=False)
        results.append((proof, ops, detail))
    return results
