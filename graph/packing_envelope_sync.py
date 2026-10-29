"""Resize measured anonymous body/cap packing views from a checked height edit.

This is deliberately a partial packing binding. It does not certify unknown
foam, unfolded cartons or perspective illustrations in other frames.
"""
import copy
import json
import math
import re

from bom.stage_links import physical_spec
from cad.edit_engine import Operation
from cad.frame_geometry import local_geometry, world
from cad.geometry import near
from graph.packing_envelopes import inspect

TOL = 1e-5


def _points(e):
    g = world(e)['geometry']
    return [g['start'], g['end']] if e['type'] == 'LINE' else [[p[0], p[1], g['elevation']] for p in g['points']]


def _checked_driver(plan, context, proof):
    choices = context['design_choices']
    anchors = [c for c in choices.get('confirmed_choices', [])
               if c.get('key') == 'height_anchor' and c.get('anchor') == 'bottom'
               and c.get('product_code', proof['product_code']) == proof['product_code']]
    delta = proof['product_target_mm'] - proof['product_before_mm']
    if len(anchors) != 1 or not near(anchors[0].get('delta_mm'), delta, TOL):
        return None
    groups = [g for g in context.get('part_graph', {}).get('packaging_groups', [])
              if g['product_code'] == proof['product_code']]
    if len(groups) != 1:
        return None
    records = {e['ref']: e for e in context['entities']}
    derived = choices.get('derived_values', {})
    old = derived.get('frame_height_before_mm', proof['product_before_mm'])
    new = derived.get('frame_height_target_mm', proof['product_target_mm'])
    if not near(new-old, delta, TOL):
        return None
    from cad.measured_features import index
    features = (context.get('source_features') or index(context, context.get('part_graph')))['features']
    for r in plan.resize_recipes:
        if r.part_code not in groups[0].get('product_part_codes', []) or not near(r.new_measurement, new, TOL):
            continue
        d = records.get(r.dimension_ref, {})
        if d.get('review_only') or not d.get('geometry') or not near(d.get('scaled_measurement'), old, TOL):
            continue
        g = world(d)['geometry']
        if abs(abs(math.sin(math.radians(g.get('angle', 0))))-1) > 1e-7:
            continue
        bottom = 'first' if g['defpoint2'][1] < g['defpoint3'][1] else 'second'
        if r.anchor != bottom:
            continue
        owned = [f for f in features if f.get('part_code') == r.part_code
                 and f.get('ownership_proof') in ('native_part_identity', 'unique_source_detail_sheet', 'local_bom_leader_profile')
                 and set(f['refs']) == set(r.outline_refs)
                 and any(b['ref'] == r.dimension_ref for b in f['dimensions'])]
        if len(owned) == 1:
            # Re-run the kernel from the original source: a recipe label and
            # an unrelated dimension edit cannot trigger a carton resize.
            cluster = [r]
            changed = True
            while changed:
                refs = {ref for item in cluster for ref in item.outline_refs + item.hole_refs}
                additions = [item for item in plan.resize_recipes if item not in cluster and
                    refs.intersection(item.outline_refs + item.hole_refs)]
                changed = bool(additions)
                cluster.extend(additions)
            try:
                if any(item.new_measurement is None for item in cluster):
                    return None
                from cad.multi_resize import resize_many
                generated = resize_many(cluster, context, {item.dimension_ref: item.new_measurement for item in cluster})
                driver_refs = set(r.outline_refs + r.hole_refs + [r.dimension_ref])
                expected = [o for o in generated if o.ref in driver_refs]
            except ValueError:
                return None
            by = {o.ref: o for o in plan.operations}
            from graph.native_instances import equivalent_operation
            if expected and all(o.ref in by and equivalent_operation(o, by[o.ref]) for o in expected):
                return r
    return None


