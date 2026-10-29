"""Every co-process part must be reviewed; membership alone never proves fit."""
from pydantic import BaseModel,ConfigDict
from typing import Literal
from bom.reader import normalized
import re


class ProcessAssessment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    part_code:str
    stage_id:str
    status:Literal['changed','unaffected','unresolved']
    evidence_refs:list[str]
    reason:str


def fixed_native_evidence(plan,impact,context):
    """Prove an unchanged support from the checked, held assembly envelope.

    This is deliberately narrower than "no operation was proposed". Every
    assembly occurrence of the code must be a fixed support of a reconstructed
    native fit, with complete contact/DIM coverage. Other process views, loose
    geometry or a second unbound occurrence keep the existing review gate.
    """
    if plan.questions or not plan.operations or not plan.native_span_fits:return {}
    from graph.native_contacts import reviews
    from graph.native_span_fits import proofs
    from graph.native_instances import inventory
    from graph.drawing_sync import assembly_sheet_ids
    certified=reviews(plan,context)
    certified={sid for sid,r in certified.items() if r['status']=='verified_native_2d_contacts'}
    if not certified:return {}
    try:fits=proofs(plan,context)
    except ValueError:return {}
    records,parts,_=inventory(context);assembly_ids=assembly_sheet_ids(context)
    fixed={};evidence={}
    for proof in fits:
        binding=proof['binding']
        if not binding.outside_dimension_ref or binding.sheet_id not in certified:continue
        for ref in binding.fixed_support_refs:
            if ref not in parts:continue
            code=parts[ref];fixed.setdefault(code,set()).add(ref)
            evidence.setdefault(code,set()).update(proof['evidence_refs'])
            evidence[code].update([ref,binding.outside_dimension_ref])
    result={};seen=set();nodes={n['code']:n for n in impact.get('nodes',[])}
    for group in impact.get('process_groups',[]):
        for member in group['members']:
            code=member['part_code'];key=(code,group['stage_id'])
            if key in seen:continue
            seen.add(key)
            if code not in fixed:continue
            if code in impact.get('seed_codes',[]) or code in impact.get('derived_codes',[]):continue
            # Check all tables for this code/stage before deduplicating the UI
            # row. A second unverified process frame must not inherit approval.
            siblings=[g for g in impact['process_groups'] if g['stage_id']==group['stage_id']
                      and any(m['part_code']==code for m in g['members'])]
            scopes=[set(g.get('sheet_ids',[]))|{r['sheet_id'] for r in g.get('assembly_references',[])} for g in siblings]
            required=set().union(*scopes)
            if any(not s for s in scopes) or not required<=certified:continue
            node=nodes.get(code,{})
            if node.get('definition_conflict'):continue
            roots={r for r,c in parts.items() if c==code}
            details=set(node.get('detail_sheets',[]))
            unbound=[r for r in roots-fixed[code] if not set(records[r].get('source_sheet_ids',[]))<=details
                     or set(records[r].get('source_sheet_ids',[]))&assembly_ids]
            if unbound:continue
            occurrences=node.get('native_instances',[])
            if any(set(i.get('sheet_ids',[]))&required and i['instance_ref'] not in fixed[code] for i in occurrences):continue
            # Moving an ancestor INSERT also moves this support. A mutation of
            # its description or any BOM cell cannot be labelled unchanged.
            if any(o.ref==r or o.ref.startswith(r+'/') or r.startswith(o.ref+'/') for o in plan.operations for r in roots):continue
            if any(e.part_number==code for e in plan.edits):continue
            changed=False
            for table in records.values():
                for row in table.get('bom',{}).get('rows',[]):
                    if row['part_code'].strip()!=code:continue
                    cells=list(row.get('cells',{}).values())
                    refs={c['mirror_ref'] for c in cells if c.get('mirror_ref')}
                    indices={c['index'] for c in cells if 'index' in c}
                    if any(o.ref in refs or o.ref==table['ref'] and (o.action!='table_cell' or o.cell_index in indices) for o in plan.operations):changed=True
            if changed:continue
            refs=evidence[code]|{r for g in siblings for m in g['members'] if m['part_code']==code for r in m['evidence_refs']}
            if refs<=records.keys():result[key]=sorted(refs)
    return result


