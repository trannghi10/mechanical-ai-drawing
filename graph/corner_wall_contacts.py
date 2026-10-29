"""Source-measured three-layer contacts in a circular 2D detail callout.

Requires a hash-bound human wall correction, executed cap/shell drivers,
three genuine orthogonal DIMs and a closed receiver touching the inner face.
This is a detail illustration adapter; it never certifies an entire assembly.
"""
import copy,json,math,re
from itertools import product
from cad.geometry import near
from cad.frame_geometry import world,local_geometry,matrix,transform
from cad.dimensions import linear_axis
from cad.edit_engine import Operation
from cad.broken_tube import tube_spec
from graph.packing_side_layers import rect
from graph.confirmed_inner_panels import proofs as panel_proofs
from bom.reader import normalized

TOL=1e-3

def proofs(plan,context):
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash') or context.get('units')!=4:return []
    corrections=[c for c in choices.get('confirmed_choices',[]) if c.get('key')=='assembly_tube_gauge_correction' and c.get('policy')=='use_verified_bom_wall_thickness']
    if not corrections:return []
    records={e['ref']:e for e in context['entities']};frames=panel_proofs(plan,context);result=[]
    for correction in corrections:
        related=[f for f in frames if f['product_code']==correction['product_code']]
        if len(related)!=1:continue
        frame=related[0]
        rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==correction['part_code']]
        specs={tube_spec(r['description']) for _,r in rows}
        if len(specs)!=1 or None in specs or any(t['bom'].get('status')!='verified_template' for t,_ in rows):continue
        spec=next(iter(specs))
        if not near(spec[2],correction['after_mm'],TOL):raise ValueError('Độ dày thành hộp đã chốt khác BOM nguồn')
        sids=set(correction['sheet_ids']);eligible=[]
        for e in records.values():
            if not sids.intersection(e.get('source_sheet_ids',[])) or e['type']!='DIMENSION' or e.get('review_only') or e.get('dimension_type')!=0:continue
            if e.get('geometry',{}).get('text') not in ('','<>'):continue
            d=world(e);axis=linear_axis(d)
            if near(abs(axis[1]),1,1e-6) and near(e.get('scaled_measurement'),correction['before_mm'],TOL):eligible.append(d)
        for wall in eligible:
            g=wall['geometry'];factor=wall.get('linear_factor',1)
            if factor<=0:continue
            ends=sorted(g[k][1] for k in ('defpoint2','defpoint3'))
            circles=[world(e) for e in records.values() if e['type']=='CIRCLE' and e.get('geometry') and sids.intersection(e.get('source_sheet_ids',[])) and
                     all(math.dist(world(e)['geometry']['center'][:2],g[k][:2])<world(e)['geometry']['radius']-TOL for k in ('defpoint2','defpoint3'))]
            if len(circles)!=1:continue
            circle=circles[0];cg=circle['geometry']
            # Old hand-trimmed view lines can extend a little beyond the
            # callout. Only a tolerance explicitly printed on this sheet may
            # bound that drafting residual; contact matching stays strict.
            tolerances=set()
            for e in records.values():
                text=normalized(e.get('text',''))
                if not sids.intersection(e.get('source_sheet_ids',[])) or not any(tag in text for tag in ('dung sai cac kich thuoc khac','general dimensional tolerance')):continue
                match=re.search(r'(?:±|%%p)\s*(\d+(?:[.,]\d+)?)\s*mm',text)
                if match:tolerances.add(float(match[1].replace(',','.')))
            clip_tolerance=max(TOL,next(iter(tolerances))/factor) if len(tolerances)==1 else TOL
            inside=lambda p:math.dist(p[:2],cg['center'][:2])<=cg['radius']+clip_tolerance
            dims=[world(e) for e in records.values() if e['type']=='DIMENSION' and e.get('geometry') and not e.get('review_only') and e.get('dimension_type')==0 and
                  e['geometry'].get('text') in ('','<>') and sids.intersection(e.get('source_sheet_ids',[])) and
                  all(inside(world(e)['geometry'][k]) for k in ('defpoint2','defpoint3'))]
            cap=[d for d in dims if near(abs(linear_axis(d)[1]),1,1e-6) and near(d.get('linear_factor',1),factor,TOL) and
                 near(d.get('scaled_measurement'),frame['cap_before_mm'][1],TOL) and near(max(d['geometry'][k][1] for k in ('defpoint2','defpoint3')),ends[0],TOL)]
            side=[d for d in dims if near(abs(linear_axis(d)[0]),1,1e-6) and near(d.get('linear_factor',1),factor,TOL) and
                  near(d.get('scaled_measurement'),frame['cap_before_mm'][1],TOL)]
            if len(cap)!=1 or len(side)!=1:continue
            low=min(cap[0]['geometry'][k][1] for k in ('defpoint2','defpoint3'))
            xends=sorted(side[0]['geometry'][k][0] for k in ('defpoint2','defpoint3'))
            # The source right-hand exterior and lower foot are fixed. Source
            # faces must actually occur as straight segments in this callout.
            items=[]
            for e in records.values():
                if e.get('review_only') or not sids.intersection(e.get('source_sheet_ids',[])) or not (e.get('geometry') or e.get('radial_geometry')):continue
                try:items.append(world(e))
                except ValueError:
                    from backend.services.geometry_retrieval import local_bounds
                    box=local_bounds(e)
                    if box is None:raise ValueError('Không định vị được đối tượng chưa hỗ trợ trong khung Detail')
                    pts=[list(matrix(e).transform(p)) for p in product(*zip(*box))]
                    a=[min(p[i] for p in pts) for i in (0,1)];b=[max(p[i] for p in pts) for i in (0,1)]
                    if all(a[i]<=cg['center'][i]+cg['radius'] and b[i]>=cg['center'][i]-cg['radius'] for i in (0,1)):
                        raise ValueError('Detail có hình học/frame chưa mở đầy đủ')
            segments=[]
            for e in items:
                geom=e.get('geometry',{})
                if e['type']=='LINE':pairs=[(geom['start'],geom['end'])]
                elif e['type'] in ('LWPOLYLINE','POLYLINE') and not any(any(p[2:]) for p in geom.get('points',[])):
                    points=[[p[0],p[1],geom['elevation']] for p in geom['points']]
                    pairs=list(zip(points,points[1:]+([points[0]] if geom['closed'] else [])))
                else:continue
                segments += [(e['ref'],a,b) for a,b in pairs if inside(a) and inside(b)]
            face_refs=[]
            for axis,value in [(1,low),(1,ends[0]),(1,ends[1]),(0,xends[0]),(0,xends[1])]:
                found=[ref for ref,a,b in segments if near(a[axis],value,TOL) and near(b[axis],value,TOL)]
                if not found:break
                face_refs+=found
            else:
                measured=[wall,cap[0],side[0]]
                if any(not any(all(near(p[i],a[i],TOL) and near(p[i],b[i],TOL) if near(a[i],b[i],TOL) else min(a[i],b[i])-TOL<=p[i]<=max(a[i],b[i])+TOL for i in (0,1))
                               for _,a,b in segments) for d in measured for p in [d['geometry'][k] for k in ('defpoint2','defpoint3')]):continue
                receivers=[(e,rect(e)) for e in items if e['type']=='LWPOLYLINE' and rect(e) and
                           all(inside(p) for p in rect(e)['geometry']['points']) and near(rect(e)['low'][1],ends[1],TOL)]
                if len(receivers)!=1:continue
                receiver,box=receivers[0]
                new_join=low+frame['cap_after_mm'][1]/factor
                new_inner=new_join+correction['after_mm']/factor
                new_side=xends[1]-frame['cap_after_mm'][1]/factor
                result.append(dict(status='source_measured_corner_contacts',product_code=correction['product_code'],tube_part_code=correction['part_code'],
                    frame_part_code=frame['frame_part_code'],circle_ref=circle['ref'],circle_geometry=cg,wall_dimension_ref=wall['ref'],
                    callout_clip_tolerance_native=clip_tolerance,source_general_tolerance_mm=next(iter(tolerances)) if len(tolerances)==1 else None,
                    cap_dimension_ref=cap[0]['ref'],side_dimension_ref=side[0]['ref'],native_dimension_factor=factor,
                    before_wall_mm=correction['before_mm'],after_wall_mm=correction['after_mm'],before_plate_mm=frame['cap_before_mm'][1],after_plate_mm=frame['cap_after_mm'][1],
                    bottom_face=low,old_join_face=ends[0],new_join_face=new_join,old_inner_face=ends[1],new_inner_face=new_inner,
                    outer_side_face=xends[1],old_inner_side_face=xends[0],new_inner_side_face=new_side,
                    face_refs=sorted(set(face_refs)),receiver_ref=receiver['ref'],receiver_box=box,sheet_ids=sorted(sids)))
    return result

