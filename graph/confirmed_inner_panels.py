"""Propagate a human-confirmed inner-panel mate from checked CAD drivers.

Identity/fit policy are hash-bound human inputs; source measurements supply
clearances. This does not declare assembly illustrations or production ready.
"""
import json
import math
import re
import copy

from cad.geometry import near
from cad.frame_geometry import world
from cad.curved_profiles import primitives
from cad.parametric import LinearResize
from graph.packing_side_layers import rect
from backend.services.design_choices import sheet_spec

TOL = 1e-5


def proofs(plan, context):
    choices = context.get('design_choices', {})
    if choices.get('source_hash') != context.get('source_hash') or context.get('units') != 4:
        return []
    mates = [c for c in choices.get('confirmed_choices', []) if c.get('key') == 'panel_inner_mate' and c.get('policy') == 'preserve_source_clearances']
    anchors = [c for c in choices.get('confirmed_choices', []) if c.get('key') == 'height_anchor' and c.get('anchor') == 'bottom']
    if len(anchors) != 1:
        return []
    records = {e['ref']:e for e in context['entities']}
    features = context.get('source_features', {}).get('features', [])
    operations = {o.ref:o for o in plan.operations if o.action == 'replace_geometry'}
    def executed_dimension(recipe):
        op = operations.get(recipe.dimension_ref)
        record = records.get(recipe.dimension_ref, {})
        if not op or record.get('type') != 'DIMENSION' or not near(json.loads(op.before), record.get('geometry'), TOL):
            return False
        from graph.fit_constraints import measurement
        return near(measurement(record, json.loads(op.after)), recipe.new_measurement, TOL)
    derived = choices.get('derived_values', {})
    before, after = derived.get('frame_height_before_mm'), derived.get('frame_height_target_mm')
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (before, after)):
        return []
    result = []
    for mate in mates:
        if mate.get('product_code') != anchors[0].get('product_code') or not near(after-before, anchors[0].get('delta_mm'), TOL):
            continue
        code = mate['panel_part_code']
        rows = [(t, r) for t in records.values() for r in t.get('bom', {}).get('rows', []) if r['part_code'] == code]
        specs = {sheet_spec(r['description']) for _, r in rows}
        if len(specs) != 1 or None in specs or any(t.get('bom', {}).get('status') != 'verified_template' for t, _ in rows):
            continue
        gauge, old_h, old_w = next(iter(specs))
        caps = []
        for cap in (mate['top_plate_part_code'], mate['bottom_plate_part_code']):
            cap_specs = {sheet_spec(r['description']) for t in records.values() if t.get('bom', {}).get('status') == 'verified_template'
                         for r in t['bom']['rows'] if r['part_code'] == cap}
            cap_recipes = [r for r in plan.resize_recipes if r.part_code == cap and r.new_measurement is not None and
                           near(records.get(r.dimension_ref, {}).get('scaled_measurement'), next(iter(cap_specs))[0] if len(cap_specs) == 1 and None not in cap_specs else -1, TOL)]
            if len(cap_specs) != 1 or None in cap_specs or not cap_recipes or len({r.new_measurement for r in cap_recipes}) != 1:
                break
            if not all(executed_dimension(r) for r in cap_recipes):
                break
            caps.append((next(iter(cap_specs))[0], cap_recipes[0].new_measurement))
        if len(caps) != 2:
            continue
        # Recompile the curved strip; a recipe label or unexecuted operation
        # cannot produce an inner-width change.
        walls = [r for r in plan.curved_wall_recipes if r.part_code == mate['side_wall_part_code'] and len(r.outline_refs) == 4]
        if len(walls) != 1:
            continue
        wall = walls[0]
        from cad.curved_wall import resize as resize_wall
        from graph.native_instances import equivalent_operation
        expected, _ = resize_wall(wall, context)
        if not all(o.ref in operations and equivalent_operation(o, operations[o.ref]) for o in expected):
            continue
        old_arc = world(records[wall.inner_arc_ref])
        new_arc = world(dict(records[wall.inner_arc_ref], geometry=json.loads(operations[wall.inner_arc_ref].after)))
        a, b = primitives(old_arc)[0], primitives(new_arc)[0]
        # A horizontal source cut plane gives an explicit front chord. The
        # window keeps its original drafting residual relative to this chord.
        if not near(a['start'][1], a['end'][1], TOL) or not near(b['start'][1], b['end'][1], TOL):
            continue
        chord0, chord1 = abs(a['end'][0]-a['start'][0]), abs(b['end'][0]-b['start'][0])
        source_windows = []
        # A multi-member BOM correctly prevents generic "detail sheet owns
        # every contour" attribution. A confirmed frame/window relation can
        # still bind the *whole* measured five-edge envelope at a proven
        # manufacturing stage. Never promote its child silhouettes globally.
        stages=[]
        if context.get('part_graph',{}).get('source_hash')==context.get('source_hash'):
            for node in context['part_graph'].get('nodes',[]):
                if node['code']!=mate['frame_part_code'] or node.get('definition_conflict'):continue
                for stage in node.get('manufacturing_stages',[]):
                    table=records.get(stage.get('evidence_table_ref'),{})
                    if stage.get('status')=='source_specification_stage_link' and table.get('bom',{}).get('status')=='verified_template' and any(r['part_code']==node['code'] for r in table['bom']['rows']):stages.append(stage)
        mate_codes={mate[k] for k in ('panel_part_code','top_plate_part_code','bottom_plate_part_code','side_wall_part_code')}
        member_tables=[t for t in records.values() if t.get('bom',{}).get('status')=='verified_template' and mate_codes<={r['part_code'] for r in t['bom']['rows']}]
        for f in features:
            direct=f.get('part_code')==mate['frame_part_code'] and f.get('ownership_proof') in ('unique_source_detail_sheet','native_part_identity')
            candidate=f.get('part_code') is None and f.get('ownership_proof')=='unverified'
            if len(f['refs'])!=1 or not (direct or candidate):continue
            local_tables=[t for t in member_tables if set(f.get('sheet_ids',[])).intersection(t.get('source_sheet_ids',[]))]
            stage_evidence=[s for s in stages if s['sheet_id'] in f.get('sheet_ids',[])]
            envelope=candidate and bool(local_tables) and bool(stage_evidence)
            if not direct and not envelope:continue
            owner = records[f['refs'][0]]
            box = rect(owner)
            if not box or not near(box['size'][1], before, TOL) or '/' not in owner['ref']:
                continue
            root = owner['ref'].rsplit('/', 1)[0]
            members = [e for e in records.values() if e['ref'].startswith(root+'/') and e['type'] in ('LINE','LWPOLYLINE','POLYLINE','ARC','CIRCLE','SPLINE','ELLIPSE','INSERT')]
            if len(members) != 5 or any(e.get('review_only') or not e.get('geometry') for e in members):
                continue
            lines = [world(e) for e in records.values() if e['ref'].startswith(root+'/') and e['type'] == 'LINE' and e.get('geometry') and not e.get('review_only')]
            horizontals = [e for e in lines if near(e['geometry']['start'][1], e['geometry']['end'][1], TOL)]
            verticals = [e for e in lines if near(e['geometry']['start'][0], e['geometry']['end'][0], TOL) and
                near(sorted(e['geometry'][k][1] for k in ('start', 'end')), [box['low'][1], box['high'][1]], TOL)]
            if len(horizontals) != 2 or len(verticals) != 2:
                continue
            ys = sorted(e['geometry']['start'][1] for e in horizontals)
            xs = sorted(e['geometry']['start'][0] for e in verticals)
            if not near([ys[0]-box['low'][1], box['high'][1]-ys[1]], [caps[1][0], caps[0][0]], TOL) or any(
                    not near(sorted(e['geometry'][k][0] for k in ('start', 'end')), xs, TOL) for e in horizontals):
                continue
            width = xs[1]-xs[0]
            width_dims = [d for d in f['dimensions'] if abs(d['axis'][0]) > 1-1e-7 and near(d['measurement'], box['size'][0], TOL)]
            if len(width_dims) != 1:
                continue
            tolerance = records[width_dims[0]['ref']].get('dimension_tolerance', {})
            allowance = max(tolerance.get('dimtp', 0), tolerance.get('dimtm', 0)) if tolerance.get('dimtol') else TOL
            if width < old_w-TOL or abs(width-chord0) > allowance+TOL:
                continue
            height_dims = [d for d in f['dimensions'] if abs(d['axis'][1]) > 1-1e-7 and near(d['measurement'], before, TOL)]
            if len(height_dims) != 1:
                continue
            source_windows.append(dict(outline_ref=owner['ref'], interior_refs=[e['ref'] for e in horizontals+verticals],
                width=width, height=ys[1]-ys[0], width_clearance_mm=width-old_w, height_clearance_mm=ys[1]-ys[0]-old_h,
                chord_drafting_residual_mm=width-chord0, dimension_ref=height_dims[0]['ref'], sheet_ids=f['sheet_ids'],
                ownership_proof='confirmed_source_stage_envelope' if envelope else f['ownership_proof'],
                stage_evidence_refs=sorted({s['evidence_table_ref'] for s in stage_evidence}|{t['ref'] for t in local_tables}) if envelope else []))
        if not source_windows or any(not near([w['width'], w['height']], [source_windows[0]['width'], source_windows[0]['height']], TOL) for w in source_windows):
            continue
        window = source_windows[0]
        if window['height_clearance_mm'] < -TOL:
            continue
        drivers = [r for r in plan.resize_recipes if r.part_code in (mate['frame_part_code'], mate['side_wall_part_code']) and
                   near(r.new_measurement, after, TOL) and near(records.get(r.dimension_ref, {}).get('scaled_measurement'), before, TOL)]
        if not drivers:
            continue
        # Height is measured in the actual frame, not guessed from a number in
        # the request. Require a real bottom-anchored, executed source DIM.
        valid_drivers = []
        for r in drivers:
            d = world(records[r.dimension_ref])
            g = d.get('geometry', {})
            if not g or abs(abs(math.sin(math.radians(g.get('angle', 0))))-1) > 1e-7:
                continue
            bottom = 'first' if g['defpoint2'][1] < g['defpoint3'][1] else 'second'
            if r.anchor == bottom and executed_dimension(r):
                valid_drivers.append(r.dimension_ref)
        if not valid_drivers:
            continue
        panel_faces = [f for f in features if f.get('part_code') == code and f.get('ownership_proof') in ('unique_source_detail_sheet', 'native_part_identity') and
                       any(near(d['measurement'], old_h, TOL) for d in f['dimensions']) and any(near(d['measurement'], old_w, TOL) for d in f['dimensions'])]
        if len(panel_faces) != 1:
            continue
        face = panel_faces[0]
        hd = [d for d in face['dimensions'] if near(d['measurement'], old_h, TOL)]
        wd = [d for d in face['dimensions'] if near(d['measurement'], old_w, TOL)]
        if len(hd) != 1 or len(wd) != 1 or abs(hd[0]['axis'][1]) < 1-1e-7 or abs(wd[0]['axis'][0]) < 1-1e-7:
            continue
        new_h = round(after-caps[0][1]-caps[1][1]-window['height_clearance_mm'], 3)
        new_w = round(old_w+chord1-chord0, 3)
        if min(new_h, new_w) <= 0:
            raise ValueError('Tấm lắp bên trong không còn đủ kích thước sau sửa')
        hg = world(records[hd[0]['ref']])['geometry']
        recipes = [LinearResize(part_code=code, dimension_ref=hd[0]['ref'], new_measurement=new_h, outline_refs=face['refs'], hole_refs=[],
            anchor='first' if hg['defpoint2'][1] < hg['defpoint3'][1] else 'second', evidence_refs=face['evidence_refs']),
            LinearResize(part_code=code, dimension_ref=wd[0]['ref'], new_measurement=new_w, outline_refs=face['refs'], hole_refs=[],
            anchor='center', evidence_refs=face['evidence_refs'])]
        result.append(dict(part_code=code, old_height_mm=old_h, new_height_mm=new_h, old_width_mm=old_w, new_width_mm=new_w,
            product_code=mate['product_code'],top_plate_part_code=mate['top_plate_part_code'],bottom_plate_part_code=mate['bottom_plate_part_code'],
            source_windows=source_windows, side_chord_before_mm=chord0, side_chord_after_mm=chord1,
            frame_part_code=mate['frame_part_code'], frame_height_before_mm=before, frame_height_after_mm=after,
            cap_before_mm=[v[0] for v in caps], cap_after_mm=[v[1] for v in caps],
            height_driver_refs=valid_drivers, recipe_data=[r.model_dump() for r in recipes], status='confirmed_source_inner_panel_fit'))
    return result


