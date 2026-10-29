"""Source-measured front elevation of a three-level welded tube core.

The nominal member decision supplies the design clearances. Native gauge and
equal-span DIMs, cap rectangles and two distinct member lengths bind the view.
Small end details translate rigidly; sheet sections change gauge; tube stock
sections keep their original size. No global scaling or perspective inference.
"""
import copy,json,math
from cad.geometry import near
from cad.frame_geometry import world,local_geometry,transform,matrix
from cad.dimensions import linear_axis
from cad.edit_engine import Operation
from graph.packing_side_layers import rect
from graph.confirmed_inner_tubes import proofs as tube_proofs

TOL=5e-5


def proofs(plan,context):
    cuts=tube_proofs(plan,context)
    if not cuts:return []
    records={e['ref']:e for e in context['entities']};result=[]
    for cut in cuts:
        choice=cut.get('mate_choice')
        if not choice:continue
        core=cut['core_height_before_mm'];new_core=cut['core_height_after_mm'];code=cut['part_code']
        rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
        sheets={sid for t,r in rows for sid in t.get('source_sheet_ids',[]) if all(any(x['part_code']==cap for x in t['bom']['rows']) for cap in
            (choice['top_plate_part_code'],choice['middle_plate_part_code'],choice['bottom_plate_part_code']))}
        local=[world(e) for e in records.values() if e['type']=='DIMENSION' and e.get('geometry') and not e.get('review_only') and sheets.intersection(e.get('source_sheet_ids',[]))]
        dims=[d for d in local if d.get('dimension_type')==0 and d['geometry'].get('text') in ('','<>') and near(d.get('linear_factor',1),1,TOL)]
        heights=[d for d in dims if near(d.get('scaled_measurement'),core,TOL) and near(abs(linear_axis(d)[1]),1,TOL)]
        for height in heights:
            g=height['geometry'];low,high=sorted(g[k][1] for k in ('defpoint2','defpoint3'))
            if not near(g['defpoint2'][0],g['defpoint3'][0],TOL):continue
            x=g['defpoint2'][0];sids=sheets.intersection(height.get('source_sheet_ids',[]));boxes=[]
            for e in records.values():
                if not sids.intersection(e.get('source_sheet_ids',[])):continue
                box=rect(e)
                if box and near(box['low'][0],x,TOL) and near(box['low'][1],low,TOL) and box['size'][0]>20*box['size'][1]:boxes.append(box)
            if len(boxes)!=1:continue
            bottom=boxes[0];old_t=bottom['size'][1]
            top=[b for e in records.values() if sids.intersection(e.get('source_sheet_ids',[])) and (b:=rect(e)) and
                 near([b['low'][0],b['high'][0],b['high'][1],b['size'][1]],[bottom['low'][0],bottom['high'][0],high,old_t],TOL)]
            if len(top)!=1:continue
            # The native chain must explicitly show equal clear spans and a
            # middle plate of the same source gauge. Merely a centred line
            # does not establish a symmetric assembly.
            middle=[d for d in dims if sids.intersection(d.get('source_sheet_ids',[])) and near(d.get('scaled_measurement'),old_t,TOL) and
                    near(abs(linear_axis(d)[1]),1,TOL) and near(sum(d['geometry'][k][1] for k in ('defpoint2','defpoint3'))/2,(low+high)/2,TOL)]
            if len(middle)!=1:continue
            mid=sorted(middle[0]['geometry'][k][1] for k in ('defpoint2','defpoint3'))
            planes=[low,low+old_t,*mid,high-old_t,high]
            chain=[]
            for a,b in zip(planes,planes[1:]):
                candidates=[d for d in dims if sids.intersection(d.get('source_sheet_ids',[])) and near(abs(linear_axis(d)[1]),1,TOL) and
                            near(d['geometry']['defpoint'][0],middle[0]['geometry']['defpoint'][0],TOL) and
                            near(sorted(d['geometry'][k][1] for k in ('defpoint2','defpoint3')),[a,b],TOL)]
                if len(candidates)!=1:break
                chain.append(candidates[0]['ref'])
            if len(chain)!=5:continue
            owned=[b for e in records.values() if sids.intersection(e.get('source_sheet_ids',[])) and (b:=rect(e)) and b['low'][0]>=bottom['low'][0]-TOL and b['high'][0]<=bottom['high'][0]+TOL and
                   near(b['low'][1],low+old_t,TOL) and near(b['high'][1],high-old_t,TOL)]
            widths={round(b['size'][0],6) for b in owned}
            if len(owned)<2 or len(widths)!=1:continue
            width=next(iter(widths))
            from cad.broken_tube import tube_spec
            specs={tube_spec(r['description']) for t,r in rows}
            if len(specs)!=1 or None in specs or not near(next(iter(specs))[:2],[width,width],TOL):continue
            full=[b for e in records.values() if sids.intersection(e.get('source_sheet_ids',[])) and (b:=rect(e)) and b['low'][0]>=bottom['low'][0]-TOL and b['high'][0]<=bottom['high'][0]+TOL and
                  near([b['low'][1],b['high'][1],b['size'][0]],[low,high,width],TOL)]
            if not full:continue
            new_top_t,new_bottom_t,new_mid_t=[v[1] for v in cut['cap_gauges']]
            target_planes=[low,low+new_bottom_t,low+new_core/2-new_mid_t/2,low+new_core/2+new_mid_t/2,low+new_core-new_top_t,low+new_core]
            if any(b-a<=0 for a,b in zip(target_planes,target_planes[1:])):raise ValueError('Cụm xương không còn đủ khoảng lắp')
            result.append(dict(status='measured_symmetric_core_front',part_code=code,sheet_ids=sorted(sids),height_dimension_ref=height['ref'],chain_dimension_refs=chain,
                source_planes=planes,target_planes=target_planes,bottom_plate_ref=bottom['ref'],top_plate_ref=top[0]['ref'],
                member_boxes=owned,full_length_boxes=full,stock_width_mm=width,member_length_mm=cut['target_nominal_mm'],
                member_low=target_planes[1]+choice['bottom_clearance_mm'],member_high=target_planes[4]-choice['top_clearance_mm'],
                bbox=[bottom['low'][0],low,bottom['high'][0],high],core_height_before_mm=core,core_height_after_mm=new_core))
            if cut.get('frame_part_code'):result[-1]['frame_caption_driver']={k:cut[k] for k in ('frame_part_code','frame_height_before_mm','frame_height_after_mm')}
    fronts=list(result)
    for front in fronts:result.extend(paired_side_views(front,context))
    return result


