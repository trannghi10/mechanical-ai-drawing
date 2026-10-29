"""Source-bound companion plate and cut-grid updates for a measured tube fit."""
import copy
import json
import math
import re
from collections import defaultdict
from bom.reader import normalized,plain
from cad.edit_engine import Operation
from cad.geometry import near
from cad.mating_plate import widen
from cad.rectangular_nesting import CutPacking,pack,geometry_box
from graph.fit_constraints import FitRule


def sheet_records(context,target):
    b=target['bbox'];roots=set();result=[]
    for e in context['entities']:
        if '/' in e['ref']:continue
        if e.get('source_sheet_ids') is not None:
            if target['id'] in e['source_sheet_ids']:result.append(e);roots.add(e['ref'])
            continue
        g=e.get('geometry',{});p=g.get('start') or g.get('center') or g.get('defpoint') or e.get('position') or e.get('text_placement',{}).get('anchor')
        if p and b[0]<=p[0]<=b[2] and b[1]<=p[1]<=b[3]:
            result.append(e);roots.add(e['ref'])
    result.extend(e for e in context['entities'] if '/' in e['ref'] and e['ref'].split('/')[0] in roots)
    return result


def has_fit_note(target,notes):
    source={plain(t) for t in target.get('texts',[])}
    return any(plain(n.get('text','')) in source for n in notes)


