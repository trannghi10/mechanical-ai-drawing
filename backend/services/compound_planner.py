"""Atomic checked planning: every clause succeeds, or none is executable."""
import copy
import re


def clauses(request):
    text=re.sub(r'^(?:yêu cầu(?:\s+thay đổi)?|yeu cau(?:\s+thay doi)?)\s*:\s*', '', request, flags=re.I)
    # A decimal dot or a dot in a material code is never a list marker.
    text=re.sub(r'(?<![\w.])\d+[.)]\s+(?=\S)', '\n', text)
    def split_command(match):
        from bom.reader import normalized
        before=normalized(text[:match.start()]);after=normalized(text[match.end():])
        if re.search(r'\bgiu\s+(?:nguyen\s+)?kich thuoc ngoai$',before) and re.match(r'chieu dai(?=\s*(?:[;,.]|$))',after):
            return match.group(0)
        return '\n'
    text=re.sub(r'\s+(?:và|va)\s+(?=(?:chi tiết|chi tiet|đổi|doi|thay|chiều|chieu|tất cả|tat ca)\b)', split_command, text, flags=re.I)
    # A comma starts another command only before an explicit command phrase.
    # Decimal commas, anchors and material-code punctuation stay untouched.
    text=re.sub(r',\s*(?=(?:tất cả|tat ca|toàn bộ|toan bo|thay đổi|thay doi|đổi|doi|chiều\s+(?:cao|dài|rộng)|chieu\s+(?:cao|dai|rong))\b)', '\n', text, flags=re.I)
    pieces=[p.strip(' .\t\r():') for p in re.split(r'[;\n]+',text) if p.strip(' .\t\r():')]
    result=[]
    for piece in pieces:
        # Preserve anchors, hole-preservation and BOM/packaging instructions with their command.
        qualifier=re.match(r'^(?:(?:sửa|sua)\s+(?:cả\s+hai|ca\s+hai|hai)\s+(?:chiều|chieu|dim|kích\s+thước|kich\s+thuoc)|(?:áp\s+dụng|ap\s+dung)\b)',piece,re.I)
        if result and (qualifier or re.match(r'^(?:giữ|giu|đồng bộ|dong bo|kiểm tra|kiem tra|tính lại|tinh lai)\b',piece,re.I)):
            result[-1]+='; '+piece
        elif re.match(r'^(?:yêu cầu(?:\s+thay đổi)?|yeu cau(?:\s+thay doi)?)$',piece,re.I):
            continue
        else:result.append(piece)
    return result or [request]


def checked_one(context,request,clarifications=None):
    from backend.services.height_request_service import review as height_review
    height=height_review(context,request,clarifications)
    invalid=[item['reason'] for item in height if item['status']=='unresolved']
    if invalid:
        from backend.services.change_service import DrawingChangePlan
        return DrawingChangePlan(summary='Chưa xác định đúng chiều cao và mốc giữ của yêu cầu.',target_part='',
            edits=[],dependencies=[],questions=invalid,warnings=[]),'checked_height_request'
    from backend.services.sheet_thickness_planner import compile_plan as sheets
    from backend.services.tube_planner import compile_plan as tube
    from backend.services.rectangular_planner import compile_plan as rectangle
    from backend.services.measured_profile_planner import compile_plan as measured
    from backend.services.relative_planner import compile_plan as relative
    from backend.services.curved_wall_planner import compile_plan as curved_wall
    from backend.services.overall_height_planner import compile_plan as overall_height
    from backend.services.hole_planner import compile_plan as holes
    from backend.services.plate_size_planner import compile_plan as plate_size
    from backend.services.assembly_planner import compile_plan as assembly
    for name,compiler in [('checked_assembly_resize',assembly),('checked_plate_size',plate_size),('checked_sheet_thickness',sheets),('checked_overall_height_views',overall_height),('checked_hole_resize',holes),('checked_tube_wall',tube),('checked_rectangular_resize',rectangle),
                          ('checked_curved_wall',curved_wall),
                          ('checked_measured_profile_resize',measured),('checked_relative_rectangular_resize',relative)]:
        plan=compiler(context,request,clarifications)
        if plan is not None:return plan,name
    from backend.services.size_commands import missing_datum_review
    review=missing_datum_review(context,request,clarifications)
    if review is not None:return review,'checked_missing_resize_datum'
    return None,None


def request_seeds(context,request,graph=None):
    from graph.part_graph import seed_codes
    return set().union(*(seed_codes(context,command,graph) for command in clauses(request)))


def operation_key(op):
    return op.ref,op.cell_index if op.action=='table_cell' else -1


def same_operation(a,b):
    # Reason text is explanatory; geometry and before/after values are binding.
    from graph.native_instances import equivalent_operation
    return a.action==b.action and a.cell_index==b.cell_index and a.mirror_ref==b.mirror_ref and equivalent_operation(a,b)


def merge_numeric_text(a,b):
    """Compose distinct source numeric fields, preserving all literal CAD text."""
    if a.action not in ('replace_text','table_cell') or a.action!=b.action or a.before!=b.before or a.mirror_ref!=b.mirror_ref:return None
    pattern=r'(\d+(?:[.,]\d+)?)'
    source=re.split(pattern,a.before);first=re.split(pattern,a.after);second=re.split(pattern,b.after)
    if len(source)!=len(first) or len(source)!=len(second) or source[::2]!=first[::2] or source[::2]!=second[::2]:return None
    final=list(source)
    for i in range(1,len(source),2):
        x,y=first[i],second[i]
        if x!=source[i] and y!=source[i] and x!=y:return None
        final[i]=x if x!=source[i] else y
    return a.model_copy(update=dict(after=''.join(final),reason=a.reason+'; '+b.reason))