def paired_side_views(front,context):
    """Bind a separate orthographic elevation by its native width and six faces.

    Sharing a Y coordinate is insufficient. The width DIM must coincide with
    both outer cap edges and both middle faces. All six source levels must
    have physical edge endpoints, with vertical members connecting levels.
    This deliberately does not infer an isometric or hidden 3D contact.
    """
    old=front['source_planes'];sids=set(front['sheet_ids']);edges=[];dims=[]
    driver=next(e for e in context['entities'] if e['ref']==front['height_dimension_ref'])
    plane_z=world(driver)['geometry']['defpoint2'][2]
    for e in context['entities']:
        if e.get('review_only') or not e.get('geometry') or not sids.intersection(e.get('source_sheet_ids',[])):continue
        try:w=world(e)
        except ValueError:continue
        g=w['geometry']
        if e['type']=='LINE':pts=[g['start'],g['end']]
        elif e['type']=='LWPOLYLINE' and not g.get('closed') and len(g['points'])==2 and not any(any(p[2:]) for p in g['points']):
            pts=[[p[0],p[1],g['elevation']] for p in g['points']]
        else:pts=[]
        if pts and all(near(p[2],plane_z,TOL) for p in pts):edges.append((e['ref'],pts))
        if e['type']=='DIMENSION' and e.get('dimension_type')==0 and g.get('text') in ('','<>') and near(w.get('linear_factor',1),1,TOL) and near(abs(linear_axis(w)[0]),1,TOL):dims.append(w)
    result=[];seen=set()
    for dim in dims:
        g=dim['geometry'];a,b=g['defpoint2'],g['defpoint3'];x0,x1=sorted((a[0],b[0]))
        if not near([a[2],b[2]],[plane_z,plane_z],TOL):continue
        if not near([a[1],b[1]],[old[0],old[0]],TOL) or x1-x0<=front['stock_width_mm']*2:continue
        if not (x1<front['bbox'][0]-TOL or x0>front['bbox'][2]+TOL):continue
        local=[(ref,pts) for ref,pts in edges if all(x0-TOL<=p[0]<=x1+TOL and old[0]-TOL<=p[1]<=old[5]+TOL for p in pts)]
        faces={}
        for i in (0,2,3,5):
            matches=[ref for ref,pts in local if near(sorted(p[0] for p in pts),[x0,x1],TOL) and all(near(p[1],old[i],TOL) for p in pts)]
            if not matches:break
            faces[i]=matches
        if len(faces)!=4:continue
        if any(sum(near(p[1],y,TOL) for _,pts in local for p in pts)<2 for y in old):continue
        vertical=[ref for ref,pts in local if near(pts[0][0],pts[1][0],TOL) and abs(pts[0][1]-pts[1][1])>front['core_height_before_mm']/3]
        if len(vertical)<2:continue
        key=(round(x0,5),round(x1,5))
        if key in seen:continue
        seen.add(key)
        result.append(dict(front,status='measured_paired_core_side',bbox=[x0,old[0],x1,old[5]],
            driver_height_dimension_ref=front['height_dimension_ref'],height_dimension_ref=None,chain_dimension_refs=[],
            width_dimension_ref=dim['ref'],face_evidence_refs=faces,vertical_evidence_refs=vertical,
            top_plate_ref=None,bottom_plate_ref=None,member_boxes=[],full_length_boxes=[],frame_caption_driver=None))
    return result


