"""Expose unchanged measured height views instead of claiming a whole goal."""
import json
from cad.geometry import near
from graph.fit_constraints import measurement


def review(plan,context):
    if not plan.requires_complete_product_review:return None
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash'):return dict(status='unresolved',rows=[],reason='Thiếu quyết định thiết kế đúng nguồn.')
    d=choices.get('derived_values',{});old=d.get('frame_height_before_mm');new=d.get('frame_height_target_mm')
    if not isinstance(old,(int,float)) or not isinstance(new,(int,float)):return dict(status='unresolved',rows=[],reason='Thiếu chiều cao khung cần đối chiếu.')
    records={e['ref']:e for e in context['entities']};ops={o.ref:o for o in plan.operations};rows=[];seen=set()
    codes={n['code'] for n in context.get('part_graph',{}).get('nodes',[])}
    for feature in context.get('source_features',{}).get('features',[]):
        if feature.get('part_code') not in codes or feature.get('ownership_proof')=='unverified':continue
        for bound in feature.get('dimensions',[]):
            ref=bound['ref']
            if ref in seen or not near(bound['measurement'],old) or abs(bound['axis'][1])<1-1e-6:continue
            seen.add(ref);record=records[ref];op=ops.get(ref);actual=bound['measurement']
            if op and op.action=='replace_geometry':actual=measurement(record,json.loads(op.after))
            rows.append(dict(part_code=feature['part_code'],dimension_ref=ref,sheet_ids=feature.get('sheet_ids',[]),
                before_mm=old,target_mm=new,after_mm=actual,status='matched' if near(actual,new,1e-6) else 'unchanged_or_mismatched'))
    pending=[r for r in rows if r['status']!='matched']
    return dict(status='partial',scope='measured_frame_height_views',rows=rows,matched_count=len(rows)-len(pending),
        pending_count=len(pending),reason='Đối chiếu các hình chiều cao đo được. Những hình đã đạt không chứng minh toàn cụm, chi tiết bên trong và đóng gói đã hoàn chỉnh.')
