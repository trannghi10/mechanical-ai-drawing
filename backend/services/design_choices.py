"""Hash-bound human choices; purchasing text must not retain a false stock code."""
import json
import re
import hashlib
import threading
from bom.reader import normalized

CHOICE_LOCK=threading.RLock()


def linear_scope(context,reading):
    """A design choice belongs to this source, local BOM, part and target.

    Re-read DIM evidence on each request. Equal STT or dimensions in another
    file/part/view cannot inherit the choice.
    """
    if not reading or reading.get('measurement_mode')!='absolute' or not reading.get('source_dimensions'):return None
    if not context.get('source_hash') or reading.get('measured_before_mm') is None:return None
    dims=sorted((d['ref'],d['mm'],[round(v,8) for v in d['axis']],sorted(d['sheet_ids']),d['ownership_proof']) for d in reading['source_dimensions'])
    payload=[context['source_hash'],sorted(context.get('root_target_ids',[])),reading['bom_refs'],reading['part_code'],
        reading['part_numbers'],reading['description'],reading['dimension'],reading['measurement_mode'],
        reading['nominal_spec_mm'],reading['measured_before_mm'],reading['target_mm'],dims]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def reuse_linear(context,reading,request,clarifications):
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash') or clarifications or reading['problems']:return reading
    text=normalized(request)
    # An explicit new selection/anchor/basis is not an omitted old answer.
    if re.search(r'\b(?:chi(?!\s+tiet\b)|mot dim|dim ngang|dim dung|chenh lech|danh nghia|khong giu)\b',text):return reading
    key=linear_scope(context,reading)
    if not key:return reading
    matching=[c for c in choices.get('confirmed_choices',[]) if c.get('key')=='linear_resize' and c.get('scope_key')==key]
    if len(matching)!=1:return reading
    saved=matching[0];choice=saved.get('choice',{})
    expected=dict(target_basis='actual_dim',confirmed_axes='both',fixed_side='tam',keep_hole_center=True)
    if choice!=expected:return reading
    for field in ('target_basis','confirmed_axes','fixed_side'):
        if reading.get(field) is not None and reading[field]!=choice[field]:return reading
    result=dict(reading,**choice,reused_decision=dict(plan_id=saved['source_plan_id'],scope_key=key))
    result['delta_mm']=round(result['target_mm']-result['measured_before_mm'],8)
    return result


def remember_linear(context,folder,request,clarifications,plan_id,*,separate=False):
    """Persist explicit human inputs only after their CAD plan validated."""
    from backend.services.size_commands import interpret_linear_request
    raw=interpret_linear_request(dict(context,design_choices={}),request,clarifications)
    expected=dict(target_basis='actual_dim',confirmed_axes='both',fixed_side='tam',keep_hole_center=True)
    if not raw or raw['problems'] or any(raw.get(k)!=v for k,v in expected.items()):return None
    key=linear_scope(context,raw)
    if not key:return None
    # Size/axis memory does not change whole-file BOM/geometry ownership.
    # Keep new whole-file requests from invalidating their own atlas when
    # remembering a choice. Mechanical/cuboid confirmations stay in the
    # existing dependency-bound design-decisions file.
    file=folder/('linear-decisions-v1.json' if separate else 'design-decisions-v1.json')
    from backend.services.catalog_service import write_json
    with CHOICE_LOCK:
        choices=json.loads(file.read_text(encoding='utf8')) if file.exists() else {}
        if choices.get('source_hash')!=context['source_hash']:choices=dict(source_hash=context['source_hash'],confirmed_choices=[])
        rows=[c for c in choices.get('confirmed_choices',[]) if not(c.get('key')=='linear_resize' and c.get('scope_key')==key)]
        rows.append(dict(key='linear_resize',scope_key=key,source_plan_id=plan_id,choice=expected,
            request=request,clarifications=clarifications or []))
        choices['confirmed_choices']=rows;write_json(file,choices)
    return key


