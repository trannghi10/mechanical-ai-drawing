"""Compile source-measured profiles across anonymous blocks and external DIMs."""
import math
import re
import numpy as np
from bom.reader import normalized
from cad.parametric import LinearResize
from cad.frame_geometry import world
from cad.measured_features import index
from bom.operations import cell_operations


HOLD_PATTERN=r'(?:giu|co dinh)\s*(?:nguyen\s*|co dinh\s*)?(?:dau\s*|canh\s*|mat\s*)?(trai|phai|tren|duoi|tam|day|chan|dinh)\b'


def anchor_question(ref,code,side,component):
    direction='ngang' if component==1 else 'đứng';sides='trái/phải' if component==1 else 'trên/dưới'
    label={'trai':'trái','phai':'phải','tren':'trên','duoi':'dưới'}.get(side,side)
    return f'DIM #{ref} của {code} đo theo hướng {direction}; mốc giữ {label} chưa xác định đầu giữ theo hướng này. Chọn giữ {sides} hoặc giữ tâm.'


def source_anchor_answers(context,clarifications,old):
    """A reply replaces the hold only for its exact source-bound DIM question."""
    if not any(normalized(c.get('question','')).startswith('dim #') for c in clarifications or []):return {},set()
    report=context.get('source_features') or index(context,context.get('part_graph'))
    roots=set(context.get('root_target_ids',[]));questions={}
    for f in report['features']:
        if f.get('ownership_proof')=='unverified' or not f.get('part_code'):continue
        if roots and not roots.intersection(f['sheet_ids']) and f.get('instance_ref') not in roots:continue
        for d in f['dimensions']:
            if abs(d['measurement']-old)>1e-6:continue
            for side,component in [('trai',0),('phai',0),('tren',1),('duoi',1)]:
                questions[normalized(anchor_question(d['ref'],f['part_code'],side,component))]=d['ref']
    holds={};used=set()
    for i,c in enumerate(clarifications or []):
        ref=questions.get(normalized(c.get('question','')))
        if not ref:continue
        answer=normalized(c.get('answer','')).strip(' .')
        if answer in ('trai','phai','tren','duoi','tam','day','chan','dinh'):answer='giu '+answer
        if not re.fullmatch(HOLD_PATTERN,answer):continue
        values=[{'day':'duoi','chan':'duoi','dinh':'tren'}.get(v,v) for v in re.findall(HOLD_PATTERN,answer)]
        if len(set(values))!=1:continue
        if ref in holds and holds[ref]!=values[0]:raise ValueError('Các câu trả lời mốc giữ cho cùng DIM bị mâu thuẫn')
        holds[ref]=values[0];used.add(i)
    return holds,used


def compile_plan(context,request,clarifications=None):
    plan=_compile_plan(context,request,clarifications)
    if plan is not None or context.get('_projection_driver_fallback'):return plan
    return continued_projection_plan(context,request,clarifications)


