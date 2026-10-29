"""Compile a single source-owned curved wall request without an LLM.

Requires the exact eight-edge section and an explicit outer datum. The other
manufacturing views still undergo process/assembly/packaging review.
"""
import math
import re
from collections import defaultdict
from bom.reader import normalized
from bom.operations import cell_operations
from cad.curved_profiles import contours
from cad.curved_wall import CurvedWallResize
from cad.geometry import near


def compile_plan(context,request,clarifications=None):
    text=normalized(request+' '+' '.join(c.get('answer','') for c in clarifications or []))
    if context.get('units')!=4 or any(w in text for w in ('tat ca','toan bo','ket cau','them lo','bo lo','doi vat lieu','thay vat lieu')):return None
    matches=list(re.finditer(r'(?:do\s+)?day\s*(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|con|->|→)\s*(?:day\s*)?(\d+(?:[.,]\d+)?)',text))
    if len(matches)!=1:return None
    old,new=(float(v.replace(',','.')) for v in matches[0].groups())
    if min(old,new)<=0 or not all(math.isfinite(v) for v in (old,new)) or near(old,new):return None
    from graph.part_graph import seed_codes
    codes=set(context.get('part_graph',{}).get('seed_codes',[])) or seed_codes(context,request,context.get('part_graph'))
    if len(codes)!=1:return None
    code=next(iter(codes));choices=context.get('design_choices',{})
    confirmed=[c for c in choices.get('confirmed_choices',[]) if choices.get('source_hash')==context.get('source_hash') and
               c.get('key')=='curved_shell_anchor' and c.get('part_code')==code]
    explicit=bool(re.search(r'giu\s+(?:nguyen\s+)?bien\s+ngoai',text))
    if re.search(r'giu\s+(?:nguyen\s+)?bien\s+trong',text) or not (explicit or len(confirmed)==1 and confirmed[0].get('anchor')=='outer'):return None
    from graph.native_instances import inventory
    records,parts,owner=inventory(context);owners=defaultdict(set)
    for node in context.get('part_graph',{}).get('nodes',[]):
        for sid in node.get('detail_sheets',[]):owners[sid].add(node['code'])
    owned_sheets={sid for sid,c in owners.items() if c=={code}}
    groups=defaultdict(list)
    for e in records.values():
        native=owner(e['ref']);owned=parts.get(native)==code if native else bool(owned_sheets.intersection(e.get('source_sheet_ids',[])))
        if owned and e.get('geometry') and not e.get('review_only') and e['type'] in ('LINE','ARC'):
            groups[(e.get('layout'),e.get('coordinate_frame'))].append(e)
    candidates=[]
    for items in groups.values():
        for loop in contours(items):
            arcs=[records[r] for r in loop['refs'] if records[r]['type']=='ARC']
            if len(loop['refs']) not in (4,8) or len(arcs)!=2:continue
            inner,outer=sorted(arcs,key=lambda e:e['geometry']['radius'])
            if not near(outer['geometry']['radius']-inner['geometry']['radius'],old,1e-5) or not near(inner['geometry']['center'],outer['geometry']['center'],1e-5):continue
            if confirmed and not near(outer['geometry']['radius'],confirmed[0].get('outer_radius_mm'),1e-5):continue
            candidates.append(CurvedWallResize(part_code=code,outer_arc_ref=outer['ref'],inner_arc_ref=inner['ref'],
                outline_refs=loop['refs'],new_thickness=new,evidence_refs=loop['refs']))
    if not candidates:return None
    rows=[(t,r) for t in records.values() if t.get('bom',{}).get('status')=='verified_template'
          for r in t['bom']['rows'] if r['part_code']==code]
    if not rows:return None
    from backend.services.change_service import DrawingChangePlan,EditProposal
    plan=DrawingChangePlan(summary=f'Sửa mặt cắt cong {code}: {old:g} → {new:g} mm; giữ biên ngoài và vị trí lắp.',
        target_part=code,edits=[],dependencies=[],questions=[],warnings=[],curved_wall_recipes=candidates)
    number=re.compile(r'(?<![\d.])(\d+(?:[.,]\d+)?)(?=\s*[x×])')
    def changed(raw):
        first=number.search(raw)
        return raw[:first.start()]+f'{new:g}'+raw[first.end():] if first and near(float(first[1].replace(',','.')),old,1e-5) else None
    try:
        for table,row in rows:
            cell=row.get('cells',{}).get('description',{});after=changed(cell.get('raw_text',''))
            if after is None:return None
            for op in cell_operations(table,cell,after,records,'Đồng bộ độ dày mặt cắt cong trong BOM nguồn'):
                plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='bom',before=op.before,after=op.after,reason=op.reason))
        from bom.stage_links import physical_spec
        from cad.edit_engine import Operation
        specs={physical_spec(r['description']) for _,r in rows}
        for e in records.values():
            if e['type'] not in ('TEXT','MTEXT') or any(o.ref==e['ref'] for o in plan.operations):continue
            raw=e.get('raw_text',e.get('text',''))
            if not owned_sheets.intersection(e.get('source_sheet_ids',[])) or physical_spec(raw) not in specs or 'vat tu' in normalized(raw):continue
            after=changed(raw)
            if after is None:continue
            op=Operation(ref=e['ref'],action='replace_text',before=raw,after=after,xyz=[],reason='Đồng bộ quy cách trên bản chi tiết cong nguồn')
            plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='annotation',before=raw,after=after,reason=op.reason))
        from backend.services.parametric_service import compile_recipes
        return compile_recipes(plan,context)
    except ValueError:return None
