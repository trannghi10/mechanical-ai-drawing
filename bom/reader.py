"""Parse the verified six-column Vietnamese material schedule template.

Cells and source indexes remain authoritative. Unsupported headings do not
produce speculative BOM rows.
"""
import unicodedata
import re
from ezdxf.tools.text import plain_mtext


def plain(value):
    return plain_mtext(value).strip()


def normalized(value):
    value=unicodedata.normalize('NFD',plain(value).lower().replace('đ','d'))
    return ' '.join(''.join(c for c in value if unicodedata.category(c)!='Mn').split())


def part_number_key(value):
    """Compare numeric balloon 07 with local BOM 7; keep lettered IDs literal."""
    value=plain(str(value)).upper()
    return str(int(value)) if re.fullmatch(r'[0-9]+',value) else value


def requested_numbers(request):
    """Explicit local BOM labels, including lettered assemblies; never codes."""
    pattern=r'\b(?:chi tiet\s*(?:so\s*)?|ct\s*(?:so\s*)?|stt\s*|cum\s*(?:khung\s*(?:chan\s*)?)?|khung\s*(?:chan\s*)?|bo phan\s*)([a-z]\d*|\d+[a-z]?)(?![\w.])\b'
    return [m.upper() for m in re.findall(pattern,normalized(request))]


def read_bom(cells,bindings):
    by_index={c['index']:c for c in cells}
    by_binding={b['cell_index']:b for b in bindings}
    aliases={
        'number':{'stt','so tt','so thu tu'},
        'code':{'ma','ma hang','ma vat tu','ma chi tiet'},
        'description':{'ten','vat tu','ten vat tu','ten chi tiet','ten hang'},
        'material':{'vl','vat lieu','chat lieu'},
        'quantity':{'sl','so luong'},
        'notes':{'ghi chu'},
    }
    canonical={alias:key for key,values in aliases.items() for alias in values}
    starts=[c['index'] for c in cells if normalized(c['raw_text']) in aliases['number']]
    for start in starts:
        labels=[normalized(by_index.get(start+i,{}).get('raw_text','')) for i in range(6)]
        keys=[canonical.get(label) for label in labels]
        if len(set(keys))!=6 or set(keys)!=set(aliases):
            continue
        columns={key:i for i,key in enumerate(keys)}
        rows=[];placeholder_rows=[]
        for row_start in range(start+6,max(by_index)+1,6):
            if not all(row_start+i in by_index for i in range(6)):
                return {'status':'unsupported','rows':[],'warning':'Ô native thiếu; không suy diễn phần bảng bị thiếu'}
            values=[plain(by_index[row_start+i]['raw_text']) for i in range(6)]
            # Lettered subassemblies are real BOM identities, e.g. A / B.
            # A template placeholder (!!) must never become a part code.
            number=values[columns['number']];code=values[columns['code']]
            import re
            if not re.fullmatch(r'(?:\d+|[A-Za-z]\d*)',number) or not code:
                continue
            if code.strip() in ('!!','?','??','-','...'):
                placeholder_rows.append(row_start);continue
            named={key:values[i] for key,i in columns.items()}
            from bom.processes import process_tags
            rows.append({'part_number':number,'part_code':code,'description':named['description'],'processes':process_tags(named['description']),
                         'material':named['material'],'quantity_text':named['quantity'],'notes':named['notes'],
                         'cells':{key:{'index':row_start+i,'raw_text':by_index[row_start+i]['raw_text'],
                                       'mirror_ref':by_binding.get(row_start+i,{}).get('mirror_ref')}
                                  for key,i in columns.items()}})
        return {'status':'verified_template','rows':rows,'columns':6,'header_start':start,
                'column_mapping':columns,'header_labels':labels,'placeholder_rows':placeholder_rows,
                'warning':'Liên kết BOM với hình chi tiết vẫn cần bằng chứng số đánh dấu/mã chi tiết.'}
    return {'status':'unsupported','rows':[],'warning':'Chưa tìm được sáu cột STT, mã, tên/vật tư, vật liệu, số lượng và ghi chú với ánh xạ duy nhất.'}