def window_operations(proof, context):
    """Update the complete measured five-edge front view, not an isometric view."""
    from cad.frame_geometry import local_geometry
    from cad.edit_engine import Operation
    records = {e['ref']:e for e in context['entities']}
    result = []
    for window in proof['source_windows']:
        source = records[window['outline_ref']]
        box = rect(source)
        low, high = box['low'], box['high']
        new_top = low[1]+proof['frame_height_after_mm']
        center = (low[0]+high[0])/2
        half = (window['width']+proof['side_chord_after_mm']-proof['side_chord_before_mm'])/2
        ref_geometries = {}
        g = copy.deepcopy(box['geometry'])
        for p in g['points']:
            if near(p[1], high[1], TOL):
                p[1] = new_top
        ref_geometries[source['ref']] = g
        for ref in window['interior_refs']:
            g = copy.deepcopy(world(records[ref])['geometry'])
            horizontal = near(g['start'][1], g['end'][1], TOL)
            for key in ('start','end'):
                p = g[key]
                p[0] = center+half if p[0] > center else center-half
                if horizontal:
                    p[1] = new_top-proof['cap_after_mm'][0] if p[1] > (low[1]+high[1])/2 else low[1]+proof['cap_after_mm'][1]
                elif near(p[1], high[1], TOL):
                    p[1] = new_top
            ref_geometries[ref] = g
        ref = window['dimension_ref']
        d = world(records[ref]); g = copy.deepcopy(d['geometry'])
        from cad.dimensions import linear_axis
        if not near(abs(linear_axis(d)[1]), 1, TOL) or not near(sorted(g[k][1] for k in ('defpoint2','defpoint3')), [low[1],high[1]], TOL):
            raise ValueError('DIM khung hàn chưa gắn đúng hai mép đo thật')
        for key in ('defpoint2','defpoint3'):
            if near(g[key][1], high[1], TOL): g[key][1] = new_top
        # Keep the source dimension line placement; only the measured upper
        # extension endpoint moves, preserving native tolerance/precision.
        ref_geometries[ref] = g
        for ref, g in ref_geometries.items():
            e = records[ref]; after = local_geometry(e,g)
            if not near(e['geometry'],after,TOL):
                result.append(Operation(ref=ref,action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(after),xyz=[],
                    reason='Đồng bộ cửa lắp đo thật: giữ đáy, biên ngoài và khe hở tấm bên trong đã chốt'))
    return result


