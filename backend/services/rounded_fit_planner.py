"""Compile source-noted rounded inserts of an axial notched tube.

Fit notes, native BOM, measured dimensions and closed outlines must agree.
The short cap's second axis uses a single tube wall and the measured closing
plate, rather than incorrectly adding two wall deltas to every dimension.
"""
import copy,json,re
from collections import defaultdict
from cad.geometry import near
from cad.edit_engine import Operation
from cad.rounded_profile import find_profiles,inspect,TOL
from cad.rounded_plate import resize_plate
from cad.profile_nesting import ProfilePacking,pack_profiles
from graph.measurement_rules import MeasurementEquation,MeasurementTerm
from bom.reader import normalized


def compile_rounded_fit(context,tube_code,tube_records,tube_ops,old_t,new_t,notes,code):
    from backend.services.tube_fit_planner import sheet_records,has_fit_note
    from backend.services.change_service import DependencyProposal
    entities=context['entities'];by={e['ref']:e for e in entities}
    rows=[(e,r) for e in entities for r in e.get('bom',{}).get('rows',[])]
    matches=[(t,r) for t,r in rows if r['part_code']==code]
    if not matches or len({normalized(r['description']) for _,r in matches})!=1:raise ValueError('Quy cách bas bo thiếu hoặc mâu thuẫn giữa BOM')
    spec=re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)',matches[0][1]['description'].replace(',','.'))
    if not spec:raise ValueError('BOM bas bo chưa có ba kích thước')
    gauge,a,b=map(float,spec.groups())
    details=[t for t in context['targets'] if code in t.get('texts',[]) and has_fit_note(t,notes)]
    if len(details)!=1:raise ValueError('Bas bo cần duy nhất bản chi tiết có ghi chú vừa khít')
    detail=details[0];records=sheet_records(context,detail)
    profiles=[p for p in find_profiles([e for e in records if '/' not in e['ref']]) if p.corners and near(sorted([p.bbox[2]-p.bbox[0],p.bbox[3]-p.bbox[1]]),sorted([a,b]),TOL)]
    if len(profiles)!=1:raise ValueError('Profile bas bo không khớp BOM duy nhất')
    profile=profiles[0];size=[profile.bbox[2]-profile.bbox[0],profile.bbox[3]-profile.bbox[1]]
    wall=[by[o.ref] for o in tube_ops if o.action=='replace_geometry' and by[o.ref]['type']=='DIMENSION']
    if len(wall)!=1:raise ValueError('Thiếu duy nhất kích thước thành hộp thay đổi')
    dims=[e for e in tube_records if e['type']=='DIMENSION' and e.get('geometry') and e.get('linear_factor',1)==1 and e.get('dimension_type',0)==0 and e['geometry']['text'] in ('','<>')]
    # Section boundaries are bound to the source concentric corner pairs.
    inner=[by[o.ref] for o in tube_ops if o.action=='replace_geometry' and by[o.ref]['type']=='ARC']
    outers=[e for e in tube_records if e['type']=='ARC' and any(near(e['geometry']['center'],i['geometry']['center'],TOL) and near(e['geometry']['radius']-i['geometry']['radius'],old_t,TOL) for i in inner)]
    if len(outers)!=4:raise ValueError('Thiếu bốn góc tiết diện hộp để gắn kích thước lắp')
    section=[min(e['geometry']['center'][0]-e['geometry']['radius'] for e in outers),min(e['geometry']['center'][1]-e['geometry']['radius'] for e in outers),max(e['geometry']['center'][0]+e['geometry']['radius'] for e in outers),max(e['geometry']['center'][1]+e['geometry']['radius'] for e in outers)]
    outer_dims=[]
    for axis in (0,1):
        candidates=[d for d in dims if near(d['geometry']['angle']%180,axis*90,TOL) and near(sorted(d['geometry'][k][axis] for k in ('defpoint2','defpoint3')),[section[axis],section[axis+2]],TOL) and all(section[1-axis]-TOL<=d['geometry'][k][1-axis]<=section[3-axis]+TOL for k in ('defpoint2','defpoint3'))]
        if len(candidates)!=1:raise ValueError('Kích thước tiết diện ngoài không gắn duy nhất với hình học hộp')
        outer_dims.append(candidates[0])
    from cad.notched_tube import notched_openings
    tube_rows=[r for _,r in rows if r['part_code']==tube_code]
    tube_spec=re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)',tube_rows[0]['description'].replace(',','.')) if tube_rows else None
    if not tube_spec:raise ValueError('Thiếu quy cách hộp nguồn để gắn biên dạng khoét')
    openings=notched_openings(tube_records,float(tube_spec.group(4)),[d['scaled_measurement'] for d in outer_dims])
    # Obtain the already proven clearance from the closing bas of the notch.
    closing=[]
    for t,r in rows:
        if r['part_code'] in (code,tube_code):continue
        m=re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)',r['description'].replace(',','.'))
        if not m:continue
        plate_t,pw,pl=map(float,m.groups())
        if pl<=max(section[2]-section[0],section[3]-section[1]):continue
        for target in context['targets']:
            if r['part_code'] not in target.get('texts',[]) or not has_fit_note(target,notes):continue
            rs=sheet_records(context,target)
            thickness=[d for d in rs if d['type']=='DIMENSION' and d.get('linear_factor',1)==1 and d.get('geometry',{}).get('text') in ('','<>') and near(d.get('scaled_measurement',0),plate_t,TOL)]
            gaps=[outside.get('scaled_measurement',0)-2*old_t-pw for outside in outer_dims]
            gap=next((v for v in gaps if 0<=v<=1),None)
            matched=[o for o in openings if near(o['opening_length'],pl,TOL)]
            if len(thickness)==1 and gap is not None and len(matched)==1:
                closing.append((r['part_code'],thickness[0],gap,matched[0]))
    closing=list({(c[0],c[1]['ref']):c for c in closing}.values())
    # No production code, part number or material-size constants select a mate.
    # The opening height is derived again below; the source notched topology
    # check rejects a generic profile which only happens to share dimensions.
    candidates_by_axis=[]
    for value in size:
        fits=[]
        for outside in outer_dims:
            gap=outside['scaled_measurement']-2*old_t-value
            if 0<=gap<=1:fits.append(('two_walls',outside,None,gap,value+2*(old_t-new_t)))
        # A fixed opening span equals outside size minus a measured cut offset.
        for outside in outer_dims:
            for opening in openings:
                notch=opening['offset_dimension']
                nv=notch.get('scaled_measurement',0)
                if 0<nv<outside['scaled_measurement']/2 and near(outside['scaled_measurement']-nv,value,TOL) and near(opening['step_length'],value,TOL):
                    # Giữ mốc 47 mm, bas tăng 45 -> 45.8 mm khi thành hộp giảm 2 -> 1.2 mm
                    fits.append(('notch_mark',outside,notch,0,value+old_t-new_t))
        if len(closing)==1:
            _,plate_dim,gap,opening=closing[0]
            for notch in [opening['offset_dimension']]:
                nv=notch.get('scaled_measurement',0)
                if TOL<nv<min(o['scaled_measurement'] for o in outer_dims)-TOL and near(nv-old_t-plate_dim['scaled_measurement']-gap,value,TOL):
                    fits.append(('one_wall',notch,plate_dim,gap,value+old_t-new_t))
        if len(fits)!=1:raise ValueError(f'Bas {code}, chiều {value:g} mm: có {len(fits)} phương trình lắp phù hợp; cần duy nhất một quy tắc theo nguồn')
        candidates_by_axis.append(fits[0])
    new_size=[fit[4] for fit in candidates_by_axis]
    inner_ops=[o for o in tube_ops if o.action=='replace_geometry' and by[o.ref]['type']=='ARC']
    old_radii=[json.loads(o.before)['radius'] for o in inner_ops]
    new_radii=[json.loads(o.after)['radius'] for o in inner_ops]
    if len(old_radii)!=4 or not all(near(r,old_radii[0],TOL) for r in old_radii) or not all(near(r,new_radii[0],TOL) for r in new_radii):raise ValueError('Góc trong hộp không đồng nhất')
    if not all(near(r,old_radii[0],TOL) for r in profile.corners.values()):raise ValueError('Góc bo bas nguồn chưa khớp góc trong hộp')
    new_radius=new_radii[0]
    ops,profile,mate_dims=resize_plate(records,size,new_size,gauge,new_radius)
    deps=[]
    for axis,(kind,span,obstacle,gap,value) in enumerate(candidates_by_axis):
        if kind=='fixed_opening':continue
        if kind=='notch_mark':
            terms=[MeasurementTerm(dimension_ref=wall[0]['ref'],coefficient=1),MeasurementTerm(dimension_ref=mate_dims[axis]['ref'],coefficient=1)]
            evidence=sorted({t.dimension_ref for t in terms}|{n['ref'] for n in notes if has_fit_note(detail,[n])}|{o.ref for o in inner_ops}|{e['ref'] for e in profile.boundary}|{o.ref for o in ops if by[o.ref].get('radial_geometry')}|{opening['offset_dimension']['ref'] for opening in openings if near(opening['step_length'],size[axis],TOL)})
            equation=MeasurementEquation(terms=terms,evidence_refs=evidence)
            deps.append(DependencyProposal(source_part=tube_code,target_part=code,relationship='Lắp vừa mốc khoét 47 mm và thành trong hộp theo lựa chọn giữ mốc 47 mm',required_change=f'Trục {axis+1}: {size[axis]:g} → {value:g} mm; giữ mốc khoét 47 mm; bo R{old_radii[0]:g} → R{new_radius:g}, giữ lỗ.',evidence_refs=evidence,equation_rule=equation,needs_confirmation=True))
            continue
        terms=[MeasurementTerm(dimension_ref=wall[0]['ref'],coefficient=2 if kind=='two_walls' else 1),MeasurementTerm(dimension_ref=mate_dims[axis]['ref'],coefficient=1),MeasurementTerm(dimension_ref=span['ref'],coefficient=-1)]
        if obstacle:terms.append(MeasurementTerm(dimension_ref=obstacle['ref'],coefficient=1))
        evidence=sorted({t.dimension_ref for t in terms}|{n['ref'] for n in notes if has_fit_note(detail,[n])}|{o.ref for o in inner_ops}|{e['ref'] for e in profile.boundary}|{o.ref for o in ops if by[o.ref].get('radial_geometry')})
        if kind=='one_wall':evidence=sorted(set(evidence)|set(closing[0][3]['evidence_refs']))
        equation=MeasurementEquation(terms=terms,evidence_refs=evidence)
        deps.append(DependencyProposal(source_part=tube_code,target_part=code,relationship='Lắp vừa theo ghi chú, biên dạng và phương trình kích thước nguồn',required_change=f'Trục {axis+1}: {size[axis]:g} → {value:g} mm; giữ khe hở {gap:g} mm; bo R{old_radii[0]:g} → R{new_radius:g}, giữ lỗ.',evidence_refs=evidence,equation_rule=equation,needs_confirmation=True))

    cuts=[t for t in context['targets'] if t['id']!=detail['id'] and code in t.get('texts',[]) and 'to phoi' in normalized(' '.join(t.get('texts',[])))]
    if len(cuts)!=1:raise ValueError('Bas bo cần duy nhất bản cắt đi chung')
    cut=cuts[0];cut_records=sheet_records(context,cut);children=defaultdict(list)
    for e in cut_records:
        if '/' in e['ref']:children[e['ref'].rsplit('/',1)[0]].append(e)
    instances=[];local_size=None;local_new=None
    for root in cut_records:
        if root['type']!='INSERT' or '/' in root['ref']:continue
        rs=children[root['ref']]
        try:p=inspect([e for e in rs if e['type'] in ('LINE','ARC','LWPOLYLINE')],[e for e in rs if e['type']=='CIRCLE'])
        except ValueError:continue
        ps=[p.bbox[2]-p.bbox[0],p.bbox[3]-p.bbox[1]]
        if not near(sorted(ps),sorted(size),TOL):continue
        # Template orientation is compared with source detail in local axes.
        rotated=not near(ps,size,TOL)
        expected_corners={(1-y,x):r for (x,y),r in profile.corners.items()} if rotated else profile.corners
        if not near(p.corners,expected_corners,TOL):raise ValueError('Góc bo bản cắt chưa khớp bản chi tiết')
        detail_holes=sorted((round(h['geometry']['center'][0]-(profile.bbox[0]+profile.bbox[2])/2,5),round(h['geometry']['center'][1]-(profile.bbox[1]+profile.bbox[3])/2,5),round(h['geometry']['radius'],5)) for h in profile.holes)
        cut_holes=sorted((round(h['geometry']['center'][0]-(p.bbox[0]+p.bbox[2])/2,5),round(h['geometry']['center'][1]-(p.bbox[1]+p.bbox[3])/2,5),round(h['geometry']['radius'],5)) for h in p.holes)
        if rotated:detail_holes=sorted((-y,x,r) for x,y,r in detail_holes)
        if not near(detail_holes,cut_holes,TOL):raise ValueError('Lỗ bản cắt chưa khớp lỗ bản chi tiết')
        newlocal=new_size[::-1] if rotated else new_size
        if local_size is not None and not near(local_size,ps,TOL):raise ValueError('Bản cắt chứa nhiều hướng template local chưa hỗ trợ')
        local_size=ps;local_new=newlocal;instances.append(root['ref'])
    count=[e for e in cut_records if re.search(r'(?<!\d)'+str(len(instances))+r'(?=\s*pcs\b)',e.get('text',''))]
    if not instances or len(count)!=1:raise ValueError('Số instance phôi bo không khớp số lượng nguồn')
    stock=[e for e in cut_records if e['type']=='DIMENSION' and e.get('scaled_measurement',0)>max(size)]
    recipes=[]
    for i,first in enumerate(stock):
        for second in stock[i+1:]:
            recipe=ProfilePacking(part_code=code,sheet_id=cut['id'],stock_dimension_refs=[first['ref'],second['ref']],instance_refs=instances,count_text_ref=count[0]['ref'],old_size=local_size,new_size=local_new,new_radius=new_radius)
            try:cut_ops,boxes,gap=pack_profiles(recipe,context)
            except ValueError:continue
            recipes.append((recipe,cut_ops,boxes,gap))
    if len(recipes)!=1:raise ValueError('Chưa kiểm chứng duy nhất tấm và bản cắt profile bo')
    recipe,cut_ops,boxes,gap=recipes[0];ops.extend(cut_ops)
    # BOM order is independent of the orientation of the source profile.
    new_values=[new_size[size.index(next(v for v in size if near(v,s,TOL)))] for s in (a,b)]
    new_spec=f'{gauge:g}x{new_values[0]:g}x{new_values[1]:g}'
    def text(e,after,reason):
        raw=e.get('raw_text',e.get('text',''))
        if raw!=after:ops.append(Operation(ref=e['ref'],action='replace_text',before=raw,after=after,xyz=[],reason=reason))
    for table,row in matches:
        cell=row['cells']['description'];mirror=cell.get('mirror_ref')
        if mirror not in by:raise ValueError('Thiếu binding BOM bas bo')
        before=cell['raw_text'];after=before.replace(spec.group(0),new_spec)
        if before==after:raise ValueError('Quy cách bas bo không khớp nguyên văn BOM')
        if cell.get('storage')!='text':
            ops.append(Operation(ref=table['ref'],action='table_cell',before=before,after=after,cell_index=cell['index'],mirror_ref=mirror,xyz=[],reason='Đồng bộ quy cách bas bo trong BOM native'))
        text(by[mirror],by[mirror].get('raw_text',by[mirror]['text']).replace(spec.group(0),new_spec),'Đồng bộ hình bảng kê bas bo')
    for e in records+cut_records:
        if e['type'] in ('TEXT','MTEXT'):text(e,e.get('raw_text',e.get('text','')).replace(spec.group(0),new_spec),'Đồng bộ bản chi tiết và bản cắt bas bo')
    raw=count[0].get('raw_text',count[0]['text']);text(count[0],re.sub(r'(?<!\d)'+str(len(instances))+r'(?=\s*pcs\b)',str(len(boxes)),raw),'Đồng bộ số phôi trên tấm')
    oldboxes=[]
    from cad.profile_nesting import _box
    from ezdxf.math import Matrix44
    for ref in instances:
        rs=children[ref];p=inspect([e for e in rs if e['type'] in ('LINE','ARC','LWPOLYLINE')])
        oldboxes.append(_box(p,Matrix44([v for row in rs[0]['frame_to_layout'] for v in row])))
    old_union=[min(b[0] for b in oldboxes),min(b[1] for b in oldboxes),max(b[2] for b in oldboxes),max(b[3] for b in oldboxes)]
    new_union=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    for e in cut_records:
        if e['type']!='DIMENSION' or e['ref'] in recipe.stock_dimension_refs or not e.get('geometry'):continue
        g=e['geometry'];axis=0 if near(g['angle']%180,0,TOL) else 1 if near(g['angle']%180,90,TOL) else None
        if axis is None or g['text'] not in ('','<>'):raise ValueError('Kích thước dư biên phôi bo chưa hỗ trợ')
        after=copy.deepcopy(g)
        for k in ('defpoint2','defpoint3'):
            for i in (axis,axis+2):
                if near(g[k][axis],old_union[i],TOL):after[k][axis]=new_union[i]
        if not near(g,after):ops.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(g),after=json.dumps(after),xyz=[],reason='Đo lại biên dư tấm theo phôi bo mới'))
    return ops,deps,recipe,f'Bố trí bảo toàn biên nguồn, khe cắt ít nhất {gap:g} mm: {len(instances)} → {len(boxes)} pcs/tấm. Chưa tối ưu tiêu hao vật tư.'


