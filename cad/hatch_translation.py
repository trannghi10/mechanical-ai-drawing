"""Follow a checked straight boundary without recreating native HATCH tags.

Curved/edge paths, gradients, OCS tilts and associations need other adapters.
Pattern definitions, handles, reactors and application data remain untouched.
"""
import math

from cad.geometry import near


def preserved_paths(entity,*,allow_boundary_refs=False):
    """Native closed polyline/analytic edge loops, without tessellation."""
    from ezdxf.entities.boundary_paths import LineEdge,ArcEdge,EllipseEdge
    result=[]
    for path in entity.paths:
        if path.source_boundary_objects and not allow_boundary_refs:raise ValueError('HATCH có liên kết biên ngoài cần CAD SDK native')
        if hasattr(path,'vertices'):
            if not path.is_closed or len(path.vertices)<3 or any(len(v)!=3 or not all(math.isfinite(x) for x in v) for v in path.vertices):
                raise ValueError('HATCH đường bao polyline không hợp lệ')
            result.append(dict(vertices=[list(v) for v in path.vertices],flags=path.path_type_flags,closed=True))
            continue
        edges=[];ends=[]
        for e in path.edges:
            if isinstance(e,LineEdge):
                item=dict(type='LINE',start=list(e.start),end=list(e.end))
                if near(item['start'],item['end'],1e-12):raise ValueError('HATCH cạnh suy biến')
            elif isinstance(e,(ArcEdge,EllipseEdge)):
                item=dict(type='ARC' if isinstance(e,ArcEdge) else 'ELLIPSE',center=list(e.center),
                          start_angle=float(e.start_angle),end_angle=float(e.end_angle),ccw=bool(e.ccw))
                if isinstance(e,ArcEdge):
                    if e.radius<=0:raise ValueError('HATCH bán kính không hợp lệ')
                    item['radius']=e.radius
                else:
                    if e.major_axis.magnitude<=0 or not 0<e.ratio<=1:raise ValueError('HATCH elip không hợp lệ')
                    item.update(major_axis=list(e.major_axis),ratio=e.ratio)
            else:raise ValueError('HATCH loại cạnh chưa hỗ trợ bảo toàn')
            values=[x for v in item.values() if not isinstance(v,str) for x in (v if isinstance(v,list) else [v])]
            if not all(math.isfinite(x) for x in values):raise ValueError('HATCH tọa độ cạnh không hữu hạn')
            ends.append((list(e.real_start_point),list(e.real_end_point)));edges.append(item)
        if not edges or any(not near(a[1],b[0],1e-6) for a,b in zip(ends,ends[1:]+ends[:1])):
            raise ValueError('HATCH cạnh chưa tạo vòng kín')
        result.append(dict(edges=edges,flags=path.path_type_flags,closed=True))
    if not result:raise ValueError('HATCH thiếu đường bao')
    return result


def validate_preserved(entity):
    """Validate raw clone eligibility without granting geometry edit support."""
    if entity.dxftype()!='HATCH' or entity.dxf.associative or entity.has_extension_dict or entity.get_reactors():
        raise ValueError('HATCH association chưa hỗ trợ clone bảo toàn')
    if entity.gradient and entity.gradient.kind!=0:raise ValueError('HATCH gradient cần adapter bảo toàn riêng')
    from ezdxf.math import Vec3
    if Vec3(entity.dxf.extrusion).magnitude<1e-12 or not all(math.isfinite(v) for v in [*entity.dxf.extrusion,*entity.dxf.elevation]):
        raise ValueError('HATCH mặt phẳng không hợp lệ')
    preserved_paths(entity)


def preserved_snapshot(entity):
    """Read-only proof for raw copies; not accepted by the HATCH edit API."""
    validate_preserved(entity)
    from ezdxf.math import Vec3
    return dict(extrusion=list(Vec3(entity.dxf.extrusion).normalize()),elevation=list(entity.dxf.elevation),
        paths=preserved_paths(entity),
        seeds=[list(v) for v in entity.seeds],pattern_name=entity.dxf.pattern_name,solid_fill=entity.dxf.solid_fill,
        pattern_angle=entity.dxf.pattern_angle,pattern_scale=entity.dxf.pattern_scale,
        pattern_double=entity.dxf.pattern_double,hatch_style=entity.dxf.hatch_style,pattern_type=entity.dxf.pattern_type,
        pattern_lines=[dict(angle=p.angle,base_point=list(p.base_point),offset=list(p.offset),dash_length_items=list(p.dash_length_items))
                       for p in entity.pattern.lines] if entity.pattern else [])