def window_captions(proof, context):
    from bom.stage_links import physical_spec
    from cad.edit_engine import Operation
    nodes = [n for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==proof['frame_part_code']]
    specs = {physical_spec(r['description']) for n in nodes for r in n.get('bom_occurrences',[])}
    sheets = {s for w in proof['source_windows'] for s in w['sheet_ids']}
    result = []
    for e in context['entities']:
        if e['type'] not in ('TEXT','MTEXT') or e.get('review_only') or not sheets.intersection(e.get('source_sheet_ids',[])):
            continue
        raw = e.get('raw_text',e.get('text',''))
        if physical_spec(raw) not in specs: continue
        matches = [m for m in re.finditer(r'(?<![\d.,])(\d+(?:[.,]\d+)?)(?=\s*[x×])',raw)
                   if near(float(m[1].replace(',','.')),proof['frame_height_before_mm'],TOL)]
        if len(matches)!=1: raise ValueError('Chưa gắn được chiều cao trong tên khung công đoạn')
        m = matches[0]; after=raw[:m.start(1)]+f'{proof["frame_height_after_mm"]:.12g}'+raw[m.end(1):]
        result.append(Operation(ref=e['ref'],action='replace_text',before=raw,after=after,xyz=[],reason='Đồng bộ tên khung công đoạn với chiều cao DIM cửa lắp đã sửa'))
    return result