def attach(context,folder):
    file=folder/'design-decisions-v1.json'
    if file.exists():
        choices=json.loads(file.read_text(encoding='utf8'))
        if choices.get('source_hash')==context['source_hash']:
            from graph.cuboid_links import read as read_cuboids
            mapped=read_cuboids(folder,context['source_hash'])
            choices['confirmed_choices']=[v for v in choices.get('confirmed_choices',[]) if not(v.get('key')=='cuboid_projection_datum' and v.get('confirmation')=='user_confirmed_cuboid_identity_and_datum')]+mapped
            context['design_choices']=choices
    linear_file=folder/'linear-decisions-v1.json'
    if linear_file.exists():
        linear=json.loads(linear_file.read_text(encoding='utf8'))
        if linear.get('source_hash')==context.get('source_hash'):
            choices=dict(context.get('design_choices',dict(source_hash=context['source_hash'],confirmed_choices=[])))
            values=[v for v in linear.get('confirmed_choices',[]) if v.get('key')=='linear_resize']
            scopes={v.get('scope_key') for v in values}
            choices['confirmed_choices']=[v for v in choices.get('confirmed_choices',[]) if not(v.get('key')=='linear_resize' and v.get('scope_key') in scopes)]+values
            context['design_choices']=choices
    return context


def sheet_spec(text):
    number=r'(\d+(?:[.,]\d+)?)'
    match=re.search(r'sat tam\s*'+number+r'\s*[x×]\s*'+number+r'\s*[x×]\s*'+number,normalized(text))
    return tuple(float(v.replace(',','.')) for v in match.groups()) if match else None


def validate(plan,context):
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash') or not plan.operations or plan.questions:return
    for choice in choices.get('confirmed_choices',[]):
        if choice.get('key')!='sheet_stock_code' or choice.get('after_code') is not None:continue
        before_code=choice.get('before_code');target=sheet_spec(choice.get('after_description',''))
        if not before_code or not target:continue
        code=re.compile(r'(?<![\w.])'+re.escape(before_code)+r'(?![\w.])')
        def changed_sheet(op):
            old=sheet_spec(op.before);new=sheet_spec(op.after)
            return old and new and old[0]!=new[0] and new[0]==target[0]
        changed_refs={op.ref for op in plan.operations if op.action in ('replace_text','table_cell') and changed_sheet(op)}
        if not changed_refs:continue
        changed_codes={e.part_number for e in plan.edits if e.entity_ref in changed_refs}
        nodes=context.get('part_graph',{}).get('nodes',[])
        scoped={sid for n in nodes if n['code'] in changed_codes for sid in n.get('detail_sheets',[])}
        # Purchasing notes are explicit source bindings. Old revision-history
        # text and unrelated numbers do not become stock update targets.
        refs={e['ref'] for e in context['entities'] if e['type'] in ('TEXT','MTEXT') and
              code.search(e.get('raw_text',e.get('text',''))) and sheet_spec(e.get('raw_text',e.get('text',''))) and
              re.search(r'vat tu\s*:',normalized(e.get('raw_text',e.get('text','')))) and
              (not scoped or scoped.intersection(e.get('source_sheet_ids',[])))}
        ops={op.ref:op for op in plan.operations if op.action=='replace_text'}
        for ref in refs:
            op=ops.get(ref)
            if not op or code.search(op.after) or sheet_spec(op.after)!=target or 'cho cap ma' not in normalized(op.after):
                raise ValueError('Quy cách nguyên liệu mới còn thiếu ghi chờ cấp mã hoặc đang giữ mã tấm cũ: '+ref)
        for op in plan.operations:
            if op.action not in ('replace_text','table_cell') or not changed_sheet(op) or not code.search(op.before):continue
            if code.search(op.after) or 'cho cap ma' not in normalized(op.after):
                raise ValueError('Không dùng mã nguyên liệu cũ cho quy cách tấm mới: '+op.ref)
