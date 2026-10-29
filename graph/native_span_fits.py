"""Source-proven resizing between two externally held faces.

No filename/product mapping. Exact planar contacts, native identity and real
DIMs establish the constraint. A single moving wall also requires an explicit
overall hold with a real DIM. Unknown fixed faces do not authorize stretching
a recipient. Packaging uses its own adapters.
"""
import json,math,re
from typing import Literal
import numpy as np
from pydantic import BaseModel,ConfigDict,Field
from cad.geometry import near
from cad.frame_geometry import world
from graph.fit_constraints import measurement

TOL=1e-5
PREFIX='source-native-span-fit:'


class NativeSpanFit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    receiver_ref:str
    dimension_ref:str
    support_refs:list[str]=Field(min_length=2,max_length=2)
    support_dimension_refs:list[str]=Field(min_length=2,max_length=2)
    axis:Literal[0,1]
    analysis_angle:float=Field(default=0.,ge=0.,lt=math.pi/2,allow_inf_nan=False)
    sheet_id:str
    source_hash:str
    clearance_dimension_refs:list[str]=Field(default_factory=lambda:['',''],min_length=2,max_length=2)
    clearances:list[float]=Field(default_factory=lambda:[0.,0.],min_length=2,max_length=2)
    clearance_policy:Literal['native_dimension','source_faces_on_explicit_keep_gap_request']='native_dimension'
    peer_refs:list[str]=Field(default_factory=list,max_length=31)
    peer_dimension_refs:list[str]=Field(default_factory=list,max_length=31)
    inner_clearance_refs:list[str]=Field(default_factory=list,max_length=31)
    inner_clearances:list[float]=Field(default_factory=list,max_length=31)
    outside_dimension_ref:str=''
    fixed_support_refs:list[str]=Field(default_factory=list,max_length=1)


def attach_envelope_request(context,request,clarifications=None):
    """Only an explicit request may turn an overall annotation into a datum."""
    from bom.reader import normalized
    text=normalized('; '.join([request,*[c.get('answer','') for c in clarifications or []]]))
    phrase=r'(?:giu|giu nguyen)\s+kich thuoc\s+(?:ngoai\s+(?:cua\s+)?cum|tong the\s+(?:cua\s+)?cum)\b'
    matches=list(re.finditer(r'(?:^|[;,\n])\s*(?:va\s+)?'+phrase,text))
    positive=bool(matches)
    negative=bool(re.search(r'khong\s+'+phrase,text))
    if positive and negative:raise ValueError('Yêu cầu giữ kích thước ngoài cụm bị mâu thuẫn')
    context['preserve_native_assembly_envelope']=positive and not negative
    values=[]
    for match in matches:
        value=re.match(r'\s*(?:(?:la|bang|o)\s*|[:=]\s*)?(\d+(?:[.,]\d+)?)\s*mm\b',text[match.end():])
        if value:values.append(float(value.group(1).replace(',','.')))
    if values and any(not near(v,values[0],TOL) for v in values):raise ValueError('Số đo giữ ngoài cụm bị mâu thuẫn')
    context['preserved_native_span_mm']=values[0] if values else None
    gap_phrase=r'(?:giu|bao toan)\s+(?:nguyen\s+)?(?:cac\s+)?khe ho\s+(?:lap(?: ghep)?\s+)?(?:(?:cad|ban ve)\s+)?(?:nguon|goc)\b'
    gap_positive=bool(re.search(r'(?:^|[;,\n])\s*(?:va\s+)?'+gap_phrase,text))
    gap_negative=bool(re.search(r'khong\s+'+gap_phrase,text))
    if gap_positive and gap_negative:raise ValueError('Yêu cầu giữ khe hở nguồn bị mâu thuẫn')
    context['preserve_source_contact_gaps']=gap_positive and not gap_negative