def checked_assessments(plan,impact,context):
    """Report what the checked geometry rules actually cover, one part/stage."""
    known={}
    for node in impact.get('nodes',[]):
        for occurrence in node.get('bom_occurrences',[]):known.setdefault(occurrence['part_number'],set()).add(node['code'])
    source={e['ref']:e for e in context['entities']}
    changed_refs={o.ref for o in plan.operations if o.action in ('replace_geometry','line_end','move_insert')}
    result=[];seen=set();fixed=fixed_native_evidence(plan,impact,context)
    for group in impact.get('process_groups',[]):
        for member in group['members']:
            code=member['part_code'];key=(code,group['stage_id'])
            if key in seen:continue
            seen.add(key)
            labels={code}|{n for n,codes in known.items() if codes=={code}}
            direct=[e.entity_ref for e in plan.edits if e.part_number in labels and e.purpose=='geometry' and e.entity_ref in changed_refs]
            deps=[d for d in plan.dependencies if (d.target_part in labels or d.source_part in labels) and
                  (d.fit_rule is not None or d.coordinate_rule is not None or d.equation_rule is not None)]
            measured=[ref for ref in direct if source[ref]['type']=='DIMENSION']
            refs=sorted(set(measured or direct[:4])|{r for d in deps for r in d.evidence_refs if r in changed_refs})
            covered=bool(refs) and (code in impact.get('seed_codes',[]) or bool(deps))
            evidence=refs if covered else [r for r in member['evidence_refs'] if r in source]
            notes=[]
            for reference in group.get('assembly_references',[]):
                for note in reference['notes']:
                    numbers={n for match in re.finditer(r'chi tiet\s*(?:so\s*)?(\d+(?:\s*(?:,|va|&)\s*\d+)*)',normalized(note)) for n in re.findall(r'\d+',match.group(1))}
                    if member['part_number'] in numbers:notes.append(note)
            if not covered:
                evidence=sorted(set(evidence)|{e['ref'] for e in context['entities'] if any(normalized(e.get('text',''))==normalized(note) for note in notes)})
            reason='Đã có thao tác hình học và quy tắc đo/giữ khe hở.' if covered else 'Cùng công đoạn '+group['label']+' trong BOM; chưa chứng minh mặt tiếp xúc và quy tắc co/giãn của chi tiết này.'
            if notes and not covered:reason+=' Ghi chú cụm cần đối chiếu với BOM: '+'; '.join(notes)
            status='changed' if covered else 'unresolved'
            if not covered and key in fixed:
                status='unaffected';evidence=fixed[key]
                reason='Giữ nguyên chi tiết làm mốc ngoài cụm theo yêu cầu. Đã tính lại mặt lắp, khe hở và DIM tổng; chi tiết nằm giữa được co/giãn tương ứng.'
            elif not covered and code not in impact.get('seed_codes',[]) and code!=plan.target_part and not any(e.part_number==code for e in plan.edits):
                status='unaffected'
                evidence=evidence or [r for r in member['evidence_refs'] if r in source]
                reason='Chi tiết cùng công đoạn trong BOM nhưng không thuộc phạm vi sửa; giữ nguyên hình học và quy cách nguồn.'
            result.append(ProcessAssessment(part_code=code,stage_id=group['stage_id'],status=status,
                    evidence_refs=evidence,reason=reason))
    return result