def bindings(plan, context):
    """Return source-bound operations without modifying the supplied plan."""
    result = []
    records = {e['ref']: e for e in context['entities']}
    for proof in inspect(context):
        driver = _checked_driver(plan, context, proof)
        if driver is None:
            continue
        delta = proof['product_target_mm'] - proof['product_before_mm']
        sections = [records[r] for r in proof['product_section_refs']]
        sections.sort(key=lambda e: min(p[1] for p in _points(e)))
        body = sections[0]
        body_points = _points(body)
        low = min(p[1] for p in body_points)
        top = max(p[1] for p in body_points)
        if top + delta <= low + TOL:
            raise ValueError('Chiều cao thân đóng gói sau sửa không hợp lệ')
        ops = []

        def geometry(e, updated):
            local = local_geometry(e, updated)
            if not near(local, e['geometry'], TOL):
                ops.append(Operation(ref=e['ref'], action='replace_geometry', before=json.dumps(e['geometry']),
                    after=json.dumps(local), xyz=[], reason='Đồng bộ hình đóng gói theo chiều cao đã kiểm chứng; giữ đáy và khe hở nguồn'))

        children = [e for r, e in records.items() if r.startswith(proof['source_product_root'] + '/')]
        valid = True
        for e in children:
            if e['type']=='HATCH':
                # inspect() has already bound the complete hatch boundary to
                # one body/cap section. Generate its change with that section.
                continue
            g = copy.deepcopy(world(e)['geometry'])
            points = _points(e)
            if e['ref'] == body['ref']:
                for p in g['points']:
                    if near(p[1], top, TOL):
                        p[1] += delta
            elif e['ref'] in proof['product_section_refs']:
                # Preserve the cap thickness; its source contact plane moves.
                for p in g['points']:
                    p[1] += delta
            elif e['type'] == 'LINE':
                ys = sorted(p[1] for p in points)
                if near(ys, [low, top], TOL) and near(points[0][0], points[1][0], TOL):
                    for k in ('start', 'end'):
                        if near(g[k][1], top, TOL):
                            g[k][1] += delta
                elif all(p[1] >= top-TOL for p in points):
                    for k in ('start', 'end'):
                        g[k][1] += delta
                elif all(near(p[1], low, TOL) for p in points):
                    pass
                else:
                    # Interior details have no established motion rule.
                    valid = False
                    break
            else:
                valid = False
                break
            geometry(e, g)
            if e['ref'] in proof['product_section_refs']:
                from graph.packing_side_layers import bound_hatches
                ops.extend(bound_hatches(context, e, local_geometry(e, g)))
        if not valid:
            continue
        carton = records[proof['carton_outline_ref']]
        box = copy.deepcopy(world(carton)['geometry'])
        box_top = max(p[1] for p in box['points'])
        for p in box['points']:
            if near(p[1], box_top, TOL):
                p[1] += delta
        geometry(carton, box)
        # One concentric inset contour of the measured carton defines a
        # uniform wall in this orthographic view. Preserve all four offsets.
        # Do not infer a shell from an arbitrary contained collection.
        from graph.packing_side_layers import rect
        outer = rect(carton)
        insets = []
        for e in records.values():
            if e['ref'] == carton['ref'] or e.get('coordinate_frame') != carton.get('coordinate_frame') or e.get('layout') != carton.get('layout') or proof['sheet_id'] not in e.get('source_sheet_ids', []):
                continue
            shape = rect(e)
            if not shape:
                continue
            gaps = [shape['low'][i]-outer['low'][i] for i in (0, 1)] + [outer['high'][i]-shape['high'][i] for i in (0, 1)]
            if min(gaps) > TOL and max(gaps) < min(outer['size'])/4 and all(near(gaps[0], gap, TOL) for gap in gaps):
                insets.append((e, shape, gaps[0]))
        inset_proof = None
        if len(insets) == 1:
            e, shape, wall = insets[0]
            updated = copy.deepcopy(shape['geometry'])
            if shape['high'][1]+delta <= shape['low'][1]+TOL:
                raise ValueError('Lòng thùng sau sửa không hợp lệ')
            for p in updated['points']:
                if near(p[1], shape['high'][1], TOL):
                    p[1] += delta
            geometry(e, updated)
            inset_proof = dict(ref=e['ref'], wall_mm=wall, before_height_mm=shape['size'][1],
                               after_height_mm=shape['size'][1]+delta, status='source_concentric_inset_contour')
        dimension = records[proof['carton_dimension_ref']]
        dg = copy.deepcopy(world(dimension)['geometry'])
        for k in ('defpoint2', 'defpoint3'):
            if near(dg[k][1], box_top, TOL):
                dg[k][1] += delta
        geometry(dimension, dg)
        from graph.packing_top_layers import bindings as top_layer_bindings
        top_layers = top_layer_bindings(context, proof)
        from graph.packing_side_layers import bindings as side_layer_bindings
        side_layers = side_layer_bindings(context, proof, top_layers)
        side_ops = [o for _, layer_ops, detail in side_layers for o in [*layer_ops, *detail.operations]]
        top_layers = top_layer_bindings(context, proof, side_ops)
        for _, layer_ops in top_layers:
            ops.extend(layer_ops)
        ops.extend(side_ops)
        from cad.vertex_dimensions import synchronize as vertex_dimensions
        ops.extend(vertex_dimensions(context,ops,[proof['sheet_id']]))
        proof = dict(proof, driver_dimension_ref=driver.dimension_ref,
            top_layer_bindings=[p for p, _ in top_layers],
            side_layer_bindings=[p for p, _, _ in side_layers],
            side_resize_recipes=[r.model_dump() for _, _, detail in side_layers for r in detail.resize_recipes],
            side_manifest=[e.model_dump() for _, _, detail in side_layers for e in detail.edits],
            side_projection_owners={o.ref:p['part_code'] for p, layer_ops, _ in side_layers for o in layer_ops},
            carton_inset_binding=inset_proof,
            status='source_matched_envelope_updated', operation_refs=[o.ref for o in ops],
            execution_available=True, complete_packaging=False,
            remaining='Đã sửa hình bao và thùng đo được; lớp đệm, hình tách rời và các hình thùng khác còn phải được kiểm chứng.')
        result.append((proof, ops))
    return result