def snapshot(entity):
    if entity.dxftype() != 'HATCH' or entity.dxf.associative or entity.has_extension_dict or entity.get_reactors():
        raise ValueError('HATCH association chưa hỗ trợ dịch chuyển')
    if not near(list(entity.dxf.extrusion), [0, 0, 1]) or entity.gradient:
        raise ValueError('HATCH OCS/gradient chưa hỗ trợ')
    paths = []
    for path in entity.paths:
        if path.source_boundary_objects:
            raise ValueError('HATCH cần đường kín thẳng không association')
        ends = None
        if hasattr(path, 'vertices'):
            if not path.is_closed:
                raise ValueError('HATCH cần đường kín')
            vertices = [list(v) for v in path.vertices]
        else:
            from ezdxf.entities.boundary_paths import LineEdge
            if not path.edges or any(not isinstance(e, LineEdge) for e in path.edges):
                raise ValueError('HATCH edge cong chưa hỗ trợ')
            vertices = [[*e.start, 0] for e in path.edges]
            ends = [[*e.end, 0] for e in path.edges]
            if any(not near(end, vertices[(i+1) % len(vertices)], 1e-7) for i, end in enumerate(ends)):
                raise ValueError('HATCH line edges chưa tạo vòng kín')
        if len(vertices) < 3 or any(len(v) != 3 or abs(v[2]) > 1e-12 for v in vertices):
            raise ValueError('HATCH đường cong chưa hỗ trợ dịch chuyển')
        item = dict(vertices=vertices, flags=path.path_type_flags, closed=True)
        if ends is not None:
            item['ends'] = ends
        paths.append(item)
    if not paths:
        raise ValueError('HATCH thiếu đường bao')
    return dict(paths=paths, seeds=[list(p) for p in entity.seeds],
                elevation=list(entity.dxf.elevation), extrusion=list(entity.dxf.extrusion))


def boundary_map(before, after):
    """Rigid translation or positive axis-aligned rectangular resize only."""
    if len(before) != len(after) or not before or any(len(p) < 2 for p in before+after):
        raise ValueError('HATCH giữ topology đường bao')
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for p in before+after for v in p[:2]):
        raise ValueError('HATCH tọa độ không hữu hạn')
    moves = [[q[i]-p[i] for i in (0, 1)] for p, q in zip(before, after)]
    if all(near(moves[0], move) for move in moves):
        return [1, 1], moves[0]
    from graph.packing_top_layers import same_boundary
    bounds = []
    for points in (before, after):
        low = [min(p[i] for p in points) for i in (0, 1)]
        high = [max(p[i] for p in points) for i in (0, 1)]
        corners = [[low[0], low[1]], [high[0], low[1]], [high[0], high[1]], [low[0], high[1]]]
        if min(high[i]-low[i] for i in (0, 1)) <= 1e-7 or not same_boundary([p[:2] for p in points], corners):
            raise ValueError('HATCH chỉ hỗ trợ tịnh tiến hoặc co/giãn hình chữ nhật')
        bounds.append((low, high))
    (a, b), (c, d) = bounds
    scale = [(d[i]-c[i])/(b[i]-a[i]) for i in (0, 1)]
    offset = [c[i]-scale[i]*a[i] for i in (0, 1)]
    if any(not near([scale[i]*p[i]+offset[i] for i in (0, 1)], q[:2], 1e-5) for p, q in zip(before, after)):
        raise ValueError('HATCH thứ tự đỉnh không khớp phép co/giãn đường bao')
    return scale, offset


def follow_boundary(hatch, before_points, after_points):
    import copy
    from graph.packing_top_layers import same_boundary
    if len(hatch['paths']) != 1 or not same_boundary([p[:2] for p in before_points],
                                                  [p[:2] for p in hatch['paths'][0]['vertices']], 1e-4):
        raise ValueError('HATCH không trùng đường bao nguồn')
    scale, offset = boundary_map(before_points, after_points)
    result = copy.deepcopy(hatch)
    for path in result['paths']:
        for points in (path['vertices'], path.get('ends', [])):
            for p in points:
                p[:2] = [scale[i]*p[i]+offset[i] for i in (0, 1)]
    for p in result['seeds']:
        p[:] = [scale[i]*p[i]+offset[i] for i in (0, 1)]
    return result