def compile_bundle(context,request,clarifications=None):
    commands=clauses(request)
    if len(commands)<2:return None,None
    from graph.part_graph import seed_codes,impact_graph
    from backend.services.change_service import DrawingChangePlan
    plans=[];review=[]
    for command in commands:
        local=copy.deepcopy(context)
        if local.get('part_graph'):
            roots=set(context.get('root_target_ids',[]))
            root_tables=set(context.get('root_bom_refs',[]))
            root_context=dict(local,entities=[e for e in local['entities'] if not roots or
                roots.intersection(e.get('source_sheet_ids',[])) or e['ref'].split('/')[0] in roots or
                e['ref'] in root_tables and e.get('bom',{}).get('status')=='verified_template'])
            codes=seed_codes(root_context,command,local['part_graph'])
            local['part_graph']=impact_graph(local['part_graph'],codes)
        plan,planner=checked_one(local,command,clarifications)
        complete=plan is not None and bool(plan.operations) and not plan.questions
        review.append(dict(clause=command,status='checked' if complete else 'unresolved',planner=planner,
                           operation_refs=sorted({o.ref for o in plan.operations}) if complete else []))
        if complete:plans.append(plan)
    audit=dict(status='complete' if len(plans)==len(commands) else 'incomplete',clauses=review,
               policy='Tất cả mệnh đề phải được thực thi và kiểm chứng cùng nhau; không lấy riêng ý đầu tiên.')
    if len(plans)!=len(commands):return None,audit
    return merge_plans(plans,context,audit)


def merge_plans(plans,context,audit=None):
    """Compose checked clauses from one source snapshot and recompile geometry."""
    from backend.services.change_service import DrawingChangePlan
    audit=dict(audit or dict(status='complete',clauses=[]))
    merged=DrawingChangePlan(summary='; '.join(p.summary for p in plans),target_part=', '.join(dict.fromkeys(p.target_part for p in plans)),
                             edits=[],dependencies=[],questions=[],warnings=[])
    ops={};edits={};recipes={}
    for plan in plans:
        merged.requires_complete_product_review=merged.requires_complete_product_review or plan.requires_complete_product_review
        generated=set()
        if plan.resize_recipes or plan.curved_wall_recipes or plan.hole_recipes:
            from backend.services.parametric_service import compile_recipes
            probe=plan.model_copy(deep=True)
            probe.operations=[o for o in probe.operations if o.action!='replace_geometry']
            try:probe=compile_recipes(probe,context)
            except ValueError:
                audit.update(status='conflict',reason='Không tái lập được hình học mệnh đề từ snapshot nguồn')
                return None,audit
            original={operation_key(o):o for o in plan.operations}
            for op in probe.operations:
                if op.action=='replace_geometry' and operation_key(op) in original and same_operation(op,original[operation_key(op)]):generated.add(operation_key(op))
        for op in plan.operations:
            key=operation_key(op)
            if key in generated:continue
            if key in ops and not same_operation(ops[key],op):
                combined=merge_numeric_text(ops[key],op)
                if combined is None:
                    audit.update(status='conflict',reason='Các mệnh đề sửa khác nhau cùng đối tượng/ô CAD: '+op.ref)
                    return None,audit
                op=combined
            ops[key]=op
        for edit in plan.edits:
            key=(edit.entity_ref,edit.purpose,edit.before,edit.after)
            edits[key]=edit
        for recipe in plan.resize_recipes:
            key=recipe.dimension_ref
            if key in recipes and recipes[key]!=recipe:
                audit.update(status='conflict',reason='Các mệnh đề có recipe kích thước mâu thuẫn: '+key)
                return None,audit
            recipes[key]=recipe
        merged.dependencies.extend(plan.dependencies)
        merged.warnings.extend(plan.warnings)
        merged.cut_recipes.extend(plan.cut_recipes)
        merged.profile_cut_recipes.extend(plan.profile_cut_recipes)
        merged.curved_wall_recipes.extend(plan.curved_wall_recipes)
        merged.hole_recipes.extend(plan.hole_recipes)
    merged.operations=list(ops.values());merged.edits=list(edits.values());merged.resize_recipes=list(recipes.values())
    merged.warnings=list(dict.fromkeys(merged.warnings))
    for edit in merged.edits:
        matches=[o for o in merged.operations if o.ref==edit.entity_ref and o.before==edit.before and o.action in ('replace_text','table_cell')]
        if len(matches)==1:edit.after=matches[0].after
    merged.edits=list({(e.entity_ref,e.purpose,e.before,e.after):e for e in merged.edits}.values())
    try:
        from backend.services.parametric_service import compile_recipes
        merged=compile_recipes(merged,context)
    except ValueError as error:
        audit.update(status='conflict',reason=str(error));return None,audit
    return merged,audit


def verify_bundle(plan,context,request,clarifications=None):
    """Recompile from source so an omitted clause cannot pass a saved-plan gate."""
    expected,audit=compile_bundle(context,request,clarifications)
    if audit is None:return None
    if expected is None:
        missing=[r['clause'] for r in audit['clauses'] if r['status']!='checked']
        raise ValueError(audit.get('reason') or 'Chưa kiểm chứng đủ yêu cầu: '+'; '.join(missing))
    by={operation_key(op):op for op in plan.operations}
    for op in expected.operations:
        actual=by.get(operation_key(op))
        if actual is None or not same_operation(op,actual):
            raise ValueError('Bản sửa thiếu hoặc sai thao tác của một mệnh đề: '+op.ref)
    plan.requires_complete_product_review=plan.requires_complete_product_review or expected.requires_complete_product_review
    return audit