def continued_projection_plan(context,request,clarifications):
    """A selected numbered continuation can use its verified flat source.

    Recheck complete face correspondence, actual receiver DIM and the held
    endpoint. A remote BOM row alone cannot authorize a view or an anchor.
    """
    from bom.continuations import continuation_links
    roots=set(context.get('root_target_ids',[]));tables=[e for e in context['entities'] if e.get('bom',{}).get('status')=='verified_template']
    links=continuation_links(tables,context.get('targets',[]),{e['ref']:e.get('source_sheet_ids',[]) for e in tables})
    if not roots or any(links.get(s,{}).get('status')!='explicit_numbered_drawing_series' for s in roots):return None
    text=normalized(request+' '+' '.join(c.get('answer','') for c in clarifications or []))
    commands=list(re.finditer(r'(chieu (?:dai|rong|cao))\s*(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|con|->|→)\s*(\d+(?:[.,]\d+)?)',text))
    keeps=re.findall(HOLD_PATTERN,text)
    if len(commands)!=1 or len(set(keeps))!=1:return None
    kind,old,new=commands[0].groups();old,new=[float(v.replace(',','.')) for v in (old,new)]
    from graph.part_graph import seed_codes
    codes=set(context.get('part_graph',{}).get('seed_codes',[])) or seed_codes(context,request,context.get('part_graph'))
    if len(codes)!=1:return None
    code=next(iter(codes));keep={'day':'duoi','chan':'duoi','dinh':'tren'}.get(keeps[0],keeps[0]);by={e['ref']:e for e in context['entities']}
    from graph.projected_profiles import bindings
    from cad.geometry import near
    from graph.fit_constraints import measurement
    import copy,json
    results={}
    for feature in (context.get('source_features') or index(context,context.get('part_graph')))['features']:
        if feature.get('part_code')!=code or feature.get('ownership_proof') not in ('native_part_identity','local_bom_leader_profile','unique_source_detail_sheet') or roots.intersection(feature['sheet_ids']):continue
        if not any(abs(d['measurement']-old)<1e-6 for d in feature['dimensions']):continue
        scoped=dict(context,root_target_ids=feature['sheet_ids'],_projection_driver_fallback=True)
        plan=_compile_plan(scoped,request,clarifications)
        if not plan or plan.questions:continue
        proofs=[p for p in bindings(plan,context) if p['part_code']==code and roots.intersection(p['sheet_ids'])];covered=set()
        for proof in proofs:
            valid=[]
            for op in proof['operations']:
                record=by[op.ref]
                if record['type']!='DIMENSION' or record.get('dimension_type') not in (0,1) or not near(record.get('scaled_measurement'),old,1e-5):continue
                updated=copy.deepcopy(record);updated['geometry']=json.loads(op.after)
                before=world(record);after=world(updated);g,h=before['geometry'],after['geometry']
                if not near(measurement(after,h),new,1e-5):continue
                points=[g[k] for k in ('defpoint2','defpoint3')];moved=[h[k] for k in ('defpoint2','defpoint3')]
                if keep=='tam':held=near(np.mean(points,axis=0).tolist(),np.mean(moved,axis=0).tolist(),1e-5)
                else:
                    axis=0 if keep in ('trai','phai') else 1
                    if abs(points[0][axis]-points[1][axis])<1e-5:continue
                    i=min(range(2),key=lambda i:points[i][axis]) if keep in ('trai','duoi') else max(range(2),key=lambda i:points[i][axis])
                    held=near(points[i],moved[i],1e-5)
                valid.append(held)
            if valid and all(valid):covered.update(roots.intersection(proof['sheet_ids']))
        if covered==roots:
            key=json.dumps([(o.ref,o.action,o.before,o.after) for o in plan.operations],sort_keys=True);results[key]=plan
    return next(iter(results.values())) if len(results)==1 else None