def patch(entity, raw, before, after):
    current = snapshot(entity)
    if not near(current, before) or current.keys() != after.keys():
        raise ValueError('HATCH snapshot không khớp nguồn')
    if not near(current['elevation'], after['elevation']) or not near(current['extrusion'], after['extrusion']):
        raise ValueError('HATCH giữ mặt phẳng nguồn')
    if len(current['paths']) != len(after['paths']) or len(current['seeds']) != len(after['seeds']):
        raise ValueError('HATCH giữ topology nguồn')
    mapping = None
    for a, b in zip(current['paths'], after['paths']):
        if a.keys() != b.keys() or a['flags'] != b['flags'] or a['closed'] != b['closed'] or len(a['vertices']) != len(b['vertices']):
            raise ValueError('HATCH giữ topology nguồn')
        for p, q in zip(a['vertices'], b['vertices']):
            if len(q) != 3 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in q) or q[2] != p[2]:
                raise ValueError('HATCH tọa độ không hợp lệ')
        candidate = boundary_map(a['vertices'], b['vertices'])
        if len(a.get('ends', [])) != len(b.get('ends', [])):
            raise ValueError('HATCH giữ số line edges')
        scale, offset = candidate
        for p, q in zip(a.get('ends', []), b.get('ends', [])):
            if len(q) != 3 or not near(q[2], p[2]) or not near([scale[i]*p[i]+offset[i] for i in (0, 1)], q[:2]):
                raise ValueError('HATCH line edge phải theo cùng đường bao')
        if mapping is None:
            mapping = candidate
        elif not near(mapping, candidate):
            raise ValueError('HATCH nhiều đường bao cần cùng phép biến đổi')
    if len(current['paths']) != 1 and not near(mapping[0], [1, 1]):
        raise ValueError('HATCH nhiều đường bao chưa hỗ trợ co/giãn')
    scale, offset = mapping
    for p, q in zip(current['seeds'], after['seeds']):
        if len(q) != 2 or not near([scale[i]*p[i]+offset[i] for i in (0, 1)], q):
            raise ValueError('HATCH seed phải theo cùng đường bao')
    result = list(raw)
    # Restrict changes to path vertex and seed coordinates. Pattern-line
    # origins also use group 10/20 in some files and must not be overwritten.
    codes = [int(raw[i].strip()) for i in range(0, len(raw), 2)]
    start = codes.index(91)
    end = codes.index(75, start)
    seed = codes.index(98, end)
    vertices = [p for path in after['paths'] for p in path['vertices']]
    ends = [p for path in after['paths'] for p in path.get('ends', [])]
    newline = b'\r\n' if raw[0].endswith(b'\r\n') else b'\n'
    for code, axis in ((10, 0), (20, 1)):
        for low, high, points in ((start, end, vertices), (seed, len(codes), after['seeds'])):
            indices = [i for i in range(low, high) if codes[i] == code]
            if len(indices) != len(points):
                raise ValueError('HATCH native group không khớp đường bao/seed')
            for i, p in zip(indices, points):
                result[2*i+1] = str(p[axis]).encode('ascii') + newline
    for code, axis in ((11, 0), (21, 1)):
        indices = [i for i in range(start, end) if codes[i] == code]
        if len(indices) != len(ends):
            raise ValueError('HATCH native line ends không khớp topology')
        for i, p in zip(indices, ends):
            result[2*i+1] = str(p[axis]).encode('ascii') + newline
    return result


def validate_operations(plan, context):
    """HATCH must follow a source-identical closed outline and its map."""
    import json
    from graph.packing_top_layers import same_boundary
    records = {e['ref']: e for e in context['entities']}
    ops = {o.ref: o for o in plan.operations}
    for op in plan.operations:
        e = records.get(op.ref, {})
        if e.get('type') != 'HATCH':
            continue
        old = e.get('hatch_translation_geometry')
        if op.action != 'replace_geometry' or not old or not near(json.loads(op.before), old):
            raise ValueError('HATCH thiếu adapter/snapshot dịch chuyển nguồn')
        new = json.loads(op.after)
        if len(old['paths']) != 1 or len(new.get('paths', [])) != 1:
            raise ValueError('HATCH dịch chuyển cần đường bao nguồn duy nhất')
        matches = []
        for ref, boundary in records.items():
            g = boundary.get('geometry', {})
            edit = ops.get(ref)
            if boundary.get('review_only') or boundary.get('type') != 'LWPOLYLINE' or not g.get('closed') or not edit or edit.action != 'replace_geometry':
                continue
            if boundary.get('coordinate_frame') != e.get('coordinate_frame') or boundary.get('layout') != e.get('layout') or not set(boundary.get('source_sheet_ids', [])).intersection(e.get('source_sheet_ids', [])):
                continue
            target = json.loads(edit.after)
            if any(any(p[2:]) for p in g['points']):
                continue
            if same_boundary([p[:2] for p in g['points']], [p[:2] for p in old['paths'][0]['vertices']], 1e-4) and same_boundary(
                    [p[:2] for p in target['points']], [p[:2] for p in new['paths'][0]['vertices']], 1e-4):
                expected = follow_boundary(old, g['points'], target['points'])
                if near(expected, new):
                    matches.append(ref)
        if len(matches) != 1:
            raise ValueError('HATCH cần đúng một đường bao kín dịch cùng từ nguồn')
