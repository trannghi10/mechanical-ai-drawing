"""Compile semantic resizing recipes into existing audited CAD operations."""
import json
import math
import re
from cad.parametric import resize
from cad.geometry import near
from graph.fit_constraints import measurement
from graph.measurement_rules import solve


def compile_recipes(plan, context):
    if plan.questions:
        return plan
    from backend.services.curved_wall_service import compile_recipes as compile_walls
    plan=compile_walls(plan,context)
    from backend.services.forming_service import compile_recipes as compile_forming
    plan=compile_forming(plan,context)
    from backend.services.hole_service import compile_recipes as compile_holes
    plan=compile_holes(plan,context)
    if not plan.resize_recipes:return plan
    records={e['ref']:e for e in context['entities']}
    from graph.measured_views import expand
    recipes=expand(plan.resize_recipes,context)
    plan.resize_recipes=recipes
    if context.get('confirmed_parameter_links'):
        from graph.parameter_links import expand as expand_parameter_links
        plan=expand_parameter_links(plan,context)
        recipes=expand(plan.resize_recipes,context)
        plan.resize_recipes=recipes
    if len(recipes)>64 or len({r.dimension_ref for r in recipes})!=len(recipes):
        raise ValueError('Recipe kích thước trùng hoặc quá nhiều')
    # Resolve a model's instance handle to the actual part name only when native
    # block membership proves every referenced feature belongs to that instance.
    # This is source-backed normalization, not an inferred assembly connection.
    for recipe in recipes:
        refs=recipe.outline_refs+recipe.hole_refs+[recipe.dimension_ref]
        frame=records.get(recipe.dimension_ref,{}).get('coordinate_frame','')
        owner=frame.removeprefix('instance:') if frame.startswith('instance:') else None
        parent=records.get(owner,{})
        from cad.part_identity import record_identity
        bom_codes={r['part_code'] for e in context['entities'] for r in e.get('bom',{}).get('rows',[])}
        owned_code=record_identity(parent,bom_codes)
        if parent.get('type')=='INSERT' and recipe.part_code in (owner,parent.get('name'),owned_code) and all(ref in records and records[ref].get('coordinate_frame')==frame for ref in refs):
            recipe.part_code=owned_code or parent['name']
            recipe.evidence_refs=sorted(set(recipe.evidence_refs+refs+[owner]))
    # Text edit proposals attached to a recipe can be compiled without asking
    # the model to repeat their raw contents in a second operation object.
    from cad.edit_engine import Operation
    graphic_cells={cell.get('mirror_ref') for table in context['entities'] if table.get('bom',{}).get('status')=='verified_template'
                   for row in table['bom']['rows'] for cell in row.get('cells',{}).values() if cell.get('storage')=='text'}
    for edit in plan.edits:
        record=records.get(edit.entity_ref,{})
        if (edit.purpose!='annotation' and not (edit.purpose=='bom' and edit.entity_ref in graphic_cells)) or record.get('type') not in ('TEXT','MTEXT') or any(op.ref==edit.entity_ref for op in plan.operations):continue
        raw=record.get('raw_text',record.get('text',''))
        if edit.before!=raw:
            # Some models return a labelled quote rather than the raw attribute.
            # Strip it only when the quoted before is exactly the native source.
            pattern=r'^(?:MTEXT|TEXT) text: ([\'\"])(.*?)\1$'
            before=re.fullmatch(pattern,edit.before,re.S);after=re.fullmatch(pattern,edit.after,re.S)
            if not before or not after or before.group(2)!=raw:
                raise ValueError('Mô tả trước sửa không khớp nguồn')
            edit.before=raw;edit.after=after.group(2)
        plan.operations.append(Operation(ref=edit.entity_ref,action='replace_text',before=raw,after=edit.after,xyz=[],reason=edit.reason))
    equations=[dep.equation_rule for dep in plan.dependencies if dep.equation_rule]
    requested={r.dimension_ref:r.new_measurement for r in recipes if r.new_measurement is not None}
    recipe_refs={r.dimension_ref for r in recipes}
    # Dimensions without a resize recipe are explicit fixed dimensions in the plan.
    for equation in equations:
        for term in equation.terms:
            if term.dimension_ref not in recipe_refs:
                record=records.get(term.dimension_ref,{})
                requested[term.dimension_ref]=measurement(record,record.get('geometry',{}))
    solved=solve(context,equations,requested)
    by_ref={op.ref:op for op in plan.operations}
    from backend.services.change_service import EditProposal
    for recipe in recipes:
        if not recipe.part_code.strip():raise ValueError('Recipe thiếu mã chi tiết')
        if recipe.dimension_ref not in solved:
            raise ValueError('Recipe chưa có kích thước đích hoặc phương trình xác định duy nhất')
        # A verified BOM row for this part must also be synchronized by the plan.
        rows=[(table,row) for table in context['entities'] for row in table.get('bom',{}).get('rows',[]) if row['part_code']==recipe.part_code]
        all_rows=[row for table in context['entities'] for row in table.get('bom',{}).get('rows',[])]
        if all_rows and not rows:
            raise ValueError('Mã recipe không khớp chi tiết trong bảng kê nguồn')
        if not rows and any(e['type'] in ('ACAD_TABLE','GRAPHIC_TABLE') for e in context['entities']):
            raise ValueError('Chưa xác định dòng bảng kê native đi cùng recipe')
        record=records.get(recipe.dimension_ref,{})
        if rows and not math.isclose(measurement(record,record.get('geometry',{})),solved[recipe.dimension_ref],abs_tol=1e-6):
            old_meas = measurement(record, record.get('geometry', {}))
            new_meas = solved[recipe.dimension_ref]
            for table,row in rows:
                cell=row.get('cells',{}).get('description',{})
                from bom.operations import has_cell_change
                if not has_cell_change(table,cell,plan.operations):
                    import re
                    raw_text = cell.get('raw_text', '')
                    old_str = f'{old_meas:g}'
                    new_str = f'{new_meas:g}'
                    updated_text = re.sub(r'(?<![\d.,])' + re.escape(old_str) + r'(?![\d.,])', new_str, raw_text)
                    if updated_text == raw_text:
                        old_comma, new_comma = old_str.replace('.', ','), new_str.replace('.', ',')
                        updated_text = re.sub(r'(?<![\d.,])' + re.escape(old_comma) + r'(?![\d.,])', new_comma, raw_text)
                    idx = cell.get('index', -1)
                    mirror = cell.get('mirror_ref', '')
                    if updated_text != raw_text and idx >= 0:
                        if cell.get('storage') != 'text':
                            plan.operations.append(Operation(ref=table['ref'], action='table_cell', cell_index=idx,
                                                             mirror_ref=mirror, before=raw_text, after=updated_text, xyz=[],
                                                             reason=f'Tự động đồng bộ mô tả BOM {recipe.part_code}: {old_str} -> {new_str}'))
                            plan.edits.append(EditProposal(entity_ref=table['ref'], part_number=row.get('part_number', ''),
                                                           purpose='bom', before=raw_text, after=updated_text,
                                                           reason=f'Đồng bộ BOM {recipe.part_code}'))
                        if mirror and mirror in records:
                            m_rec = records[mirror]
                            m_raw = m_rec.get('raw_text', m_rec.get('text', raw_text))
                            m_updated = re.sub(r'(?<![\d.,])' + re.escape(old_str) + r'(?![\d.,])', new_str, m_raw)
                            if m_updated == m_raw:
                                m_updated = re.sub(r'(?<![\d.,])' + re.escape(old_comma), new_comma, m_raw)
                            if m_updated != m_raw:
                                plan.operations.append(Operation(ref=mirror, action='replace_text',
                                                                 before=m_raw, after=m_updated, xyz=[],
                                                                 reason=f'Tự động đồng bộ text mirror BOM {recipe.part_code}'))
                                plan.edits.append(EditProposal(entity_ref=mirror, part_number=row.get('part_number', ''),
                                                               purpose='bom', before=m_raw, after=m_updated,
                                                               reason=f'Đồng bộ text mirror BOM {recipe.part_code}'))
                    else:
                        plan.warnings.append('Recipe chưa tự động tìm thấy kích thước trong mô tả bảng kê của '+recipe.part_code)
    from cad.multi_resize import resize_many
    operation_owners={}
    for operation in resize_many(recipes,context,solved,operation_owners):
        # The preview manifest must describe what the deterministic engine
        # actually computes, including moving holes the model left unchanged.
        plan.edits=[edit for edit in plan.edits if edit.entity_ref!=operation.ref]
        plan.edits.append(EditProposal(entity_ref=operation.ref,part_number=operation_owners[operation.ref],purpose='geometry',before=operation.before,after=operation.after,reason=operation.reason))
        previous=by_ref.get(operation.ref)
        if previous:
            if previous.action!='replace_geometry' or not near(json.loads(previous.before),json.loads(operation.before)) or not near(json.loads(previous.after),json.loads(operation.after)):
                raise ValueError('Recipe xung đột thao tác trực tiếp hoặc recipe khác: '+operation.ref)
            continue
        by_ref[operation.ref]=operation
        plan.operations.append(operation)
    owned={ref for recipe in recipes for ref in recipe.outline_refs+recipe.hole_refs+[recipe.dimension_ref]}
    plan.edits=[edit for edit in plan.edits if not (edit.entity_ref in owned and edit.entity_ref not in by_ref and edit.before==edit.after)]
    from graph.confirmed_inner_panels import synchronize as sync_inner_panels
    plan = sync_inner_panels(plan, context)
    from graph.laminar_stage_gauges import synchronize as sync_stage_gauges
    plan = sync_stage_gauges(plan, context)
    from graph.confirmed_inner_tubes import synchronize as sync_inner_tubes
    plan = sync_inner_tubes(plan, context)
    from graph.corner_wall_contacts import synchronize as sync_corner_contacts
    plan = sync_corner_contacts(plan, context)
    from graph.core_stack_views import synchronize as sync_core_views
    plan=sync_core_views(plan, context)
    from graph.curved_detail_contacts import synchronize as sync_curved_details
    return sync_curved_details(plan, context)