def validate(plan, context):
    from graph.native_instances import equivalent_operation
    from graph.fit_constraints import measurement
    operations = {o.ref:o for o in plan.operations if o.action == 'replace_geometry'}
    records = {e['ref']:e for e in context['entities']}
    for proof in proofs(plan, context):
        for data in proof['recipe_data']:
            ref = data['dimension_ref']; op = operations.get(ref)
            if not op or not near(measurement(records[ref],json.loads(op.after)),data['new_measurement'],TOL):
                raise ValueError('Tấm bên trong chưa đồng bộ DIM theo khe hở đã chốt: '+ref)
        for expected in window_operations(proof, context):
            if expected.ref not in operations or not equivalent_operation(expected,operations[expected.ref]):
                raise ValueError('Cửa lắp khung hàn chưa đồng bộ với tấm bên trong: '+expected.ref)
        texts = {o.ref:o for o in plan.operations if o.action=='replace_text'}
        for expected in window_captions(proof,context):
            if expected.ref not in texts or not equivalent_operation(expected,texts[expected.ref]):
                raise ValueError('Tên khung công đoạn chưa đồng bộ DIM đã sửa')
        for table in records.values():
            for row in table.get('bom',{}).get('rows',[]):
                if row['part_code'] != proof['part_code']: continue
                cell = row['cells']['description']
                edits = [o for o in plan.operations if
                    (o.action == 'table_cell' and o.ref == table['ref'] and o.cell_index == cell.get('index')) or
                    (cell.get('storage') == 'text' and o.action == 'replace_text' and o.ref == cell.get('mirror_ref'))]
                spec = sheet_spec(edits[0].after) if len(edits) == 1 else None
                if not spec or not near(list(spec[1:]),[proof['new_height_mm'],proof['new_width_mm']],TOL):
                    raise ValueError('BOM tấm bên trong chưa giữ khe hở lắp đã chốt')


