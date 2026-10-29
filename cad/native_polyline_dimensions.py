"""Discover the bounded translation probe group; never authorizes an edit."""
from cad.dimension_associations import source_binding


def discover(inventory, doc, handle):
    graph = inventory.get("native_dependencies", {})
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    require(graph.get("status") == "inspected" and not graph.get("errors") and graph.get("truncated") is False
            and graph.get("action_dependency_limit") == 128, "Incomplete native dependency inspection")
    nodes = {n["handle"]: n for n in graph["nodes"]}
    rows = {r["handle"]: r for r in inventory["entities"]}
    require(len(nodes) == len(graph["nodes"]) and len(rows) == len(inventory["entities"]), "Duplicate inventory handles")
    edges = graph["edges"]
    def targets(source, relation):
        values = [e["target"] for e in edges if e["source"] == source and e["relation"] == relation]
        require(len(values) == len(set(values)), "Duplicate native relation")
        return set(values)
    def one(source, relation):
        values = targets(source, relation)
        require(len(values) == 1, "Missing or ambiguous " + relation)
        return next(iter(values))
    def entity(h):
        require(h in rows and h in nodes, "Missing entity inventory")
        row = rows[h]; obj = doc.entitydb.get(h)
        require(obj is not None and obj.is_alive and obj.dxftype() == row["type"]
                and obj.dxf.owner == row["owner_handle"] == nodes[h]["owner_handle"], "DXF entity ownership mismatch")
        require(set(obj.get_reactors()) == set(row["persistent_reactor_handles"]) == targets(h, "persistent_reactor"), "Reactor mismatch")
        ext = obj.get_extension_dict().dictionary.dxf.handle if obj.has_extension_dict else None
        require(ext == row["extension_dictionary_handle"], "Extension dictionary mismatch")
        return obj
    require(handle in graph.get("requested_roots", []), "Polyline was not inspected")
    poly = entity(handle); row = rows[handle]
    require(poly.dxftype() == "LWPOLYLINE" and row.get("is_layout") and poly.closed and len(poly) == 8
            and not poly.has_extension_dict and tuple(poly.dxf.extrusion) == (0, 0, 1)
            and all(p[4] == 0 for p in poly.get_points()), "Unsupported probe polyline")
    reactors = targets(handle, "persistent_reactor")
    require(len(reactors) == 6, "Expected six source reactors")
    legacy = []; actions = []; dims = []
    for reactor in sorted(reactors):
        node = nodes[reactor]
        if node["native_class"] == "AcDbDimAssoc":
            dictionary = node["owner_handle"]
            require(nodes[dictionary]["native_class"] == "AcDbDictionary"
                    and targets(dictionary, "dictionary:ACAD_DIMASSOC") == {reactor}
                    and {e["relation"] for e in edges if e["source"] == dictionary and e["relation"].startswith("dictionary:")} == {"dictionary:ACAD_DIMASSOC"}, "Legacy dictionary mismatch")
            dim = nodes[dictionary]["owner_handle"]
            obj = entity(dim)
            require(obj.has_extension_dict and obj.get_extension_dict().dictionary.dxf.handle == dictionary
                    and targets(dim, "persistent_reactor") == {reactor}, "Legacy DIM ownership mismatch")
            binding = source_binding(obj)
            require(binding.get("status") == "verified_source_points" and binding.get("source_refs") == [handle]
                    and binding.get("association_ref") == reactor, "Legacy binding mismatch")
            legacy.append(dict(association_ref=reactor, dimension_handle=dim, binding=binding))
        elif node["native_class"] == "AcDbAssocGeomDependency":
            require(one(reactor, "native:DependentOnObject") == handle, "Geometry dependency mismatch")
            action = one(reactor, "native:OwningAction")
            require(node["owner_handle"] == action and nodes[action]["native_class"] == "AcDbAssocAction", "Action ownership mismatch")
            body = one(action, "native:ActionBody")
            require(nodes[body]["native_class"] == "AcDbAssocRotatedDimActionBody" and nodes[body]["owner_handle"] == action
                    and one(body, "native:ParentAction") == action, "Unsupported action body")
            deps = targets(action, "native:Dependency")
            require(len(deps) == 2 and reactor in deps, "Unexpected action dependencies")
            other = next(iter(deps - {reactor}))
            require(nodes[other]["native_class"] == "AcDbAssocDependency" and nodes[other]["owner_handle"] == action
                    and one(other, "native:OwningAction") == action, "DIM dependency mismatch")
            dim = one(other, "native:DependentOnObject"); obj = entity(dim)
            require(not obj.has_extension_dict and targets(dim, "persistent_reactor") == {other}, "Native DIM topology mismatch")
            actions.append(dict(action_handle=action, body_handle=body, geometry_dependency=reactor, dimension_dependency=other, dimension_handle=dim))
        else:
            raise ValueError("Unsupported source reactor")
        require(nodes[dim]["native_class"] == "AcDbRotatedDimension" and obj.dxftype() == "DIMENSION"
                and obj.dxf.dimtype & 15 == 0 and obj.dxf.owner == poly.dxf.owner, "Unsupported DIM type or layout")
        dims.append(dim)
    require(len(legacy) == 4 and len(actions) == 2 and len(set(dims)) == 6
            and len({a["action_handle"] for a in actions}) == 2, "Unexpected group cardinality")
    return dict(status="discovered_polyline_dimension_probe_group", polyline_handle=handle,
                dimension_handles=sorted(dims), legacy_associations=legacy, native_actions=actions,
                edit_authorization=False, requires_native_preflight=True,
                scope="Listed polyline/DIM translation probe topology; does not prove complete mechanical dependencies.")
