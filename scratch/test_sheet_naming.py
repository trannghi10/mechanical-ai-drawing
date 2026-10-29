import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

IGNORE_STARTS = (
    'công ty', 'dntn', 'người lập', 'kiểm tra', 'duyệt', 'ngày', 'yckt',
    'dung sai', 'mục đích', 'tỷ lệ', 'vật liệu', 'số lượng', 'nội dung',
    'người sửa', 'ngày sửa', 'lần', 'ss400', 'f.03', 'mã tp', 'mã btp',
    'tên sản phẩm', 'tên chi tiết', 'plot', 'sheet', 'tolerance', 'khung tên',
    'bảo quản', 'cắt bằng', 'nhám sạch', 'yêu cầu', 'gò nắn', 'đảm bảo',
    'không', 'hàn', 'sơn', 'thử lỗ', 'lỗ lã'
)

def format_sheet_name(sheet):
    texts = sheet.get('texts', [])
    codes = sheet.get('source_codes', [])
    if not codes:
        codes = list(dict.fromkeys(code for text in texts for code in re.findall(r'(?<![\d.])(?:[89]\.1\.\d{5}(?:\.\d{2,3})?)(?![\d.])', text)))

    # 1. CT or Cụm (e.g. CT1, Cụm 01, Cụm 6)
    ct_str = ""
    for t in texts:
        m = re.search(r'\b(CT\s*\d+|Cụm\s*\d+|Chi\s+tiết\s*\d+)\b', t, re.I)
        if m:
            ct_str = m.group(1).title()
            break

    # 2. Sheet Page: "Số tờ : 01/02" or "ST/TST : 01/02"
    page_str = ""
    for t in texts:
        m = re.search(r'(?:Số\s+tờ|ST/TST)\s*:?\s*(\d+/\d+)', t, re.I)
        if m:
            page_str = f"Tờ {m.group(1)}"
            break
        if not page_str:
            m2 = re.search(r'(?<!\d/)\b(\d{2}/\d{2})\b(?!\s*/\s*\d{4})', t)
            # Only if text also has 'tờ' or 'sheet' or 'bản vẽ'
            if m2 and any(k in t.lower() for k in ('tờ', 'st', 'bản vẽ', 'sheet')):
                page_str = f"Tờ {m2.group(1)}"

    # 3. Part Code
    part_code = ""
    for c in codes:
        if c.startswith('8.1.') or c.startswith('9.1.'):
            part_code = c
            break
    if not part_code and codes:
        part_code = codes[0]

    # 4. Part / Component Name
    part_name = ""
    # Check for mechanical keywords first (e.g. Khung, Cụm, La, Tấm, Bas, Chân, Thanh...)
    kw_regex = re.compile(r'^(?:Cụm\s+[\w\s]+|Khung\s+[\w\s\d.x]+|La\s+[\w\s]+|Tấm\s+[\w\s]+|Bas\s+[\w\s]+|Chân\s+[\w\s]+|Thanh\s+[\w\s]+|Vòng\s+[\w\s]+|Giằng\s+[\w\s]+)', re.I)
    
    for t in texts:
        t_clean = t.strip()
        t_norm = t_clean.lower()
        if any(t_norm.startswith(ig) for ig in IGNORE_STARTS):
            continue
        # Filter out revision notes like "Huy.LQ-3199", "Ng N H Anh", dates
        if re.search(r'\d{2}/\d{2}/\d{4}', t_clean) or re.search(r'\b[A-Z][a-z]+\.[A-Z]{2}-\d+', t_clean):
            continue
        # If it matches mechanical keyword pattern
        clean_text = re.sub(r'\(.*?\)', '', t_clean).strip()
        clean_prefix = clean_text.split('-')[0].strip()
        m_kw = kw_regex.match(clean_prefix)
        if m_kw:
            candidate = m_kw.group(0).strip()
            # Clean trailing dims if needed or keep short
            if 3 <= len(candidate) <= 50:
                part_name = candidate
                break

    # If still not found, check any hyphenated text "Name - Spec"
    if not part_name:
        for t in texts:
            t_clean = t.strip()
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

    # 5. Drawing Type
    dwg_type = ""
    for t in texts:
        m = re.search(r'(Bản\s+vẽ\s+(?:Tổ\s+\w+|bảng\s+kê|chi\s+tiết))', t, re.I)
        if m:
            dwg_type = m.group(1).strip()
            break

    sid = sheet.get('id', '')
    
    # Build title components
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

p = ROOT / 'storage' / 'documents' / '34ee84f35e1a44fb81c56044397a0fff' / 'sheets-v3.json'
data = json.load(open(p, encoding='utf-8'))
targets = ['3AAABC', '3AC12B', '3B3987', '3ACF75', '3D337A', '3A0786', '3A2D0F', '3A3E3F', '3A3EDF', '3A499E', '3A4A2B', '3A5A28', '3A5ACA', '3A76E8', '3A7775', '3A8114', '3A81A0', '3A94EF', '3A9588', '3AA019', '3AA0A6', '3B8A74', '3B8B05', '3B8B98', '3B8C84', '3BB719', '3BB7AA', '3BD614', '3BD6A5', '3C41A7', '3E1D2E']
p2 = ROOT / 'storage' / 'documents' / '5a1955b75d4345b69d19d38b7cfaf75c' / 'sheets-v3.json'
if p2.exists():
    data2 = json.load(open(p2, encoding='utf-8'))
    print("\n=== SECOND DOC SHEETS ===")
    for s in data2.get('items', [])[:10]:
        print(f"#{s['id']} -> {format_sheet_name(s)}")
