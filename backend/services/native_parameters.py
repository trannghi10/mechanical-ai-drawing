"""Bounded, source-grounded dynamic parameter plans. No generated CAD code."""
import math
import re
import unicodedata
import uuid

from backend.services import catalog_service as storage
from backend.services.aps_jobs import NativeOperation
from cad.edit_engine import digest


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
                   if unicodedata.category(c) != 'Mn').strip()


def names_for(parameter):
    name = normalized(parameter['name'])
    aliases = {'length': ['chieu dai'], 'width': ['chieu rong'], 'height': ['chieu cao'],
               'thickness': ['do day'], 'outside diameter': ['duong kinh ngoai'],
               'bore': ['duong kinh lo'], 'part number': ['ma chi tiet'],
               'visibility': ['trang thai hien thi'], 'size': ['kich co']}
    return {name, *aliases.get(name, [])}


def scalar(parameter, value):
    kind = parameter.get('value_type')
    if kind == 'String':
        return str(value)
    if kind not in ('Double', 'Int16', 'Int32'):
        raise ValueError('Kiểu tham số native chưa được hỗ trợ.')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Tham số phải là số hữu hạn.')
    if kind in ('Int16', 'Int32'):
        limit = 32768 if kind == 'Int16' else 2147483648
        if number != int(number) or not -limit <= number < limit:
            raise ValueError('Tham số trạng thái phải là số nguyên trong giới hạn CAD.')
    return number


def same(a, b):
    return a == b if isinstance(a, str) or isinstance(b, str) else math.isclose(a, b, abs_tol=1e-8, rel_tol=0)


def validate_parameter(row, operation):
    matches = [p for p in row.get('parameters', []) if p['name'] == operation.property]
    if len(matches) != 1 or matches[0].get('read_only'):
        raise ValueError('Tham số không tồn tại, trùng tên hoặc chỉ đọc.')
    parameter = matches[0]
    before, after = scalar(parameter, operation.before), scalar(parameter, operation.after)
    if isinstance(operation.before, str) != isinstance(before, str) or isinstance(operation.after, str) != isinstance(after, str):
        raise ValueError('Kiểu giá trị không khớp tham số CAD.')
    if not same(before, scalar(parameter, parameter['value'])):
        raise ValueError('Giá trị trước sửa không khớp block nguồn; đọc lại tham số.')
    allowed = [scalar(parameter, v) for v in parameter.get('allowed', [])]
    if (isinstance(after, str) and not allowed) or (allowed and not any(same(after, a) for a in allowed)):
        raise ValueError('Giá trị mới không nằm trong lựa chọn được định nghĩa trong block.')


