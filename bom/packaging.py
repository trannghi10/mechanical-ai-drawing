"""Locate packaging by explicit drawing purpose and exact product identity.

This is scope evidence, not an inferred carton size or packing orientation.
"""
import re
from bom.reader import plain,normalized


def carton_height_text(raw,before,after):
    """Change the third field of one source-bound L×W×H specification.

    The caller proves this role using its measured packing view and BOM.
    Equal width/height numbers and unrelated numbers (layers, stock, rating)
    must not be replaced together.
    """
    import math
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (before,after)):
        raise ValueError('Chiều cao quy cách thùng không hợp lệ')
    pattern=r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?![\d.,])'
    matches=list(re.finditer(pattern,raw))
    if len(matches)!=1 or not math.isclose(float(matches[0].group(3).replace(',','.')),before,abs_tol=1e-5,rel_tol=0):
        raise ValueError('Chưa xác định đúng trường chiều cao L×W×H trong quy cách thùng')
    match=matches[0]
    return raw[:match.start(3)]+f'{after:g}'+raw[match.end(3):]


def groups(parts,sheets,table_sheets):
    by={s['id']:s for s in sheets}
    products={s['id']:{plain(t) for t in s.get('texts',[]) if re.fullmatch(r'9\.\d+\.\d+',plain(t)) and plain(t) not in parts} for s in sheets}
    packing={s['id'] for s in sheets if any(re.fullmatch(r'(?:ban ve\s+)?dong goi',normalized(t)) for t in s.get('texts',[]))}
    result=[]
    for product in sorted({p for sid in packing for p in products[sid] if len(products[sid])==1}):
        ids={sid for sid in packing if products[sid]=={product}}
        product_ids={sid for sid in by if sid not in packing and products[sid]=={product}}
        def packaging_material(o):
            return bool(re.search(r'carton|honeycomb|xop|foam|dong goi',normalized(o.get('material',''))) or
                        re.search(r'^(?:thung|hop|pallet|lot goc|tam lot carton|xop tam|day dai|giang goc|goi hut am|tui)',normalized(o.get('description',''))))
        package_codes={code for code,n in parts.items() if
                       (ids.intersection(n.get('detail_sheets',[])) and any(packaging_material(o) for o in n['bom_occurrences'])) or
                       any(ids.intersection(o['sheet_ids']) and packaging_material(o) for o in n['bom_occurrences'])}
        product_codes={code for code,n in parts.items() if code not in package_codes and
                       (product_ids.intersection(n.get('detail_sheets',[])) or
                        any(product_ids.intersection(o['sheet_ids']) for o in n['bom_occurrences']))}
        result.append(dict(product_code=product,sheet_ids=sorted(ids),product_sheet_ids=sorted(product_ids),
            package_codes=sorted(package_codes),product_part_codes=sorted(product_codes),
            table_refs=sorted(ref for ref,sids in table_sheets.items() if ids.intersection(sids)),
            evidence=[dict(sheet_id=sid,purpose='Bản vẽ đóng gói',product_code=product) for sid in sorted(ids)],
            status='source_packaging_scope',
            policy='Preserve source packing orientation, individual clearances, pads, carton material and pallet. Shared product code alone does not establish a numeric resize rule.'))
    return result