def synchronize(plan, context):
    checks = proofs(plan, context)
    if not checks:
        return plan
    records = {e['ref']:e for e in context['entities']}
    from backend.services.compound_planner import operation_key, same_operation, merge_numeric_text
    from backend.services.change_service import EditProposal
    from bom.operations import cell_operations
    from bom.stage_links import physical_spec
    new_recipes = []
    by_recipe = {r.dimension_ref:r for r in plan.resize_recipes}
    for proof in checks:
        for data in proof['recipe_data']:
            r = LinearResize.model_validate(data)
            if r.dimension_ref in by_recipe:
                old = by_recipe[r.dimension_ref]
                if old.model_dump() != r.model_dump():
                    raise ValueError('Recipe tấm bên trong không giữ quan hệ lắp đã chốt')
            else:
                new_recipes.append(r)
    if not new_recipes:
        return plan
    candidate = plan.model_copy(deep=True)
    ops = {operation_key(o):o for o in candidate.operations}
    for proof in checks:
        code = proof['part_code']
        rows = [(t, r) for t in records.values() for r in t.get('bom', {}).get('rows', []) if r['part_code'] == code]
        specs = {physical_spec(r['description']) for _, r in rows}
        number = r'(\d+(?:[.,]\d+)?)'
        pattern = re.compile(r'(?<![\d.,])(?='+number+r'\s*([x×])\s*'+number+r'(?![\d.,]))')
        def proposed(raw):
            matches = [m for m in pattern.finditer(raw) if near(float(m[1].replace(',','.')),proof['old_height_mm'],TOL) and
                       near(float(m[3].replace(',','.')),proof['old_width_mm'],TOL)]
            if len(matches) != 1:
                raise ValueError('Chưa gắn được cặp chiều cao/rộng trong quy cách tấm bên trong')
            match = matches[0]
            return raw[:match.start(1)]+f'{proof["new_height_mm"]:.12g}x{proof["new_width_mm"]:.12g}'+raw[match.end(3):]
        additions = []
        for table, row in rows:
            cell = row['cells']['description']
            additions.extend(cell_operations(table, cell, proposed(cell['raw_text']), records, 'Giữ khe hở tấm lắp giữa các mặt trong đã được user xác nhận'))
        owned_sheets = {sid for n in context['part_graph']['nodes'] if n['code'] == code for sid in n.get('detail_sheets', [])}
        cells = {cell.get('mirror_ref') for t in records.values() for row in t.get('bom', {}).get('rows', []) for cell in row.get('cells', {}).values()}
        from cad.edit_engine import Operation
        for e in records.values():
            if e['type'] not in ('TEXT', 'MTEXT') or e['ref'] in cells or not owned_sheets.intersection(e.get('source_sheet_ids', [])):
                continue
            raw = e.get('raw_text', e.get('text', ''))
            if physical_spec(raw) in specs:
                additions.append(Operation(ref=e['ref'], action='replace_text', before=raw, after=proposed(raw), xyz=[], reason='Đồng bộ quy cách tấm bên trong theo quan hệ lắp đã chốt'))
        for op in additions:
            key = operation_key(op)
            previous = ops.get(key)
            if previous and not same_operation(previous, op):
                op = merge_numeric_text(previous, op)
                if op is None:
                    raise ValueError('BOM tấm lắp bên trong xung đột thay đổi đã có')
            ops[key] = op
            candidate.edits = [e for e in candidate.edits if not (e.entity_ref == op.ref and e.before == op.before)]
            candidate.edits.append(EditProposal(entity_ref=op.ref, part_number=code, purpose='bom' if op.ref in cells or op.action == 'table_cell' else 'annotation',
                before=op.before, after=op.after, reason=op.reason))
    candidate.operations = list(ops.values())
    from graph.native_instances import equivalent_operation
    geometry_ops = {o.ref:o for o in candidate.operations if o.action == 'replace_geometry'}
    for proof in checks:
        for op in window_operations(proof, context):
            previous = geometry_ops.get(op.ref)
            if previous and not equivalent_operation(previous,op):
                raise ValueError('Hình cửa lắp khung hàn có thay đổi xung đột: '+op.ref)
            if not previous:
                candidate.operations.append(op)
            candidate.edits = [e for e in candidate.edits if e.entity_ref != op.ref]
            candidate.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['frame_part_code'],purpose='geometry',before=op.before,after=op.after,reason=op.reason))
        texts = {o.ref:o for o in candidate.operations if o.action=='replace_text'}
        for op in window_captions(proof,context):
            if op.ref in texts and not equivalent_operation(texts[op.ref],op):
                raise ValueError('Tên khung công đoạn có sửa xung đột')
            if op.ref not in texts: candidate.operations.append(op)
            candidate.edits = [e for e in candidate.edits if e.entity_ref!=op.ref]
            candidate.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['frame_part_code'],purpose='annotation',before=op.before,after=op.after,reason=op.reason))
    # Recompose the same panel's orthogonal axes only after proving that the
    # old operations are exactly those produced by its existing recipes.
    # A manually supplied conflicting geometry operation must still fail.
    from cad.multi_resize import resize_many
    from graph.native_instances import equivalent_operation
    panel_codes = {p['part_code'] for p in checks}
    old_recipes = [r for r in candidate.resize_recipes if r.part_code in panel_codes]
    values = {r.dimension_ref:r.new_measurement for r in old_recipes}
    old_geometry = resize_many(old_recipes, context, values) if old_recipes else []
    previous = {o.ref:o for o in candidate.operations if o.action == 'replace_geometry'}
    for op in old_geometry:
        if op.ref not in previous or not equivalent_operation(op, previous[op.ref]):
            raise ValueError('Hình tấm bên trong đã có sửa trực tiếp khác recipe nguồn: '+op.ref)
    replaced = {o.ref for o in old_geometry}
    candidate.operations = [o for o in candidate.operations if o.ref not in replaced or o.action != 'replace_geometry']
    candidate.edits = [e for e in candidate.edits if e.entity_ref not in replaced or e.purpose != 'geometry']
    # Compile only the affected panel axes here. Recompiling every unrelated
    # curved/laser/packing part recursively made large CAD plans slow. The
    # normal validate_plan path still independently checks the whole plan.
    from graph.measured_views import expand
    panel_recipes = expand(old_recipes+new_recipes, context)
    if any(r.new_measurement is None for r in panel_recipes):
        candidate.resize_recipes.extend(new_recipes)
        from backend.services.parametric_service import compile_recipes
        return compile_recipes(candidate, context)
    dimensions = {r.dimension_ref:r for r in candidate.resize_recipes}
    for r in panel_recipes:
        if r.dimension_ref in dimensions and dimensions[r.dimension_ref].model_dump() != r.model_dump():
            raise ValueError('DIM tấm lắp bên trong đang thuộc recipe khác')
        if r.dimension_ref not in dimensions:
            candidate.resize_recipes.append(r); dimensions[r.dimension_ref] = r
    owners = {}
    values = {r.dimension_ref:r.new_measurement for r in panel_recipes}
    geometry = {o.ref:o for o in candidate.operations if o.action == 'replace_geometry'}
    for op in resize_many(panel_recipes, context, values, owners):
        if op.ref in geometry and not equivalent_operation(geometry[op.ref],op):
            raise ValueError('Hình tấm bên trong xung đột chi tiết khác: '+op.ref)
        if op.ref not in geometry:
            candidate.operations.append(op)
        candidate.edits = [e for e in candidate.edits if e.entity_ref != op.ref]
        candidate.edits.append(EditProposal(entity_ref=op.ref,part_number=owners[op.ref],purpose='geometry',before=op.before,after=op.after,reason=op.reason))
    validate(candidate,context)
    return candidate
