"""Recognize bounded native CenterMark evidence; never authorize an edit."""
import math


def inspection_roots(inventory, allowed):
    """Find possible circle/mark pairs inside selection, for read-only inspection."""
    rows=[e for e in inventory.get('entities',[]) if e.get('handle') in allowed and e.get('is_layout') is True]
    def point(e,key):
        p=e.get(key)
        return p if isinstance(p,list) and len(p)==3 and all(type(v) in (int,float) and math.isfinite(v) for v in p) else None
    inserts=[e for e in rows if e.get('type')=='INSERT' and not e.get('dynamic') and point(e,'position') is not None]
    roots=set()
    for circle in rows:
        center=point(circle,'center')
        if circle.get('type')!='CIRCLE' or center is None:continue
        matching=[e for e in inserts if e.get('owner_handle')==circle.get('owner_handle') and math.dist(center,e['position'])<=1e-6]
        if matching:
            roots.add(circle['handle']);roots.update(e['handle'] for e in matching)
    if not roots:raise ValueError('Phạm vi chọn chưa có đường tròn và dấu tâm trùng tâm để kiểm tra.')
    if len(roots)>64:raise ValueError('Phạm vi có quá nhiều cặp dấu tâm; chọn khung hoặc block nhỏ hơn để kiểm tra.')
    return sorted(roots)


def candidates(inventory):
    graph = inventory.get('native_dependencies', {})
    if graph.get('status') != 'inspected' or graph.get('truncated') is not False or graph.get('errors') != []:
        raise ValueError('Cần đọc dependency native đầy đủ trong phạm vi yêu cầu.')
    nodes = graph.get('nodes', [])
    by_handle = {n['handle']: n for n in nodes}
    if len(by_handle) != len(nodes):
        raise ValueError('Inventory dependency có handle trùng.')
    entities = {e['handle']: e for e in inventory.get('entities', [])}
    edges = {(e['source'], e['relation'], e['target']) for e in graph.get('edges', [])}
    roots = set(graph.get('requested_roots', []))

    def targets(handle, relation):
        return {t for s, r, t in edges if s == handle and r == relation}

    def one(handle, relation):
        found = targets(handle, relation)
        return next(iter(found)) if len(found) == 1 else None

    result = []
    for circle in entities.values():
        handle = circle['handle']
        if handle not in roots or circle.get('type') != 'CIRCLE' or circle.get('is_layout') is not True:
            continue
        dependency = one(handle, 'persistent_reactor')
        if by_handle.get(dependency, {}).get('native_class') != 'AcDbAssocGeomDependency':
            continue
        action = one(dependency, 'native:OwningAction')
        if (one(dependency, 'native:DependentOnObject') != handle or
                by_handle.get(action, {}).get('native_class') != 'AcDbAssocAction'):
            continue
        body = one(action, 'native:ActionBody')
        if (by_handle.get(body, {}).get('native_class') != 'AcDbCenterMarkActionBody' or
                one(body, 'native:ParentAction') != action):
            continue
        owned = {s for s, r, t in edges if r == 'native:OwningAction' and t == action}
        if len(owned) != 2 or dependency not in owned:
            continue
        if graph.get('action_dependency_limit') is not None and targets(action,'native:Dependency') != owned:
            continue
        mark_dependency = next(iter(owned - {dependency}))
        mark_handle = one(mark_dependency, 'native:DependentOnObject')
        mark = entities.get(mark_handle, {})
        owner = circle.get('owner_handle')
        if (mark_handle not in roots or mark.get('type') != 'INSERT' or mark.get('is_layout') is not True or
                not owner or mark.get('owner_handle') != owner or
                targets(mark_handle, 'persistent_reactor') != {mark_dependency} or
                by_handle.get(mark_dependency, {}).get('native_class') != 'AcDbAssocDependency'):
            continue
        center, position = circle.get('center'), mark.get('position')
        if not all(isinstance(v, list) and len(v) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in v) for v in (center, position)):
            continue
        if math.dist(center, position) > 1e-6:
            continue
        result.append(dict(circle_handle=handle, mark_handle=mark_handle, owner_handle=owner,
                           action_handle=action, action_body_handle=body,
                           dependency_handles=sorted(owned), source_center=center,
                           edit_authorization=False, requires_native_preflight=True))
    return sorted(result, key=lambda c: c['circle_handle'])


