"""Gemini REST adapter: image + CAD context, validated structured output."""
import os
import re
import httpx


class AIError(Exception):
    def __init__(self,status,message):
        super().__init__(message)
        self.status=status


def settings():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=True, encoding='utf-8-sig')
    key=os.environ.get('GEMINI_API_KEY','').strip()
    if not key or key=='replace_with_your_api_key':
        raise ValueError('Chưa cấu hình GEMINI_API_KEY hợp lệ trong .env trên server')
    model=os.environ.get('GEMINI_MODEL','gemini-2.5-flash').strip()
    if not re.fullmatch(r'gemini-[A-Za-z0-9._-]+',model):
        raise ValueError('GEMINI_MODEL không hợp lệ; dùng tên model Gemini từ Google AI Studio')
    return key,model


def quota_message(response):
    """Explain quota category without exposing upstream messages or credentials."""
    try:
        details=response.json().get('error',{}).get('details',[])
        violations=[v for detail in details for v in detail.get('violations',[])]
        ids=' '.join(str(v.get('quotaId','')) for v in violations).lower()
        metrics=' '.join(str(v.get('quotaMetric','')) for v in violations).lower()
        if 'input_token' in metrics or 'inputtokens' in ids:
            if 'perday' in ids:
                return 'Gemini đã hết hạn mức token trong ngày. Kiểm tra quota trong Google AI Studio; chưa tạo bản sửa.'
            return 'Nội dung CAD vượt hạn mức token của Gemini trong phút hiện tại. Thử lại sau hoặc dùng cấu hình có hạn mức cao hơn; chưa tạo bản sửa.'
        if 'perday' in ids:
            return 'Gemini đã hết số yêu cầu trong ngày. Kiểm tra quota trong Google AI Studio; chưa tạo bản sửa.'
        if 'perminute' in ids:
            return 'Gemini vượt số yêu cầu mỗi phút. Chờ rồi phân tích lại; chưa tạo bản sửa.'
    except (ValueError,TypeError,AttributeError):
        pass
    return 'Gemini hết hạn mức hoặc vượt giới hạn tốc độ. Kiểm tra quota trong Google AI Studio.'