def outside_dimension(left,right,axis,items,sid):
    """Unique real overall DIM whose endpoints touch the two exterior faces."""
    from graph.native_contacts import bounds
    from shapely.geometry import Polygon,Point
    from cad.dimensions import linear_axis
    a,b=bounds(left),bounds(right);found=[]
    pa,pb=Polygon([p[:2] for p in left]),Polygon([p[:2] for p in right])
    for e in items.values():
        if e['type']!='DIMENSION' or e.get('dimension_type') not in (0,1) or sid not in e.get('source_sheet_ids',[]) or e.get('review_only') or e.get('geometry',{}).get('text') not in ('','<>'):continue
        try:d=world(e);unit=linear_axis(d)
        except ValueError:continue
        if abs(abs(unit[axis])-1)>1e-7:continue
        g=d['geometry'];factor=abs(d.get('linear_factor',1))
        if factor<=0 or not near(d.get('scaled_measurement'),(b[1,axis]-a[0,axis])*factor,TOL):continue
        for k1,k2 in [('defpoint2','defpoint3'),('defpoint3','defpoint2')]:
            x,y=g[k1],g[k2]
            if near(x[2],a[0,2],TOL) and near(y[2],b[0,2],TOL) and near(x[axis],a[0,axis],TOL) and near(y[axis],b[1,axis],TOL) and pa.boundary.distance(Point(x[:2]))<TOL and pb.boundary.distance(Point(y[:2]))<TOL:
                found.append(e['ref']);break
    return found[0] if len(found)==1 else ''


def held_envelope(plan,context,by,local,old,driven,left,right,axis,sid):
    """Prove an explicit overall hold, shared by single and serial receivers.

    Unchanged geometry is not itself permission to use a face as a fixed datum.
    A unique native overall DIM must bind the exterior of this whole assembly.
    """
    if not context.get('preserve_native_assembly_envelope'):return '',[]
    if not near(old[left][0,axis],min(v[0,axis] for v in old.values()),TOL) or not near(old[right][1,axis],max(v[1,axis] for v in old.values()),TOL):return None
    outside=outside_dimension(local[left]['points'],local[right]['points'],axis,by,sid)
    if not outside:return None
    requested=context.get('preserved_native_span_mm')
    if requested is not None and not near(by[outside].get('scaled_measurement'),requested,TOL):
        raise ValueError('Số đo giữ ngoài cụm không khớp DIM nguồn; cần yêu cầu đổi kích thước tổng riêng')
    if any(o.ref==outside and o.action=='replace_geometry' for o in plan.operations):
        raise ValueError('DIM ngoài cụm phải giữ nguyên theo yêu cầu')
    return outside,[r for r in [left,right] if (r,axis) not in driven]


def measured_gap(a,b,axis,items,sid,occupied=(),allow_source_geometry=False):
    """A positive gap needs a true DIM or an explicit keep-source-gap rule.

    The opt-in only preserves the measured space between these actual parallel
    faces. It supplies no fixed datum, ownership, depth or attachment rule.
    """
    from graph.native_contacts import bounds,profile_contact
    from shapely.geometry import Polygon,Point
    from cad.dimensions import linear_axis
    ba,bb=bounds(a),bounds(b);gap=float(bb[0,axis]-ba[1,axis])
    if gap<-TOL:return None
    translated=[list(p) for p in b]
    for p in translated:p[axis]-=gap
    if profile_contact(a,translated)!=(axis,1,0):return None
    if abs(gap)<=TOL:return ('',0.)
    from shapely.geometry import box
    cross=1-axis;lo=max(ba[0,cross],bb[0,cross]);hi=min(ba[1,cross],bb[1,cross])
    corridor=box(ba[1,0],lo,bb[0,0],hi) if axis==0 else box(lo,ba[1,1],hi,bb[0,1])
    for points in occupied:
        body=bounds(points)
        if abs(body[0,2]-ba[0,2])>TOL:continue
        if min(body[1,axis],bb[0,axis])-max(body[0,axis],ba[1,axis])<=TOL or min(body[1,cross],hi)-max(body[0,cross],lo)<=TOL:continue
        if Polygon([p[:2] for p in points]).intersection(corridor).area>TOL*TOL:return None
    pa,pb=Polygon([p[:2] for p in a]),Polygon([p[:2] for p in b]);found=[];invalid=False
    for e in items.values():
        if e['type']!='DIMENSION' or e.get('dimension_type') not in (0,1) or sid not in e.get('source_sheet_ids',[]) or e.get('review_only') or not e.get('geometry'):continue
        try:
            d=world(e)
            # Inspect origins/orientation even for a literal annotation so
            # that it blocks a geometry-only fallback instead of vanishing.
            unit=linear_axis(dict(d,geometry=dict(d['geometry'],text='<>')))
        except ValueError:continue
        if abs(abs(unit[axis])-1)>1e-7:continue
        g=d['geometry'];factor=abs(d.get('linear_factor',1))
        for k1,k2 in [('defpoint2','defpoint3'),('defpoint3','defpoint2')]:
            x,y=g[k1],g[k2]
            if near(x[2],ba[0,2],TOL) and near(y[2],bb[0,2],TOL) and near(x[axis],ba[1,axis],TOL) and near(y[axis],bb[0,axis],TOL) and pa.boundary.distance(Point(x[:2]))<TOL and pb.boundary.distance(Point(y[:2]))<TOL:
                if g.get('text') not in ('','<>') or not math.isfinite(factor) or factor<=0 or not near(d.get('scaled_measurement'),gap*factor,TOL):invalid=True
                else:found.append(e['ref'])
                break
    if invalid:return None
    if len(found)==1:return found[0],gap
    if not found and allow_source_geometry:return '',gap
    return None