def compile_request(context, request):
    """Return None for ordinary geometry requests; never silently drop clauses."""
    native = context.get('aps_native')
    if not native:
        return None
    candidates = [(r, p) for r in native['records'] if r['type'] == 'INSERT'
                  for p in r.get('parameters', []) if not p.get('read_only')]
    names = {name for _, p in candidates for name in names_for(p)}
    text = normalized(request)
    explicit = any(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text) for name in names)
    native_words='tham so' in text or 'block dong' in text
    if not explicit and not native_words:
        return None
    operations, questions = [], []
    clauses = [part.strip() for part in re.split(r'[;\n]+', request) if part.strip()]
    grammar=(r'(?:(?:doi|thay doi|sua|cap nhat|giam|tang)\s+)?(?:tham so\s+)?'
             r'(?:#([0-9a-f]+(?:/[0-9a-f]+){0,7})\s+)?(.+?)(?:\s+tu\s+(.+?))?\s+(?:thanh|sang|xuong|len|->|→)\s+(.+)')
    parsed=[re.fullmatch(grammar,normalized(clause)) for clause in clauses]
    # An assembly can contain a dynamic Length parameter and an unrelated
    # plate. Merely mentioning "chiều dài" must not intercept that plate's
    # BOM/STT request and replace the geometric compiler with a syntax error.
    if not native_words and not any(match and match[2] in names for match in parsed):
        return None
    selected_paths=[]
    for match in parsed:
        # Full-clause grammar ensures extra requests cannot be ignored.
        if not match:
            questions.append('Nhập từng tham số theo dạng “Length từ 50 thành 75 mm” hoặc “Part Number từ 626 thành 627”; ngăn cách các yêu cầu bằng dấu ;.')
            continue
        handle, name, old, new = match.groups()
        matches = [(r, p) for r, p in candidates if name in names_for(p)
                   and (not handle or r['ref'].lower() == handle or '/' not in handle and r['handle'].lower()==handle)]
        if len(matches) != 1:
            questions.append(f'Tham số “{name}” chưa xác định duy nhất trong phạm vi. Chọn đúng block hoặc ghi #đường_dẫn_instance trước tên tham số.')
            continue
        row, parameter = matches[0]
        selected_paths.append(bool(handle and handle==row['ref'].lower()))
        if row.get('nested_editable') is False:
            questions.append(f'Block #{row["ref"]}: nhánh cha động, XREF hoặc dữ liệu thuộc tính chưa cho phép cô lập an toàn; chưa tạo lệnh sửa nhánh dùng chung.')
            continue
        try:
            # Resolve string casing from authored choices/current value, not the normalized request.
            if parameter.get('value_type') == 'String':
                def lookup(v):
                    choices = {str(parameter['value']), *map(str, parameter.get('allowed', []))}
                    found = [c for c in choices if normalized(c) == v.strip('"\'')]
                    if len(found) != 1:
                        raise ValueError('Mã/trạng thái không khớp lựa chọn có sẵn trong block.')
                    return found[0]
                before, after = str(parameter['value']) if old is None else lookup(old), lookup(new)
            else:
                def number(v):
                    m = re.fullmatch(r'([-+]?\d+(?:[.,]\d+)?)\s*(mm)?', v)
                    if not m:
                        raise ValueError('Giá trị số phải ghi rõ, không kèm yêu cầu khác trong cùng mệnh đề.')
                    result = float(m[1].replace(',', '.'))
                    if m[2]:
                        units = native.get('drawing_units')
                        factors = {'Millimeters': 1, 'Centimeters': 10, 'Meters': 1000, 'Inches': 25.4, 'Feet': 304.8}
                        if parameter.get('units') != 'Distance' or units not in factors:
                            raise ValueError('Chưa xác minh đơn vị chiều dài CAD cho giá trị mm.')
                        result /= factors[units]
                    return result
                if old is not None and new.endswith('mm') and not old.endswith('mm'):
                    old += ' mm'
                before, after = scalar(parameter, parameter['value']) if old is None else number(old), number(new)
            operation = NativeOperation(action='set_dynamic_property', handle=row['handle'], owner_handle=row['owner_handle'],
                                        expected_type='INSERT', property=parameter['name'], before=before, after=after,
                                        instance_path=row['ref'].split('/') if '/' in row['ref'] else [])
            validate_parameter(row, operation)
            if same(before, after):
                raise ValueError('Giá trị mới trùng giá trị nguồn.')
            operations.append(operation.model_dump())
        except ValueError as error:
            questions.append(f'{parameter["name"]}: {error}')
    keys = [(tuple(op['instance_path']) or (op['handle'],), op['property']) for op in operations]
    if len(keys) != len(set(keys)):
        questions.append('Một tham số xuất hiện nhiều lần; cần một giá trị đích duy nhất.')
    deferred=native.get('deferred_parameter_record_count',native.get('deferred_record_count',0))
    if deferred and (not selected_paths or not all(selected_paths)):
        questions.append('Phạm vi có thêm tham số chưa hiển thị; chọn một block cụ thể để xác định duy nhất.')
    return dict(operations=operations if not questions else [], questions=list(dict.fromkeys(questions)))


def proposal(document_id, source, targets, context, request, clarifications=None):
    native=context.get('aps_native')
    if native and native.get('deferred_parameter_record_count'):
        requested={ref.upper() for ref in re.findall(r'#([0-9a-fA-F]+(?:/[0-9a-fA-F]+){0,7})(?![\w/])',request)}
        if requested-set(row['ref'] for row in native['records']):
            # Exact occurrence retrieval stays outside the LLM prompt budget;
            # attach rechecks every owner segment and the native readback hash.
            from backend.services.aps_context import attach
            context=attach(dict(context),source,record_refs=requested)
    compiled = compile_request(context, request)
    if compiled is None:
        return None
    native = context['aps_native']
    result = dict(id=uuid.uuid4().hex, document_id=document_id, status='proposal_only', request=request,
                  target_ids=[t['id'] for t in targets], root_target_ids=[t['id'] for t in targets], targets=targets,
                  source_hash=digest(source), provider=native['provider'], model='native-parameter-compiler',
                  clarifications=clarifications or [], execution_available=False,
                  native_execution_available=bool(compiled['operations']), complete_product_backup=False,
                  plan=dict(summary='Sửa tham số block theo cấu hình nguồn và mở lại DWG để đối chiếu.',
                            target_part='', edits=[], dependencies=[], warnings=['Các liên kết BOM/lắp ghép ngoài block chưa được chứng minh bởi thao tác tham số.'],
                            operations=[], questions=compiled['questions']),
                  native_edit=dict(inspection_id=native['inspection_id'], source_hash=native['original_source_hash'],
                                   ids=[t['id'] for t in targets], operations=compiled['operations']))
    output = storage.folder(document_id) / 'change-plans'
    output.mkdir(exist_ok=True)
    storage.write_json(output / (result['id'] + '.json'), result)
    return result