def compile_fit(context,tube_code,tube_records,tube_ops,old_t,new_t,notes,companion_code=None):
    from backend.services.change_service import DependencyProposal
    entities=context['entities'];by={e['ref']:e for e in entities}
    tables=[e for e in entities if e.get('bom',{}).get('rows')]
    rows=[(t,r) for t in tables for r in t['bom']['rows']]
    candidates=[]
    for target in context['targets']:
        if not target.get('bbox') or not has_fit_note(target,notes):continue
        for table,row in rows:
            if row['part_code'] not in target.get('texts',[]) or row['part_code']==tube_code:continue
            if companion_code and row['part_code']!=companion_code:continue
            size=re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)',row['description'].replace(',','.'))
            if not size:continue
            material,width,length=map(float,size.groups());records=sheet_records(context,target)
            for dimension in records:
                if dimension['type']!='DIMENSION' or abs(dimension.get('scaled_measurement',0)-width)>1e-6:continue
                try:ops,outline,holes=widen(records,dimension,width+2*(old_t-new_t))
                except ValueError:continue
                candidates.append((table,row,size,target,records,dimension,ops,outline,holes))
    # Repeated BOM occurrences are mirrors of a part, not separate profiles.
    unique={}
    for candidate in candidates:
        key=(candidate[1]['part_code'],candidate[3]['id'],candidate[5]['ref'])
        if key in unique and normalized(unique[key][1]['description'])!=normalized(candidate[1]['description']):
            raise ValueError('Các dòng BOM của bas chưa thống nhất quy cách')
        unique.setdefault(key,candidate)
    candidates=list(unique.values())
    if len(candidates)!=1:raise ValueError('Chưa chứng minh duy nhất bas/mặt tiếp xúc theo ghi chú vừa khít và BOM')
    table,row,size,detail,detail_records,width_dim,plate_ops,outline,holes=candidates[0]
    code=row['part_code'];width=float(size.group(2));length=float(size.group(3));new_width=width+2*(old_t-new_t)
    changed_wall=[by[o.ref] for o in tube_ops if o.action=='replace_geometry' and by[o.ref]['type']=='DIMENSION']
    wall_angle=changed_wall[0]['geometry']['angle'] if len(changed_wall)==1 else None
    outer=[e for e in tube_records if e['type']=='DIMENSION' and e.get('geometry') and e.get('dimension_type',0)==0 and near(e['geometry']['angle'],wall_angle) and 0<=e.get('scaled_measurement',0)-2*old_t-width<=1]
    if len(changed_wall)!=1 or len(outer)!=1:raise ValueError('Chưa xác định duy nhất ba kích thước đo khe hở lắp')
    cut_sheets=[t for t in context['targets'] if code in t.get('texts',[]) and 'to phoi' in normalized(' '.join(t.get('texts',[]))) and t['id']!=detail['id']]
    if len(cut_sheets)!=1:raise ValueError('Thiếu hoặc có nhiều bản cắt bas; chưa tự sửa bố trí cắt')
    cut=cut_sheets[0];cut_records=sheet_records(context,cut);bbox=cut['bbox']
    groups=defaultdict(list)
    cut_children=defaultdict(list)
    for e in cut_records:
        if '/' in e['ref']:cut_children[e['ref'].rsplit('/',1)[0]].append(e)
    for root in cut_records:
        if root['type']!='INSERT' or '/' in root['ref'] or root.get('rotation') not in (0,90) or not near(root.get('scale'),[1,1,1]):continue
        try:b=geometry_box(cut_children[root['ref']],root['ref'])
        except ValueError:continue
        expected=[width,length] if root['rotation']==0 else [length,width]
        if near([b[2]-b[0],b[3]-b[1]],expected,1e-5) and bbox[0]<=b[0]<=b[2]<=bbox[2] and bbox[1]<=b[1]<=b[3]<=bbox[3]:
            children=cut_children[root['ref']]
            lines=[e for e in children if e['type']=='LINE']
            lo=min(e['geometry'][k][0] for e in lines for k in ('start','end'))
            top=max(e['geometry'][k][1] for e in lines for k in ('start','end'))
            signature=tuple(sorted(tuple(round(v,5) for v in (e['geometry']['center'][0]-lo,top-e['geometry']['center'][1],e['geometry']['radius'])) for e in children if e['type']=='CIRCLE'))
            groups[signature].append(root['ref'])
    if len(groups)!=1:raise ValueError('Bản cắt chưa có duy nhất template bas theo bề rộng/chiều dài nguồn')
    instance_refs=next(iter(groups.values()))
    plate_lo=min(e['geometry'][k][0] for e in outline for k in ('start','end'))
    plate_top=max(e['geometry'][k][1] for e in outline for k in ('start','end'))
    drilling=sorted([h['geometry']['center'][0]-plate_lo,plate_top-h['geometry']['center'][1],h['geometry']['radius']] for h in holes)
    for root in instance_refs:
        children=cut_children[root]
        lines=[e for e in children if e['type']=='LINE']
        lo=min(e['geometry'][k][0] for e in lines for k in ('start','end'))
        top=max(e['geometry'][k][1] for e in lines for k in ('start','end'))
        cut_drilling=sorted([e['geometry']['center'][0]-lo,top-e['geometry']['center'][1],e['geometry']['radius']] for e in children if e['type']=='CIRCLE')
        if not near(drilling,cut_drilling,1e-5):raise ValueError('Pattern lỗ bản cắt không khớp bas chi tiết theo nguồn')
    count_texts=[e for e in cut_records if re.search(r'\b'+str(len(instance_refs))+r'\s*pcs',e.get('text',''))]
    if len(count_texts)!=1:raise ValueError('Số lượng trên bản cắt không khớp số instance thực tế')
    stock_dims=[e for e in cut_records if e['type']=='DIMENSION' and e.get('geometry') and e.get('scaled_measurement',0)>length]
    recipes=[]
    for first in stock_dims:
        for second in stock_dims:
            if first['ref']>=second['ref']:continue
            recipe=CutPacking(part_code=code,sheet_id=cut['id'],stock_dimension_refs=[first['ref'],second['ref']],instance_refs=instance_refs,count_text_ref=count_texts[0]['ref'],old_width=width,new_width=new_width,length=length)
            try:ops,boxes,gap=pack(recipe,context)
            except ValueError:continue
            recipes.append((recipe,ops,boxes,gap))
    if len(recipes)!=1:raise ValueError('Chưa kiểm chứng duy nhất đường bao tấm và bố trí bas mới')
    recipe,cut_ops,boxes,gap=recipes[0];operations=plate_ops+cut_ops
    def text(e,before,after,reason):
        if before!=after:operations.append(Operation(ref=e['ref'],action='replace_text',before=before,after=after,xyz=[],reason=reason))
    old_spec=size.group(0);new_spec=f'{float(size.group(1)):g}x{new_width:g}x{length:g}'
    cell=row['cells']['description'];mirror=cell['mirror_ref']
    if mirror not in by:raise ValueError('Thiếu mirror native BOM của bas')
    before=cell['raw_text'];after=before.replace(old_spec,new_spec)
    if before==after:raise ValueError('Quy cách bas không khớp nguyên văn ô bảng')
    if cell.get('storage')!='text':
        operations.append(Operation(ref=table['ref'],action='table_cell',cell_index=cell['index'],mirror_ref=mirror,before=before,after=after,xyz=[],reason='Đồng bộ quy cách bas lắp vừa trong BOM'))
    raw=by[mirror].get('raw_text',by[mirror]['text']);text(by[mirror],raw,raw.replace(old_spec,new_spec),'Đồng bộ hình bảng kê bas')
    for other_table,other_row in rows:
        if other_row['part_code']!=code:continue
        other_cell=other_row['cells']['description']
        if other_table['ref']==table['ref'] and other_cell['index']==cell['index']:continue
        if normalized(other_row['description'])!=normalized(row['description']):raise ValueError('Quy cách bas giữa các BOM chưa thống nhất')
        other_mirror=other_cell.get('mirror_ref')
        if other_mirror not in by:raise ValueError('Thiếu binding một bảng kê bas liên quan')
        before=other_cell['raw_text'];after=before.replace(old_spec,new_spec)
        if before==after:raise ValueError('Quy cách bas tại bảng kê liên quan không khớp nguyên văn')
        if other_cell.get('storage')!='text':
            operations.append(Operation(ref=other_table['ref'],action='table_cell',cell_index=other_cell['index'],mirror_ref=other_mirror,before=before,after=after,xyz=[],reason='Đồng bộ bas tại bảng kê liên quan'))
        raw=by[other_mirror].get('raw_text',by[other_mirror]['text']);text(by[other_mirror],raw,raw.replace(old_spec,new_spec),'Đồng bộ hình bảng kê bas liên quan')
    for e in detail_records+cut_records:
        if e['type'] not in ('TEXT','MTEXT'):continue
        raw=e.get('raw_text',e.get('text',''))
        text(e,raw,raw.replace(old_spec,new_spec),'Đồng bộ quy cách bas ở bản chi tiết/bản cắt')
    count=count_texts[0];raw=count.get('raw_text',count['text'])
    text(count,raw,re.sub(r'(?<!\d)'+str(len(instance_refs))+r'(?=\s*pcs)',str(len(boxes)),raw),'Đồng bộ số bas thực tế trên một tấm sau xếp lại')
    # Rebind edge-margin dimensions to the new union of packed profiles.
    old_boxes=[geometry_box(cut_children[r],r) for r in instance_refs]
    old_union=[min(b[0] for b in old_boxes),min(b[1] for b in old_boxes),max(b[2] for b in old_boxes),max(b[3] for b in old_boxes)]
    new_union=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    for e in cut_records:
        if e['type']!='DIMENSION' or not e.get('geometry') or e['ref'] in recipe.stock_dimension_refs:continue
        g=e['geometry'];axis=0 if abs(g['angle'])<1e-6 else 1 if abs(g['angle']-90)<1e-6 else None
        if axis is None or g['text'] not in ('','<>'):raise ValueError('Kích thước dư biên bản cắt chưa hỗ trợ')
        after=copy.deepcopy(g)
        for key in ('defpoint2','defpoint3'):
            for index in (axis,axis+2):
                if near(g[key][axis],old_union[index]):after[key][axis]=new_union[index]
        if not near(g,after):operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(g),after=json.dumps(after),xyz=[],reason='Đo lại mép dư tấm theo vị trí bas mới'))
    fit=FitRule(thickness_dimension_ref=changed_wall[0]['ref'],outside_dimension_ref=outer[0]['ref'],mating_dimension_ref=width_dim['ref'])
    source_rows=[r for _,r in rows if r['part_code']==tube_code]
    if not source_rows:raise ValueError('Thiếu dòng BOM hộp')
    dependency=DependencyProposal(source_part=source_rows[0]['part_number'],target_part=row['part_number'],relationship='Bas lắp vừa lòng trong hộp, theo ghi chú nguồn',required_change=f'Đổi bas {width:g} → {new_width:g} mm; giữ khe hở {outer[0]["scaled_measurement"]-2*old_t-width:g} mm và lỗ; xếp lại {len(instance_refs)} → {len(boxes)} pcs/tấm, gap {gap:g} mm.',evidence_refs=[fit.thickness_dimension_ref,fit.outside_dimension_ref,fit.mating_dimension_ref,*[n['ref'] for n in notes]],fit_rule=fit,needs_confirmation=True)
    warning=f'Bản cắt giữ tấm và gap {gap:g} mm: {len(boxes)} bas/tấm thay cho {len(instance_refs)}. Bố trí theo grid nguồn, chưa tối ưu nesting toàn cục. Lỗ bas giữ nguyên vị trí/đường kính; hình phối cảnh ngoài cần đối chiếu preview.'
    return operations,dependency,recipe,warning