def _axis_proofs(plan,context):
    if context.get('units')!=4 or not context.get('source_hash'):return []
    if not context.get('source_features'):
        from cad.measured_features import index
        context=dict(context,source_features=index(context,context.get('part_graph')))
    from graph.native_contacts import inventory,bounds,profile_contact
    from cad.closed_profiles import polygon_from
    by,parts,sheets=inventory(context,allow_profiles=True)
    recipes={r.dimension_ref:r for r in plan.resize_recipes};ops={o.ref:o for o in plan.operations if o.action=='replace_geometry'}
    angle=context.get('contact_analysis_angle',0.)
    tagged={ref for p in plan.native_span_fits if near(p.analysis_angle,angle,1e-7)
            for ref in [p.receiver_ref,*p.peer_refs]}
    auto_codes={parts[r]['part_code'] for r in tagged if r in parts}
    result=[]
    roots=set(context.get('root_target_ids',[]))
    for sid in sorted(sheets,key=lambda s:(s not in roots,s)):
        local={r:f for r,f in parts.items() if sid in f['sheet_ids']}
        occupied=[f['points'] for f in local.values()]
        old={r:bounds(f['points']) for r,f in local.items()};after={};driven={};stationary={}
        for r,f in local.items():
            items=[world(dict(by[ref],geometry=json.loads(ops[ref].after))) if ref in ops else world(by[ref]) for ref in f['refs']]
            after[r]=bounds(polygon_from(items))
            if f['part_code'] in auto_codes:continue
            if any(o.ref==r and o.action=='move_insert' for o in plan.operations) or any(d.coordinate_rule and d.coordinate_rule.target_ref==r for d in plan.dependencies):continue
            for axis in (0,1):
                if context.get('preserve_native_assembly_envelope') and near(after[r][:,axis].tolist(),old[r][:,axis].tolist(),TOL):
                    fixed=[d for d in f['dimensions'] if abs(abs(d['axis'][axis])-1)<1e-7 and near(d['measurement']/d['linear_factor'],old[r][1,axis]-old[r][0,axis],TOL)]
                    if len(fixed)==1:stationary[(r,axis)]=fixed[0]
                candidates=[d for d in f['dimensions'] if d['ref'] in recipes and d['ref'] in ops and abs(abs(d['axis'][axis])-1)<1e-7 and
                    near(d['measurement']/d['linear_factor'],old[r][1,axis]-old[r][0,axis],TOL)]
                if len(candidates)!=1:continue
                d=candidates[0];recipe=recipes[d['ref']]
                actual=measurement(by[d['ref']],json.loads(ops[d['ref']].after))
                if recipe.new_measurement is None or not near(actual,recipe.new_measurement,TOL) or near(actual,d['measurement'],TOL):continue
                if not near(actual/d['linear_factor'],after[r][1,axis]-after[r][0,axis],TOL):continue
                driven[(r,axis)]=d
        for receiver,f in local.items():
            # Closed straight profiles may have notches. The measured resize
            # compiler independently checks edge directions, topology and holes;
            # a rectangular bounding box is neither required nor contact proof.
            if f['part_code'] not in auto_codes and any(ref in ops for ref in f['refs']):continue
            if any(o.ref==receiver and o.action=='move_insert' for o in plan.operations) and receiver not in tagged:continue
            for axis in (0,1):
                holders={**stationary,**driven}
                low={r:measured_gap(local[r]['points'],f['points'],axis,by,sid,occupied,context.get('preserve_source_contact_gaps',False)) for r in local if r!=receiver and (r,axis) in holders}
                high={r:measured_gap(f['points'],local[r]['points'],axis,by,sid,occupied,context.get('preserve_source_contact_gaps',False)) for r in local if r!=receiver and (r,axis) in holders}
                low={r:g for r,g in low.items() if g is not None};high={r:g for r,g in high.items() if g is not None}
                if len(low)!=1 or len(high)!=1:continue
                left,right=next(iter(low)),next(iter(high));gaps=[low[left][1],high[right][1]];gap_refs=[low[left][0],high[right][0]]
                if not any((r,axis) in driven for r in [left,right]):continue
                if not near(after[left][0,axis],old[left][0,axis],TOL) or not near(after[right][1,axis],old[right][1,axis],TOL):continue
                envelope=held_envelope(plan,context,by,local,old,driven,left,right,axis,sid)
                if envelope is None:continue
                outside,fixed_refs=envelope
                new_span=after[right][0,axis]-after[left][1,axis]-sum(gaps)
                if near(new_span,old[receiver][1,axis]-old[receiver][0,axis],TOL):continue
                dims=[d for d in f['dimensions'] if abs(abs(d['axis'][axis])-1)<1e-7 and near(d['measurement']/d['linear_factor'],old[receiver][1,axis]-old[receiver][0,axis],TOL)]
                if len(dims)!=1:raise ValueError('Thiếu DIM đo thật duy nhất cho chi tiết lắp giữa: '+f['part_code'])
                d=dims[0];target=new_span*d['linear_factor']
                if not math.isfinite(target) or target<=TOL:raise ValueError('Chi tiết lắp giữa không còn chiều dài hợp lệ sau sửa')
                if near(target,d['measurement'],TOL):continue
                g=world(by[d['ref']])['geometry'];anchor='first' if g['defpoint2'][axis]<g['defpoint3'][axis] else 'second'
                policy='source_faces_on_explicit_keep_gap_request' if any(g>TOL and not ref for g,ref in zip(gaps,gap_refs)) else 'native_dimension'
                binding=NativeSpanFit(receiver_ref=receiver,dimension_ref=d['ref'],support_refs=[left,right],support_dimension_refs=[holders[(left,axis)]['ref'],holders[(right,axis)]['ref']],axis=axis,sheet_id=sid,source_hash=context['source_hash'],clearance_dimension_refs=gap_refs,clearances=gaps,clearance_policy=policy,outside_dimension_ref=outside,fixed_support_refs=fixed_refs)
                refs=sorted(set(f['evidence_refs']+local[left]['evidence_refs']+local[right]['evidence_refs']+binding.support_dimension_refs+[d['ref'],receiver,left,right]+[r for r in [*gap_refs,outside] if r]))
                result.append(dict(binding=binding,part_code=f['part_code'],source_parts=[local[left]['part_code'],local[right]['part_code']],old_mm=d['measurement'],new_mm=target,anchor=anchor,evidence_refs=refs,
                    coefficients=[1/holders[(left,axis)]['linear_factor'],1/d['linear_factor'],1/holders[(right,axis)]['linear_factor']]))
        from graph.native_series_fits import proofs as series_proofs
        result.extend(series_proofs(plan,context,by,local,old,after,driven,sid,auto_codes,tagged,stationary))
        if context.get('preserve_native_assembly_envelope'):
            for axis in {k for _,k in driven}:
                if not any(p['binding'].sheet_id==sid and p['binding'].axis==axis and p['binding'].outside_dimension_ref for p in result):
                    raise ValueError('Chưa gắn được DIM ngoài cụm và hai mặt lắp để giữ kích thước tổng; không tự dịch mặt đối diện.')
    # A selected block and its containing sheet can describe exactly the same
    # native assembly. Count that proof once, preferring the selected target;
    # different supports/clearances for the same DIM remain an ambiguity.
    unique={}
    for p in result:
        key=p['binding'].dimension_ref
        previous=unique.get(key)
        if previous:
            a=previous['binding'].model_dump(exclude={'sheet_id'})
            b=p['binding'].model_dump(exclude={'sheet_id'})
            if a!=b or any(previous[k]!=p[k] for k in ('part_code','new_mm','anchor','coefficients')):
                raise ValueError('Mốc co/giãn chi tiết nhận không duy nhất')
            continue
        unique[key]=p
    result=list(unique.values())
    # Reusing a purchasing code cannot silently create differently sized parts.
    values={}
    for p in result:
        key=(p['part_code'],p['binding'].axis)
        if key in values and not near(values[key],p['new_mm'],TOL):raise ValueError('Một mã chi tiết có các lòng lắp yêu cầu kích thước khác nhau')
        values[key]=p['new_mm']
    if len({p['binding'].dimension_ref for p in result})!=len(result):raise ValueError('Mốc co/giãn chi tiết nhận không duy nhất')
    for receiver in {p['binding'].receiver_ref for p in result}:
        axes=[p['binding'].axis for p in result if p['binding'].receiver_ref==receiver]
        if len(axes)>2 or len(axes)!=len(set(axes)):
            raise ValueError('Mốc co/giãn chi tiết nhận không độc lập theo hai trục')
    return result