def operations(proof,context):
    from ezdxf.math import Matrix44
    from backend.services.geometry_retrieval import local_bounds
    old,new=proof['source_planes'],proof['target_planes'];box=proof['bbox'];width=proof['stock_width_mm'];result=[]
    inside=lambda p:box[0]-TOL<=p[0]<=box[2]+TOL and box[1]-TOL<=p[1]<=box[3]+TOL
    def mapped(y):
        for a,b in zip(old,new):
            if near(y,a,TOL):return y+b-a
        anchors=[0,3,5];i=min(anchors,key=lambda i:abs(y-old[i]))
        if abs(y-old[i])<=width+TOL:return y+new[i]-old[i]
        raise ValueError('Điểm CAD chưa gắn được tầng/mốc giữ của cụm xương')
    def member(p):
        q=list(p)
        if near(p[1],old[1],TOL):q[1]+=proof['member_low']-old[1]
        elif near(p[1],old[4],TOL):q[1]+=proof['member_high']-old[4]
        else:q[1]=mapped(p[1])
        return q
    records={e['ref']:e for e in context['entities']};rigid_roots=set()
    # A complete small native INSERT is a rigid fitting, including text and
    # nested children. Move the instance rather than stretching its screws.
    for root,parent in records.items():
        if parent['type']!='INSERT' or '/' in root or not set(proof['sheet_ids']).intersection(parent.get('source_sheet_ids',[])):continue
        children=[e for ref,e in records.items() if ref.startswith(root+'/') and e.get('geometry')]
        if not children:continue
        pts=[]
        for child in children:
            try:bounds=local_bounds(world(child))
            except ValueError:pts=[];break
            if bounds:pts.extend(bounds)
        if not pts or not all(inside(p) for p in pts):continue
        lo,hi=min(p[1] for p in pts),max(p[1] for p in pts)
        if hi-lo>width+TOL:continue
        i=min((0,3,5),key=lambda i:abs((lo+hi)/2-old[i]))
        if max(abs(lo-old[i]),abs(hi-old[i]))>width+TOL:continue
        delta=new[i]-old[i];rigid_roots.add(root)
        if abs(delta)<=1e-7:continue
        inv=matrix(parent);inv.inverse();shift=list(inv.transform_direction((0,delta,0)))
        position=parent['position'];xyz=[a+b for a,b in zip(position,shift)]
        result.append(Operation(ref=root,action='move_insert',before=json.dumps(position),after='',xyz=xyz,reason='Dịch nguyên block phụ kiện theo tầng cụm; giữ ren, lỗ và ký hiệu nguồn'))
    for e in context['entities']:
        if e['ref'].split('/')[0] in rigid_roots:continue
        if e.get('review_only') or not set(proof['sheet_ids']).intersection(e.get('source_sheet_ids',[])) or not e.get('geometry'):continue
        try:w=world(e)
        except ValueError:
            bounds=local_bounds(e)
            if bounds:
                from itertools import product
                pts=[matrix(e).transform(p) for p in product(*zip(*bounds))]
                if any(inside(p) for p in pts):raise ValueError('Hình cụm có CAD chưa hỗ trợ chuyển frame: '+e['ref'])
            continue
        g=w['geometry'];points=[g[k] for k in ('start','end','center') if k in g]+[[p[0],p[1],g['elevation']] for p in g.get('points',[])]
        is_dim=e['type']=='DIMENSION'
        if is_dim:
            points=[g[k] for k in g if k.startswith('defpoint') and k not in ('defpoint','defpoint5')]
            # Chain annotation sits outside the view, but its native source
            # endpoints are exactly those measured layer faces.
            chain=e['ref'] in proof['chain_dimension_refs']+[proof['height_dimension_ref']]
            layer_bound=False
            if points and len(points)==2 and e.get('dimension_type') in (0,1) and g.get('text') in ('','<>') and near(abs(linear_axis(w)[1]),1,TOL):
                layer_bound=any(inside(p) for p in points) and all(any(near(p[1],y,TOL) for y in old) for p in points)
            if not chain and not layer_bound and (not points or not all(inside(p) for p in points)):continue
        elif not points or not all(inside(p) for p in points):continue
        ys=[p[1] for p in points];lo,hi=min(ys),max(ys);after=copy.deepcopy(g)
        member_box=next((b for b in proof['member_boxes'] if e['ref']==b['ref'] or all(b['low'][0]-TOL<=p[0]<=b['high'][0]+TOL and b['low'][1]-TOL<=p[1]<=b['high'][1]+TOL for p in points)),None)
        plate_band=next((i for i in (0,2,4) if lo>=old[i]-TOL and hi<=old[i+1]+TOL),None)
        short=hi-lo<=width+TOL
        if proof['status']=='measured_paired_core_side' and plate_band is not None and not all(any(near(p[1],y,TOL) for y in old) for p in points):
            # A tube wall/fitting can project into the cap band. Only the
            # actual source faces authorize a gauge change; retain offsets
            # of separate stock edges instead of thinning them as a sheet.
            plate_band=None
        def move(p):
            q=list(p)
            if member_box and not short:return member(p)
            if plate_band is not None:
                i=plate_band;q[1]=new[i]+(p[1]-old[i])*(new[i+1]-new[i])/(old[i+1]-old[i])
            elif short:
                i=min((0,3,5),key=lambda i:abs((lo+hi)/2-old[i]))
                if max(abs(lo-old[i]),abs(hi-old[i]))>width+TOL:raise ValueError('Chi tiết nhỏ chưa gắn được tầng cụm xương')
                q[1]+=new[i]-old[i]
            else:q[1]=mapped(p[1])
            return q
        if e['type']=='LINE':
            for k in ('start','end'):after[k]=move(g[k])
            if not near(g['start'][0],g['end'][0],TOL) and not near(g['start'][1],g['end'][1],TOL) and not near(
                after['start'][1]-g['start'][1],after['end'][1]-g['end'][1],TOL):raise ValueError('Nét xiên trong cụm xương cần liên kết riêng: '+e['ref'])
        elif e['type']=='LWPOLYLINE':
            if any(any(p[2:]) for p in g['points']):raise ValueError('Cụm xương có LWP cong/width chưa gắn quan hệ')
            for p in after['points']:p[:2]=move([p[0],p[1],g['elevation']])[:2]
        elif is_dim:
            if e.get('dimension_type') not in (0,1,2) or g.get('text') not in ('','<>'):continue
            # Horizontal extension legs can have different Y ordinates (a
            # source projection point, not a second measured height). Keep
            # that drafting offset when both belong to one end tier.
            rigid_dim_tier=None
            if e.get('dimension_type')==0 and near(abs(linear_axis(w)[0]),1,TOL) and hi-lo<proof['core_height_before_mm']/4:
                tiers={i for p in points for i in (0,3,5) if abs(p[1]-old[i])<=width+TOL}
                if len(tiers)==1:rigid_dim_tier=next(iter(tiers))
            for k in g:
                if not k.startswith('defpoint'):continue
                if rigid_dim_tier is not None:
                    after[k][1]+=new[rigid_dim_tier]-old[rigid_dim_tier];continue
                if k in ('defpoint','defpoint5'):
                    # Label location follows its nearest measured layer and
                    # keeps its offset. Measurement legs follow real faces.
                    i=min(range(6),key=lambda i:abs(g[k][1]-old[i]));after[k][1]+=new[i]-old[i]
                else:
                    try:after[k][1]=mapped(g[k][1])
                    except ValueError as error:raise ValueError(str(error)+': '+e['ref']+' / '+k) from error
            if e.get('dimension_type')==2:
                from ezdxf.math import Vec2,intersection_line_line_2d
                pairs=(('defpoint','defpoint4'),('defpoint3','defpoint2'))
                centers=[intersection_line_line_2d(*[tuple(Vec2(v[k]) for k in pair) for pair in pairs]) for v in (g,after)]
                if any(v is None for v in centers):raise ValueError('DIM góc cụm xương không có giao điểm')
                shift=centers[1]-centers[0];after['defpoint5']=[g['defpoint5'][0]+shift.x,g['defpoint5'][1]+shift.y,g['defpoint5'][2]]
        elif short:
            delta=move(points[0])[1]-points[0][1]
            if any(not near(move(p)[1]-p[1],delta,TOL) for p in points):raise ValueError('Đường cong cụm xương cần tái tính hình học')
            after=transform(e['type'],g,Matrix44.translate(0,delta,0))
        else:raise ValueError('Đối tượng dài chưa gắn được cụm xương: '+e['ref'])
        local=local_geometry(e,after)
        if not near(g,after,1e-7):result.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(local),xyz=[],
            reason='Cụm xương đo thật: giữ đáy, bố trí tầng giữa đối xứng, sửa tấm theo BOM và giữ khe hở thanh đã chốt'))
    # Text centred on a moved circle is source-bound, including justified
    # TEXT whose insertion point differs from its visible alignment point.
    # A detail leader keeps its label in place and follows at its arrow tip.
    circles=[]
    for op in result:
        e=records[op.ref]
        if op.action!='replace_geometry' or e['type']!='CIRCLE':continue
        before=world(e)['geometry'];after=world(dict(e,geometry=json.loads(op.after)))['geometry']
        if near(before['radius'],after['radius'],TOL):circles.append((e,before,after))
    for e in context['entities']:
        if e.get('review_only') or e['ref'].split('/')[0] in rigid_roots or not set(proof['sheet_ids']).intersection(e.get('source_sheet_ids',[])):continue
        placement=e.get('text_placement',{})
        if e['type'] in ('TEXT','MTEXT') and placement:
            position=list(matrix(e).transform(placement['anchor']))
            matches=[(a,b) for _,a,b in circles if near(position,a['center'],TOL)]
            if len(matches)!=1:continue
            a,b=matches[0];delta=[y-x for x,y in zip(a['center'],b['center'])];inv=matrix(e);inv.inverse();shift=inv.transform_direction(delta)
            xyz=[x+y for x,y in zip(placement['anchor'],shift)]
            result.append(Operation(ref=e['ref'],action='move_text',before=json.dumps(dict(anchor=placement['anchor'],text=e.get('raw_text',e.get('text','')))),after='',xyz=xyz,
                reason='Chữ đồng tâm với vòng tròn đã gắn nguồn: dịch cùng tâm, giữ nội dung và căn lề'))
        elif e['type']=='LEADER' and e.get('geometry'):
            g=world(e)['geometry'];pts=g.get('vertices',[])
            if len(pts)<2:continue
            matches=[(a,b) for _,a,b in circles if abs(math.dist(pts[0],a['center'])-a['radius'])<=TOL]
            if len(matches)!=1:continue
            a,b=matches[0];after=copy.deepcopy(g);after['vertices'][0]=[p+y-x for p,x,y in zip(pts[0],a['center'],b['center'])]
            result.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(local_geometry(e,after)),xyz=[],
                reason='Đầu leader Detail bám vòng tròn nguồn đã dịch; giữ vị trí chữ và các đỉnh còn lại'))
    # A member cut and the cavity between caps can have the same source
    # length, yet differ after adding the confirmed end clearances. Native
    # snaps bind a dimension to the physical member, not just the nearest
    # layer plane. Evaluate them after all body changes are available; include
    # associated DIMs whose label/extension points sit outside the view box.
    from cad.dimension_associations import follow
    by_ref={op.ref:i for i,op in enumerate(result)};unchanged=set()
    for e in context['entities']:
        if e['type']!='DIMENSION' or e.get('review_only') or not e.get('geometry'):continue
        current=result[by_ref[e['ref']]] if e['ref'] in by_ref else None
        before=e['geometry'];after=json.loads(current.after) if current else before
        bound=follow(e,before,after,records,result)
        if bound is None:continue
        if near(before,bound,1e-7):
            if current:unchanged.add(e['ref'])
            continue
        op=Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(before),after=json.dumps(bound),xyz=[],
            reason='DIM bám geometry native của cụm xương; phân biệt chiều dài thanh với khoảng lọt lòng giữa các tấm')
        if current:result[by_ref[e['ref']]]=op
        else:by_ref[e['ref']]=len(result);result.append(op)
    result=[op for op in result if op.ref not in unchanged]
    required={proof['height_dimension_ref'],proof['top_plate_ref'],proof['bottom_plate_ref'],*proof['chain_dimension_refs'],*(b['ref'] for b in proof['member_boxes']+proof['full_length_boxes'])}-{None}
    if proof['status']=='measured_paired_core_side':
        required.update(ref for i,refs in proof['face_evidence_refs'].items() if int(i)!=0 for ref in refs)
        required.update(proof['vertical_evidence_refs'])
    if not required<={o.ref for o in result}:raise ValueError('Cụm xương chưa sửa đủ các mặt và DIM đo thật')
    driver=proof.get('frame_caption_driver')
    if driver:
        nodes=[n for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==driver['frame_part_code']]
        stage_sheets={s['sheet_id'] for n in nodes for s in n.get('manufacturing_stages',[]) if s.get('status')=='source_specification_stage_link'}
        if set(proof['sheet_ids'])<=stage_sheets:
            from graph.confirmed_inner_panels import window_captions
            result.extend(window_captions(dict(driver,source_windows=[dict(sheet_ids=proof['sheet_ids'])]),context))
    return result


