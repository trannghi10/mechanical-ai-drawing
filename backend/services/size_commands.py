"""Resolve omitted old size only from a unique selected measured feature."""
import math
import re
import numpy as np


NUMBER=r'\d+(?:[.,]\d+)?'


def selected_bom_rows(context,code):
    """Resolve a selected detail to source BOM rows, never to a global STT.

    A detail often has no BOM inside its frame. Its graph owner and measured
    contour must agree before following exact BOM occurrence refs in the
    expanded source context. A local BOM, including a nonmatching one, always
    takes precedence over an inherited assembly table.
    """
    from bom.reader import plain
    roots=set(context.get('root_target_ids',[]))
    refs=set(context.get('root_bom_refs',[]))
    tables=[e for e in context.get('entities',[]) if e.get('bom',{}).get('status')=='verified_template']
    local=[e for e in tables if e['ref'] in refs or roots.intersection(e.get('source_sheet_ids',[]))]
    if local:
        return [(e,r) for e in local for r in e['bom']['rows'] if r['part_code']==code], 'selected_bom'
    if not roots:return [],None
    nodes=context.get('part_graph',{}).get('nodes',[])
    owners={n['code'] for n in nodes if roots.intersection(n.get('detail_sheets',[]))}
    features=[f for f in context.get('source_features',{}).get('features',[])
              if f.get('ownership_proof') not in (None,'unverified') and f.get('part_code')==code and
              (roots.intersection(f.get('sheet_ids',[])) or f.get('instance_ref') in roots)]
    if owners!={code} or not features:return [],None
    occurrences=[o for n in nodes if n['code']==code for o in n.get('bom_occurrences',[])]
    rows=[]
    for e in tables:
        for row in e['bom']['rows']:
            if row['part_code']!=code:continue
            if any(o.get('table_ref')==e['ref'] and
                   str(o.get('part_number','')).strip().upper()==str(row['part_number']).strip().upper() and
                   plain(o.get('description',''))==plain(row['description']) and
                   set(o.get('sheet_ids',[])).intersection(e.get('source_sheet_ids',[])) for o in occurrences):
                rows.append((e,row))
    if not rows and occurrences:
        fake_table={'ref':occurrences[0].get('table_ref',''),'source_sheet_ids':occurrences[0].get('sheet_ids',[])}
        rows=[(fake_table,dict(part_code=code,part_number=o.get('part_number',''),description=o.get('description',''),material=o.get('material',''))) for o in occurrences]
        return rows,'source_owned_detail_bom' if rows else None
    return rows,'source_owned_detail_bom' if rows else None


def parse_part_dimensions(description, features=None, code=None):
    from bom.reader import normalized
    desc = normalized(description)
    dims = {}
    m_len = re.search(r'\b(?:l\s*[:=]?|dai\s*[:=]?)\s*('+NUMBER+r')\b', desc)
    if m_len:
        dims['dai'] = float(m_len.group(1).replace(',', '.'))
    m = list(re.finditer(r'(?<![\d.,x×])('+NUMBER+r')\s*[x×*]\s*('+NUMBER+r')(?:[x×*]\s*('+NUMBER+r'))?(?:[x×*]\s*('+NUMBER+r'))?(?![\d.,x×])', desc))
    if m:
        nums = [float(v.replace(',', '.')) for v in m[0].groups() if v is not None]
        if 'dai' in dims:
            if len(nums) == 3:
                dims['rong'] = min(nums[0], nums[1])
                dims['cao'] = max(nums[0], nums[1])
                dims['day'] = nums[2]
            elif len(nums) == 2:
                dims['rong'] = min(nums[0], nums[1])
                dims['cao'] = max(nums[0], nums[1])
        else:
            if len(nums) == 3:
                if 'hop' in desc or 'ong' in desc:
                    dims['rong'] = min(nums[0], nums[1])
                    dims['cao'] = max(nums[0], nums[1])
                    dims['day'] = nums[2]
                else:
                    dims['day'] = nums[0]
                    dims['rong'] = nums[1]
                    dims['dai'] = nums[2]
            elif len(nums) == 4:
                dims['day'] = nums[0]
                dims['rong'] = max(nums[1], nums[2])
                dims['dai'] = nums[3]
            elif len(nums) == 2:
                dims['rong'] = min(nums[0], nums[1])
                dims['dai'] = max(nums[0], nums[1])
    if features and code:
        for f in features:
            if f.get('part_code') != code or f.get('ownership_proof') == 'unverified':
                continue
            for d in f.get('dimensions', []):
                val = round(d['measurement'], 4)
                if 'dai' in dims and abs(val - dims['dai']) < 0.1:
                    dims['dai'] = val
                elif 'rong' in dims and abs(val - dims['rong']) < 0.1:
                    dims['rong'] = val
                elif 'day' in dims and abs(val - dims['day']) < 0.1:
                    dims['day'] = val
    return dims