def proofs(plan,context):
    """Reconstruct each fit in the orthogonal basis measured from its drivers.

    The angle is source evidence, never a user-supplied projection or an
    operation on the document. Recipes and output geometry stay native.
    """
    if context.get('units')!=4 or not context.get('source_hash'):return []
    from graph.contact_frames import angles,rotated
    contexts=[context]+[rotated(context,a) for a in angles(plan,context)]
    found={};receiver_angles={}
    for basis in contexts:
        angle=basis.get('contact_analysis_angle',0.)
        for proof in _axis_proofs(plan,basis):
            binding=proof['binding'];binding.analysis_angle=angle
            for ref in [binding.receiver_ref,*binding.peer_refs]:
                previous=receiver_angles.setdefault(ref,angle)
                if not near(previous,angle,1e-7):
                    raise ValueError('Một chi tiết nhận có các hệ trục lắp ghép không vuông góc')
            prior=found.get(binding.dimension_ref)
            if prior:
                if prior['binding']!=binding or not near(prior['new_mm'],proof['new_mm'],TOL):
                    raise ValueError('Mốc co/giãn chi tiết nhận không duy nhất trong cụm xoay')
                continue
            found[binding.dimension_ref]=proof
    if context.get('preserve_native_assembly_envelope') and not found:
        from cad.measured_features import index
        features=(context.get('source_features') or index(context,context.get('part_graph')))['features']
        from graph.native_instances import inventory
        _,identities,_=inventory(context)
        refs={r for f in features if identities.get(f.get('instance_ref'))==f.get('part_code') and f.get('instance_ref') for r in f['refs']}
        roots={f['instance_ref'] for f in features if f.get('instance_ref')}
        changed=any(o.ref in refs and o.action=='replace_geometry' and not near(json.loads(o.before),json.loads(o.after),TOL)
                    or o.ref in roots and o.action=='move_insert' for o in plan.operations)
        if changed:raise ValueError('Chưa gắn được DIM ngoài cụm và các recipe mặt lắp để giữ kích thước tổng')
    return list(found.values())


