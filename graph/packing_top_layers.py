"""Bind BOM-sized top packing pads/liners to an already measured envelope.

Only a contiguous stack of horizontal closed rectangles above the product is
handled. Adjacent layers may have different widths when their actual contact
segments overlap. Side pads, compressed pads and perspective stay unresolved.
No material is resized here: thickness and footprint are preserved.
"""
import copy
import json
import re

from cad.edit_engine import Operation
from cad.frame_geometry import local_geometry, world
from cad.geometry import near
from cad.measured_features import rectangle
from bom.reader import normalized

TOL = 1e-5


def same_boundary(a, b, tolerance=TOL):
    """Exact unordered boundary for straight rectangles (not bounding boxes)."""
    if len(a) == 5 and near(a[0], a[-1], tolerance):
        a = a[:-1]
    if len(b) == 5 and near(b[0], b[-1], tolerance):
        b = b[:-1]
    if len(a) != 4 or len(b) != 4:
        return False
    for candidate in (b, list(reversed(b))):
        if any(all(near(a[i], candidate[(i+j) % 4], tolerance) for i in range(4)) for j in range(4)):
            return True
    return False


def bindings(context, proof, additional_operations=()):
    sid = proof['sheet_id']
    records = {e['ref']: e for e in context['entities']}
    group = next(g for g in context['part_graph']['packaging_groups'] if g['product_code'] == proof['product_code'])
    sizes = {}
    for table in records.values():
        if sid not in table.get('source_sheet_ids', []) or table.get('bom', {}).get('status') != 'verified_template':
            continue
        for row in table['bom']['rows']:
            text = normalized(row.get('description', ''))
            if row['part_code'] not in group['package_codes'] or not re.search(r'\b(?:xop\s+tam|tam\s+lot\s+carton)\b', text):
                continue
            m = re.search(r'(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)', text)
            if m:
                sizes.setdefault(row['part_code'], set()).add(tuple(float(v.replace(',', '.')) for v in m.groups()))
    box = world(records[proof['carton_outline_ref']])['geometry']['points']
    left, right = min(p[0] for p in box), max(p[0] for p in box)
    box_top = max(p[1] for p in box)
    product_top = max(p[1] for ref in proof['product_section_refs'] for p in world(records[ref])['geometry']['points'])
    layers = []
    for e in records.values():
        if e.get('review_only') or sid not in e.get('source_sheet_ids', []) or e['type'] != 'LWPOLYLINE' or not e.get('geometry'):
            continue
        g = world(e)['geometry']
        pts = g['points']
        if not g['closed'] or any(any(p[2:]) for p in pts) or not rectangle([[p[0], p[1], g['elevation']] for p in pts]):
            continue
        low, high = min(p[1] for p in pts), max(p[1] for p in pts)
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        # Four actual axis-aligned corner vertices; a rotated rectangle's
        # bounding box must not be treated as a measured material projection.
        if any(not (near(p[0], x0, TOL) or near(p[0], x1, TOL)) or
               not (near(p[1], low, TOL) or near(p[1], high, TOL)) for p in pts):
            continue
        if low < product_top-TOL or high > box_top+TOL or x0 < left-TOL or x1 > right+TOL:
            continue
        matches = [code for code, specs in sizes.items() if len(specs) == 1 and
                   any(near(high-low, s[0], TOL) and (near(x1-x0, s[1], TOL) or near(x1-x0, s[2], TOL))
                       and s[0] < min(s[1:]) for s in specs)]
        if len(matches) == 1:
            layers.append(dict(ref=e['ref'], part_code=matches[0], low=low, high=high, points=[p[:2] for p in pts], hatch_refs=[]))
    layers.sort(key=lambda layer: layer['low'])
    if not layers:
        return []
    contacts=[]
    for a,b in zip(layers,layers[1:]):
        start=max(min(p[0] for p in a['points']),min(p[0] for p in b['points']))
        end=min(max(p[0] for p in a['points']),max(p[0] for p in b['points']))
        if not near(a['high'],b['low'],TOL) or end-start<=TOL:return []
        contacts.append(dict(lower_ref=a['ref'],upper_ref=b['ref'],source_contact=[[start,a['high']],[end,a['high']]],
                             after_contact=[[start,a['high']+proof['product_target_mm']-proof['product_before_mm']],
                                            [end,a['high']+proof['product_target_mm']-proof['product_before_mm']]]))
    for layer in layers:
        boundary_record = records[layer['ref']]
        for hatch in records.values():
            if hatch['type'] != 'HATCH' or hatch.get('review_only') or hatch.get('coordinate_frame') != boundary_record.get('coordinate_frame') or hatch.get('layout') != boundary_record.get('layout') or sid not in hatch.get('source_sheet_ids', []):
                continue
            paths = (hatch.get('hatch_translation_geometry') or {}).get('paths') or hatch.get('read_only_geometry', {}).get('boundary_paths', [])
            boundary = boundary_record['geometry']['points']
            if len(paths) == 1 and same_boundary([p[:2] for p in boundary], [p[:2] for p in paths[0].get('vertices', [])]):
                if not hatch.get('hatch_translation_geometry'):
                    raise ValueError('Lớp đóng gói có HATCH association/đường cong chưa hỗ trợ: ' + hatch['ref'])
                layer['hatch_refs'].append(hatch['ref'])
        if len(layer['hatch_refs']) > 1:
            raise ValueError('Lớp đóng gói có nhiều HATCH trùng đường bao: ' + layer['ref'])
    delta = proof['product_target_mm']-proof['product_before_mm']
    operations = []
    for layer in layers:
        e = records[layer['ref']]
        g = copy.deepcopy(world(e)['geometry'])
        for p in g['points']:
            p[1] += delta
        operations.append(Operation(ref=e['ref'], action='replace_geometry', before=json.dumps(e['geometry']),
            after=json.dumps(local_geometry(e, g)), xyz=[], reason='Dịch lớp đệm/lót trên theo thùng; giữ độ dày, tiếp xúc và khe hở CAD nguồn'))
        # Derive local motion from the checked outline frame, not from global
        # Y directly: nested rotated/scaled static blocks use local coordinates.
        local = json.loads(operations[-1].after)['points']
        for ref in layer['hatch_refs']:
            old = records[ref]['hatch_translation_geometry']
            from cad.hatch_translation import follow_boundary
            new = follow_boundary(old, e['geometry']['points'], local)
            operations.append(Operation(ref=ref, action='replace_geometry', before=json.dumps(old), after=json.dumps(new),
                xyz=[], reason='Dịch HATCH cùng đường bao đệm/lót nguồn; giữ pattern native'))
    # A dimension belongs to this motion only when BOTH source origins bind
    # actual stack corners. Never move a clearance DIM with one stationary
    # end, nor use an overridden number as geometric evidence.
    dimension_refs=[]
    unbound_dimensions=[]
    corners=[[p[0],p[1],world(records[layer['ref']])['geometry']['elevation']] for layer in layers for p in layer['points']]
    by={o.ref:o for o in [*additional_operations,*operations]}
    vertices=[]
    for e in records.values():
        if e.get('review_only') or sid not in e.get('source_sheet_ids',[]) or e['type'] not in ('LINE','LWPOLYLINE','POLYLINE') or not e.get('geometry'):continue
        updated=copy.deepcopy(e);op=by.get(e['ref'])
        if op:
            if op.action!='replace_geometry':continue
            updated['geometry']=json.loads(op.after)
        before,after=world(e)['geometry'],world(updated)['geometry']
        def points(g):
            return [g['start'],g['end']] if e['type']=='LINE' else [[p[0],p[1],g['elevation']] for p in g['points']]
        a,b=points(before),points(after)
        if len(a)==len(b):vertices.extend((e.get('layout'),p,q) for p,q in zip(a,b))
    for e in records.values():
        if e.get('review_only') or e['type']!='DIMENSION' or sid not in e.get('source_sheet_ids',[]) or not e.get('geometry'):continue
        w=world(e);g=w['geometry']
        hits=[any(near(g.get(key,[]),p,TOL) for p in corners) for key in ('defpoint2','defpoint3')]
        if not any(hits):continue
        if not all(hits) or e.get('dimension_type') not in (0,1) or g.get('text') not in ('','<>'):
            unbound_dimensions.append(e['ref']);continue
        if any(any(not near(q,[g[key][0],g[key][1]+delta,g[key][2]],TOL)
                   for layout,p,q in vertices if layout==e.get('layout') and near(p,g[key],TOL))
               for key in ('defpoint2','defpoint3')):
            unbound_dimensions.append(e['ref']);continue
        from graph.fit_constraints import measurement
        updated=copy.deepcopy(g)
        for key in ('defpoint','defpoint2','defpoint3'):updated[key][1]+=delta
        if not near(measurement(w,g),measurement(w,updated),TOL):
            raise ValueError('DIM lớp đệm không giữ số đo khi dịch theo mặt lắp: '+e['ref'])
        operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),
            after=json.dumps(local_geometry(e,updated)),xyz=[],reason='Dịch DIM có hai đầu đo gắn góc lớp đệm; giữ số đo và khe hở nguồn'))
        dimension_refs.append(e['ref'])
    audit = dict(status='source_bom_contact_stack', layers=layers, delta_mm=delta,
                 carton_gap_mm=box_top-layers[-1]['high'], product_gap_mm=layers[0]['low']-product_top,
                 contacts=contacts,dimension_refs=dimension_refs,unbound_dimension_refs=unbound_dimensions,
                 resized_materials=False, complete_packaging=False)
    # A partial preview can move a checked layer while an unbound side pad
    # remains at its old height. Expose any newly introduced 2D intersection;
    # correct native coordinates do not establish a usable packing assembly.
    from shapely.geometry import Polygon
    ignored = {layer['ref'] for layer in layers} | set(proof['product_section_refs'])
    updated = {o.ref: o for o in additional_operations if o.action == 'replace_geometry'}
    conflicts = []
    for e in records.values():
        if e['ref'] in ignored or e.get('review_only') or sid not in e.get('source_sheet_ids', []) or e['type'] != 'LWPOLYLINE' or not e.get('geometry'):
            continue
        if e['ref'].startswith(proof['source_product_root']+'/'):
            continue
        g = world(e)['geometry']
        if not g['closed'] or any(any(p[2:]) for p in g['points']):
            continue
        other = Polygon([p[:2] for p in g['points']])
        if not other.is_valid:
            continue
        after_other = other
        if e['ref'] in updated:
            after_record = dict(e, geometry=json.loads(updated[e['ref']].after))
            after_other = Polygon([p[:2] for p in world(after_record)['geometry']['points']])
        for layer in layers:
            before = Polygon(layer['points'])
            after = Polygon([(p[0], p[1]+delta) for p in layer['points']])
            # Existing containment (carton/lining) is not a new collision.
            if before.intersection(other).area <= TOL and after.intersection(after_other).area > TOL:
                conflicts.append(dict(layer_ref=layer['ref'], unresolved_ref=e['ref'],
                                      overlap_area_mm2=after.intersection(after_other).area))
    audit['unresolved_intersections'] = conflicts
    return [(audit, operations)]