def generate_plan(prompt,parts,schema):
    import time
    if os.environ.get('AI_OFFLINE','1').lower() not in ('0','false','no'):
        raise ValueError('Chế độ nội bộ đang bật; đã chặn gửi dữ liệu đến Gemini.')
    key,model=settings()
    models_to_try = [model]
    for alt in ('gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-flash-latest'):
        if alt not in models_to_try:
            models_to_try.append(alt)

    body={'systemInstruction':{'parts':[{'text':prompt}]},
          'contents':[{'role':'user','parts':parts}],
          'generationConfig':{'responseMimeType':'application/json'}}

    response = None
    for cur_model in models_to_try:
        try:
            with httpx.Client(trust_env=False,follow_redirects=False,timeout=httpx.Timeout(300,connect=20)) as client:
                resp=client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{cur_model}:generateContent',
                                 headers={'x-goog-api-key':key},json=body)
                response = resp
                if resp.status_code in (404, 429) and cur_model != models_to_try[-1]:
                    time.sleep(1)
                    continue
                model = cur_model
                break
        except httpx.TimeoutException as error:
            if cur_model == models_to_try[-1]:
                raise AIError(504,'Gemini hết thời gian chờ. Thu hẹp phạm vi hoặc thử lại.') from error
            continue
        except httpx.RequestError as error:
            if cur_model == models_to_try[-1]:
                raise AIError(502,'Không kết nối được Gemini. Kiểm tra mạng/proxy trên server.') from error
            continue
    if response.is_error:
        err_msg = ""
        try:
            err_msg = response.json().get('error', {}).get('message', '')
        except Exception:
            pass
        messages={400: f'Gemini từ chối yêu cầu ({model}): {err_msg}' if err_msg else 'Gemini từ chối khóa, model hoặc schema yêu cầu. Kiểm tra GEMINI_API_KEY và GEMINI_MODEL.',
                  401:'Khóa GEMINI_API_KEY không hợp lệ. Cập nhật .env và khởi động lại server.',
                  403:'Gemini từ chối quyền truy cập. Kiểm tra khóa, project và quyền sử dụng API.',
                  404: f'Không tìm thấy model Gemini ({model}). Kiểm tra GEMINI_MODEL và quyền truy cập.',
                  429:quota_message(response),
                  500:'Gemini gặp lỗi xử lý trên máy chủ Google. Chưa tạo bản sửa; thử lại sau.',
                  503:'Gemini đang quá tải hoặc tạm không khả dụng. Chưa tạo bản sửa; thử lại sau.'}
        status=response.status_code
        raise AIError(status if status in messages else 502,messages.get(status,'Gemini tạm thời không xử lý được yêu cầu. Thử lại sau.'))
    try:
        data=response.json()
        candidates=data.get('candidates',[])
        if not candidates or candidates[0].get('finishReason')!='STOP':
            raise ValueError('Gemini chưa trả kế hoạch đầy đủ hoặc nội dung bị chặn. Chưa tạo bản sửa.')
        text=''.join(p.get('text','') for p in candidates[0].get('content',{}).get('parts',[]) if not p.get('thought'))
        clean_text=re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.I)
        clean_text=re.sub(r'\s*```$', '', clean_text).strip()
        import json as _json
        try:
            parsed = _json.loads(clean_text)
            if isinstance(parsed, dict):
                def _norm_resize(item):
                    if not isinstance(item, dict): return None
                    dim_ref = str(item.get('dimension_ref') or item.get('ref') or '')
                    if not dim_ref: return None
                    meas = item.get('new_measurement') or item.get('after')
                    new_meas = None
                    if isinstance(meas, str):
                        meas_m = re.search(r'(\d+(?:\.\d+)?)', meas.replace(',', '.'))
                        if meas_m: new_meas = float(meas_m.group(1))
                    elif isinstance(meas, (int, float)):
                        new_meas = float(meas)
                    anc = item.get('anchor')
                    if anc not in ('first', 'second', 'center'):
                        anc = 'center' if anc in ('center', 'mid', 'middle', 'tam') else 'first'
                    outlines = [str(x) for x in item.get('outline_refs', []) if x]
                    holes = [str(x) for x in item.get('hole_refs', []) if x]
                    evidence = [str(x) for x in (item.get('evidence_refs') or outlines or [dim_ref]) if x]
                    return {
                        'part_code': str(item.get('part_code') or ''),
                        'dimension_ref': dim_ref,
                        'new_measurement': new_meas,
                        'outline_refs': outlines,
                        'hole_refs': holes,
                        'anchor': anc,
                        'evidence_refs': evidence
                    }

                clean_ops = []
                clean_resize = []
                for rec_item in parsed.get('resize_recipes', []):
                    cleaned_r = _norm_resize(rec_item)
                    if cleaned_r: clean_resize.append(cleaned_r)

                for item in parsed.get('operations', []):
                    if not isinstance(item, dict):
                        continue
                    if item.get('type') == 'resize_recipes' or ('dimension_ref' in item and ('new_measurement' in item or 'outline_refs' in item)):
                        cleaned_r = _norm_resize(item)
                        if cleaned_r: clean_resize.append(cleaned_r)
                        continue

                    ref = str(item.get('ref') or item.get('entity_ref') or item.get('table_ref') or '')
                    action = str(item.get('action') or item.get('type') or 'replace_text')
                    if action not in ('replace_text','move_text','line_end','move_insert','table_cell','replace_geometry','remove_insert','append_geometry'):
                        action = 'replace_text'

                    before_val = item.get('before', '')
                    if isinstance(before_val, dict):
                        before_str = str(before_val.get('raw_text') or before_val.get('text') or '')
                    else:
                        before_str = str(before_val) if before_val is not None else ''

                    after_val = item.get('after', '')
                    if isinstance(after_val, dict):
                        after_str = str(after_val.get('raw_text') or after_val.get('text') or '')
                    else:
                        after_str = str(after_val) if after_val is not None else ''

                    xyz_val = item.get('xyz')
                    xyz_list = [float(x) for x in xyz_val] if isinstance(xyz_val, list) and all(isinstance(x, (int, float)) for x in xyz_val) else []

                    c_idx = -1
                    if item.get('cell_index') is not None:
                        try: c_idx = int(item['cell_index'])
                        except (ValueError, TypeError): c_idx = -1

                    clean_op = {
                        'ref': ref,
                        'action': action,
                        'before': before_str,
                        'after': after_str,
                        'xyz': xyz_list,
                        'reason': str(item.get('reason') or item.get('purpose') or 'Cập nhật theo yêu cầu'),
                        'cell_index': c_idx,
                        'mirror_ref': str(item.get('mirror_ref', ''))
                    }
                    if clean_op['ref']:
                        clean_ops.append(clean_op)

                clean_edits = []
                for edit in parsed.get('edits', []):
                    if isinstance(edit, dict):
                        e_ref = str(edit.get('entity_ref') or edit.get('ref') or '')
                        p_num = str(edit.get('part_number') or edit.get('part_code') or '')
                        purp = edit.get('purpose') if edit.get('purpose') in ('geometry', 'annotation', 'bom') else 'annotation'
                        b_val = edit.get('before', '')
                        b_str = str(b_val.get('raw_text') or b_val.get('text') or '') if isinstance(b_val, dict) else str(b_val or '')
                        a_val = edit.get('after', '')
                        a_str = str(a_val.get('raw_text') or a_val.get('text') or '') if isinstance(a_val, dict) else str(a_val or '')
                        reas = str(edit.get('reason') or edit.get('purpose') or 'Cập nhật theo yêu cầu')
                        if e_ref:
                            clean_edits.append({
                                'entity_ref': e_ref,
                                'part_number': p_num,
                                'purpose': purp,
                                'before': b_str,
                                'after': a_str,
                                'reason': reas
                            })

                clean_questions = []
                clean_warnings = []
                # Keep questions non-blocking: move non-fatal technical notes into warnings
                for q in parsed.get('questions', []):
                    q_text = str(q.get('reason') or q.get('question') or q.get('message') or '') if isinstance(q, dict) else str(q or '')
                    if q_text:
                        if clean_ops or clean_resize:
                            clean_warnings.append(q_text)
                        else:
                            clean_questions.append(q_text)

                for w in parsed.get('warnings', []):
                    w_text = str(w.get('reason') or w.get('message') or '') if isinstance(w, dict) else str(w or '')
                    if w_text:
                        clean_warnings.append(w_text)

                clean_deps = []
                for dep in parsed.get('dependencies', []):
                    if isinstance(dep, dict) and dep.get('source_part') and dep.get('target_part'):
                        clean_deps.append({
                            'source_part': str(dep['source_part']),
                            'target_part': str(dep['target_part']),
                            'relationship': str(dep.get('relationship', 'assembly')),
                            'evidence_refs': [str(x) for x in dep.get('evidence_refs', []) if x],
                            'required_change': str(dep.get('required_change', '')),
                            'needs_confirmation': bool(dep.get('needs_confirmation', True)),
                            'coordinate_rule': None,
                            'fit_rule': None,
                            'equation_rule': None
                        })

                clean_gq = []
                for gq in parsed.get('geometry_queries', []):
                    if isinstance(gq, dict) and gq.get('target_id'):
                        lim = 40
                        try: lim = max(1, min(80, int(gq.get('limit', 40))))
                        except Exception: pass
                        clean_gq.append({
                            'target_id': str(gq['target_id']),
                            'region': list(gq.get('region', [])),
                            'types': list(gq.get('types', ['LINE', 'ARC'])),
                            'layer': str(gq.get('layer', '')),
                            'offset': int(gq.get('offset', 0)),
                            'limit': lim
                        })

                clean_pa = []
                for pa in parsed.get('process_assessments', []):
                    if isinstance(pa, dict) and (pa.get('part_code') or pa.get('stage_id')):
                        st = pa.get('status')
                        if st not in ('changed', 'unaffected', 'unresolved'):
                            st = 'changed'
                        clean_pa.append({
                            'part_code': str(pa.get('part_code') or ''),
                            'stage_id': str(pa.get('stage_id') or ''),
                            'status': st,
                            'evidence_refs': [str(x) for x in pa.get('evidence_refs', []) if x],
                            'reason': str(pa.get('reason') or 'Quy trình kiểm tra')
                        })

                clean_plan = {
                    'summary': str(parsed.get('summary') or parsed.get('cad_change_plan') or 'Cập nhật chiều dài theo yêu cầu'),
                    'target_part': str(parsed.get('target_part') or parsed.get('part_code') or ''),
                    'edits': clean_edits,
                    'dependencies': clean_deps,
                    'questions': clean_questions,
                    'warnings': clean_warnings,
                    'operations': clean_ops,
                    'resize_recipes': clean_resize,
                    'geometry_requests': [str(x) for x in parsed.get('geometry_requests', []) if x],
                    'context_requests': [str(x) for x in parsed.get('context_requests', []) if x],
                    'geometry_queries': clean_gq,
                    'metadata_requests': [],
                    'curved_wall_recipes': [],
                    'hole_recipes': [],
                    'cut_recipes': [],
                    'profile_cut_recipes': [],
                    'process_assessments': clean_pa,
                    'requires_complete_product_review': bool(parsed.get('requires_complete_product_review', False)),
                    'native_span_fits': []
                }
                try:
                    return schema.model_validate(clean_plan)
                except Exception:
                    clean_plan['process_assessments'] = []
                    clean_plan['dependencies'] = []
                    return schema.model_validate(clean_plan)
        except Exception:
            pass
        return schema.model_validate_json(clean_text)
    except (KeyError,TypeError) as error:
        raise ValueError('Gemini trả dữ liệu không hợp lệ. Chưa tạo bản sửa.') from error