def equation(proof):
    from graph.measurement_rules import MeasurementEquation,MeasurementTerm
    b=proof['binding'];refs=[b.support_dimension_refs[0],b.dimension_ref,*b.peer_dimension_refs,b.support_dimension_refs[1]]
    if len(set(refs))!=len(refs):raise ValueError('DIM hai mặt giữ và các chi tiết nhận phải riêng biệt')
    return MeasurementEquation(terms=[MeasurementTerm(dimension_ref=r,coefficient=v) for r,v in zip(refs,proof['coefficients'])],evidence_refs=proof['evidence_refs'])


def recipe(proof,plan,context):
    from graph.parameter_links import add_recipe
    r=add_recipe(plan,context,proof['binding'].dimension_ref,proof['anchor'])
    if r.new_measurement is not None and not near(r.new_measurement,proof['new_mm'],TOL):raise ValueError('Recipe chi tiết nhận xung đột hai mặt lắp')
    r.new_measurement=proof['new_mm'];r.evidence_refs=sorted(set(r.evidence_refs+proof['evidence_refs']))
    return r


def recipes_for(proof,plan,context):
    first=recipe(proof,plan,context);result=[first]
    if not proof['binding'].peer_refs:return result
    from graph.measured_views import expand
    candidates={r.dimension_ref:r for r in expand([first],context)}
    for ref in proof['binding'].peer_dimension_refs:
        if ref not in candidates:raise ValueError('Chi tiết nối tiếp chưa có định nghĩa/recipe native tương đương')
        r=candidates[ref];previous=next((a for a in plan.resize_recipes if a.dimension_ref==ref),None)
        if previous:
            if previous.anchor!=r.anchor or previous.part_code!=r.part_code or set(previous.outline_refs)!=set(r.outline_refs) or set(previous.hole_refs)!=set(r.hole_refs) or previous.new_measurement is not None and not near(previous.new_measurement,r.new_measurement,TOL):
                raise ValueError('Recipe chi tiết nối tiếp xung đột định nghĩa CAD nguồn')
            previous.new_measurement=r.new_measurement;r=previous
        else:plan.resize_recipes.append(r)
        result.append(r)
    return result