def synchronize(plan,context):
    from backend.services.change_service import EditProposal
    from graph.native_instances import equivalent_operation
    checks=proofs(plan,context)
    if not checks:return plan
    result=plan.model_copy(deep=True);actual={o.ref:o for o in result.operations}
    for proof in checks:
        for op in operations(proof,context):
            if op.ref in actual and not equivalent_operation(op,actual[op.ref]):raise ValueError('Hình cụm xương có thay đổi xung đột: '+op.ref)
            if op.ref not in actual:result.operations.append(op);actual[op.ref]=op
            result.edits=[e for e in result.edits if e.entity_ref!=op.ref]
            result.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['part_code'],purpose='annotation' if op.action=='replace_text' else 'geometry',before=op.before,after=op.after,reason=op.reason))
    validate(result,context);return result


def validate(plan,context):
    from graph.native_instances import equivalent_operation
    actual={o.ref:o for o in plan.operations}
    for proof in proofs(plan,context):
        for expected in operations(proof,context):
            if expected.ref not in actual or not equivalent_operation(expected,actual[expected.ref]):raise ValueError('Hình cụm xương chưa đồng bộ đủ tầng và thanh')


def review(plan,context):
    """Credit only the particular verified view, never the whole BOM sheet."""
    from graph.native_instances import equivalent_operation
    checks=proofs(plan,context)
    if not checks:return []
    actual={o.ref:o for o in plan.operations};result=[]
    for proof in checks:
        try:expected=operations(proof,context)
        except ValueError:continue
        if not expected or any(o.ref not in actual or not equivalent_operation(o,actual[o.ref]) for o in expected):continue
        for sid in proof['sheet_ids']:
            result.append(dict(sheet_id=sid,status='verified_view',view='Hình cạnh cụm: cao độ và mặt tấm theo DIM nguồn' if proof['status']=='measured_paired_core_side' else 'Hình đứng cụm: tầng tấm và khe hở thanh',
                refs=[o.ref for o in expected],binding_count=len(expected),part_code=proof['part_code'],
                source_dimension_ref=proof.get('driver_height_dimension_ref') or proof['height_dimension_ref'],
                width_dimension_ref=proof.get('width_dimension_ref'),before_height_mm=proof['core_height_before_mm'],after_height_mm=proof['core_height_after_mm']))
    return result