def _compile_plan(context,request,clarifications=None):
    text=normalized(request+' '+' '.join(c.get('answer','') for c in clarifications or []))
    if context.get('units')!=4:return None
    if any(w in text for w in ('tat ca','toan bo','ket cau','doi vat lieu','thay vat lieu','them lo','bo lo','xoa lo','di chuyen lo','doi vi tri')):return None
    if re.search(r'(?:doi|thay|tang|giam)\s+(?:duong kinh|ban kinh)',text):return None
    commands=list(re.finditer(r'(chieu (?:dai|rong|cao)|do day)\s*(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|con|->|→)\s*(\d+(?:[.,]\d+)?)',text))
    if not commands:
        from backend.services.size_commands import inferred_command
        command=inferred_command(context,text)
        if command:commands=[command]
    if not commands:
        m=re.search(r'(?:giam|ha)\s+(?:khung\s+|chieu cao\s+)?xuong\s+(\d+(?:[.,]\d+)?)\s*(?:mm)?',text)
        if m:
            new_val=m.group(1)
            choices=context.get('design_choices',{})
            derived=choices.get('derived_values',{})
            old_val=derived.get('frame_height_before_mm')
            if isinstance(old_val,(int,float)) and math.isfinite(old_val) and old_val>0:
                commands=[('chieu cao',str(old_val),new_val)]
    if not commands:
        m=re.search(r'(?:giam|ha)\s+(?:khung|chieu cao)\s+(?:tu\s*)?(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:xuong|thanh|con)\s*(\d+(?:[.,]\d+)?)',text)
        if m:
            commands=[('chieu cao',m.group(1),m.group(2))]
    if not commands:
        from backend.services.size_commands import interpret_linear_request
        reading=interpret_linear_request(context,request,clarifications)
        if reading and reading.get('target_mm') is not None and (reading.get('measured_before_mm') or reading.get('nominal_before_mm')):
            old_val=reading.get('measured_before_mm') or reading.get('nominal_before_mm')
            kind_map={'length':'chieu dai','width':'chieu rong','height':'chieu cao'}
            commands=[(kind_map.get(reading['dimension'],'chieu dai'),str(old_val),str(reading['target_mm']))]
    if len(commands)!=1:return None
    item=commands[0]
    kind,old,new=item.groups() if hasattr(item,'groups') else item
    old=float(old.replace(',','.'));new=float(new.replace(',','.'))
    if min(old,new)<=0 or math.isclose(old,new):return None
    scoped_holds,answered=source_anchor_answers(context,clarifications,old)
    hold_text=normalized(request+' '+' '.join(c.get('answer','') for i,c in enumerate(clarifications or []) if i not in answered))
    raw_keep=re.findall(HOLD_PATTERN,hold_text)
    mapping={'day':'duoi','chan':'duoi','dinh':'tren'}
    keep=[mapping.get(k,k) for k in raw_keep]
    if not keep and re.search(r'(?:ha|giam|thu)\s+(?:dau\s*|mat\s*|canh\s*)?tren\b',text):keep=['duoi']
    elif not keep and re.search(r'(?:nang|tang|keo)\s+(?:dau\s*|mat\s*|canh\s*)?duoi\b',text):keep=['tren']
    if not keep and kind=='chieu cao':
        from backend.services.height_request_service import stored_anchor
        confirmed=stored_anchor(context)
        if confirmed:keep=[{'bottom':'duoi','top':'tren'}[confirmed]]
    if not keep and not scoped_holds and not context.get('confirmed_parameter_links'):
        keep=['tam' if kind in ('chieu rong','do day') else 'trai']
    if len(set(keep))>1:return None
    from graph.part_graph import seed_codes
    codes=set(context.get('part_graph',{}).get('seed_codes',[])) or seed_codes(context,request,context.get('part_graph'))
    if len(codes)!=1 and 'reading' in locals() and reading and reading.get('part_code'):
        codes={reading['part_code']}
    if len(codes)!=1:
        roots=set(context.get('root_target_ids',[]))
        if roots:
            report_features=(context.get('source_features') or index(context,context.get('part_graph')))['features']
            matched_codes={f['part_code'] for f in report_features if f.get('part_code') and
                           (roots.intersection(f['sheet_ids']) or f.get('instance_ref') in roots) and
                           any(abs(d['measurement']-old)<1e-6 for d in f['dimensions'])}
            if len(matched_codes)==1:
                codes=matched_codes
    if len(codes)!=1:
        nodes={n['code']:n for n in context.get('part_graph',{}).get('nodes',[])}
        with_sheets=[c for c in codes if c in nodes and nodes[c].get('detail_sheets')]
        if len(with_sheets)==1:
            codes=set(with_sheets)
    if len(codes)!=1:return None
    code=next(iter(codes));roots=set(context.get('root_target_ids',[]));by={e['ref']:e for e in context['entities']}
    # An explicit part-height instruction applies to its owned manufacturing
    # views, even when they have different cross-sections (flat/bent/painted).
    # Each view still needs its own real DIM, closed contour and ownership;
    # equal numbers in another part or an unmeasured perspective are excluded.
    explicit_height=kind=='chieu cao' and bool(re.search(r'(?<![\w.])'+re.escape(code)+r'(?![\w.])',request))
    if explicit_height and any(n.get('definition_conflict') for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==code):return None
    report=context.get('source_features') or index(context,context.get('part_graph'))
    candidates=[];anchor_conflicts=[]
    target_ids={t['id'] for t in context.get('targets',[])}
    for feature in report['features']:
        if feature['part_code']!=code or feature['ownership_proof']=='unverified':continue
        if roots and not explicit_height and not (roots.intersection(feature['sheet_ids']) or target_ids.intersection(feature['sheet_ids'])) and feature.get('instance_ref') not in roots:continue
        for d in feature['dimensions']:
            if abs(d['measurement']-old)>1e-6:continue
            axis=np.asarray(d['axis']);p=np.asarray(feature['points']);span=float(np.ptp(p@axis));cross=float(np.ptp(p@np.array([-axis[1],axis[0],0.])))
            if kind=='chieu dai' and span<=cross+1e-6 or kind in ('chieu rong','do day') and span>=cross-1e-6:continue
            if kind=='chieu cao' and abs(axis[1])<1-1e-6:continue
            dim=world(by[d['ref']]);g=dim['geometry'];side=scoped_holds.get(d['ref'],keep[0] if keep else None)
            if side is None:
                anchors={entry['rule'][key] for entry in context.get('confirmed_parameter_links',[]) for role,key in [('driver_ref','driver_anchor'),('receiver_ref','receiver_anchor')] if entry['rule'][role]==d['ref']}
                if len(anchors)!=1:continue
                anchor=next(iter(anchors))
            elif side=='tam':anchor='center'
            else:
                component=0 if side in ('trai','phai') else 1
                first=g['defpoint2'][component];second=g['defpoint3'][component]
                if abs(first-second)<1e-6:
                    anchor_conflicts.append((d['ref'],component,side));continue
                anchor='first' if ((first<second)==(side in ('trai','duoi'))) else 'second'
            from shapely.geometry import Polygon,Point
            polygon=Polygon([q[:2] for q in feature['points']]);holes=[]
            for e in context['entities']:
                if e['type']!='CIRCLE' or not e.get('geometry') or e.get('layout')!=feature['layout']:continue
                try:q=world(e)['geometry']['center']
                except ValueError:continue
                if polygon.contains(Point(q[:2])) and abs(q[2]-p[0,2])<1e-5:holes.append(e['ref'])
            recipe=LinearResize(part_code=code,dimension_ref=d['ref'],new_measurement=new,outline_refs=feature['refs'],hole_refs=holes,
                anchor=anchor,evidence_refs=sorted(set(feature['evidence_refs']+holes+[d['ref']])))
            candidates.append(recipe)
    if not candidates:
        # A source-proven dimension perpendicular to the requested hold cannot
        # determine which end to retain. Return the precise question directly;
        # sending the same ambiguity to a CPU vision model adds no evidence.
        if len(anchor_conflicts)==1:
            from backend.services.change_service import DrawingChangePlan
            ref,component,side=anchor_conflicts[0]
            return DrawingChangePlan(summary='Cần xác định mốc giữ theo hướng DIM nguồn.',target_part=code,edits=[],dependencies=[],operations=[],
                questions=[anchor_question(ref,code,side,component)],warnings=[])
        return None
    if len(candidates)>1:
        from graph.measured_views import coalesce_equivalent_recipes
        candidates=coalesce_equivalent_recipes(candidates,context)
    if len(candidates)>1 and not explicit_height:
        from graph.measured_views import expand
        try:equivalents=expand(candidates[:1],context)
        except ValueError:equivalents=[]
        if {r.dimension_ref for r in candidates}<={r.dimension_ref for r in equivalents}:
            candidates=candidates[:1]
        elif not (all(r.part_code==code for r in candidates) and
                  len({r.dimension_ref for r in candidates})==len(candidates) and
                  all(len(set(candidates[i].outline_refs)&set(candidates[j].outline_refs))==0
                      for i in range(len(candidates)) for j in range(i+1,len(candidates)))):
            return None
    from backend.services.change_service import DrawingChangePlan,EditProposal
    hold_label='mốc đã xác nhận theo từng DIM' if scoped_holds else keep[0] if keep else 'mốc liên kết đã xác nhận'
    plan=DrawingChangePlan(summary=f'Sửa profile đo thật {code}: {old:g} → {new:g} mm; giữ {hold_label}.',target_part=code,edits=[],dependencies=[],questions=[],warnings=[],resize_recipes=candidates)
    if code.startswith('BLOCK@'):
        plan.warnings.append('Block độc lập chưa có bảng kê: chỉ sửa hình học đo thật trong instance đã chọn; chưa có bằng chứng để đồng bộ vật tư hoặc các block khác.')
    number=re.compile(r'(?<![\d.])'+re.escape(f'{old:g}').replace(r'\.',r'[.,]')+r'(?![\d.])')
    rows=[(t,r) for t in context['entities'] for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
    for table,row in rows:
        cell=row.get('cells',{}).get('description',{});raw=cell.get('raw_text','')
        if len(number.findall(raw))!=1:return None
        for op in cell_operations(table,cell,number.sub(f'{new:g}',raw),by,'Đồng bộ BOM theo DIM/profile đã gắn nguồn'):
            plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='bom',before=op.before,after=op.after,reason=op.reason))
    # Source title/specification text is synchronized in a uniquely owned
    # detail sheet. Revision history and purchasing codes are not rewritten.
    from collections import defaultdict
    owners=defaultdict(set)
    for node in context.get('part_graph',{}).get('nodes',[]):
        for sid in node.get('detail_sheets',[]):owners[sid].add(node['code'])
    owned_sheets={sid for sid,c in owners.items() if c=={code}}
    instances={f['instance_ref'] for f in report['features'] if f.get('part_code')==code and f.get('instance_ref')}
    bom_cells={c.get('mirror_ref') for t in context['entities'] for r in t.get('bom',{}).get('rows',[]) for c in r.get('cells',{}).values()}
    from bom.stage_links import physical_spec
    specs={physical_spec(r['description']) for _,r in rows}
    if not specs:
        specs={physical_spec(r.get('description','')) for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==code for r in n.get('bom_occurrences',[])}
    for e in context['entities']:
        if e['type'] not in ('TEXT','MTEXT') or e['ref'] in bom_cells:continue
        native_owned=any(e['ref'].startswith(root+'/') for root in instances)
        spec_matched=physical_spec(e.get('text','')) in specs
        frame_owned=bool(owned_sheets.intersection(e.get('source_sheet_ids',[])))
        if not native_owned and not spec_matched and not (frame_owned and spec_matched):continue
        raw=e.get('raw_text',e.get('text',''))
        if 'ma vat tu' in normalized(raw):continue
        if not re.search(r'(?:\d\s*[x×]\s*'+re.escape(f'{old:g}')+r'|'+re.escape(f'{old:g}')+r'\s*[x×]\s*\d)',raw) or len(number.findall(raw))!=1:continue
        if any(op.ref==e['ref'] for op in plan.operations):continue
        from cad.edit_engine import Operation
        is_detail=bool(owned_sheets.intersection(e.get('source_sheet_ids',[])))
        reason='Đồng bộ quy cách trên bản chi tiết nguồn' if is_detail else 'Đồng bộ quy cách công đoạn / cắt phôi'
        after=number.sub(f'{new:g}',raw);op=Operation(ref=e['ref'],action='replace_text',before=raw,after=after,xyz=[],reason=reason)
        plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='annotation',before=raw,after=after,reason=op.reason))
    from backend.services.parametric_service import compile_recipes
    try:return compile_recipes(plan,context)
    except ValueError as error:
        print("DEBUG COMPILE_RECIPES ERROR:", error)
        from graph.parameter_links import active
        if active(context,[r.dimension_ref for r in plan.resize_recipes]):
            raise ValueError('Không thể sửa theo liên kết đã xác nhận: '+str(error)) from error
        return None