def text_changes(plan,context,recipes):
    """Compose proven numeric replacements using positions in source cells.

    Never substitute into an already changed value: one target may equal the
    other source DIM. Repeated source numbers remain ambiguous and are rejected
    by sync_text. Only its exact source-bound replacements can be combined.
    """
    import re
    from graph.parameter_links import sync_text
    grouped={}
    by={e['ref']:e for e in context['entities']}
    for r in recipes:
        probe=plan.model_copy(update=dict(operations=[],edits=[]))
        sync_text(probe,context,r,r.new_measurement)
        old=measurement(by[r.dimension_ref],by[r.dimension_ref]['geometry'])
        pattern=re.compile(r'(?<![\d.])'+re.escape(f'{old:g}').replace(r'\.',r'[.,]')+r'(?![\d.])')
        for op in probe.operations:
            matches=list(pattern.finditer(op.before))
            replacement=f'{r.new_measurement:g}'
            if len(matches)!=1 or pattern.sub(replacement,op.before)!=op.after:
                raise ValueError('Thay đổi quy cách không có vị trí số nguồn duy nhất')
            match=matches[0];key=(op.ref,op.cell_index)
            edit=next(e for e in probe.edits if e.entity_ref==op.ref)
            entry=grouped.setdefault(key,dict(operation=op,edit=edit,replacements={}))
            if entry['operation'].before!=op.before or entry['operation'].action!=op.action or entry['edit'].part_number!=edit.part_number:
                raise ValueError('Các DIM sửa mâu thuẫn chủ sở hữu ô quy cách')
            position=(match.start(),match.end());previous=entry['replacements'].get(position)
            if previous is not None and previous!=replacement:
                raise ValueError('Các DIM yêu cầu giá trị khác nhau cho cùng số trong BOM')
            entry['replacements'][position]=replacement
    result=[]
    for entry in grouped.values():
        op=entry['operation'].model_copy();after=op.before;last=len(after)
        for (start,end),replacement in sorted(entry['replacements'].items(),reverse=True):
            if end>last:raise ValueError('Các vị trí kích thước trong BOM bị chồng nhau')
            after=after[:start]+replacement+after[end:];last=start
        op.after=after
        edit=entry['edit'].model_copy(update=dict(after=after))
        result.append((op,edit))
    return result


