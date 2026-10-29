"""Find sheet borders owned by INSERTs; surrounding CAD stays in layout space."""
import re

from ezdxf.math import Matrix44
from cad.catalog import text_of

TITLE_WORDS = (
    'CÔNG TY', 'TÊN SẢN PHẨM', 'KHUNG TÊN', 'KHUNGTEN', 'KHUNG_TEN', 'BẢN VẼ', 'DRAWING', 'TITLE', 'PROJECT',
    'TITLE_BLOCK', 'NGƯỜI VẼ', 'THIẾT KẾ', 'KÝ DUYỆT', 'SỐ BẢN VẼ', 'DWG NO', 'DWG. NO', 'DRAWING NO',
    'SCALE', 'DATE', 'DESIGN', 'DRAWN', 'CHECKED', 'APPROVED', 'MATERIAL', 'VẬT LIỆU', 'CHI TIẾT', 'PART'
)


def rectangles(entities):
    """Native rectangular polylines and closed, four-LINE borders."""
    lines = []
    for entity in entities:
        kind = entity.dxftype()
        points = None
        if kind == 'LWPOLYLINE' and entity.closed and len(entity) == 4:
            vertices = list(entity.get_points('xyb'))
            if not any(abs(p[2]) > 1e-9 for p in vertices):
                points = [(p[0], p[1], 0) for p in vertices]
        elif kind == 'POLYLINE' and entity.is_closed and len(entity.vertices) == 4:
            if not any(abs(v.dxf.get('bulge', 0)) > 1e-9 for v in entity.vertices):
                points = list(entity.points())
        elif kind == 'LINE':
            a, b = entity.dxf.start, entity.dxf.end
            if (a-b).magnitude > 1e-6:
                lines.append((entity.dxf.handle, a, b))
        if points is not None and rectangular(points):
            yield entity.dxf.handle, points
    # Match exact connected sides rather than inferring a border from extents.
    horizontal, vertical = {}, set()
    key = lambda v: round(float(v), 4)
    for handle, a, b in lines:
        if abs(a.y-b.y) < 1e-5:
            ends = tuple(sorted((key(a.x), key(b.x))))
            horizontal.setdefault(ends, []).append((key(a.y), handle))
        elif abs(a.x-b.x) < 1e-5:
            vertical.add((key(a.x), *sorted((key(a.y), key(b.y)))))
    for (x1, x2), rows in horizontal.items():
        for i, (y1, handle) in enumerate(rows):
            for y2, _ in rows[i+1:]:
                lo, hi = sorted((y1, y2))
                if hi-lo > 10 and (x1,lo,hi) in vertical and (x2,lo,hi) in vertical:
                    yield handle, [(x1,lo,0),(x2,lo,0),(x2,hi,0),(x1,hi,0)]


def rectangular(points):
    # Block-local borders are axis-aligned; INSERT placement may rotate/scale.
    return all(abs(points[i][0]-points[(i+1)%4][0]) < 1e-5 or
               abs(points[i][1]-points[(i+1)%4][1]) < 1e-5 for i in range(4)) and len({(round(p[0],5),round(p[1],5)) for p in points}) == 4


