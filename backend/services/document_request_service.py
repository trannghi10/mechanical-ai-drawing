"""Resolve whole-file requests from source identities, never visual guesswork."""
import re
import time
from bom.reader import normalized, requested_numbers, part_number_key
from backend.services import document_atlas_service as atlas
from backend.services.planning_control import CURRENT, progress, remaining


def prepare(document_id):
    """Join a shared inventory job; cancelling this request leaves it usable."""
    job = atlas.submit(document_id)
    progress('whole_file', 'Đang đọc toàn file trước khi tìm chi tiết cần sửa.', atlas_id=job['id'])
    while True:
        remaining()
        control = CURRENT.get()
        if control: control.check()
        state = atlas.read(document_id, job['id'])
        if state['status'] == 'ready': return atlas.report(document_id, job['id']), job['id']
        if state['status'] == 'failed': raise ValueError(state['message'])
        if control: control.cancelled.wait(min(.25, remaining()))
        else: time.sleep(.25)


def _mentions(text, value):
    return bool(re.search(r'(?<![\w.])'+re.escape(value.casefold())+r'(?![\w.])', text.casefold()))


def resolve(value, job_id, request, choice=None):
    """A target choice binds identity only; downstream geometry gates still apply."""
    base = dict(atlas_id=job_id, source_hash=value['source_hash'], edit_authorized=False,
                complete_design_understanding=False)
    parts = value['parts']
    codes = {p['part_code']: p for p in parts}
    mentioned = [p for p in parts if _mentions(request, p['part_code'])]
    # Unknown explicit codes must not fall through to a similarly named part.
    explicit = re.findall(r'(?<![\w.])\d+(?:\.\d+){2,}(?![\w.])', request)
    explicit += [c for c in re.findall(r'\bma(?:\s+(?:vat tu|chi tiet))?\s+([\w.-]+)', normalized(request))
                 if re.search(r'[\d.-]',c)]
    unknown = sorted({c for c in explicit if c.casefold() not in {k.casefold() for k in codes}})
    numbers = {part_number_key(n) for n in requested_numbers(request)}
    by_number = [p for p in parts if any(part_number_key(o['part_number']) in numbers
                                        for o in p.get('bom_occurrences', []))]
    missing_numbers=numbers-{part_number_key(o['part_number']) for p in by_number for o in p.get('bom_occurrences', [])}
    # Physical specification matching (tube stock, section profiles, dimensions)
    by_spec = []
    from backend.services.tube_planner import intent as tube_intent
    from cad.tube_stock import parse as parse_tube
    t_intent = tube_intent(request)
    req_norm = normalized(request).replace(',', '.')
    sec_match = re.search(r'\bhop\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)', req_norm)
    wanted_sec = sorted(map(float, sec_match.groups())) if sec_match else None

    from backend.services.sheet_thickness_planner import command as sheet_command, _gauge
    from bom.processes import process_tags
    s_cmd = sheet_command(request)
    if s_cmd:
        old_gauge, _ = s_cmd
        req_laser = bool(re.search(r'cat\s+la[sz]er|la[sz]er', req_norm))
        for p in parts:
            for d in p.get('descriptions', []):
                gauge = _gauge(d)
                if gauge is not None and abs(gauge - old_gauge) < 1e-5:
                    if not req_laser or any(t['id'] == 'cut_laser' for t in process_tags(d)):
                        if p not in by_spec:
                            by_spec.append(p)
        if not by_spec and not mentioned and not by_number:
            existing_gauges = set()
            for p in parts:
                for d in p.get('descriptions', []):
                    g = _gauge(d)
                    if g is not None:
                        existing_gauges.add(g)
            if existing_gauges:
                g_str = ', '.join(f"{g:g} mm" for g in sorted(existing_gauges))
                msg = f"Không tìm thấy chi tiết sắt tấm độ dày {old_gauge:g} mm trong bảng kê (BOM) nguồn. Độ dày sắt tấm hiện có trong bản vẽ: {g_str}."
            else:
                msg = f"Không tìm thấy chi tiết sắt tấm độ dày {old_gauge:g} mm trong bảng kê (BOM) nguồn của bản vẽ."
            return dict(base, status='blocked', message=msg, candidates=[])

    if t_intent:
        _, old_wall, _ = t_intent
        for p in parts:
            for d in p.get('descriptions', []):
                stock = parse_tube(d, old_wall)
                if not stock: continue
                if abs(stock.wall - old_wall) < 1e-5:
                    if wanted_sec is None or all(abs(a - b) < 1e-5 for a, b in zip(sorted(stock.section), wanted_sec)):
                        if p not in by_spec:
                            by_spec.append(p)

    if not by_spec and wanted_sec:
        for p in parts:
            for d in p.get('descriptions', []):
                d_norm = normalized(d).replace(',', '.')
                if 'hop' in d_norm:
                    dims = re.findall(r'(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)', d_norm)
                    for pair in dims:
                        pair_sorted = sorted(map(float, pair))
                        if all(abs(a - b) < 1e-5 for a, b in zip(pair_sorted, wanted_sec)):
                            if p not in by_spec:
                                by_spec.append(p)

    if not by_spec and not mentioned and not by_number:
        req_pairs = [sorted(map(float, pair)) for pair in re.findall(r'(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)', req_norm)]
        if req_pairs:
            for p in parts:
                for d in p.get('descriptions', []):
                    d_norm = normalized(d).replace(',', '.')
                    d_pairs = [sorted(map(float, pair)) for pair in re.findall(r'(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)', d_norm)]
                    if any(any(all(abs(a - b) < 1e-5 for a, b in zip(rp, dp)) for dp in d_pairs) for rp in req_pairs):
                        if p not in by_spec:
                            by_spec.append(p)
        if not by_spec:
            dim_candidates = re.findall(r'(?:tu|chieu\s+dai|dai|rong|cao|kich\s+thuoc|day)?\s*(\d+(?:\.\d+)?)\s*(?:mm\b|\s*(?:thanh|sang|len|xuong|con))', req_norm)
            if not dim_candidates:
                dim_candidates = re.findall(r'\b(\d+(?:\.\d+)?)\s*mm\b', req_norm)
            for num_str in dim_candidates:
                try: target_val = float(num_str)
                except ValueError: continue
                if target_val <= 0: continue
                for p in parts:
                    for d in p.get('descriptions', []):
                        d_norm = normalized(d).replace(',', '.')
                        d_nums = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)', d_norm) if x]
                        if any(abs(dn - target_val) < 1e-5 for dn in d_nums):
                            if p not in by_spec:
                                by_spec.append(p)

    # Multi-word descriptive phrase matching
    by_desc = []
    stop_words = {'thay', 'doi', 'thanh', 'day', 'mm', 'cho', 'file', 'toan', 'chi', 'tiet', 'bo', 'phan', 'kich', 'thuoc', 'yeu', 'cau', 'giam', 'tang', 'tu', 'xuong', 'len'}
    req_words = [w for w in req_norm.split() if len(w) >= 2 and w not in stop_words and not re.match(r'^\d+(?:\.\d+)?$', w)]
    if len(req_words) >= 2:
        for p in parts:
            for d in p.get('descriptions', []):
                d_norm = normalized(d)
                matched_words = [w for w in req_words if w in d_norm]
                if len(matched_words) >= 2 and len(matched_words) >= len(req_words) * 0.5:
                    if p not in by_desc:
                        by_desc.append(p)

    descriptions = [p for p in parts if any(len(normalized(d)) >= 4 and
                     _mentions(normalized(request), normalized(d)) for d in p.get('descriptions', []))]
    matches = mentioned or by_number or by_spec or by_desc or descriptions
    reason = ('part_code' if mentioned else
              'bom_number' if by_number else
              'specification' if by_spec else
              'source_description')
    if unknown:
        matches = []
        message = 'Không tìm thấy mã nguồn '+', '.join(unknown)+'. Kiểm tra lại mã trong hồ sơ toàn file.'
    else:
        message = 'Cần xác định chi tiết từ hồ sơ toàn file. STT có thể lặp ở các cụm khác nhau.'
    if mentioned and numbers and any(p not in by_number for p in mentioned):
        return dict(base, status='blocked', message='Mã chi tiết và STT trong yêu cầu không khớp cùng dòng BOM nguồn.', candidates=[_candidate(p) for p in mentioned])
    if missing_numbers:
        return dict(base, status='blocked', message='Không tìm thấy STT '+', '.join(sorted(missing_numbers))+' trong BOM nguồn; cần kiểm tra lại yêu cầu.', candidates=[])
    if numbers and mentioned and not numbers<={part_number_key(o['part_number']) for p in mentioned for o in p.get('bom_occurrences', [])}:
        return dict(base, status='blocked', message='Yêu cầu còn STT chưa gắn với các mã đã ghi; cần ghi rõ mã cho từng chi tiết.', candidates=[])
    if len(numbers)>1 and not mentioned:
        return dict(base, status='blocked', message='Yêu cầu nhiều STT cần ghi rõ mã từng chi tiết để giữ đủ phạm vi sửa.', candidates=[_candidate(p) for p in by_number])
    if choice:
        if choice['atlas_id'] != job_id or choice['source_hash'] != value['source_hash']:
            raise ValueError('Lựa chọn chi tiết thuộc hồ sơ cũ; cần phân tích lại toàn file.')
        selected = codes.get(choice['part_code'])
        if not selected or unknown or (matches and selected not in matches):
            raise ValueError('Chi tiết được chọn không khớp bằng chứng hoặc mã/STT trong yêu cầu.')
        if len(mentioned)>1: raise ValueError('Không dùng một lựa chọn để bỏ bớt mã trong yêu cầu nhiều chi tiết.')
        matches = [selected]; reason = 'user_source_identity'

    # Disambiguation: specifications synchronize automatically across the whole file.
    # Only ambiguous repeated numbers or vague descriptions require a user choice.
    ambiguous = False
    if not mentioned and not by_spec:
        if by_number and len(matches) > 1:
            ambiguous = len({p['part_code'] for p in matches}) > 1
        elif by_desc and len(matches) > 1:
            ambiguous = True

    if not value['traversal_complete'] or value.get('graph_error'):
        return dict(base, status='blocked', message='Chưa đọc đủ cấu trúc toàn file để tìm phạm vi sửa. Cần xử lý phần đọc còn thiếu.', candidates=[])
    if unknown:
        return dict(base, status='blocked', message=message, candidates=[])
    if not matches:
        if not dim_candidates:
            dim_candidates = re.findall(r'\b(\d{2,5}(?:\.\d+)?)\b', req_norm)
        found_target_frames = []
        if dim_candidates:
            for num_str in dim_candidates:
                try: target_val = float(num_str)
                except ValueError: continue
                if target_val <= 0: continue
                for f in value.get('frames', []):
                    f_dims = f.get('dimensions', [])
                    for d in f_dims:
                        d_val = float(d.get('val', 0) if isinstance(d, dict) else (getattr(d, 'val', None) or (d if isinstance(d, (int, float)) else 0)))
                        if abs(d_val - target_val) < 1e-2:
                            if f not in found_target_frames:
                                found_target_frames.append(f)
                            break
                    f_texts = f.get('texts', []) + [f.get('name', '')]
                    if any(num_str in str(t) for t in f_texts):
                        if f not in found_target_frames:
                            found_target_frames.append(f)
        if not found_target_frames and value.get('frames'):
            found_target_frames = list(value['frames'])[:3]
        elif not found_target_frames:
            found_target_frames = [dict(id='layout_Model', kind='sheet', layout='Model', name='Toàn bộ Model Space', bbox=[0.0, 0.0, 10000.0, 10000.0])]

        target_code = f'CAD_DIM_{dim_candidates[0]}' if dim_candidates else 'DRAWING_SCOPE'
        target_desc = f'Kích thước {dim_candidates[0]} mm trên bản vẽ' if dim_candidates else 'Phạm vi bản vẽ CAD'
        matches = [dict(part_code=target_code,
                        descriptions=[target_desc],
                        detail_sheet_ids=[found_target_frames[0]['id']],
                        frames=found_target_frames)]
        reason = 'cad_dimension' if dim_candidates else 'drawing_scope'

    if ambiguous:
        return dict(base, status='needs_target', message=message,
                    candidate_count=len(matches), candidates=[_candidate(p) for p in matches[:100]])
    from backend.services.sheet_thickness_planner import command as sheet_command
    is_batch = bool(by_spec or sheet_command(request) or t_intent or re.search(r'\b(?:tat ca|toan bo|dong loat|hang loat)\b', normalized(request)))
    max_matches = 64 if is_batch else 10
    if len(matches) > max_matches:
        return dict(base, status='blocked',
                    message=f'Yêu cầu khớp {len(matches)} mã chi tiết (vượt quá giới hạn {max_matches} mã trong một lần sửa); cần chia thành nhóm sửa có thể đối chiếu.',
                    candidates=[_candidate(p) for p in matches[:100]])
    frames = {f['id']: f for f in value['frames']}
    targets = []
    for p in matches:
        # Include detail sheet first, then all assembly sheets where the part appears,
        # ensuring the compiler has both detail geometry and verified BOM tables.
        ids = (p.get('detail_sheet_ids', []) or []) + [f['id'] for f in p.get('frames', [])]
        for sid in ids:
            if sid in frames and frames[sid]['id'] not in {t['id'] for t in targets}:
                targets.append(frames[sid])
    if not targets:
        if frames:
            targets = list(frames.values())[:3]
        elif value.get('frames'):
            targets = list(value['frames'])[:3]
        else:
            targets = [dict(id='layout_Model', kind='sheet', layout='Model', name='Toàn bộ Model Space', bbox=[0.0, 0.0, 10000.0, 10000.0])]

    chosen = {p['part_code'] for p in matches}
    assemblies = [a for a in value.get('assembly_structure', {}).get('assemblies', [])
                  if a.get('owner_code') in chosen or chosen.intersection(a.get('descendant_part_codes', []))]
    evidence = dict(base, status='ready', resolution=reason,
                    traversal_complete=value['traversal_complete'], all_placed_data_read=value['all_placed_data_read'],
                    placed_record_count=value['placed_record_count'], frame_count=len(frames), part_count=len(parts),
                    gap_count=value['gap_count'], metadata_only_types=value['metadata_only_types'], partial_types=value['partial_types'],
                    selected_parts=matches, assembly_candidates=assemblies,
                    directory=[_candidate(p) for p in parts],
                    policy='Source identity and BOM membership only. No inferred contact, confirmed datum or automatic release permission.')
    return dict(base, status='resolved', message='Đã tìm chi tiết từ hồ sơ toàn file.',
                targets=targets, part_codes=sorted(chosen), evidence=evidence)


def _candidate(part):
    return dict(part_code=part['part_code'], descriptions=part.get('descriptions', []),
                part_numbers=sorted({str(o['part_number']) for o in part.get('bom_occurrences', [])}),
                frame_ids=[f['id'] for f in part['frames']],
                definition_conflict=part.get('definition_conflict', False))


def resolve_request(document_id, request, choice=None):
    value, job_id = prepare(document_id)
    return resolve(value, job_id, request, choice)


def validate_plan_source(document_id, proposal):
    if not proposal.get('whole_document'):return
    reading=proposal['document_reading']
    value=atlas.report(document_id,reading['atlas_id'])
    if value['source_hash']!=proposal['source_hash'] or value['source_hash']!=reading['source_hash']:
        raise ValueError('Hồ sơ toàn file đã đổi; cần phân tích lại trước khi tạo bản sửa.')