def operations(proof,context):
    from ezdxf.math import Matrix44
    records={e['ref']:e for e in context['entities']};cg=proof['circle_geometry'];box=proof['receiver_box'];delta=proof['new_inner_face']-proof['old_inner_face']
    clip_tolerance=proof['callout_clip_tolerance_native']
    inside=lambda p:math.dist(p[:2],cg['center'][:2])<=cg['radius']+clip_tolerance
    contained=lambda p:all(box['low'][i]-TOL<=p[i]<=box['high'][i]+TOL for i in (0,1))
    def move(p):
        q=list(p)
        for old,new in ((proof['old_join_face'],proof['new_join_face']),(proof['old_inner_face'],proof['new_inner_face'])):
            if near(p[1],old,TOL):q[1]+=new-old;break
        if near(p[0],proof['old_inner_side_face'],TOL):q[0]+=proof['new_inner_side_face']-proof['old_inner_side_face']
        return q
    results=[];moving_receiver=[]
    for e in context['entities']:
        if e.get('review_only') or not set(proof['sheet_ids']).intersection(e.get('source_sheet_ids',[])) or not (e.get('geometry') or e.get('radial_geometry')):continue
        try:w=world(e)
        except ValueError:continue # relevant unsupported frames were rejected by proofs()
        key='geometry' if e.get('geometry') else 'radial_geometry';g=w[key]
        pts=[g[k] for k in ('start','end','center','defpoint2','defpoint3','defpoint4') if k in g]+[[p[0],p[1],g['elevation']] for p in g.get('points',[])]
        if not pts or not all(inside(p) for p in pts) or e['ref']==proof['circle_ref']:continue
        rigid=(e['ref']==proof['receiver_ref'] or all(contained(p) for p in pts))
        if rigid:
            after=transform(e['type'],g,Matrix44.translate(0,delta,0));moving_receiver.append(e['ref'])
        elif e['type']=='LINE':
            after=copy.deepcopy(g)
            for k in ('start','end'):after[k]=move(g[k])
            # Source lines were trimmed to the circular callout. Recompute
            # that clipping after a measured face moves; keep the callout.
            for k in ('start','end'):
                if near(math.dist(g[k][:2],cg['center'][:2]),cg['radius'],clip_tolerance) and not near(g[k],after[k],TOL):
                    if near(g['start'][1],g['end'][1],TOL):
                        rad=cg['radius']**2-(after[k][1]-cg['center'][1])**2
                        if rad<=0:raise ValueError('Mặt Detail nằm ngoài vòng trích')
                        after[k][0]=cg['center'][0]+math.copysign(math.sqrt(rad),g[k][0]-cg['center'][0])
                    elif near(g['start'][0],g['end'][0],TOL):
                        rad=cg['radius']**2-(after[k][0]-cg['center'][0])**2
                        if rad<=0:raise ValueError('Mặt Detail nằm ngoài vòng trích')
                        after[k][1]=cg['center'][1]+math.copysign(math.sqrt(rad),g[k][1]-cg['center'][1])
                    else:raise ValueError('Nét cắt xiên Detail cần adapter riêng')
        elif e['type']=='LWPOLYLINE':
            after=copy.deepcopy(g)
            for p in after['points']:p[:2]=move([p[0],p[1],g['elevation']])[:2]
            if any(p[4] for p in g['points']) and not near(after,g,TOL):raise ValueError('LWP cong trong Detail cần tính lại bulge trước sửa')
            for i,p in enumerate(g['points']):
                if not near(math.dist(p[:2],cg['center'][:2]),cg['radius'],clip_tolerance) or near(p[:2],after['points'][i][:2],TOL):continue
                adjacent=[]
                if i>0:adjacent.append(g['points'][i-1])
                if i<len(g['points'])-1:adjacent.append(g['points'][i+1])
                if g['closed'] and i in (0,len(g['points'])-1):adjacent.append(g['points'][-1 if i==0 else 0])
                axes={1 if near(p[1],q[1],TOL) else 0 if near(p[0],q[0],TOL) else -1 for q in adjacent}
                if len(axes)!=1 or -1 in axes:raise ValueError('Đỉnh LWP trên vòng trích chưa có mặt cắt duy nhất')
                fixed=next(iter(axes));other=1-fixed;new=after['points'][i]
                rad=cg['radius']**2-(new[fixed]-cg['center'][fixed])**2
                if rad<=0:raise ValueError('Đỉnh LWP vượt vòng trích')
                new[other]=cg['center'][other]+math.copysign(math.sqrt(rad),p[other]-cg['center'][other])
        elif e['type']=='DIMENSION' and e['ref'] in (proof['wall_dimension_ref'],proof['cap_dimension_ref'],proof['side_dimension_ref']):
            after=copy.deepcopy(g)
            for k in ('defpoint','defpoint2','defpoint3'):after[k]=move(g[k])
        else:
            if any(not near(move(p),p,TOL) for p in pts):raise ValueError('Có đường cong/đối tượng chạm mặt Detail chưa có binding: '+e['ref'])
            continue
        local=local_geometry(e,after)
        if not near(e[key],local,1e-7):results.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e[key]),after=json.dumps(local),xyz=[],
            reason='Đồng bộ Detail đo thật: giữ đáy/biên ngoài; thành hộp theo BOM, tấm laser và cụm ren giữ tiếp xúc nguồn'))
    expected={proof['wall_dimension_ref'],proof['cap_dimension_ref'],proof['side_dimension_ref'],proof['receiver_ref']}
    if not expected<={o.ref for o in results}:raise ValueError('Detail chưa sửa đủ DIM và chi tiết tiếp xúc')
    return results

