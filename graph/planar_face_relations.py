"""Observed end-face contacts and DIM-measured clearances in a 2D assembly.

No gap is inferred from proximity. A clearance needs a real unscaled DIM with
both extension points on unique, facing straight source end faces. Material
overlap, a dimension across the whole assembly, text overrides and ambiguous
endpoints cannot introduce a relation.
"""
import math
import numpy as np
from cad.geometry import near
from cad.frame_geometry import world
from cad.dimensions import linear_axis
from graph.native_contacts import bounds, profile_contact

TOL = 1e-5


def analysis_angle(vector):
    angle = math.atan2(vector[1], vector[0]) % (math.pi/2)
    return 0. if min(angle, math.pi/2-angle) < 1e-9 else round(angle, 10)


def rotation(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, s, 0.], [-s, c, 0.], [0., 0., 1.]])


def intervals(points, axis, side):
    coordinate = bounds(points)[side, axis]
    other = 1 - axis
    return [(min(p[other], q[other]), max(p[other], q[other]))
            for p, q in zip(points, points[1:] + points[:1])
            if abs(p[axis] - coordinate) <= TOL and abs(q[axis] - coordinate) <= TOL
            and abs(p[other] - q[other]) > TOL]


def on_face(point, points, axis, side):
    b = bounds(points)
    return (abs(point[2] - b[0, 2]) <= TOL and abs(point[axis] - b[side, axis]) <= TOL
            and any(lo - TOL <= point[1-axis] <= hi + TOL
                    for lo, hi in intervals(points, axis, side)))


def matches_gap(a, b, axis, first_side, second_side, gap):
    if first_side == second_side or gap <= TOL:
        return False
    ba, bb = bounds(a), bounds(b)
    direction = 1 if first_side == 1 else -1
    if not near(ba[:, 2].tolist(), bb[:, 2].tolist(), TOL):
        return False
    if abs(direction * (bb[second_side, axis] - ba[first_side, axis]) - gap) > TOL:
        return False
    return any(min(y, v) - max(x, u) > TOL
               for x, y in intervals(a, axis, first_side)
               for u, v in intervals(b, axis, second_side))


def source_relations(context, bodies, records):
    """Return deterministic equations, each preserving its observed source gap."""
    if not bodies:
        return []
    result = []
    keys = sorted(bodies)

    def relation(a, b, angle, axis, fa, fb, gap, dim_refs):
        first, second = bodies[a], bodies[b]
        return dict(source_body=a, target_body=b, source_part=first['part_code'],
                    target_part=second['part_code'],
                    sheet_ids=sorted(set(first['sheet_ids']) & set(second['sheet_ids'])),
                    kind='planar_measured_clearance' if dim_refs else 'planar_end_face_contact',
                    analysis_angle_degrees=math.degrees(angle), axis='xy'[axis],
                    source_side=fa, target_side=fb, source_gap_mm=float(gap),
                    dimension_refs=sorted(dim_refs),
                    equation='target_face_after - source_face_after = signed_source_gap',
                    evidence_refs=sorted(set(first['evidence_refs'] + second['evidence_refs'] + list(dim_refs))),
                    scope='source_closed_faces_in_one_2d_assembly')

    for i, a in enumerate(keys):
        for b in keys[i+1:]:
            first, second = bodies[a], bodies[b]
            if first['layout'] != second['layout'] or not set(first['sheet_ids']) & set(second['sheet_ids']):
                continue
            angles = {0.}
            angles.update(analysis_angle(d['axis'])
                          for f in (first, second) for d in f['dimensions'])
            for angle in sorted(angles):
                r = rotation(angle)
                found = profile_contact((np.asarray(first['points']) @ r.T).tolist(),
                                        (np.asarray(second['points']) @ r.T).tolist())
                if found:
                    result.append(relation(a, b, angle, *found, 0., []))
                    break

    if context.get('units') != 4:
        return result
    member_refs = {ref for body in bodies.values() for ref in body['members']}
    gaps = {}
    for ref, e in sorted(records.items()):
        if (ref in member_refs or '/' in ref or e.get('review_only') or e.get('type') != 'DIMENSION'
                or e.get('dimension_type') not in (0, 1) or e.get('linear_factor', 1) != 1):
            continue
        try:
            dim = world(e)
            axis_vector = linear_axis(dim)
            angle = analysis_angle(axis_vector)
            r = rotation(angle)
            points = [np.asarray(dim['geometry'][field]) @ r.T for field in ('defpoint2', 'defpoint3')]
            axis = int(abs(points[1][1] - points[0][1]) > abs(points[1][0] - points[0][0]))
            gap = abs(float(points[1][axis] - points[0][axis]))
            if (gap <= TOL or abs(points[1][1-axis] - points[0][1-axis]) > TOL
                    or abs(points[1][2] - points[0][2]) > TOL
                    or not near(e.get('scaled_measurement'), gap, TOL)):
                continue
        except (ValueError, KeyError, TypeError):
            continue
        local = {k: (np.asarray(f['points']) @ r.T).tolist() for k, f in bodies.items()
                 if f['layout'] == e.get('layout') and set(f['sheet_ids']) & set(e.get('source_sheet_ids', []))}
        owners = []
        for point in points:
            owners.append([(k, side) for k, polygon in local.items() for side in (0, 1)
                           if on_face(point, polygon, axis, side)])
        if any(len(o) != 1 for o in owners):
            continue
        (a, fa), (b, fb) = owners[0][0], owners[1][0]
        if a == b or not set(bodies[a]['sheet_ids']) & set(bodies[b]['sheet_ids']) & set(e.get('source_sheet_ids', [])):
            continue
        if not matches_gap(local[a], local[b], axis, fa, fb, gap):
            continue
        linked = set(e.get('dimension_association', {}).get('source_refs', []))
        if linked - set(bodies[a]['members']) - set(bodies[b]['members']):
            continue
        if b < a:
            a, b, fa, fb = b, a, fb, fa
        signature = (a, b, angle, axis, fa, fb)
        scope = sorted(set(bodies[a]['sheet_ids']) & set(bodies[b]['sheet_ids']) & set(e.get('source_sheet_ids', [])))
        if signature not in gaps:
            gaps[signature] = relation(a, b, angle, axis, fa, fb, gap, [ref])
            gaps[signature]['sheet_ids'] = scope
        else:
            gaps[signature]['dimension_refs'].append(ref)
            gaps[signature]['evidence_refs'] = sorted(set(gaps[signature]['evidence_refs']) | {ref})
            gaps[signature]['sheet_ids'] = sorted(set(gaps[signature]['sheet_ids']) | set(scope))
    return result + [gaps[key] for key in sorted(gaps)]
