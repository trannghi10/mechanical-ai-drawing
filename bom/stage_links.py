"""Source specification links between manufacturing stages of a part family.

Matching codes alone are insufficient: require the exact physical description,
material, product and an explicit HDCV route. These links locate drawings; they
do not authorize reusing coordinates between different manufacturing stages.
"""
import re
from bom.reader import normalized,plain
from bom.processes import process_tags


def physical_spec(text):
    value=plain(text)
    return normalized(re.sub(r'\([^()]*\)',lambda m:'' if process_tags(m.group(0)) else m.group(0),value))


def material_input_tables(tables,sheets,table_sheets,parts):
    """Only an explicit source heading distinguishes stock from installed parts.

    A stock-looking code or large sheet dimensions are insufficient. The title
    must belong to a scope with one verified BOM and one distinct detail owner.
    These observations locate manufacturing inputs; they grant no edit rights.
    """
    headings={'bang ke nguyen lieu','bang ke vat lieu phoi','raw material list','raw material schedule'}
    result={}
    for sheet in sheets:
        labels=[plain(t) for t in sheet.get('texts',[]) if normalized(t).rstrip(' :') in headings]
        local=[t for t in tables if sheet['id'] in table_sheets.get(t['ref'],[]) and t.get('bom',{}).get('status')=='verified_template']
        if len(local)!=1 or not labels:continue
        table=local[0];codes={r['part_code'].strip() for r in table['bom']['rows']}
        owners={n['code'] for n in parts.values() if sheet['id'] in n.get('detail_sheets',[]) and n['code'] not in codes}
        if len(owners)!=1:continue
        entry=result.setdefault(table['ref'],dict(table_ref=table['ref'],owner_codes=set(),stock_codes=sorted(codes),source_headings=[],sheet_ids=[]))
        entry['owner_codes'].update(owners);entry['source_headings'].extend(labels);entry['sheet_ids'].append(sheet['id'])
    return {ref:dict(table_ref=ref,owner_code=next(iter(r['owner_codes'])),stock_codes=r['stock_codes'],
                    source_headings=sorted(set(r['source_headings'])),sheet_ids=sorted(set(r['sheet_ids'])),status='source_material_input')
            for ref,r in result.items() if len(r['owner_codes'])==1}


