"""A part edit does not prove that detached assembly projections were updated."""


def assembly_sheet_ids(context):
    result=set()
    from bom.continuations import scoped_table_sheets
    scopes=scoped_table_sheets(context)
    for entity in context['entities']:
        codes={r['part_code'] for r in entity.get('bom',{}).get('rows',[])}
        if entity.get('bom',{}).get('status')=='verified_template' and len(codes)>1:
            result.update(scopes.get(entity.get('ref'),set(entity.get('source_sheet_ids',[]))))
    return result


def assembly_sync_review(plan,context):
    if not any(o.action in ('replace_geometry','line_end','move_insert') for o in plan.operations):return []
    # Native multi-part BOMs identify assembly frames; a drawing of one part
    # with a one-row material table is not classified as an assembly.
    assembly_ids=assembly_sheet_ids(context)
    from backend.services.assembly_projection_planner import TEMPLATE,validate_projections
    import json
    try:
        views=validate_projections(plan,context)
        template=json.loads(TEMPLATE.read_text(encoding='utf8')) if views else {}
        complete=set(template.get('complete_sheets',[]))
        error=None
    except ValueError as failure:
        views=[];complete=set();error=str(failure)
    result=[]
    from graph.native_instances import assembly_reviews
    native=assembly_reviews(plan,context) if hasattr(plan,'edits') else {}
    from graph.native_contacts import reviews as contact_reviews
    contacts=contact_reviews(plan,context) if hasattr(plan,'edits') else {}
    from graph.flat_contacts import reviews as flat_reviews
    flat=flat_reviews(plan,context) if hasattr(plan,'edits') else {}
    from graph.packaging_fit import review as packaging_review
    packing={sid:r for r in packaging_review(plan,context) if r['status']=='verified_native_2d_packaging' for sid in r['sheet_ids']} if hasattr(plan,'edits') else {}
    # A proven callout is visible in the coverage report; it does not certify
    # all other geometry in the containing assembly sheet.
    curved={}
    projected={}
    measured_core={}
    cuboids={}
    if hasattr(plan,'edits'):
        from graph.cuboid_projections import validate as validate_cuboids
        for proof in validate_cuboids(plan,context):
            for sid in proof['sheet_ids']:
                cuboids.setdefault(sid,[]).append(dict(sheet_id=sid,view='Hình hộp chiếu trực giao: đủ cạnh và ba kích thước BOM',status='verified_view',
                    refs=proof['target_refs'],binding_count=len(proof['target_refs']),part_code=proof['part_code'],source_dimension_ref=proof['source_dimension_ref'],
                    source_hash=proof['source_hash'],before_spec_mm=proof['before_spec_mm'],after_spec_mm=proof['after_spec_mm']))
        from graph.core_stack_views import review as core_review
        for view in core_review(plan,context):measured_core.setdefault(view['sheet_id'],[]).append(view)
        from graph.projected_profiles import bindings as projected_bindings
        for proof in projected_bindings(plan,context):
            for sid in proof['sheet_ids']:
                projected.setdefault(sid,[]).append(dict(sheet_id=sid,view='Mặt cong vẽ nghiêng: cung elip và lỗ đã đồng bộ' if proof['status']=='verified_analytic_curved_face_projection' else 'Mặt phẳng vẽ nghiêng: biên dạng và lỗ đã đồng bộ',
                    status='verified_view',refs=proof['target_refs'],binding_count=len(proof['target_refs']),
                    part_code=proof['part_code'],source_dimension_ref=proof['source_dimension_ref'],
                    source_hash=proof['source_hash'],hole_count=proof['hole_count'],face_count=proof['face_count'],
                    target_outline_ref=proof['target_outline_ref']))
        from graph.curved_detail_contacts import validate as validate_curved
        try:
            for proof in validate_curved(plan,context):
                for sid in proof['sheet_ids']:
                    refs=list(proof['bindings'].values())
                    curved.setdefault(sid,[]).append(dict(sheet_id=sid,view='Detail cong: cung trong, chân thẳng và DIM độ dày',status='verified_view',refs=refs,binding_count=len(refs)))
        except ValueError:
            pass  # No coverage is credited for an incomplete callout edit.
    for target in context.get('targets',[]):
        sid=target['id']
        if sid not in assembly_ids:continue
        if sid in packing:
            refs=[o.ref for o in plan.operations if any(e['ref']==o.ref and sid in e.get('source_sheet_ids',[]) for e in context['entities'])]
            result.append(dict(sheet_id=sid,status='verified_native_2d_packaging',reason=packing[sid]['reason'],
                verified_views=[dict(sheet_id=sid,view='Thùng và lớp đệm trong hình đóng gói native 2D',status='verified_view',refs=refs,binding_count=len(refs))]));continue
        if sid in native:
            result.append(native[sid]);continue
        if sid in contacts:
            result.append(contacts[sid]);continue
        if sid in flat:
            result.append(flat[sid]);continue
        mapped=[v for v in views if v['sheet_id']==sid]
        done=sid in complete and bool(mapped)
        mapped=mapped+curved.get(sid,[])+projected.get(sid,[])+measured_core.get(sid,[])+cuboids.get(sid,[])
        result.append(dict(sheet_id=sid,status='verified_projection_mapping' if done else 'unverified_projection_mapping',
            verified_views=mapped,reason='Đã đối chiếu hình chiếu với tọa độ CAD nguồn và thao tác sửa.' if done else error or
            'Còn hình chiếu/phối cảnh công đoạn chưa gắn đủ theo từng chi tiết; các hình đã gắn được liệt kê riêng.'))
    return result


def require_assembly_sync(plan,context):
    from graph.native_contacts import validate as validate_contacts
    if hasattr(plan,'edits'):validate_contacts(plan,context)
    unresolved=[r for r in assembly_sync_review(plan,context) if r['status'] not in ('verified_projection_mapping','verified_native_instances','verified_native_2d_contacts','verified_loose_2d_contacts','verified_native_2d_packaging')]
    if unresolved:
        extra=' '.join(sorted({r['reason'] for r in unresolved if r.get('unmeasured_native_parts')}))
        raise ValueError('Chưa thể duyệt backup hoàn chỉnh: hình cụm lắp chưa đồng bộ ở khung '+', '.join(r['sheet_id'] for r in unresolved)+'. '+(extra+' ' if extra else '')+'Có thể tải DWG xem trước để kiểm tra các bản chi tiết, BOM và bản cắt đã sửa.')