def placed_frames(doc, space):
    from cad.sheets import anchor, inside
    definitions = {}

    def placed_texts(entities, matrix, ancestors=()):
        for entity in entities:
            value=text_of(entity);point=anchor(entity)
            if value and point is not None:
                yield value,matrix.transform(point)
            if entity.dxftype()=='INSERT' and entity.dxf.name not in ancestors and len(ancestors)<6:
                for attribute in entity.attribs:
                    if text_of(attribute):yield text_of(attribute),matrix.transform(attribute.dxf.insert)
                block=doc.blocks.get(entity.dxf.name)
                if block is not None:
                    yield from placed_texts(block,entity.matrix44()*matrix,ancestors+(entity.dxf.name,))

    def definition(name):
        if name not in definitions:
            block = doc.blocks.get(name)
            entities = list(block) if block is not None else []
            texts = list(placed_texts(entities,Matrix44(),(name,)))
            definitions[name] = (entities, list(rectangles(entities)), texts)
        return definitions[name]

    def visit(insert, parent, path, ancestors):
        name = insert.dxf.name
        if name in ancestors or len(ancestors) >= 6:
            return
        matrix = insert.matrix44() * parent
        entities, borders, texts = definition(name)
        for handle, points in borders:
            local = [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
            content = [t for t,p in texts if p is not None and inside(p,local)]
            if not any(any(word in t.upper() for word in TITLE_WORDS) for t in content):
                continue
            corners = list(matrix.transform_vertices(points))
            box = [min(p.x for p in corners),min(p.y for p in corners),max(p.x for p in corners),max(p.y for p in corners)]
            w,h = box[2]-box[0],box[3]-box[1]
            if w < 100 or h < 50 or not .35 < w/h < 3:
                continue
            yield dict(id='frame_'+'_'.join(path+[handle]),kind='sheet',layout=space.name,
                       name='Khung '+name, bbox=box, texts=content,
                       border_ref='/'.join(path+[handle]),frame_insert=path[0],
                       detection='insert_border',read_status='needs_confirmation',
                       warning='Khung trong block; phạm vi bao gồm hình và bảng rời nằm trong khung. Cần đối chiếu preview.')
        for child in entities:
            if child.dxftype() == 'INSERT':
                yield from visit(child,matrix,path+[child.dxf.handle],ancestors+(name,))

    for insert in space.query('INSERT'):
        yield from visit(insert,Matrix44(),[insert.dxf.handle],())


IGNORE_STARTS = (
    'công ty', 'dntn', 'người lập', 'kiểm tra', 'duyệt', 'ngày', 'yckt',
    'dung sai', 'mục đích', 'tỷ lệ', 'vật liệu', 'số lượng', 'nội dung',
    'người sửa', 'ngày sửa', 'lần', 'ss400', 'f.03', 'mã tp', 'mã btp',
    'tên sản phẩm', 'tên chi tiết', 'plot', 'sheet', 'tolerance', 'khung tên',
    'bảo quản', 'cắt bằng', 'nhám sạch', 'yêu cầu', 'gò nắn', 'đảm bảo',
    'không', 'hàn', 'sơn', 'thử lỗ', 'lỗ lã', '*', '*yckt'
)


def extract_sheet_title(sheet):
    """Generate human-readable drawing title with part name, CT, code, and sheet number."""
    texts = sheet.get('texts', [])
    codes = sheet.get('source_codes', [])
    if not codes:
        codes = list(dict.fromkeys(code for text in texts for code in re.findall(r'(?<![\d.])(?:[89]\.1\.\d{5}(?:\.\d{2,3})?)(?![\d.])', text)))

    ct_str = ""
    for t in texts:
        m = re.search(r'\b(CT\s*\d+|Cụm\s*\d+|Chi\s+tiết\s*\d+)\b', t, re.I)
        if m:
            ct_str = m.group(1).title()
            break

    page_str = ""
    for t in texts:
        m = re.search(r'(?:Số\s+tờ|ST/TST)\s*:?\s*(\d+/\d+)', t, re.I)
        if m:
            page_str = f"Tờ {m.group(1)}"
            break
        if not page_str:
            m2 = re.search(r'(?<!\d/)\b(\d{2}/\d{2})\b(?!\s*/\s*\d{4})', t)
            if m2 and any(k in t.lower() for k in ('tờ', 'st', 'bản vẽ', 'sheet')):
                page_str = f"Tờ {m2.group(1)}"

    part_code = ""
    for c in codes:
        if c.startswith('8.1.') or c.startswith('9.1.'):
            part_code = c
            break
    if not part_code and codes:
        part_code = codes[0]

    part_name = ""
    kw_regex = re.compile(r'^(?:Cụm\s+[\w\s]+|Khung\s+[\w\s\d.x]+|La\s+[\w\s]+|Tấm\s+[\w\s]+|Bas\s+[\w\s]+|Chân\s+[\w\s]+|Thanh\s+[\w\s]+|Vòng\s+[\w\s]+|Giằng\s+[\w\s]+)', re.I)

    for t in texts:
        t_clean = t.strip().lstrip('*').strip()
        t_norm = t_clean.lower()
        if any(t_norm.startswith(ig) for ig in IGNORE_STARTS):
            continue
        if re.search(r'\d{2}/\d{2}/\d{4}', t_clean) or re.search(r'\b[A-Z][a-z]+\.[A-Z]{2}-\d+', t_clean):
            continue
        clean_text = re.sub(r'\(.*?\)', '', t_clean).strip()
        clean_prefix = clean_text.split('-')[0].strip()
        m_kw = kw_regex.match(clean_prefix)
        if m_kw:
            candidate = m_kw.group(0).strip()
            if 3 <= len(candidate) <= 50:
                part_name = candidate
                break

    if not part_name:
        for t in texts:
            t_clean = t.strip().lstrip('*').strip()
            t_norm = t_clean.lower()
            if any(t_norm.startswith(ig) for ig in IGNORE_STARTS):
                continue
            if re.search(r'\d{2}/\d{2}/\d{4}', t_clean) or re.search(r'\b[A-Z][a-z]+\.[A-Z]{2}-\d+', t_clean):
                continue
            if '-' in t_clean and len(t_clean) >= 5:
                prefix = t_clean.split('-')[0].strip()
                prefix = re.sub(r'\(.*?\)', '', prefix).strip()
                if 3 <= len(prefix) <= 40 and not any(prefix.lower().startswith(ig) for ig in IGNORE_STARTS):
                    part_name = prefix
                    break

    dwg_type = ""
    for t in texts:
        m = re.search(r'(Bản\s+vẽ\s+(?:Tổ\s+\w+|bảng\s+kê|chi\s+tiết))', t, re.I)
        if m:
            dwg_type = m.group(1).strip()
            break

    sid = sheet.get('id', '')
    title_main = part_name or dwg_type or sheet.get('name', '')
    if not title_main or re.match(r'^(?:tên sản phẩm|sheet|khung bản vẽ|bản vẽ)\s*:?$', title_main.strip(), re.I):
        title_main = f"Khung #{sid}"

    info_parts = []
    if ct_str:
        info_parts.append(ct_str)
    if part_code:
        info_parts.append(part_code)
    if page_str:
        info_parts.append(page_str)

    if info_parts:
        return f"{title_main} ({' · '.join(info_parts)})"
    return f"{title_main} (#{sid})"


def describe_frame(sheet):
    """Prefer source identifiers to the generic printed 'Tên sản phẩm' label."""
    texts = sheet.get('texts',[])
    codes = list(dict.fromkeys(code for text in texts for code in re.findall(r'(?<![\d.])(?:[89]\.1\.\d{5}(?:\.\d{2,3})?)(?![\d.])',text)))
    sheet['source_codes'] = codes
    rich_name = extract_sheet_title(sheet)
    if rich_name:
        sheet['name'] = rich_name
    elif codes:
        sheet['name'] = ' · '.join(codes[:3])
    sheet['category'] = 'reference' if not codes and (sheet.get('detection')=='insert_border' or any(any(word in t.upper() for word in ('TIÊU CHUẨN','KHUNG TÊN','TC ĐƯỜNG NÉT')) for t in texts)) else 'drawing'
    return sheet