def synchronize(plan, context, audit=None):
    from backend.services.change_service import EditProposal
    from bom.operations import cell_operations
    from backend.services.compound_planner import same_operation, operation_key
    checked = bindings(plan, context)
    if not checked:
        return plan
    records = {e['ref']: e for e in context['entities']}
    by = {operation_key(o): o for o in plan.operations}
    additions = []

    def add(op, code, purpose):
        key = operation_key(op)
        previous = by.get(key)
        if previous:
            if not same_operation(previous, op):
                raise ValueError('Hình/BOM đóng gói xung đột với liên kết nguồn: ' + op.ref)
        else:
            by[key] = op
            additions.append((op, code, purpose))

    for proof, operations in checked:
        code = proof['carton_code']
        detail_manifest = {e['entity_ref']:e for e in proof['side_manifest']}
        for op in operations:
            manifest = detail_manifest.get(op.ref)
            if manifest:
                add(op, manifest['part_number'], manifest['purpose'])
            else:
                owner = proof['side_projection_owners'].get(op.ref)
                add(op, owner or (code if op.ref.startswith(proof['carton_outline_ref']) or op.ref == proof['carton_dimension_ref'] else proof['product_code']), 'geometry')
        rows = [(t, r) for t in records.values() if t.get('bom', {}).get('status') == 'verified_template'
                for r in t['bom']['rows'] if r['part_code'] == code]
        old = proof['carton_before_mm']
        from bom.packaging import carton_height_text
        for table, row in rows:
            cell = row.get('cells', {}).get('description', {})
            raw = cell.get('raw_text', '')
            for op in cell_operations(table, cell, carton_height_text(raw,old,proof['carton_target_mm']), records,
                    'Đồng bộ chiều cao thùng; giữ khe hở từng đầu đo từ CAD nguồn'):
                add(op, code, 'bom')
        specs = {physical_spec(r['description']) for _, r in rows}
        owned = {sid for n in context.get('part_graph', {}).get('nodes', []) if n['code'] == code for sid in n.get('detail_sheets', [])}
        cell_refs = {c.get('mirror_ref') for e in records.values() for r in e.get('bom', {}).get('rows', []) for c in r.get('cells', {}).values()}
        for e in records.values():
            if e['type'] not in ('TEXT', 'MTEXT') or e['ref'] in cell_refs or not owned.intersection(e.get('source_sheet_ids', [])):
                continue
            raw = e.get('raw_text', e.get('text', ''))
            if physical_spec(raw) not in specs:
                continue
            add(Operation(ref=e['ref'], action='replace_text', before=raw, after=carton_height_text(raw,old,proof['carton_target_mm']),
                xyz=[], reason='Đồng bộ quy cách trên khung tên thùng'), code, 'annotation')
    # All checks above complete before mutating the plan.
    from cad.parametric import LinearResize
    recipes = {r.dimension_ref:r for r in plan.resize_recipes}
    recipe_additions = []
    for proof, _ in checked:
        for data in proof['side_resize_recipes']:
            recipe = LinearResize.model_validate(data)
            if recipe.dimension_ref in recipes:
                if recipe.model_dump() != recipes[recipe.dimension_ref].model_dump():
                    raise ValueError('Recipe xốp bên hông xung đột nguồn')
            else:
                recipes[recipe.dimension_ref] = recipe
                recipe_additions.append(recipe)
    plan.resize_recipes.extend(recipe_additions)
    for op, code, purpose in additions:
        plan.operations.append(op)
        plan.edits.append(EditProposal(entity_ref=op.ref, part_number=code, purpose=purpose,
            before=op.before, after=op.after, reason=op.reason))
    warning = 'Hình bao đóng gói và quy cách thùng đã đồng bộ; các lớp đệm/hình tách rời chưa được coi là hoàn tất.'
    if warning not in plan.warnings:
        plan.warnings.append(warning)
    conflicts = sorted({c['unresolved_ref'] for proof, _ in checked for stack in proof['top_layer_bindings']
                        for c in stack.get('unresolved_intersections', [])})
    if conflicts:
        collision_warning = 'Lớp đệm/lót đã dịch nhưng còn giao hình với vật tư chưa đồng bộ ở khung đóng gói: ' + ', '.join(conflicts) + '. Chỉ dùng đối chiếu, chưa được dùng đóng gói sản xuất.'
        if collision_warning not in plan.warnings:
            plan.warnings.append(collision_warning)
    if audit is not None:
        audit['envelope_bindings'] = [p for p, _ in checked]
    return plan
