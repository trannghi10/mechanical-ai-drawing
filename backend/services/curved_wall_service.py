"""Compile and recheck source-owned curved-wall recipes and matching BOM edits."""
import json
import re
from cad.curved_wall import resize
from cad.geometry import near
from bom.reader import normalized


def compile_recipes(plan,context):
    if not plan.curved_wall_recipes or plan.questions:return plan
    records={e['ref']:e for e in context['entities']}
    from graph.native_instances import inventory
    _,parts,owner=inventory(context)
    owners={}
    for node in context.get('part_graph',{}).get('nodes',[]):
        for sid in node.get('detail_sheets',[]):owners.setdefault(sid,set()).add(node['code'])
    # All explicitly owned sections of the same source shell must agree about
    # thickness. Discover complete contours, not nearby arcs or matching text.
    from collections import defaultdict
    from cad.curved_profiles import contours
    from cad.curved_wall import CurvedWallResize
    groups=defaultdict(list)
    codes={r.part_code for r in plan.curved_wall_recipes}
    owned_sheets={sid for sid,values in owners.items() if len(values)==1 and values<=codes}
    for e in records.values():
        root=owner(e['ref'])
        owned=parts.get(root) in codes if root else bool(owned_sheets.intersection(e.get('source_sheet_ids',[])))
        if owned and e.get('geometry') and not e.get('review_only') and e['type'] in ('LINE','ARC'):
            groups[(e.get('layout'),e.get('coordinate_frame'))].append(e)
    source_loops=[loop for items in groups.values() for loop in contours(items) if len(loop['refs']) in (4,8)]
    known={r.inner_arc_ref:r for r in plan.curved_wall_recipes}
    for recipe in list(plan.curved_wall_recipes):
        if recipe.outer_arc_ref not in records or recipe.inner_arc_ref not in records:continue
        og=records[recipe.outer_arc_ref]['geometry'];ig=records[recipe.inner_arc_ref]['geometry'];old=og['radius']-ig['radius']
        for loop in source_loops:
            if len(loop['refs']) not in (4,8):continue
            arcs=[records[r] for r in loop['refs'] if records[r]['type']=='ARC']
            if len(arcs)!=2:continue
            inner,outer=sorted(arcs,key=lambda e:e['geometry']['radius'])
            if not near(outer['geometry']['radius'],og['radius'],1e-5) or not near(outer['geometry']['radius']-inner['geometry']['radius'],old,1e-5):continue
            if not near(outer['geometry']['center'],inner['geometry']['center'],1e-5):continue
            sids=set.intersection(*(set(records[r].get('source_sheet_ids',[])) for r in loop['refs']))
            detail=set().union(*(owners.get(s,set()) for s in sids)) if sids else set()
            native={parts[root] for r in loop['refs'] for root in [owner(r)] if root}
            if not (native=={recipe.part_code} or not native and detail=={recipe.part_code}):continue
            copied=CurvedWallResize(part_code=recipe.part_code,outer_arc_ref=outer['ref'],inner_arc_ref=inner['ref'],outline_refs=loop['refs'],new_thickness=recipe.new_thickness,evidence_refs=loop['refs'])
            previous=known.get(inner['ref'])
            if previous:
                if previous.part_code!=copied.part_code or previous.new_thickness!=copied.new_thickness or set(previous.outline_refs)!=set(copied.outline_refs):raise ValueError('Các mặt cắt cùng chi tiết có độ dày đích mâu thuẫn')
            else:plan.curved_wall_recipes.append(copied);known[inner['ref']]=copied
    by={op.ref:op for op in plan.operations};seen=set()
    from backend.services.change_service import EditProposal
    for recipe in plan.curved_wall_recipes:
        if recipe.inner_arc_ref in seen:raise ValueError('Recipe mặt cắt cong trùng')
        seen.add(recipe.inner_arc_ref)
        items=[records[r] for r in recipe.outline_refs if r in records]
        native={parts[root] for e in items for root in [owner(e['ref'])] if root}
        sids=set.intersection(*(set(e.get('source_sheet_ids',[])) for e in items)) if items else set()
        detail=set().union(*(owners.get(s,set()) for s in sids)) if sids else set()
        if len(items)!=len(recipe.outline_refs) or not (native=={recipe.part_code} or not native and detail=={recipe.part_code}):
            raise ValueError('Chưa xác định chủ sở hữu mặt cắt cong từ mã native/khung nguồn')
        choices=context.get('design_choices',{})
        if choices.get('source_hash')==context.get('source_hash'):
            for choice in choices.get('confirmed_choices',[]):
                if choice.get('key')=='curved_shell_anchor' and choice.get('part_code')==recipe.part_code:
                    radius=records[recipe.outer_arc_ref].get('geometry',{}).get('radius')
                    if choice.get('anchor')!=recipe.anchor or not near(radius,choice.get('outer_radius_mm'),1e-5):
                        raise ValueError('Mặt cắt không khớp biên ngoài đã được người dùng chốt')
        operations,report=resize(recipe,context)
        rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==recipe.part_code]
        from bom.operations import has_cell_change
        for table,row in rows:
            cell=row.get('cells',{}).get('description',{})
            old=row.get('description','')
            target=next((o.after for o in plan.operations if
                (o.action=='replace_text' and o.ref==cell.get('mirror_ref')) or
                (o.action=='table_cell' and o.ref==table['ref'] and o.cell_index==cell.get('index'))),None)
            # Nominal thickness is the first number before x in this source
            # sheet specification; do not replace an unrelated length token.
            pattern=r'(?<![\d.])(\d+(?:[.,]\d+)?)\s*[x×]'
            first=re.search(pattern,old);changed=re.search(pattern,target or '')
            if not has_cell_change(table,cell,plan.operations) or not first or not changed or abs(float(first[1].replace(',','.'))-report['before_thickness_mm'])>1e-5 or abs(float(changed[1].replace(',','.'))-recipe.new_thickness)>1e-5:
                raise ValueError('Recipe mặt cắt cong thiếu đồng bộ đúng độ dày trong BOM: '+recipe.part_code)
        for op in operations:
            previous=by.get(op.ref)
            if previous and (previous.action!=op.action or not near(json.loads(previous.before),json.loads(op.before)) or not near(json.loads(previous.after),json.loads(op.after))):
                raise ValueError('Recipe mặt cắt cong xung đột thao tác: '+op.ref)
            if not previous:plan.operations.append(op);by[op.ref]=op
            plan.edits=[e for e in plan.edits if e.entity_ref!=op.ref]
            plan.edits.append(EditProposal(entity_ref=op.ref,part_number=recipe.part_code,purpose='geometry',before=op.before,after=op.after,reason=op.reason))
    return plan