def validate_group(operations, scopes=None):
    if not 1<=len(operations)<=16 or any(op.get('action')!='translate_centermark' for op in operations):
        raise ValueError('Chỉ gộp từ 1 đến 16 cặp CenterMark; không trộn thao tác khác.')
    handles=[op.get(key) for op in operations for key in ('handle','mark_handle','action_handle')]
    if any(not isinstance(h,str) or not h for h in handles) or len(set(handles))!=len(handles):
        raise ValueError('Các cặp CenterMark trùng hình, dấu tâm hoặc action.')
    if scopes is not None and any(op[key] not in scopes for op in operations for key in ('handle','mark_handle')):
        raise ValueError('Phải chọn đủ từng đường tròn và dấu tâm trong nhóm.')


def verify_result(operation, inventory, dxf_path, source_hash, output_hash):
    """Compatibility entry point for one-pair artifact audits."""
    verify_results([dict(operation,action=operation.get('action','translate_centermark'))],inventory,dxf_path,source_hash,output_hash)


def verify_results(operations, inventory, dxf_path, source_hash, output_hash):
    validate_group(operations)
    effects=inventory.get('centermark_effects',[])
    if not isinstance(effects,list) or len(effects)!=len(operations) or any(not isinstance(e,dict) for e in effects):
        raise ValueError('Thiếu bằng chứng dịch CenterMark.')
    by_pair={(e.get('circle_handle'),e.get('mark_handle'),e.get('action_handle')):e for e in effects}
    expected={(op['handle'],op['mark_handle'],op['action_handle']) for op in operations}
    if set(by_pair)!=expected or len(by_pair)!=len(effects):
        raise ValueError('Bằng chứng CenterMark thiếu, dư hoặc trùng cặp.')
    doc=None
    for op in operations:
        effect=by_pair[(op['handle'],op['mark_handle'],op['action_handle'])]
        doc=_verify_effect(op,effect,inventory,dxf_path,source_hash,output_hash,len(operations),doc)


def _verify_effect(operation,effect,inventory,dxf_path,source_hash,output_hash,group_count,doc):
    import json
    import ezdxf
    before, after = json.loads(operation['before']), json.loads(operation['after'])
    if (effect.get('source_sha256') != source_hash or effect.get('output_sha256') != output_hash or
            any(effect.get(key) != operation[field] for key, field in
                [('circle_handle', 'handle'), ('mark_handle', 'mark_handle'), ('action_handle', 'action_handle')]) or
            effect.get('persisted_state_verified_before_evaluation') is not True or
            effect.get('reopened_evaluation_stable') is not True or
            effect.get('selected_pair_count',1) != group_count or len(inventory.get('entities',[]))<2*group_count or
            effect.get('unselected_inventory_entries_verified') != len(inventory.get('entities', []))-2*group_count or
            effect.get('numeric_tolerance') != 1e-7):
        raise ValueError('Bằng chứng CenterMark không khớp lệnh/nguồn hoặc thiếu kiểm tra mở lại.')
    def close(a, b):
        return (isinstance(a, (list, tuple)) and len(a) == 3 and
                all(type(x) in (int, float) and math.isfinite(x) for x in a) and math.dist(a, b) <= 1e-6)
    if not all(close(effect.get(key), expected) for key, expected in
               [('source_circle_center', before), ('source_mark_position', before),
                ('circle_center', after), ('mark_position', after), ('delta', [b-a for a,b in zip(before,after)])]):
        raise ValueError('Tâm hoặc vector dịch CenterMark sai lệnh.')
    pairs = candidates(inventory)
    if not any(p['circle_handle']==operation['handle'] and p['mark_handle']==operation['mark_handle'] and
               p['action_handle']==operation['action_handle'] and p['owner_handle']==operation['owner_handle'] and
               close(p['source_center'], after) for p in pairs):
        raise ValueError('Dependency CenterMark không được bảo toàn sau xuất.')
    if doc is None:doc = ezdxf.readfile(dxf_path)
    circle, mark = (doc.entitydb.get(operation[k]) for k in ('handle','mark_handle'))
    if (circle is None or mark is None or circle.dxftype()!='CIRCLE' or mark.dxftype()!='INSERT' or
            circle.dxf.owner!=operation['owner_handle'] or mark.dxf.owner!=operation['owner_handle'] or
            not close(list(circle.dxf.center),after) or not close(list(mark.dxf.insert),after) or
            not circle.get_reactors() or not mark.get_reactors() or
            not isinstance(effect.get('radius'), (int,float)) or not math.isfinite(effect['radius']) or
            abs(circle.dxf.radius-effect['radius'])>1e-8):
        raise ValueError('DXF đọc độc lập không khớp cặp CenterMark đã dịch.')
    return doc
