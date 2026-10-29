"""Read-only, scoped geometric observations; never inferred design authorization."""
import math
from itertools import combinations


def candidates(doc, handles, *, distance_mm=0.01, angle_degrees=0.5):
    if doc.units != 4:
        raise ValueError("Explicit millimeter drawing units required")
    if not 0 < distance_mm <= 1 or not 0 < angle_degrees <= 5:
        raise ValueError("Invalid candidate tolerance")
    if not handles or len(handles) > 64 or len(set(handles)) != len(handles):
        raise ValueError("Select 1 to 64 distinct entity handles")
    nodes = []; edges = []; geometry = {}; owners = set()
    layout_owners = {layout.layout_key for layout in doc.layouts}
    for handle in handles:
        obj = doc.entitydb.get(handle)
        if obj is None or not obj.is_alive or obj.dxf.owner not in layout_owners:
            raise ValueError("Selection must contain live layout entities")
        owners.add(obj.dxf.owner)
        node = dict(handle=handle, type=obj.dxftype(), owner_handle=obj.dxf.owner)
        try:
            if obj.dxftype() == "LINE":
                a = tuple(obj.dxf.start); b = tuple(obj.dxf.end)
                if not all(math.isfinite(v) for v in a + b) or abs(a[2]-b[2]) > 1e-8:
                    raise ValueError("Non-planar or nonfinite LINE")
                length = math.hypot(b[0]-a[0], b[1]-a[1])
                if length <= 1e-8:
                    raise ValueError("Degenerate LINE")
                geometry[handle] = dict(kind="line", a=a, b=b, unit=((b[0]-a[0])/length, (b[1]-a[1])/length), z=a[2])
            elif obj.dxftype() == "CIRCLE":
                center = tuple(obj.dxf.center); radius = obj.dxf.radius
                if tuple(obj.dxf.extrusion) != (0, 0, 1) or not all(math.isfinite(v) for v in center + (radius,)) or radius <= 0:
                    raise ValueError("Unsupported CIRCLE plane or radius")
                geometry[handle] = dict(kind="circle", center=center, z=center[2])
            else:
                raise ValueError("Entity type not covered by geometric candidate scan")
            node["status"] = "observed"
        except ValueError as error:
            node.update(status="unsupported", reason=str(error))
        nodes.append(node)
    if len(owners) != 1:
        raise ValueError("Do not mix layout coordinate systems")
    def add(a, b, relation, evidence):
        edges.append(dict(source=a, target=b, relation=relation, evidence=evidence,
                          status="candidate", edit_authorization=False, requires_design_confirmation=True))
    for a, b in combinations(geometry, 2):
        x, y = geometry[a], geometry[b]
        if abs(x["z"]-y["z"]) > 1e-8:
            continue
        if x["kind"] == y["kind"] == "line":
            dot = max(-1, min(1, abs(sum(u*v for u, v in zip(x["unit"], y["unit"])))))
            angle = math.degrees(math.acos(dot))
            if angle <= angle_degrees:
                add(a, b, "parallel", dict(angular_residual_degrees=angle))
            if abs(90-angle) <= angle_degrees:
                add(a, b, "perpendicular", dict(angular_residual_degrees=abs(90-angle)))
            for i, p in enumerate((x["a"], x["b"])):
                for j, q in enumerate((y["a"], y["b"])):
                    distance = math.dist(p, q)
                    if distance <= distance_mm:
                        add(a, b, "coincident_endpoints", dict(source_endpoint=i, target_endpoint=j, distance_mm=distance))
        if x["kind"] == y["kind"] == "circle":
            distance = math.dist(x["center"], y["center"])
            if distance <= distance_mm:
                add(a, b, "concentric", dict(center_distance_mm=distance))
    return dict(schema_version=1, status="geometric_candidates_only", nodes=nodes, edges=edges,
                tolerances=dict(distance_mm=distance_mm, angle_degrees=angle_degrees, plane_mm=1e-8),
                edit_authorization=False, degrees_of_freedom=None,
                coverage="Selected layout LINE endpoints/directions and XY CIRCLE centers only; no native constraints, mechanical identity, solver, or full dependency closure.")
