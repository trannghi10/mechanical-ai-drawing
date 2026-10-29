"""Compile measured height views under hash-bound finished/frame decisions.

This does not certify assembly coverage. That remains a separate approval gate.
"""
import math
import re
from bom.reader import normalized
from cad.geometry import near


def compile_plan(context,request,clarifications=None):
    text=normalized(request)
    match=re.search(r'chieu cao\s+(?:tong the|thanh pham|san pham)\s*(?:san pham\s*)?(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|con|->|→)\s*(\d+(?:[.,]\d+)?)',text)
    if not match or context.get('units')!=4 or any(w in text for w in ('tat ca','do day','ket cau','them lo','bo lo')):return None
    old,new=[float(v.replace(',','.')) for v in match.groups()]
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash'):return None
    heights=[c for c in choices.get('confirmed_choices',[]) if c.get('key')=='overall_height']
    anchors=[c for c in choices.get('confirmed_choices',[]) if c.get('key')=='height_anchor']
    if len(heights)!=1 or len(anchors)!=1:return None
    height,anchor=heights[0],anchors[0];derived=choices.get('derived_values',{})
    from backend.services.height_request_service import overall_goal
    try:overall_goal(context,request,clarifications)
    except ValueError:return None
    before,after,stack=[derived.get(k) for k in ('frame_height_before_mm','frame_height_target_mm','top_stack_mm')]
    values=[before,after,stack,height.get('before_mm'),height.get('target_mm'),anchor.get('delta_mm')]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):return None
    if not near(new,height['target_mm']) or not any(near(old,v) for v in (before,height['before_mm'])) or \
            not near(before+stack,height['before_mm']) or not near(after+stack,new) or not near(after-before,anchor['delta_mm']):return None
    if anchor.get('anchor') not in ('bottom','top'):return None
    product=anchor.get('product_code')
    roots=set(context.get('root_target_ids',[]))
    if not product or not any(t['id'] in roots and product in t.get('texts',[]) for t in context.get('targets',[])):return None
    tables=set(context.get('root_bom_refs',[]))
    codes={r['part_code'] for e in context['entities'] if e['ref'] in tables and e.get('bom',{}).get('status')=='verified_template' for r in e['bom']['rows']}
    # A later assembly/finishing BOM can name the same product's frame under a
    # stage code absent from the first BOM page. Require its own product title
    # and verified BOM occurrence, not just an equal height elsewhere.
    product_sheets={t['id'] for t in context.get('targets',[]) if product in t.get('texts',[])}
    codes.update(n['code'] for n in context.get('part_graph',{}).get('nodes',[]) if any(
        product_sheets.intersection(o.get('sheet_ids',[])) and any(e['ref']==o.get('table_ref') and e.get('bom',{}).get('status')=='verified_template'
            for e in context['entities']) for o in n.get('bom_occurrences',[])))
    features=context.get('source_features',{}).get('features',[])
    candidate_codes={f['part_code'] for f in features if f.get('part_code') in codes and f.get('ownership_proof')!='unverified' and
        any(near(d['measurement'],before) and abs(d['axis'][1])>1-1e-6 for d in f['dimensions'])}
    from backend.services.measured_profile_planner import compile_plan as measured
    plans=[];unresolved=[]
    side='đáy' if anchor['anchor']=='bottom' else 'đỉnh'
    for code in sorted(candidate_codes):
        local=dict(context,part_graph=dict(context.get('part_graph',{}),seed_codes=[code]))
        plan=measured(local,f'Mã {code} chiều cao từ {before:g} thành {after:g} mm, giữ {side}',clarifications)
        if plan and plan.operations and not plan.questions:plans.append(plan)
        else:
            unresolved.append(code)
            # One unsupported assembly projection must not suppress the other
            # independently measured source views. Keep the full entity store
            # for collision/ownership checks; narrow only candidate features.
            for feature in features:
                if feature.get('part_code')!=code or not any(near(d['measurement'],before) and abs(d['axis'][1])>1-1e-6 for d in feature.get('dimensions',[])):continue
                scoped=dict(local,source_features=dict(context['source_features'],features=[feature]))
                partial=measured(scoped,f'Mã {code} chiều cao từ {before:g} thành {after:g} mm, giữ {side}',clarifications)
                if not partial or not partial.operations or partial.questions:continue
                records={e['ref']:e for e in context['entities']};supported=set(feature.get('sheet_ids',[]))
                omitted={e.entity_ref for e in partial.edits if e.purpose=='annotation' and not supported.intersection(records[e.entity_ref].get('source_sheet_ids',[]))}
                partial.operations=[o for o in partial.operations if o.ref not in omitted]
                partial.edits=[e for e in partial.edits if e.entity_ref not in omitted]
                plans.append(partial)
    if not plans:return None
    from backend.services.compound_planner import merge_plans
    result,audit=merge_plans(plans,context)
    if result is None:return None
    result.summary=f'Sửa các hình chiều cao đo được theo lựa chọn đã chốt: thành phẩm {new:g} mm, khung {after:g} mm, giữ {side}.'
    result.requires_complete_product_review=True
    result.warnings.append('Các hình đo được không thay thế kiểm tra toàn cụm; chỉ duyệt backup khi đủ liên kết công đoạn, hình cụm và đóng gói.')
    if unresolved:result.warnings.append('Các mã có DIM chiều cao nhưng hình học chưa sửa được đầy đủ: '+', '.join(unresolved))
    return result
