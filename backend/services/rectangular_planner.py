"""Compile one explicit dimension command on a uniquely measured rectangular part."""
import math
import re
from collections import defaultdict
from ezdxf.math import Matrix44,Vec3
from bom.reader import normalized
from cad.parametric import LinearResize,resize
from cad.edit_engine import Operation
from graph.part_graph import seed_codes


def compile_plan(context, request, clarifications=None):
    policy=normalized(request+' '+' '.join(c.get('answer','') for c in clarifications or []))
    command=re.search(r'chieu (?:dai|rong|cao)\s*(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|con|->|→)\s*(\d+(?:[.,]\d+)?)',policy)
    inferred=re.search(r'(?:rut ngan|chieu dai).*?(?:con|thanh|xuong)\s*(\d+(?:[.,]\d+)?)',policy) if not command else None
    if not (command or inferred) or context.get('units')!=4:
        return None
    if len(re.findall(r'chieu (?:dai|rong|cao)\s*(?:tu\s*)?\d',policy))!=(1 if command else 0) or any(word in policy for word in ('doi vat lieu','thay vat lieu','doi do day','thay do day','tat ca','ket cau')):
        return None
    if any(word in policy for word in ('bo lo','them lo','doi vi tri','di chuyen lo')) or re.search(r'(?:doi|thay|tang|giam)\s+(?:duong kinh|ban kinh)',policy):return None
    if re.search(r'(?:duong kinh|ban kinh)\s*\d.*?(?:thanh|len|xuong)\s*\d',policy):return None
    kind=re.search(r'chieu (dai|rong|cao)',command.group(0)).group(1) if command else 'dai'
    old,new=([float(v.replace(',','.')) for v in command.groups()] if command else (None,float(inferred.group(1).replace(',','.'))))
    if new<=0 or (old is not None and (old<=0 or math.isclose(old,new))):return None
    keep_center='giu tam' in policy or 'giu co dinh tam' in policy
    side_map={'dau trai':'left','canh trai':'left','trai':'left',
              'dau phai':'right','canh phai':'right','phai':'right',
              'dau duoi':'bottom','mat duoi':'bottom','canh duoi':'bottom','duoi':'bottom',
              'mat day':'bottom','dau day':'bottom','canh day':'bottom','day':'bottom','chan':'bottom',
              'dau tren':'top','mat tren':'top','canh tren':'top','tren':'top','dinh':'top'}
    sides={side for phrase,side in side_map.items() if re.search(r'giu(?: co dinh| nguyen)?\s*'+phrase,policy) or re.search(phrase+r'\s*giu(?: co dinh| nguyen)?',policy)}
    if not sides and re.search(r'(?:ha|giam|thu)\s+(?:dau\s*|mat\s*|canh\s*)?tren\b',policy):sides={'bottom'}
    elif not sides and re.search(r'(?:nang|tang|keo)\s+(?:dau\s*|mat\s*|canh\s*)?duoi\b',policy):sides={'top'}
    if not sides and kind=='cao':
        from backend.services.height_request_service import stored_anchor
        confirmed=stored_anchor(context)
        if confirmed:sides={confirmed}
    if len(sides)>1:return None
    side=next(iter(sides),None)
    if not keep_center and side is None:return None
    if keep_center and side:return None
    records=context['entities'];codes=seed_codes(context,request)
    if not codes:
        codes={e['name'] for e in records if e['type']=='INSERT' and re.search(r'(?<![\w.-])'+re.escape(e.get('name',''))+r'(?![\w.-])',request)}
    if not codes:
        from backend.services.size_commands import interpret_linear_request
        reading=interpret_linear_request(context,request,clarifications)
        if reading and reading.get('part_code'):codes={reading['part_code']}
    if len(codes)!=1:
        nodes={n['code']:n for n in context.get('part_graph',{}).get('nodes',[])}
        with_sheets=[c for c in codes if c in nodes and nodes[c].get('detail_sheets')]
        if len(with_sheets)==1:
            codes=set(with_sheets)
    if len(codes)!=1:return None
    code=next(iter(codes));by_ref={e['ref']:e for e in records}
    from cad.part_identity import record_identity
    owner_inserts={e['ref'] for e in records if record_identity(e,{code})==code}
    nodes=context.get('part_graph',{}).get('nodes',[])
    owners={}
    for node in nodes:
        for sheet in node.get('detail_sheets',[]):owners.setdefault(sheet,set()).add(node['id'])
    detail_targets=[t for t in context.get('targets',[]) if owners.get(t['id'])=={code} and t.get('bbox')]
    frames=defaultdict(list)
    for e in records:
        if e.get('coordinate_frame'):frames[(e['coordinate_frame'],e.get('layout'))].append(e)
    candidates=[]
    for _,entities in frames.items():
        for dim in entities:
            if dim['type']!='DIMENSION' or not dim.get('geometry'):continue
            from cad.dimensions import linear_axis
            try:direction=linear_axis(dim)
            except ValueError:continue
            roots=set(context.get('root_target_ids',[]))
            if roots and not roots.intersection(dim.get('source_sheet_ids',[])) and dim['ref'].split('/')[0] not in roots:continue
            previous=dim.get('scaled_measurement',-1)
            if previous<=0 or (old is not None and abs(previous-old)>1e-6) or abs(previous-new)<1e-6:continue
            dg=dim['geometry'];axis=direction[:2];normal=(-axis[1],axis[0])
            def uv(p):return sum(p[i]*axis[i] for i in range(2)),sum(p[i]*normal[i] for i in range(2))
            ends=sorted(uv(dg[k])[0] for k in ('defpoint2','defpoint3'))
            outlines=[[e] for e in entities if e['type']=='LWPOLYLINE' and e.get('geometry',{}).get('closed') and len(e['geometry']['points'])==4]
            lines=[e for e in entities if e['type']=='LINE' and e.get('geometry')]
            # Pair the two end caps and find the matching two side edges.
            caps=[]
            for e in lines:
                a,b=[uv(e['geometry'][k]) for k in ('start','end')]
                if abs(a[0]-b[0])<1e-6 and any(abs(a[0]-end)<1e-6 for end in ends):caps.append((e,sorted([a[1],b[1]]),a[0]))
            for first,span,u in caps:
                for second,other,v in caps:
                    if first['ref']>=second['ref'] or abs(u-v)<1e-6 or any(abs(a-b)>1e-6 for a,b in zip(span,other)):continue
                    sides=[]
                    for e in lines:
                        a,b=[uv(e['geometry'][k]) for k in ('start','end')]
                        if abs(a[1]-b[1])<1e-6 and any(abs(a[1]-x)<1e-6 for x in span) and all(abs(x-y)<1e-6 for x,y in zip(sorted([a[0],b[0]]),ends)):sides.append(e)
                    if len(sides)==2:outlines.append([first,second,*sides])
            for outline in outlines:
                points=[p for e in outline for p in ([e['geometry']['start'],e['geometry']['end']] if e['type']=='LINE' else [[p[0],p[1],e['geometry']['elevation']] for p in e['geometry']['points']])]
                frame=dim['coordinate_frame']
                if frame.startswith('instance:'):
                    instance=frame.removeprefix('instance:')
                    if not any(instance==ref or instance.startswith(ref+'/') for ref in owner_inserts):continue
                elif not any(t.get('layout')==dim.get('layout') and all(t['bbox'][0]<=p[0]<=t['bbox'][2] and t['bbox'][1]<=p[1]<=t['bbox'][3] for p in points) for t in detail_targets):
                    continue
                us,vs=zip(*(uv(p) for p in points));lo,hi,bot,top=min(us),max(us),min(vs),max(vs)
                if any(abs(a-b)>1e-6 for a,b in zip([lo,hi],ends)):continue
                if kind=='dai' and hi-lo<=top-bot+1e-6:continue
                if kind=='rong' and hi-lo>=top-bot-1e-6:continue
                matrix=Matrix44([value for row in dim['frame_to_layout'] for value in row])
                if kind=='cao':
                    direction=matrix.transform_direction(Vec3([*axis,0]))
                    if abs(direction.x)>1e-5 or abs(direction.y)<1e-5:continue
                holes=[e for e in entities if e['type']=='CIRCLE' and e.get('geometry') and lo<=uv(e['geometry']['center'])[0]<=hi and bot<=uv(e['geometry']['center'])[1]<=top]
                if keep_center:anchor='center'
                else:
                    a,b=[matrix.transform(Vec3(dg[k])) for k in ('defpoint2','defpoint3')]
                    i=0 if side in ('left','right') else 1
                    if abs(a[i]-b[i])<1e-6:continue
                    first_low=a[i]<b[i];keep_low=side in ('left','bottom')
                    anchor='first' if first_low==keep_low else 'second'
                refs=[e['ref'] for e in outline+holes]+[dim['ref']]
                recipe=LinearResize(part_code=code,dimension_ref=dim['ref'],new_measurement=new,outline_refs=[e['ref'] for e in outline],hole_refs=[e['ref'] for e in holes],anchor=anchor,evidence_refs=refs)
                try:resize(recipe,context,new)
                except ValueError:continue
                candidates.append((recipe,entities,previous))
    if len(candidates)!=1:return None
    recipe,entities,old=candidates[0]
    from backend.services.change_service import DrawingChangePlan,EditProposal
    plan=DrawingChangePlan(summary=f'Sửa kích thước {code}: {old:g} → {new:g} mm theo profile và DIMENSION nguồn.',target_part=code,edits=[],dependencies=[],questions=[],warnings=[],resize_recipes=[recipe])
    number=re.compile(r'(?<![\d.])'+re.escape(f'{old:g}').replace(r'\.',r'[.,]')+r'(?![\d.])')
    bom_cells={c.get('mirror_ref') for t in records for r in t.get('bom',{}).get('rows',[]) for c in r.get('cells',{}).values()}
    from bom.stage_links import physical_spec
    specs={physical_spec(r['description']) for t in records for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code}
    detail_ids={t['id'] for t in detail_targets}
    def text_op(ref,before,after,purpose='annotation'):
        if before==after:return
        op=Operation(ref=ref,action='replace_text',before=before,after=after,xyz=[],reason='Đồng bộ mô tả với kích thước mới đo thật')
        plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=ref,part_number=code,purpose=purpose,before=before,after=after,reason=op.reason))
    for table in records:
        for row in table.get('bom',{}).get('rows',[]):
            if row['part_code']!=code:continue
            cell=row.get('cells',{}).get('description',{});raw=cell.get('raw_text','');mirror=cell.get('mirror_ref')
            if len(number.findall(raw))!=1 or mirror not in by_ref:return None
            after=number.sub(f'{new:g}',raw)
            from bom.operations import cell_operations
            for op in cell_operations(table,cell,after,by_ref,'Đồng bộ đúng dòng BOM theo mã chi tiết'):
                plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='bom',before=op.before,after=op.after,reason=op.reason))
    for e in entities:
        if e['type'] not in ('TEXT','MTEXT','ATTRIB') or e['ref'] in bom_cells:continue
        raw=e.get('raw_text',e.get('text',''))
        native_owned=any(e['ref'].startswith(root+'/') for root in owner_inserts)
        frame_owned=bool(detail_ids.intersection(e.get('source_sheet_ids',[]))) and physical_spec(raw) in specs
        if not native_owned and not frame_owned:continue
        # Update only specifications containing this number as a dimension token.
        if re.search(r'(?:\d\s*[x×]\s*'+re.escape(f'{old:g}')+r'|'+re.escape(f'{old:g}')+r'\s*[x×]\s*\d)',raw) and len(number.findall(raw))==1:
            text_op(e['ref'],raw,number.sub(f'{new:g}',raw))
    from backend.services.parametric_service import compile_recipes
    try:return compile_recipes(plan,context)
    except ValueError as error:
        from graph.parameter_links import active
        if active(context,[r.dimension_ref for r in plan.resize_recipes]):
            raise ValueError('Không thể sửa theo liên kết đã xác nhận: '+str(error)) from error
        return None
