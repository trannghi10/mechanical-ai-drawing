"""Compile explicit edge offsets against measured source profiles."""
import re
from bom.reader import normalized
from backend.services.rectangular_planner import compile_plan as compile_rectangular
from graph.part_graph import seed_codes


def compile_plan(context,request,clarifications=None):
    text=normalized(request+' '+' '.join(c.get('answer','') for c in clarifications or []))
    if context.get('units')!=4:return None
    if any(w in text for w in ('tat ca','toan bo','do day','vat lieu','ket cau','them lo','bo lo','di chuyen lo','doi vi tri')):return None
    if re.search(r'(?:doi|thay|tang|giam)\s+(?:duong kinh|ban kinh)',text):return None
    # Accept one explicit edge displacement; no free-form instruction is
    # silently reduced to a scaling operation.
    commands=list(re.finditer(r'(?:dua|dich)\s+canh\s+(trai|phai|tren|duoi)\s+(vao|ra)\s+(\d+(?:[.,]\d+)?)\s*mm\b',text))
    if len(commands)!=1:return None
    numeric_mm=re.findall(r'(?<![\w.])\d+(?:[.,]\d+)?\s*mm\b',text)
    if len(numeric_mm)!=1:return None
    if re.search(r'chieu (?:dai|rong|cao)\s*\d|(?:duong kinh|ban kinh)\s*\d|\blo\s*\d',text):return None
    edge,direction,delta=commands[0].groups();delta=float(delta.replace(',','.'))
    if delta<=0:return None
    opposite={'trai':'phai','phai':'trai','tren':'duoi','duoi':'tren'}[edge]
    anchors={side for side in ('trai','phai','tren','duoi','tam') if re.search(r'(?:giu|co dinh)\s*(?:nguyen\s*|co dinh\s*)?(?:dau\s*|canh\s*|mat\s*)?'+side+r'\b',text)}
    if anchors!={opposite}:return None
    codes=set(context.get('part_graph',{}).get('seed_codes',[])) or seed_codes(context,request,context.get('part_graph'))
    if len(codes)!=1:return None
    code=next(iter(codes));roots=set(context.get('root_target_ids',[]))
    values={e['scaled_measurement'] for e in context['entities'] if e['type']=='DIMENSION'
            and e.get('dimension_type')==0 and e.get('scaled_measurement',0)>0
            and (not roots or roots.intersection(e.get('source_sheet_ids',[])) or e['ref'].split('/')[0] in roots)}
    plans=[]
    for old in values:
        new=old+delta*(1 if direction=='ra' else -1)
        if new<=0:continue
        for axis in (('dài','rộng') if edge in ('trai','phai') else ('cao',)):
            command=f'Mã {code}: chiều {axis} từ {old:g} thành {new:g} mm, giữ đầu {opposite}'
            plan=compile_rectangular(context,command)
            if plan is not None:plans.append(plan)
    # A square profile or several source dimensions must not become a guess.
    unique={tuple((r.dimension_ref,r.new_measurement,r.anchor) for r in p.resize_recipes):p for p in plans}
    return next(iter(unique.values())) if len(unique)==1 else None