def synchronize(plan,context):
    if plan.questions or not plan.operations:return plan
    if not context.get('source_features'):
        from cad.measured_features import index
        context=dict(context,source_features=index(context,context.get('part_graph')))
    found=proofs(plan,context);bindings=[p['binding'] for p in found]
    if any(p not in bindings for p in plan.native_span_fits):raise ValueError('Liên kết co/giãn native không còn khớp nguồn hoặc mốc giữ')
    if not found:return plan
    from backend.services.change_service import DependencyProposal
    before=(len(plan.resize_recipes),len(plan.operations))
    receivers=[]
    for p in found:
        b=p['binding'];group=recipes_for(p,plan,context);receivers.extend(group)
        if b not in plan.native_span_fits:plan.native_span_fits.append(b)
        rel=PREFIX+b.dimension_ref;eq=equation(p)
        previous=next((d for d in plan.dependencies if d.relationship==rel),None)
        if previous and previous.equation_rule!=eq:raise ValueError('Phương trình co/giãn native đã bị thay đổi')
        if previous is None:
            plan.dependencies.append(DependencyProposal(source_part=', '.join(p['source_parts']),target_part=p['part_code'],relationship=rel,evidence_refs=p['evidence_refs'],
                required_change=f'Co/giãn {p["old_mm"]:g} → {p["new_mm"]:g} mm cho {1+len(b.peer_refs)} chi tiết giữa hai mặt lắp; giữ hai mốc ngoài nguồn.',needs_confirmation=True,equation_rule=eq))
    for op,edit in text_changes(plan,context,receivers):
        existing=next((o for o in plan.operations if (o.ref,o.cell_index)==(op.ref,op.cell_index)),None)
        if existing:
            from graph.native_instances import equivalent_operation
            if not equivalent_operation(existing,op):raise ValueError('Thay đổi BOM xung đột các mặt lắp nguồn')
        else:
            plan.operations.append(op);plan.edits.append(edit)
    if before!=(len(plan.resize_recipes),len(plan.operations)):
        from backend.services.parametric_service import compile_recipes
        plan=compile_recipes(plan,context)
        from graph.native_instances import synchronize as sync_instances
        plan=sync_instances(plan,context)
    return plan


def validate(plan,context):
    if plan.questions or not plan.operations:return
    if not context.get('source_features'):
        from cad.measured_features import index
        context=dict(context,source_features=index(context,context.get('part_graph')))
    found=proofs(plan,context);bindings=[p['binding'] for p in found]
    if len(bindings)!=len(plan.native_span_fits) or any(b not in plan.native_span_fits for b in bindings):raise ValueError('Thiếu/sai liên kết co/giãn chi tiết giữa hai mặt lắp')
    if not found:return
    from cad.multi_resize import resize_many
    from graph.native_instances import equivalent_operation
    probe=plan.model_copy(deep=True);receivers=[]
    for p in found:
        required={p['binding'].dimension_ref,*p['binding'].peer_dimension_refs}
        if not required<={r.dimension_ref for r in plan.resize_recipes}:raise ValueError('Thiếu recipe cho chi tiết nhận/nối tiếp')
        receivers.extend(recipes_for(p,probe,context))
        dep=next((d for d in plan.dependencies if d.relationship==PREFIX+p['binding'].dimension_ref),None)
        if not dep or dep.equation_rule!=equation(p):raise ValueError('Thiếu/sai phương trình co/giãn native')
    expected=resize_many(receivers,context,{r.dimension_ref:r.new_measurement for r in receivers})
    expected+=[op for op,_ in text_changes(probe,context,receivers)]
    for o in expected:
        matches=[a for a in plan.operations if a.ref==o.ref and a.cell_index==o.cell_index]
        if len(matches)!=1 or not equivalent_operation(matches[0],o):raise ValueError('Thiếu/sai hình, DIM hoặc BOM chi tiết co/giãn: '+o.ref)