def interpret_linear_request(context,request,clarifications=None):
    """Read the requested value separately from CAD ownership and datums.

    BOM sizes are nominal source facts, never substituted for a different
    measured DIM. STT/code numbers are removed before reading change amounts.
    This record grants no CAD operations or default anchor.
    """
    from bom.reader import normalized,plain
    from graph.part_graph import seed_codes,requested_numbers
    text=normalized(request)
    answers=normalized(' '.join(c.get('answer','') for c in clarifications or []))
    search_text=text+' '+answers
    if context.get('units')!=4 or re.search(r'\b(?:tat ca|toan bo|tong the|ket cau|vat lieu|duong kinh|ban kinh)\b',text):return None
    graph=context.get('part_graph',{});codes=set(graph.get('seed_codes',[])) or seed_codes(context,request,graph)
    if not codes:
        roots=set(context.get('root_target_ids',[]))
        if roots:
            tid=next(iter(roots))
            sheet_parts={row['part_code'] for e in context.get('entities',[]) if (tid in e.get('source_sheet_ids',[]) or e['ref'].split('/')[0]==tid) for row in e.get('bom',{}).get('rows',[])}
            if len(sheet_parts)==1:
                codes=sheet_parts
    if len(codes)!=1:
        nodes={n['code']:n for n in graph.get('nodes',[])}
        with_sheets=[c for c in codes if c in nodes and nodes[c].get('detail_sheets')]
        if len(with_sheets)==1:
            codes=set(with_sheets)
    if len(codes)!=1:return None
    code=next(iter(codes))
    rows,bom_scope=selected_bom_rows(context,code)
    descriptions={plain(row['description']) for _,row in rows}
    if len(descriptions)!=1:return None
    description=next(iter(descriptions))
    numbers=requested_numbers(request);local_numbers={str(row['part_number']).strip().upper() for _,row in rows}
    if numbers and (len(numbers)!=1 or numbers[0] not in local_numbers):return None
    features=(context.get('source_features') or {}).get('features',[])
    part_dims=parse_part_dimensions(description,features,code)
    cleaned=re.sub(re.escape(normalized(code)),' ',text)
    cleaned=re.sub(r'\bchi tiet\s*(?:so\s*)?[a-z]?\d+\b',' ',cleaned)
    if re.search(r'\b(?:cm|inch|inches)\b|["″]',cleaned) or re.search(NUMBER+r'\s*m\b',cleaned):return None
    explicit=list(re.finditer(r'(?:\btu\s+)?('+NUMBER+r')\s*(?:mm)?\s*(?:thanh|xuong|con|len|sang|->|→)\s*('+NUMBER+r')\s*(?:mm)?\b',cleaned))
    absolute=list(re.finditer(r'\b(?:thanh|xuong|con|len|sang)\s*('+NUMBER+r')\s*(?:mm)?\b',cleaned))
    amount_numbers=re.findall(NUMBER,cleaned)
    before_literal=None
    if len(explicit)==1 and len(amount_numbers)==2:
        before_literal,value=[float(v.replace(',','.')) for v in explicit[0].groups()];mode='absolute'
    elif len(absolute)==1 and len(amount_numbers)==1:
        value=float(absolute[0].group(1).replace(',','.'));mode='absolute'
    elif not absolute and not re.search(r'\b(?:thanh|xuong|con|len|sang|tu)\b',cleaned) and len(amount_numbers)==1:
        value=float(amount_numbers[0].replace(',','.'))
        down=bool(re.search(r'\b(?:giam|ha|rut ngan|bot)\b',cleaned));up=bool(re.search(r'\b(?:tang|nang|keo dai|them)\b',cleaned))
        if down==up:return None
        mode='decrease_by' if down else 'increase_by'
    else:return None
    if value<=0 or not math.isfinite(value):return None
    kinds=[]
    if re.search(r'\b(?:chieu\s+)?dai\b',search_text):kinds.append('dai')
    if re.search(r'\b(?:chieu\s+)?rong\b|\bban\s*(?:la|rong)\b',search_text):kinds.append('rong')
    if re.search(r'\b(?:chieu\s+)?cao\b',search_text):kinds.append('cao')
    if re.search(r'\b(?:chieu\s+)?day\b|\b(?:do|be)\s*day\b',search_text):kinds.append('day')
    if not kinds and before_literal is not None:
        matches=[]
        if 'dai' in part_dims and abs(before_literal-part_dims['dai'])<1e-4:matches.append('dai')
        if 'rong' in part_dims and abs(before_literal-part_dims['rong'])<1e-4:matches.append('rong')
        if 'day' in part_dims and abs(before_literal-part_dims['day'])<1e-4:matches.append('day')
        if len(matches)==1:kinds=matches
    p_num=sorted(local_numbers)[0] if local_numbers else ''
    p_str=f"chi tiết số {p_num}" if p_num else f"chi tiết {code}"
    dim_choices=[]
    dim_descriptions=[]
    if 'dai' in part_dims:
        dim_descriptions.append(f"Chiều dài {part_dims['dai']:g} mm")
        dim_choices.append({'kind':'dai','label':f"Chiều dài ({part_dims['dai']:g} mm)",'value':'chiều dài'})
    if 'rong' in part_dims:
        dim_descriptions.append(f"Chiều rộng {part_dims['rong']:g} mm")
        dim_choices.append({'kind':'rong','label':f"Chiều rộng ({part_dims['rong']:g} mm)",'value':'chiều rộng'})
    if 'day' in part_dims:
        dim_descriptions.append(f"Độ dày {part_dims['day']:g} mm")
        dim_choices.append({'kind':'day','label':f"Độ dày ({part_dims['day']:g} mm)",'value':'độ dày'})
    if len(kinds)!=1:
        dim_info=f" Kích thước hiện có: {', '.join(dim_descriptions)}." if dim_descriptions else ""
        ask_q=f"Bạn muốn thay đổi chiều dài, chiều rộng hay độ dày của {p_str} ({code})?{dim_info}"
        return dict(version=1,source_hash=context.get('source_hash'),part_code=code,part_numbers=sorted(local_numbers),
            description=description,dimension='unknown',measurement_mode=mode,requested_value_mm=value,
            nominal_before_mm=None,measured_before_mm=None,explicit_before_mm=before_literal,target_mm=value if mode=='absolute' else None,
            delta_mm=None,target_basis=None,nominal_dim_mismatch=False,fixed_side=None,confirmed_axes=None,
            keep_hole_center=False,selected_dim_axis=None,nominal_spec_mm=[part_dims.get(k) for k in ('day','rong','dai') if k in part_dims],
            bom_refs=sorted({e['ref'] for e,_ in rows}),bom_scope=bom_scope,source_dimensions=[],
            unit='mm',unit_source='request' if re.search(r'(?<![a-z])mm\b',text) else 'CAD_INSUNITS_4',
            problems=[ask_q],dimension_choices=dim_choices,status='ambiguous_dimension',executable=False)
    kind=kinds[0];nominal=part_dims.get(kind);spec=None
    if nominal is None and kind=='cao' and 'dai' in part_dims:
        nominal=part_dims.get('dai')
    elif nominal is None and kind=='dai' and 'cao' in part_dims:
        nominal=part_dims.get('cao')
    dims_spec=list(re.finditer(r'(?<![\d.,x×])('+NUMBER+r')\s*[x×]\s*('+NUMBER+r')(?:\s*[x×]\s*('+NUMBER+r'))?\s*[x×]\s*('+NUMBER+r')(?![\d.,x×])',normalized(description)))
    if len(dims_spec)==1 and 'sat tam' in normalized(description) and kind in ('dai','rong','day','cao'):
        spec=[float(v.replace(',','.')) for v in dims_spec[0].groups() if v is not None]
        if all(v>0 and math.isfinite(v) for v in spec):
            nominal=spec[-1] if kind in ('dai','cao') else spec[1] if kind=='rong' else spec[0]
    requested_axes=set(re.findall(r'\bdim\s+(ngang|dung)\b',text))
    selected_axis=next(iter(requested_axes)) if len(requested_axes)==1 else None
    dimensions=[]
    for f in context.get('source_features',{}).get('features',[]):
        if f.get('part_code')!=code or f.get('ownership_proof')=='unverified':continue
        points=np.asarray(f.get('points',[]))
        if points.ndim!=2 or points.shape[1]!=3:continue
        for d in f.get('dimensions',[]):
            a=np.asarray(d['axis']);span=float(np.ptp(points@a));cross=float(np.ptp(points@np.array([-a[1],a[0],0.])))
            if selected_axis and abs(a[0 if selected_axis=='ngang' else 1])<1-1e-7:continue
            if kind=='dai' and span<cross-1e-5 or kind=='rong' and span>cross+1e-5 or kind=='cao' and abs(a[1])<1-1e-6:continue
            if spec and abs(d['measurement']-spec[0])<1e-6 and nominal!=spec[0]:continue
            dimensions.append(dict(ref=d['ref'],mm=round(d['measurement'],8),axis=d['axis'],sheet_ids=f['sheet_ids'],ownership_proof=f['ownership_proof']))
    expected_val=before_literal if before_literal is not None else nominal
    if expected_val is not None:
        matched_dims=[d for d in dimensions if abs(d['mm']-expected_val)<1e-5]
        if matched_dims:dimensions=matched_dims
    dimensions=list({d['ref']:d for d in dimensions}.values());values={d['mm'] for d in dimensions}
    measured=next(iter(values)) if len(values)==1 else None
    from backend.services.measured_profile_planner import HOLD_PATTERN
    from rules.dimension_rules import resolve_dimension_intent
    resolved=resolve_dimension_intent(text,answers,spec=spec,measured=measured,nominal=nominal,before_literal=before_literal)
    holds=set(re.findall(HOLD_PATTERN,text+' '+answers));holds={dict(day='duoi',chan='duoi',dinh='tren').get(h,h) for h in holds}
    if resolved.get('fixed_side'):holds.add(resolved['fixed_side'])
    policy=resolved.get('policy')
    if policy is None and nominal is not None and measured is not None and abs(nominal-measured)<1e-5:
        policy='actual_dim'  # identical source facts need no nominal/actual choice
    both=resolved.get('both')
    hole_center=resolved.get('hole_center')
    base=before_literal if before_literal is not None else measured if policy=='actual_dim' and measured is not None else nominal if nominal is not None else measured
    target=value if mode=='absolute' else None if base is None else base+value*(-1 if mode=='decrease_by' else 1)
    problems=[]
    if both and selected_axis:problems.append('Yêu cầu chọn một DIM nhưng đồng thời ghi sửa cả hai DIM; cần xác định số hướng cần sửa.')
    if re.search(r'\b(?:khong|chua)\s+(?:giu|sua|doi|giam|tang)\b',text+' '+answers) or re.search(r'\bđừng\s+(?:giữ|sửa|đổi|giảm|tăng)\b',request+' '+' '.join(c.get('answer','') for c in clarifications or []),re.I):
        problems.append('Yêu cầu có phần phủ định hướng hoặc mốc sửa; cần xác định thao tác được phép thực hiện trước khi sửa CAD.')
    if re.search(r'\bkhong\s+(?:ap dung|dung|lay|theo)\b.*\b(?:dim|thuc te|truc tiep|danh nghia)\b',text+' '+answers):
        problems.append('Cách áp dụng DIM/BOM trong yêu cầu đang bị phủ định; cần xác định cơ sở kích thước đích trước khi sửa.')
    answer_targets=re.findall(r'(?:\b(?:thanh|con|xuong)\s*(?:dung\s*)?|->\s*|→\s*)('+NUMBER+r')\s*(?:mm)?',answers)
    if mode=='absolute' and any(abs(float(v.replace(',','.'))-value)>1e-6 for v in answer_targets):
        problems.append('Kích thước đích trong câu trả lời bổ sung khác yêu cầu gốc; cần xác định một giá trị cuối trước khi sửa.')
    if target is not None and target<=0:problems.append('Kích thước đích phải lớn hơn 0 mm.')
    if before_literal is not None and measured is not None and abs(before_literal-measured)>1e-5 and (nominal is None or abs(before_literal-nominal)>1e-5):problems.append('Kích thước trước trong yêu cầu không khớp DIM hoặc quy cách nguồn.')
    if target is not None and base is not None:
        if re.search(r'\b(?:giam|ha|rut ngan)\b',text) and target>=base:problems.append('Yêu cầu ghi giảm nhưng kích thước đích không nhỏ hơn kích thước trước.')
        if re.search(r'\b(?:tang|nang|keo dai)\b',text) and target<=base:problems.append('Yêu cầu ghi tăng nhưng kích thước đích không lớn hơn kích thước trước.')
    dim_map={'dai':'length','rong':'width','cao':'height','day':'thickness'}
    reading=dict(version=1,source_hash=context.get('source_hash'),part_code=code,part_numbers=sorted(local_numbers),description=description,
        dimension=dim_map.get(kind,'length'),measurement_mode=mode,requested_value_mm=value,
        nominal_before_mm=nominal,measured_before_mm=measured,explicit_before_mm=before_literal,target_mm=target,
        delta_mm=None if target is None or base is None else round(target-base,8),target_basis=policy,
        nominal_dim_mismatch=nominal is not None and measured is not None and abs(nominal-measured)>1e-5,
        fixed_side=next(iter(holds)) if len(holds)==1 else None,confirmed_axes='both' if both else None,keep_hole_center=hole_center,
        selected_dim_axis={'ngang':'horizontal','dung':'vertical'}.get(selected_axis),
        nominal_spec_mm=spec,bom_refs=sorted({e['ref'] for e,_ in rows}),bom_scope=bom_scope,source_dimensions=dimensions,
        unit='mm',unit_source='request' if re.search(r'(?<![a-z])mm\b',text) else 'CAD_INSUNITS_4',problems=problems,
        dimension_choices=dim_choices,
        status='conflicting_request' if problems else 'understood',executable=False)
    from backend.services.design_choices import reuse_linear
    return reuse_linear(context,reading,request,clarifications)


