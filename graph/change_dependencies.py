"""Propagation of explicit, confirmed coordinate rules, never inferred constraints."""
import json
import math
import networkx as nx
from ezdxf.math import Matrix44,Vec3,OCS
from pydantic import BaseModel,ConfigDict
from typing import Literal
from cad.edit_engine import Operation
from graph.dependency_graph import DependencyGraph


class CoordinateRule(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_ref: str
    target_ref: str
    target_action: Literal['line_end','move_insert','dimension_point','geometry_point','translate_geometry']
    axis: Literal['x','y','z']
    multiplier: float
    source_field: Literal['start','end','center','position','defpoint2','defpoint3'] = 'end'
    target_point: Literal['defpoint','defpoint2','defpoint3','start','end','center'] = 'defpoint3'
    composition: Literal['exclusive','orthogonal'] = 'exclusive'


def _propagate_exclusive(operations,rules,context):
    by_ref={op.ref:op for op in operations}
    entities={e['ref']:e for e in context['entities']}
    design=DependencyGraph();graph=design.graph
    for rule in rules:
        if not math.isfinite(rule.multiplier):raise ValueError('Hệ số quan hệ không hữu hạn')
        if rule.source_ref not in entities or rule.target_ref not in entities:raise ValueError('Quan hệ ngoài phạm vi')
        source_frame=entities[rule.source_ref].get('coordinate_frame')
        target_frame=entities[rule.target_ref].get('coordinate_frame')
        if source_frame is not None and source_frame!=target_frame and not all(entities[ref].get('frame_to_layout') for ref in (rule.source_ref,rule.target_ref)):
            raise ValueError('Quan hệ nối hai hệ tọa độ nhưng thiếu ma trận instance')
        if entities[rule.source_ref].get('layout')!=entities[rule.target_ref].get('layout'):
            raise ValueError('Quan hệ vượt layout cần mapping hình chiếu được xác nhận riêng')
        if graph.has_edge(rule.source_ref,rule.target_ref):raise ValueError('Quan hệ trùng lặp')
        graph.add_edge(rule.source_ref,rule.target_ref,rule=rule)
    if not nx.is_directed_acyclic_graph(graph):raise ValueError('Quan hệ có vòng lặp; cần giải ràng buộc riêng')
    generated=[]
    for source in design.topological_order():
        if not graph.out_degree(source):continue
        driver=by_ref.get(source)
        if driver is None or driver.action not in ('line_end','move_insert','replace_geometry'):
            raise ValueError('Quan hệ tọa độ cần thao tác tọa độ nguồn; không suy delta từ tên vật liệu')
        old=json.loads(driver.before)
        for target in graph.successors(source):
            rule=graph.edges[source,target]['rule'];axis='xyz'.index(rule.axis)
            if driver.action=='replace_geometry':
                after=json.loads(driver.after)
                if rule.source_field not in old or rule.source_field not in after:raise ValueError('Nguồn quan hệ thiếu điểm được ràng buộc')
                previous,new=old[rule.source_field],after[rule.source_field]
            else:previous,new=old,driver.xyz
            delta=(new[axis]-previous[axis])*rule.multiplier
            record=entities[target];key='end' if rule.target_action=='line_end' else 'position'
            before=record.get('geometry') if rule.target_action=='translate_geometry' else record.get('geometry',{}).get(rule.target_point) if rule.target_action in ('dimension_point','geometry_point') else record.get(key)
            if rule.target_action=='dimension_point' and record.get('type')!='DIMENSION':raise ValueError('Quy tắc dimension cần entity DIMENSION')
            if rule.target_action=='geometry_point' and record.get('type') not in ('LINE','CIRCLE','ARC','ELLIPSE'):raise ValueError('Quy tắc điểm geometry không hỗ trợ entity đích')
            if rule.target_action in ('dimension_point','geometry_point') and (before is None or len(before)!=3):raise ValueError('Thiếu điểm geometry được liên kết')
            if before is None:raise ValueError('Thiếu tọa độ chi tiết phụ thuộc')
            vector=[0.,0.,0.];vector[axis]=delta
            source_record=entities[source]
            if driver.action=='replace_geometry' and source_record.get('type') in ('CIRCLE','ARC') and rule.source_field=='center':
                vector=list(OCS(source_record['geometry']['extrusion']).to_wcs(Vec3(vector)))
            source_matrix=entities[source].get('frame_to_layout')
            target_matrix=record.get('frame_to_layout')
            if source_matrix and target_matrix:
                source_matrix=Matrix44([v for row in source_matrix for v in row])
                target_matrix=Matrix44([v for row in target_matrix for v in row])
                try:target_matrix.inverse()
                except ZeroDivisionError:raise ValueError('Instance có ma trận suy biến')
                vector=list(target_matrix.transform_direction(source_matrix.transform_direction(Vec3(vector))))
            if rule.target_action=='translate_geometry':
                from cad.rigid_translation import translated
                from cad.geometry import near
                original=record['geometry'];changed=translated(record,vector)
                if target in by_ref:
                    op=by_ref[target]
                    if op.action!='replace_geometry' or not near(json.loads(op.before),original) or not near(json.loads(op.after),changed):
                        raise ValueError('Dịch hình trực tiếp xung đột với quan hệ phụ thuộc')
                else:
                    op=Operation(ref=target,action='replace_geometry',before=json.dumps(original),after=json.dumps(changed),xyz=[],reason='Dịch nguyên hình theo quan hệ mặt lắp đã gắn nguồn')
                    by_ref[target]=op;generated.append(op)
                continue
            if rule.target_action=='geometry_point' and record.get('type') in ('CIRCLE','ARC'):
                vector=list(OCS(record['geometry']['extrusion']).from_wcs(Vec3(vector)))
            xyz=[a+b for a,b in zip(before,vector)]
            if rule.target_action in ('dimension_point','geometry_point'):
                from cad.geometry import near
                original=record['geometry'];changed=json.loads(json.dumps(original));changed[rule.target_point]=xyz
                if target in by_ref:
                    op=by_ref[target]
                    if op.action!='replace_geometry' or not near(json.loads(op.before),original) or not near(json.loads(op.after),changed):
                        raise ValueError('Geometry trực tiếp xung đột với quan hệ phụ thuộc')
                    continue
                op=Operation(ref=target,action='replace_geometry',before=json.dumps(original),after=json.dumps(changed),xyz=[],reason=f'Đồng bộ {rule.target_point} theo quan hệ đã xác nhận từ {source}')
                by_ref[target]=op;generated.append(op)
                continue
            if target in by_ref:
                op=by_ref[target]
                if op.action!=rule.target_action or any(abs(a-b)>1e-8 for a,b in zip(op.xyz,xyz)):
                    raise ValueError('Thao tác trực tiếp xung đột với quan hệ phụ thuộc')
                continue
            op=Operation(ref=target,action=rule.target_action,before=json.dumps(before),after='',xyz=xyz,
                         reason=f'Lan truyền theo quan hệ đã xác nhận từ {source}')
            by_ref[target]=op;generated.append(op)
    return operations+generated


def _orthogonal_vector(rule,operations,entities):
    """Return a proven source displacement and its direction in target space."""
    driver=next((op for op in operations if op.ref==rule.source_ref),None)
    if driver is None or driver.action not in ('line_end','move_insert','replace_geometry'):
        raise ValueError('Quan hệ tọa độ cần thao tác tọa độ nguồn')
    old=json.loads(driver.before)
    if driver.action=='replace_geometry':
        after=json.loads(driver.after)
        if rule.source_field not in old or rule.source_field not in after:raise ValueError('Nguồn quan hệ thiếu điểm được ràng buộc')
        old,new=old[rule.source_field],after[rule.source_field]
    else:new=driver.xyz
    axis='xyz'.index(rule.axis)
    if len(old)!=3 or len(new)!=3 or not all(math.isfinite(v) for v in old+new):raise ValueError('Tọa độ nguồn không hợp lệ')
    delta=(new[axis]-old[axis])*rule.multiplier
    direction=[0.,0.,0.];direction[axis]=1.
    source,target=entities[rule.source_ref],entities[rule.target_ref]
    if driver.action=='replace_geometry' and source.get('type') in ('CIRCLE','ARC') and rule.source_field=='center':
        direction=list(OCS(source['geometry']['extrusion']).to_wcs(Vec3(direction)))
    sm,tm=source.get('frame_to_layout'),target.get('frame_to_layout')
    if sm and tm:
        sm=Matrix44([v for row in sm for v in row]);tm=Matrix44([v for row in tm for v in row])
        try:tm.inverse()
        except ZeroDivisionError:raise ValueError('Instance có ma trận suy biến')
        direction=list(tm.transform_direction(sm.transform_direction(Vec3(direction))))
    length=math.sqrt(sum(v*v for v in direction))
    if length<1e-12 or not all(math.isfinite(v) for v in direction) or not math.isfinite(delta):raise ValueError('Vector quan hệ không hợp lệ')
    return [v*delta for v in direction],[v/length for v in direction]


def propagate(operations,rules,context):
    """Compose independently proven orthogonal translations in dependency order.

    Legacy rules remain exclusive. Only explicit orthogonal move rules can
    combine; duplicate, nonorthogonal, mixed and cyclic constraints fail.
    """
    from cad.geometry import near
    entities={e['ref']:e for e in context['entities']};design=DependencyGraph();graph=design.graph;incoming={};pairs={}
    for rule in rules:
        if not math.isfinite(rule.multiplier):raise ValueError('Hệ số quan hệ không hữu hạn')
        if not {rule.source_ref,rule.target_ref}<=entities.keys():raise ValueError('Quan hệ ngoài phạm vi')
        source,target=entities[rule.source_ref],entities[rule.target_ref]
        if source.get('layout')!=target.get('layout'):raise ValueError('Quan hệ vượt layout cần mapping hình chiếu được xác nhận riêng')
        if source.get('coordinate_frame') is not None and source.get('coordinate_frame')!=target.get('coordinate_frame') and not all(e.get('frame_to_layout') for e in (source,target)):
            raise ValueError('Quan hệ nối hai hệ tọa độ nhưng thiếu ma trận instance')
        pair=(rule.source_ref,rule.target_ref);previous=pairs.setdefault(pair,[])
        if previous and (rule.composition!='orthogonal' or any(r.composition!='orthogonal' or r==rule for r in previous)):
            raise ValueError('Quan hệ trùng lặp')
        previous.append(rule);incoming.setdefault(rule.target_ref,[]).append(rule);graph.add_edge(*pair)
    if not nx.is_directed_acyclic_graph(graph):raise ValueError('Quan hệ có vòng lặp; cần giải ràng buộc riêng')
    result=list(operations)
    for target in design.topological_order():
        selected=incoming.get(target,[])
        if not selected:continue
        if all(r.composition=='exclusive' for r in selected):
            result=_propagate_exclusive(result,selected,context);continue
        if any(r.composition!='orthogonal' or r.target_action not in ('move_insert','translate_geometry') for r in selected) or len({r.target_action for r in selected})!=1:
            raise ValueError('Chỉ ghép các quan hệ dịch instance trực giao, không trộn quy tắc khác')
        geometry=selected[0].target_action=='translate_geometry'
        before=entities[target].get('geometry') if geometry else entities[target].get('position')
        if before is None or not geometry and (len(before)!=3 or not all(math.isfinite(v) for v in before)):raise ValueError('Thiếu tọa độ chi tiết phụ thuộc')
        delta=[0.,0.,0.];directions=[]
        for rule in selected:
            vector,direction=_orthogonal_vector(rule,result,entities)
            if any(abs(sum(a*b for a,b in zip(direction,d)))>1e-8 for d in directions):
                raise ValueError('Quan hệ dịch không trực giao; cần giải ràng buộc riêng')
            directions.append(direction);delta=[a+b for a,b in zip(delta,vector)]
        if geometry:
            from cad.rigid_translation import translated
            after=translated(entities[target],delta)
        else:xyz=[a+b for a,b in zip(before,delta)]
        direct=next((op for op in result if op.ref==target),None)
        if direct:
            if geometry:
                valid=direct.action=='replace_geometry' and near(json.loads(direct.before),before,1e-8) and near(json.loads(direct.after),after,1e-8)
            else:valid=direct.action=='move_insert' and near(json.loads(direct.before),before,1e-8) and near(direct.xyz,xyz,1e-8)
            if not valid:
                raise ValueError('Thao tác trực tiếp xung đột với quan hệ phụ thuộc')
        else:
            result.append(Operation(ref=target,action='replace_geometry' if geometry else 'move_insert',before=json.dumps(before),after=json.dumps(after) if geometry else '',xyz=[] if geometry else xyz,reason='Giữ các tiếp xúc trực giao đã gắn nguồn'))
    return result
