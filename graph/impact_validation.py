"""Reject executable plans that silently omit observed affected parts."""

def validate_impact(plan, impact, context=None):
    if not plan.operations or plan.questions:
        return plan
    missing=[];material_missing=[]
    from bom.stage_links import review_material_inputs
    material_reviews=review_material_inputs(plan,impact,context or {}) if impact.get('material_inputs') else []
    nodes={node['id']:node for node in impact.get('nodes',[])}
    number_codes={}
    for node in nodes.values():
        for occurrence in node.get('bom_occurrences',[]):
            number_codes.setdefault(str(occurrence['part_number']),set()).add(node['id'])
    for code in impact.get('affected_codes',[]):
        incident=[e for e in impact.get('edges',[]) if code in (e['source'],e['target'])]
        inputs=[e for e in incident if e['kind']=='manufacturing_input' and e['source']==code]
        if inputs and len(inputs)==len(incident):
            for edge in inputs:
                checks=[r for r in material_reviews if r['stock_code']==code and r['part_code']==edge['target']]
                if not checks or any(r['status']!='verified_single_blank_envelope' for r in checks):
                    material_missing.append(code);break
            continue
        if incident and all(e['kind']=='assembly_bom' for e in incident):
            continue
        labels={code}
        labels.update(number for number,codes in number_codes.items() if codes=={code})
        dependencies=[dep for dep in plan.dependencies if dep.target_part in labels or dep.source_part in labels]
        if not any(dep.evidence_refs and (dep.coordinate_rule is not None or dep.fit_rule is not None or getattr(dep,'equation_rule',None) is not None) for dep in dependencies):
            missing.append(code)
    conflicts=[code for code,node in nodes.items() if node.get('definition_conflict')]
    if missing or material_missing or conflicts:
        plan.operations=[]
        if missing:
            plan.questions.append('Cần xác định ràng buộc hình học cho các chi tiết liên quan: '+', '.join(missing)+'. Đồ thị đã tìm thấy liên kết nhưng kế hoạch chưa có quy tắc kiểm chứng.')
        if conflicts:
            plan.questions.append('Cần đối chiếu mô tả/phiên bản khác nhau của mã chi tiết: '+', '.join(conflicts)+'.')
        if material_missing:
            plan.questions.append('Cần kiểm tra nguyên liệu/phôi, quy cách và bố trí cắt: '+', '.join(sorted(set(material_missing)))+'. Đây là liên kết gia công, không phải mặt lắp giữa các chi tiết.')
        plan.warnings.append('Chưa tạo bản sửa: kiểm tra độ bao phủ liên kết chưa đạt.')
    return plan