def missing_datum_review(context,request,clarifications=None):
    """Ask for an absent datum from local BOM facts, without vision inference.

    This is a non-executable clarification, never a default left/bottom anchor
    or a claim that the requested geometry can already be edited.
    """
    from bom.reader import normalized
    reading=interpret_linear_request(context,request,clarifications)
    if not reading:return None
    if context.get('confirmed_parameter_links'):return None
    from backend.services.change_service import DrawingChangePlan
    code=reading['part_code']
    label_map={'length':'dài','width':'rộng','height':'cao','thickness':'độ dày','unknown':''}
    label=label_map.get(reading.get('dimension'),'')
    questions=list(reading.get('problems',[]))
    if not questions and reading.get('nominal_dim_mismatch') and reading['target_basis'] is None:
        questions=[f"BOM của {code} ghi chiều {label} {reading['nominal_before_mm']:g} mm, DIM đo {reading['measured_before_mm']:g} mm. Đích {reading['target_mm']:g} mm áp dụng trực tiếp cho DIM thực tế hay giữ chênh lệch giữa DIM và BOM nguồn?"]
    if not questions and reading.get('fixed_side') is None:
        if re.search(r'\b(?:giu|co dinh|moc|chot)\b',normalized(request+' '+' '.join(c.get('answer','') for c in clarifications or []))):return None
        if reading.get('dimension')=='height':
            from backend.services.height_request_service import stored_anchor
            if stored_anchor(context):return None
        questions=[f"Đã hiểu: chi tiết {code} ({reading['description']}), chiều {label} mới {reading['target_mm']:g} mm. CAD chưa xác định hướng và mốc giữ cho phép đổi này; cần chọn DIM và mặt/tâm lắp cần giữ."] if reading.get('target_mm') is not None else [f"Đã hiểu lượng thay đổi của {code}; còn thiếu DIM nguồn để tính kích thước cuối và mốc giữ."]
    if not questions:return None
    summary=f"Chưa xác định chiều cần thay đổi cho chi tiết {code}." if reading.get('dimension')=='unknown' else 'Đã đọc yêu cầu; còn dữ liệu thiết kế cần xác định trước khi sửa.'
    return DrawingChangePlan(summary=summary,target_part=code,
        edits=[],dependencies=[],operations=[],questions=questions,warnings=[])