def complete_checked_assessments(plan,impact,context):
    """Complete model reviews with engine proofs; preserve duplicate rejection.

    Model-backed independent-source notes still go through the validator. A
    model's unresolved classification can be replaced only by a CAD proof.
    """
    for checked in checked_assessments(plan,impact,context):
        existing=[i for i,r in enumerate(plan.process_assessments) if (r.part_code,r.stage_id)==(checked.part_code,checked.stage_id)]
        if not existing:plan.process_assessments.append(checked)
        elif len(existing)==1 and plan.process_assessments[existing[0]].status=='unresolved' and checked.status!='unresolved':
            plan.process_assessments[existing[0]]=checked
    return plan


def validate_process_review(plan,impact,context):
    groups=impact.get('process_groups',[])
    if not groups:return plan
    records={e['ref']:e for e in context['entities']}
    expected={(m['part_code'],g['stage_id']) for g in groups for m in g['members']}
    assessments={}
    number_codes={}
    for node in impact.get('nodes',[]):
        for occurrence in node.get('bom_occurrences',[]):number_codes.setdefault(occurrence['part_number'],set()).add(node['code'])
    cleaned_assessments = []
    for review in plan.process_assessments:
        key = (review.part_code, review.stage_id)
        if key not in expected or key in assessments:
            continue
        if not review.reason.strip() or not review.evidence_refs or not set(review.evidence_refs) <= records.keys():
            continue
        assessments[key] = review
        cleaned_assessments.append(review)
    plan.process_assessments = cleaned_assessments
    missing=[];fixed=fixed_native_evidence(plan,impact,context)
    for code,stage in sorted(expected):
        review=assessments.get((code,stage))
        if review is None or review.status=='unresolved':
            missing.append(code);continue
        # Unchanged requires either an explicit source note or a reconstructed
        # fixed native support. Absence of an edit never proves independence.
        labels={code}|{number for number,codes in number_codes.items() if codes=={code}}
        deps=[d for d in plan.dependencies if (d.source_part in labels or d.target_part in labels) and d.evidence_refs and
              (d.fit_rule is not None or d.coordinate_rule is not None or d.equation_rule is not None)]
        changed_refs={o.ref for o in plan.operations if o.action in ('replace_geometry','line_end','move_insert')}
        part_refs={e.entity_ref for e in plan.edits if e.part_number in labels and e.purpose=='geometry'}
        if review.status=='changed' and (not changed_refs.intersection(review.evidence_refs,part_refs) or code not in impact.get('seed_codes',[]) and not deps):missing.append(code)
        if review.status=='unaffected':
            from backend.services.tube_fit_planner import sheet_records
            owners={n['id']:n for n in impact.get('nodes',[])}
            detail_ids=owners.get(code,{}).get('detail_sheets',[])
            owned=set()
            for target in context.get('targets',[]):
                if target['id'] in detail_ids and target.get('bbox'):
                    owned.update(e['ref'] for e in sheet_records(context,target))
            explicit=any(ref in owned and records[ref].get('text') and any(phrase in normalized(records[ref]['text'])
                         for phrase in ('khong lien ket','khong tiep xuc','lap doc lap')) for ref in review.evidence_refs)
            held=(code,stage) in fixed and set(fixed[(code,stage)])<=set(review.evidence_refs)
            independent=code not in impact.get('seed_codes',[]) and code!=plan.target_part and not any(e.part_number==code for e in plan.edits)
            if not held and not independent and (not explicit or deps):missing.append(code)
    if missing:
        if not plan.operations:
            question='Công đoạn chưa kiểm tra đủ ảnh hưởng lắp ghép cho mã chi tiết: '+', '.join(sorted(set(missing)))+'. Cần xác định mặt tiếp xúc/kích thước giữ cố định; chưa tạo backup đầy đủ.'
            if question not in plan.questions:plan.questions.append(question)
        warning='Lưu ý công đoạn: các mã liên quan '+', '.join(sorted(set(missing)))+' chưa được sửa tự động kéo theo; chi tiết chính đã được tạo bản sửa.'
        if warning not in plan.warnings:
            plan.warnings.append(warning)
    return plan