def review(plan,context):
    result=[];seen=set()
    for recipe in plan.curved_wall_recipes:
        if recipe.part_code in seen:continue
        seen.add(recipe.part_code)
        notes=[o.get('description','') for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==recipe.part_code for o in n.get('bom_occurrences',[])]
        notes.extend(r.get('description','') for e in context.get('entities',[]) for r in e.get('bom',{}).get('rows',[]) if r.get('part_code')==recipe.part_code)
        from backend.services.forming_service import authorized
        if any('uon' in normalized(note) for note in notes) or authorized(context,recipe.part_code):
            from backend.services.forming_service import review as forming_review
            try:
                result.append(forming_review(plan,context,recipe.part_code))
                continue
            except ValueError as error:
                reason=str(error)
            result.append(dict(part_code=recipe.part_code,status='unverified_developed_blank',
                outline_refs=recipe.outline_refs,reason='Mặt cắt sau uốn đã sửa nhưng chưa kiểm chứng phôi: '+reason))
    return result


def require_developed_blanks(plan,context):
    """A corrected section is not proof of a corrected manufacturing blank."""
    pending=[r for r in review(plan,context) if r['status']!='verified_source_calibrated_blank']
    if pending:raise ValueError('Chưa đủ backup hoàn chỉnh: '+pending[0]['part_code']+' — '+pending[0]['reason'])