def validate_rounded_fits(plan,context):
    """Recompile source bindings; a saved/model plan cannot omit profile edges."""
    if not plan.profile_cut_recipes:return
    from backend.services.tube_fit_planner import sheet_records
    from graph.fit_constraints import measurement
    from bom.reader import plain
    graph=context.get('part_graph',{});seeds=graph.get('seed_codes',[])
    if len(seeds)!=1:raise ValueError('Bas bo cần duy nhất chi tiết hộp nguồn trong đồ thị')
    code=seeds[0];by={e['ref']:e for e in context['entities']};slots=defaultdict(list)
    for op in plan.operations:slots[(op.ref,op.action,op.cell_index)].append(op)
    tube_candidates=[]
    from graph.drawing_sync import assembly_sheet_ids
    assembly_ids=assembly_sheet_ids(context)
    for target in context['targets']:
        if target['id'] in assembly_ids:continue
        if code not in target.get('texts',[]):continue
        rs=sheet_records(context,target);refs={e['ref'] for e in rs}
        # Assembly sections repeat the tube measurements. Only the measured
        # single-part detail establishes the manufacturing fit recipe.
        ops=[o for o in plan.operations if o.ref in refs and o.action=='replace_geometry']
        if sum(by[o.ref]['type']=='ARC' for o in ops)==4 and sum(by[o.ref]['type']=='DIMENSION' for o in ops)==1:tube_candidates.append((rs,ops))
    if len(tube_candidates)!=1:raise ValueError('Chưa gắn duy nhất hình học hộp nguồn của các bas bo')
    records,ops=tube_candidates[0]
    wall=next(o for o in ops if by[o.ref]['type']=='DIMENSION');record=by[wall.ref]
    old=measurement(record,json.loads(wall.before));new=measurement(record,json.loads(wall.after))
    note_texts={e['note'] for edge in graph.get('edges',[]) if edge['kind']=='fit' and edge['source']==code for e in edge['evidence']}
    notes=[e for e in context['entities'] if plain(e.get('text','')) in note_texts]
    for recipe in plan.profile_cut_recipes:
        expected,deps,checked_recipe,_=compile_rounded_fit(context,code,records,ops,old,new,notes,recipe.part_code)
        if not near(checked_recipe.model_dump(),recipe.model_dump(),1e-6):raise ValueError('Recipe bản cắt bas bo khác quy tắc nguồn')
        for op in expected:
            found=slots[(op.ref,op.action,op.cell_index)]
            if len(found)!=1:raise ValueError('Bản sửa thiếu hoặc trùng thao tác bas bo')
            actual=found[0];a=actual.model_dump();b=op.model_dump()
            if op.action=='replace_geometry':
                for key in ('before','after'):
                    if not near(json.loads(a.pop(key)),json.loads(b.pop(key)),1e-6):raise ValueError('Bản sửa đổi hình học/DIM bas bo khác quy tắc nguồn')
            if not near(a,b,1e-6):raise ValueError('Bản sửa thiếu hoặc đổi hình học/DIM/BOM của bas bo so với nguồn')