def compile_fits(context,tube_code,tube_records,tube_ops,old_t,new_t,notes):
    """Compile every independently proven snug-fit companion as one transaction.

    Unknown/ambiguous companions abort the entire plan; the first bas is never
    used as a substitute for coverage of the rest of the assembly.
    """
    rows=[r for e in context['entities'] for r in e.get('bom',{}).get('rows',[])]
    codes={r['part_code'] for r in rows if r['part_code']!=tube_code}
    companions={code for target in context['targets']
                if has_fit_note(target,notes)
                for code in codes if code in target.get('texts',[])}
    if not companions:raise ValueError('Ghi chú vừa khít chưa có mã chi tiết/BOM đi kèm')
    operations=[];dependencies=[];recipes=[];warnings=[];slots={};labels={}
    for code in sorted(companions):
        try:
            ops,dep,recipe,warning=compile_fit(context,tube_code,tube_records,tube_ops,old_t,new_t,notes,code)
            deps=[dep]
        except ValueError:
            from backend.services.rounded_fit_planner import compile_rounded_fit
            ops,deps,recipe,warning=compile_rounded_fit(context,tube_code,tube_records,tube_ops,old_t,new_t,notes,code)
        numbers={r['part_number'] for r in rows if r['part_code']==code}
        label=next(iter(numbers)) if len(numbers)==1 else code
        for op in ops:
            slot=(op.ref,op.cell_index if op.action=='table_cell' else None)
            previous=slots.get(slot)
            if previous and previous.model_dump()!=op.model_dump():
                raise ValueError('Hai liên kết yêu cầu sửa khác nhau trên cùng đối tượng/ô BOM')
            if not previous:slots[slot]=op;operations.append(op);labels[slot]=label
        # Exact codes avoid merging balloon numbers from different BOMs.
        for dep in deps:
            dep.source_part=tube_code;dep.target_part=code
        dependencies.extend(deps);recipes.append(recipe);warnings.append(warning)
    return operations,dependencies,recipes,warnings,labels