def review_material_inputs(plan,impact,context):
    """Check one unchanged sheet supplies one measured blank; never infer nesting."""
    import json,math
    from graph.fit_constraints import measurement
    from cad.geometry import near
    records={e['ref']:e for e in context.get('entities',[])};ops={o.ref:o for o in plan.operations};result=[]
    pattern=r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?![\d.,])'
    def spec(value):
        matches=list(re.finditer(pattern,plain(value)))
        if len(matches)!=1 or re.search(r'\binch\b|["″]',plain(value),re.I):return None
        values=[float(v.replace(',','.')) for v in matches[0].groups()]
        return values if all(math.isfinite(v) and v>0 for v in values) else None
    def cell_value(table,row,key):
        cell=row.get('cells',{}).get(key,{})
        source=cell.get('raw_text',row.get('quantity_text' if key=='quantity' else key,''));op=ops.get(cell.get('mirror_ref'))
        if not op:op=next((o for o in plan.operations if o.ref==table['ref'] and o.action=='table_cell' and o.cell_index==cell.get('index')),None)
        if op:
            if op.before!=source or op.action not in ('replace_text','table_cell'):raise ValueError('Ô nguyên liệu/vật tư đã khác nguồn CAD')
            return plain(op.after)
        return plain(source)
    for entry in impact.get('material_inputs',[]):
        owner=entry['owner_code'];table=records.get(entry['table_ref'],{})
        for code in entry['stock_codes']:
            row=dict(part_code=owner,stock_code=code,table_ref=entry['table_ref'],sheet_ids=entry['sheet_ids'],status='unresolved_material_input',
                     reason='Chưa kiểm chứng quy cách phôi, số lượng hoặc bố trí cắt của nguyên liệu.',evidence_refs=[])
            result.append(row)
            if context.get('units')!=4 or table.get('bom',{}).get('status')!='verified_template':continue
            headings=[e['ref'] for e in records.values() if e.get('type') in ('TEXT','MTEXT') and
                      set(e.get('source_sheet_ids',[])).intersection(entry['sheet_ids']) and plain(e.get('text','')) in entry['source_headings']]
            if not headings:continue
            stock_rows=table['bom']['rows']
            if len(stock_rows)!=1 or stock_rows[0]['part_code']!=code:continue
            stock=stock_rows[0];raw=spec(stock['description'])
            if not raw or not re.search(r'\b(?:sat tam|thep tam|inox tam|steel sheet|sheet steel)\b',normalized(stock['description'])):continue
            stock_refs={c['mirror_ref'] for c in stock.get('cells',{}).values() if c.get('mirror_ref')}
            if any(o.ref in stock_refs or o.ref==table['ref'] for o in plan.operations):
                row['reason']='Nguyên liệu đã đổi: cần kiểm tra lại mã, quy cách và bố trí cắt.';continue
            if stock.get('quantity_text','').strip() not in ('1','01','1.0'):continue
            owners=[(t,r) for t in records.values() if t.get('bom',{}).get('status')=='verified_template' for r in t['bom']['rows'] if r['part_code']==owner]
            recipes=[r for r in getattr(plan,'resize_recipes',[]) if r.part_code==owner]
            if not owners or not recipes:continue
            values=[];valid=True;evidence=set(headings)|stock_refs|{table['ref']}
            for t,r in owners:
                before=spec(r['description']);after=spec(cell_value(t,r,'description'))
                if (not before or not after or normalized(r.get('material',''))!=normalized(stock.get('material','')) or
                    r.get('quantity_text','').strip() not in ('1','01','1.0') or cell_value(t,r,'quantity') not in ('1','01','1.0')):
                    valid=False;break
                if not near(before[0],raw[0]) or not near(after[0],raw[0]):
                    row['reason']='Độ dày chi tiết sau sửa không khớp nguyên liệu nguồn.';valid=False;break
                checked=list(before)
                for recipe in recipes:
                    dim=records.get(recipe.dimension_ref,{});op=ops.get(recipe.dimension_ref)
                    feature=next((f for f in context.get('source_features',{}).get('features',[]) if f.get('part_code')==owner and
                        f.get('ownership_proof') in ('native_part_identity','unique_source_detail_sheet','local_bom_leader_profile') and
                        set(f['refs'])==set(recipe.outline_refs) and any(d['ref']==recipe.dimension_ref for d in f['dimensions'])),None)
                    if not feature or not op or op.action!='replace_geometry':valid=False;break
                    old=measurement(dim,dim['geometry']);new=measurement(dim,json.loads(op.after))
                    axes=[i for i in (1,2) if near(before[i],old,1e-5)]
                    if len(axes)!=1 or not near(new,after[axes[0]],1e-5):valid=False;break
                    checked[axes[0]]=new;evidence.update(recipe.evidence_refs)
                if not valid or not near(checked,after,1e-5):valid=False;break
                if before[1]>raw[1]+1e-6 or before[2]>raw[2]+1e-6 or after[1]>raw[1]+1e-6 or after[2]>raw[2]+1e-6:
                    row['reason']='Phôi vượt khổ nguyên liệu nguồn; cần đổi quy cách hoặc bố trí cắt.';valid=False;break
                values.append(after);evidence.add(t['ref']);evidence.update(c['mirror_ref'] for c in r.get('cells',{}).values() if c.get('mirror_ref'))
            if valid and values and all(near(v,values[0]) for v in values):
                row.update(status='verified_single_blank_envelope',stock_mm=raw,blank_mm=values[0],evidence_refs=sorted(evidence),
                    reason='Giữ nguyên tấm nguyên liệu: cùng độ dày, một phôi nằm trong khổ tấm theo hướng nguồn. Không chứng nhận nesting hàng loạt, hao hụt hoặc độ bền.')
    return result


def stage_links(parts,sheets):
    by_id={s['id']:s for s in sheets};result=[]
    def products(sheet):return {plain(t) for t in sheet.get('texts',[]) if re.fullmatch(r'9\.\d+\.\d+',plain(t)) and plain(t) not in parts}
    for sheet in sheets:
        texts=[plain(t) for t in sheet.get('texts',[])]
        # A stage sheet can contain a native BOM. Its known member codes do
        # not identify the stage owner; retain only the uncatalogued stage code.
        codes={t for t in texts if re.fullmatch(r'\d+(?:\.\d+){3}',t) and t not in parts}
        notes=[t for t in texts if re.search(r'\bhdcv\s*:',normalized(t)) and (' =>' in t or '=>' in t or '→' in t)]
        if len(codes)!=1 or not notes or len(products(sheet))!=1:continue
        code=next(iter(codes))
        if code in parts:continue
        descriptions=[t for t in texts if process_tags(t) and re.search(r'\d+(?:\.\d+)?\s*[x×]\s*\d+',t)]
        candidates={}
        for node in parts.values():
            if node['code'].rsplit('.',1)[0]!=code.rsplit('.',1)[0]:continue
            for occurrence in node['bom_occurrences']:
                for desc in descriptions:
                    if physical_spec(desc)!=physical_spec(occurrence['description']):continue
                    if normalized(occurrence['material']) not in {normalized(t) for t in texts}:continue
                    parent_ids=set(occurrence['sheet_ids'])|set(node.get('detail_sheets',[]))
                    if not any(products(sheet)==products(by_id[sid]) for sid in parent_ids if sid in by_id):continue
                    candidates[node['code']]=(desc,occurrence)
        if len(candidates)!=1:continue
        target,(desc,occurrence)=next(iter(candidates.items()))
        result.append(dict(sheet_id=sheet['id'],source_part_code=code,bom_part_code=target,
                           source_description=desc,bom_description=occurrence['description'],route_notes=notes,
                           evidence_table_ref=occurrence['table_ref'],status='source_specification_stage_link',
                           geometry_rule='unverified: stage views require their own measured geometry'))
    return result