def synchronize(plan,context):
    from graph.native_instances import equivalent_operation
    from backend.services.change_service import EditProposal
    checks=proofs(plan,context)
    if not checks:return plan
    result=plan.model_copy(deep=True);existing={o.ref:o for o in result.operations if o.action=='replace_geometry'}
    for proof in checks:
        for op in operations(proof,context):
            if op.ref in existing and not equivalent_operation(existing[op.ref],op):raise ValueError('Detail có phép sửa xung đột: '+op.ref)
            if op.ref not in existing:result.operations.append(op);existing[op.ref]=op
            result.edits=[e for e in result.edits if e.entity_ref!=op.ref]
            result.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['frame_part_code'],purpose='geometry',before=op.before,after=op.after,reason=op.reason))
    validate(result,context);return result

def validate(plan,context):
    from graph.native_instances import equivalent_operation
    from graph.fit_constraints import measurement
    actual={o.ref:o for o in plan.operations if o.action=='replace_geometry'};records={e['ref']:e for e in context['entities']}
    for proof in proofs(plan,context):
        for expected in operations(proof,context):
            if expected.ref not in actual or not equivalent_operation(expected,actual[expected.ref]):raise ValueError('Detail/cụm ren chưa giữ đúng tiếp xúc nguồn')
        for ref,target in [(proof['wall_dimension_ref'],proof['after_wall_mm']), (proof['cap_dimension_ref'],proof['after_plate_mm']), (proof['side_dimension_ref'],proof['after_plate_mm'])]:
            if not near(measurement(records[ref],json.loads(actual[ref].after)),target,1e-5):raise ValueError('DIM Detail không khớp độ dày vật tư')