def inferred_command(context,text):
    matches=list(re.finditer(r'(?:(giam|ha|rut ngan|tang|nang|keo dai)\s+)?chieu\s+(cao|dai|rong)\s*(?:(xuong|con|thanh|len|di)\s*)?(\d+(?:[.,]\d+)?)\s*mm\b',text))
    if len(matches)!=1:return None
    m=matches[0];verb,kind,connector,number=m.groups()
    if not verb and connector not in ('xuong','con','thanh','len'):return None
    from graph.part_graph import seed_codes
    graph=context.get('part_graph',{});codes=set(graph.get('seed_codes',[])) or seed_codes(context,text,graph)
    roots=set(context.get('root_target_ids',[]))
    from cad.measured_features import index
    features=(context.get('source_features') or index(context,graph))['features'];candidates=set()
    for f in features:
        if not f.get('part_code') or f.get('ownership_proof')=='unverified':continue
        if codes and f['part_code'] not in codes:continue
        if roots and not (roots.intersection(f.get('sheet_ids',[])) or f.get('instance_ref') in roots):continue
        p=np.asarray(f['points'])
        for d in f['dimensions']:
            a=np.asarray(d['axis']);span=float(np.ptp(p@a));cross=float(np.ptp(p@np.array([-a[1],a[0],0.])))
            if kind=='cao' and abs(a[1])<1-1e-6:continue
            if kind=='dai' and span<=cross+1e-6 or kind=='rong' and span>=cross-1e-6:continue
            old=d['measurement']
            if math.isfinite(old) and old>0:candidates.add((f['part_code'],round(old,8)))
    if len(candidates)!=1:return None
    code,old=next(iter(candidates));number=float(number.replace(',','.'))
    if connector in ('xuong','con','thanh','len'):new=number
    elif verb in ('giam','ha','rut ngan'):new=old-number
    elif verb in ('tang','nang','keo dai'):new=old+number
    else:return None
    if not math.isfinite(new) or new<=0:return None
    return ('chieu '+kind,str(old),str(new))
