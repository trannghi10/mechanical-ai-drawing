"""Solve exact end-face contacts in complete planar native part assemblies.

This adapter covers source-closed straight measured part blocks, including
notched outlines. Contacts must overlap on actual axis-aligned end faces;
touching bounding boxes alone are not evidence of a physical contact.
It does not infer hidden 3D contacts, weld tangential constraints or depth from
an isometric drawing. Non-native/overlapping/ambiguous views retain their gate.
"""
import copy
import json
import math
from collections import defaultdict
import numpy as np
import networkx as nx
from ezdxf.math import Vec3
from cad.frame_geometry import world,matrix
from cad.measured_features import index,rectangle
from cad.geometry import near
from graph.change_dependencies import CoordinateRule

TOL=1e-5


def bounds(points):
    p=np.asarray(points,dtype=float);return np.array([p.min(axis=0),p.max(axis=0)])


def inventory(context,allow_profiles=False):
    report=context.get('source_features')
    if report is None:
        report=index(context,context.get('part_graph'))
    by={e['ref']:e for e in context['entities']};parts=defaultdict(list)
    from graph.native_instances import inventory as identity_inventory
    _,identities,_=identity_inventory(dict(context,source_features=report))
    from graph.native_instances import leader_body_features
    derived=leader_body_features(dict(context,source_features=report),by,set(identities.values()))
    features=list(report['features'])+[f for f in derived.values() if not any(set(f['refs'])==set(existing['refs']) for existing in report['features'])]
    for f in features:
        if not f.get('instance_ref') or identities.get(f['instance_ref'])!=f.get('part_code'):continue
        if allow_profiles:
            from cad.closed_profiles import polygon_from
            try:points=polygon_from([world(by[r]) for r in f['refs']])
            except (ValueError,KeyError):continue
            f=dict(f,points=points)
        else:
            # Packaging still requires rectangular envelopes. Do not relax its
            # containment/clearance assumptions with an irregular silhouette.
            if rectangle(f['points']) is None:continue
            b=bounds(f['points']);p=np.asarray(f['points'])
            if any(min(abs(q[i]-b[0,i]),abs(q[i]-b[1,i]))>TOL for q in p for i in (0,1)):continue
        parts[f['instance_ref']].append(f)
    # Multiple measured silhouettes for one instance can be separate views.
    # Do not turn those into a single physical body.
    parts={r:v[0] for r,v in parts.items() if len(v)==1 and r in by}
    from shapely.geometry import Polygon,Point
    invalid=[]
    for r,f in parts.items():
        shape=Polygon([p[:2] for p in f['points']])
        for e in context['entities']:
            if not e['ref'].startswith(r+'/') or e['ref'] in f['refs'] or e['type'] in ('DIMENSION','TEXT','MTEXT','ATTRIB','ATTDEF','INSERT'):continue
            if e['type']!='CIRCLE' or not e.get('geometry'):
                invalid.append(r);break
            try:g=world(e)['geometry']
            except ValueError:invalid.append(r);break
            p=Point(g['center'][:2])
            if not shape.contains(p) or shape.boundary.distance(p)<=g['radius']+TOL:
                invalid.append(r);break
    parts={r:f for r,f in parts.items() if r not in invalid}
    assemblies={s for e in context['entities'] if len(e.get('bom',{}).get('rows',[]))>1
                for s in e.get('source_sheet_ids',[])}
    # Container outlines are empty envelopes, not solid contact bodies.
    # The packaging adapter checks their padding/containment separately.
    assemblies-={sid for g in context.get('part_graph',{}).get('packaging_groups',[]) for sid in g['sheet_ids']}
    return by,parts,assemblies


def contact(a,b):
    if max(abs(a[0,2]-b[0,2]),abs(a[1,2]-b[1,2]))>TOL:return None
    found=[]
    for axis in (0,1):
        other=1-axis
        if min(a[1,other],b[1,other])-max(a[0,other],b[0,other])<=TOL:continue
        for fa,fb in ((1,0),(0,1)):
            if abs(a[fa,axis]-b[fb,axis])<=TOL:found.append((axis,fa,fb))
    return found[0] if len(found)==1 else None


def profile_contact(a,b):
    """An end-face contact requires positive length on both CAD boundaries."""
    ba,bb=bounds(a),bounds(b);candidate=contact(ba,bb)
    if candidate is None:return None
    axis,fa,fb=candidate;other=1-axis
    def intervals(points,coordinate):
        return [(min(p[other],q[other]),max(p[other],q[other]))
                for p,q in zip(points,points[1:]+points[:1])
                if abs(p[axis]-coordinate)<=TOL and abs(q[axis]-coordinate)<=TOL
                and abs(p[other]-q[other])>TOL]
    aa=intervals(a,ba[fa,axis]);ab=intervals(b,bb[fb,axis])
    if any(min(y,v)-max(x,u)>TOL for x,y in aa for u,v in ab):return candidate
    return None


def _synchronize_axis_aligned(plan,context,audit=None,allow_span_fits=True):
    if plan.questions or not plan.operations:return plan
    from graph.native_span_fits import synchronize as sync_span_fits
    if allow_span_fits:plan=sync_span_fits(plan,context)
    angle=context.get('contact_analysis_angle',0.)
    active_fits=[p for p in plan.native_span_fits if near(p.analysis_angle,angle,1e-7)]
    fixed={(ref,p.axis) for p in active_fits for ref in p.fixed_support_refs}
    adaptive={(ref,p.axis) for p in active_fits for ref in [p.receiver_ref,*p.peer_refs]}
    by,parts,assembly_ids=inventory(context,allow_profiles=True)
    ops={o.ref:o for o in plan.operations};moves={};proofs=[];dimension_proofs={};shift_by={};contact_sheets=set();annotation_refs=set();annotation_proofs=[]
    roots=set(context.get('root_target_ids',[]))
    for sid in sorted(assembly_ids,key=lambda s:(s not in roots,s)):
        local={r:f for r,f in parts.items() if sid in f['sheet_ids']}
        old={r:bounds(f['points']) for r,f in local.items()};new={};changed=set();profiles={};vertices={};edge_maps={}
        for r,f in local.items():
            records=[];pairs=[];edges=[]
            for ref in f['refs']:
                e=dict(by[ref]);op=ops.get(ref)
                if op:
                    if op.action!='replace_geometry':raise ValueError('Contact adapter cần snapshot geometry đầy đủ')
                    e['geometry']=json.loads(op.after);changed.add(r)
                placed=world(e);records.append(placed)
                from cad.closed_profiles import segments,polygon_from
                before_edges=segments(world(by[ref]));after_edges=segments(placed)
                if len(before_edges)!=len(after_edges):raise ValueError('Topology tiếp xúc đã thay đổi')
                for before_edge,after_edge in zip(before_edges,after_edges):pairs.extend(zip(before_edge,after_edge));edges.append((before_edge,after_edge))
            profiles[r]=polygon_from(records);vertices[r]=pairs;edge_maps[r]=edges
            new[r]=bounds(profiles[r])
        if not changed:continue
        contacts=[]
        refs=sorted(local)
        for i,a in enumerate(refs):
            for b in refs[i+1:]:
                c=profile_contact(local[a]['points'],local[b]['points'])
                if c:contacts.append((a,b,*c))
        gap_contacts={}
        for binding in active_fits:
            chain=[binding.support_refs[0],binding.receiver_ref,*binding.peer_refs,binding.support_refs[1]]
            # The selected block and its enclosing frame can expose these same
            # physical instances. Reuse the source-proven gap in either view;
            # a different/partial set of bodies cannot inherit this binding.
            if not set(chain)<=local.keys():continue
            gaps=[binding.clearances[0],*binding.inner_clearances,binding.clearances[1]]
            for a,b,gap in zip(chain,chain[1:],gaps):
                if gap<=TOL:continue
                key=(a,b,binding.axis,1,0);contacts.append(key);gap_contacts[key]=gap
        if not contacts:continue
        shifts={r:np.zeros(3) for r in refs};drivers={}
        for axis in (0,1):
            graph=nx.Graph()
            for a,b,k,fa,fb in contacts:
                if k==axis:graph.add_edge(a,b,faces=(fa,fb))
            for component in nx.connected_components(graph):
                driven=[r for r in component if (r,axis) in fixed or (r,axis) not in adaptive and np.max(np.abs(new[r][:,axis]-old[r][:,axis]))>TOL]
                if not driven:continue
                driven=sorted(driven);names=sorted(component);rows=[];rhs=[]
                for a,b,k,fa,fb in contacts:
                    if k!=axis or a not in component:continue
                    rows.append([(-1. if n==a else 1. if n==b else 0.) for n in names])
                    rhs.append(float((new[a][fa,axis]-old[a][fa,axis])-(new[b][fb,axis]-old[b][fb,axis])))
                # Every directly edited body retains the anchor selected in its
                # own measured recipe. Multiple drivers are valid only when all
                # those independent anchors and contact equations agree.
                for driver in driven:
                    rows.append([1. if n==driver else 0. for n in names]);rhs.append(0.)
                if np.linalg.matrix_rank(rows)!=len(names):raise ValueError('Hệ tiếp xúc chưa có nghiệm dịch chuyển duy nhất')
                answer=np.linalg.lstsq(rows,rhs,rcond=None)[0]
                if not np.allclose(np.asarray(rows)@answer,rhs,rtol=0,atol=TOL):raise ValueError('Tiếp xúc/mốc giữ xung đột')
                for r,v in zip(names,answer):shifts[r][axis]=float(v);drivers[(r,axis)]=driven
        after={r:new[r]+shifts[r] for r in refs}
        placed_profiles={r:[(np.asarray(p)+shifts[r]).tolist() for p in profiles[r]] for r in refs}
        for a,b,k,fa,fb in contacts:
            gap=gap_contacts.get((a,b,k,fa,fb),0.)
            placed_b=[list(p) for p in placed_profiles[b]]
            if gap:
                if not near(after[b][fb,k]-after[a][fa,k],gap,TOL):raise ValueError('Mất khe hở có DIM nguồn sau sửa')
                for p in placed_b:p[k]-=gap
            if profile_contact(placed_profiles[a],placed_b)!=(k,fa,fb):
                raise ValueError('Mất tiếp xúc 2D sau sửa')
        from shapely.geometry import Polygon
        for i,a in enumerate(refs):
            for b in refs[i+1:]:
                if abs(after[a][0,2]-after[b][0,2])>TOL:continue
                overlap=Polygon([p[:2] for p in placed_profiles[a]]).intersection(Polygon([p[:2] for p in placed_profiles[b]]))
                if overlap.area>TOL*TOL:raise ValueError('Chi tiết native chồng lấn trong mặt phẳng sau sửa')
        if any(np.linalg.norm(s)>TOL for s in shifts.values()) or any(
            f.receiver_ref in local and set(f.support_refs)<=local.keys() for f in active_fits):
            contact_sheets.add(sid)
        for r,shift in shifts.items():
            if np.linalg.norm(shift)<=TOL:continue
            if r in shift_by and not near(shift_by[r],shift.tolist(),TOL):raise ValueError('Hai khung yêu cầu vị trí instance khác nhau')
            shift_by[r]=shift.tolist()
            axes=[k for k in (0,1) if abs(shift[k])>TOL]
            for axis in axes:
                # The same native INSERT can occur in a selected block and its
                # enclosing sheet inventory. Its shift was checked above; one
                # source rule per world axis describes that physical motion.
                if any(p['rule'].target_ref==r and p['world_axis']=='xy'[axis] for p in proofs):continue
                sources=[]
                for driver in drivers[(r,axis)]:
                    for d in local[driver]['dimensions']:
                        op=ops.get(d['ref'])
                        if not op or op.action!='replace_geometry':continue
                        e=by[d['ref']];g0=e['geometry'];g1=json.loads(op.after)
                        for key in ('defpoint2','defpoint3'):
                            delta=np.asarray(g1[key])-g0[key]
                            nonzero=np.flatnonzero(abs(delta)>TOL)
                            if len(nonzero)!=1:continue
                            delta_world=np.asarray(matrix(e).transform_direction(Vec3(delta)))
                            if abs(delta_world[axis])>TOL and np.linalg.norm(np.delete(delta_world,axis))<TOL:
                                sources.append((d['ref'],key,int(nonzero[0]),float(delta_world[axis]),driver))
                if not sources:raise ValueError('Thiếu DIM nguồn để tái kiểm chứng dịch chuyển tiếp xúc')
                source,key,local_axis,delta,driver=sources[0];df=local[driver]
                rule=CoordinateRule(source_ref=source,source_field=key,target_ref=r,target_action='move_insert',axis='xyz'[local_axis],multiplier=float(shift[axis]/delta),composition='orthogonal' if len(axes)>1 else 'exclusive')
                evidence=sorted(set(df['evidence_refs']+local[r]['evidence_refs']+[r,source]))
                proofs.append(dict(sheet_id=sid,source_part=df['part_code'],target_part=local[r]['part_code'],evidence_refs=evidence,rule=rule,world_axis='xy'[axis]))
            parent=matrix(by[r]);parent.inverse();local_shift=list(parent.transform_direction(Vec3(shift)))
            xyz=[a+b for a,b in zip(by[r]['position'],local_shift)]
            if r in moves and not near(moves[r].xyz,xyz,TOL):raise ValueError('Hai ràng buộc làm xung đột instance')
            from cad.edit_engine import Operation
            moves[r]=Operation(ref=r,action='move_insert',before=json.dumps(by[r]['position']),after='',xyz=xyz,reason='Giữ tiếp xúc đầu mặt 2D được chứng minh từ block native')
        # A local BOM/balloon can bind an arrow to an actual face even when
        # the bubble is outside the block. Keep the bubble/label fixed and
        # follow only the proven arrow point. Nearest geometry is never used.
        from bom.reader import part_number_key
        for binding in (context.get('source_features') or {}).get('leader_profile_bindings',[]):
            if sid not in binding.get('sheet_ids',[]) or binding.get('status') not in (
                    'verified_endpoint_dimension_chain','verified_interior_dimension_chain','verified_interior_region'):continue
            candidates=binding.get('candidates',[]);endpoints=binding.get('leader_endpoints',[])
            if len(candidates)!=1 or len(endpoints)!=1 or len(binding.get('part_codes',[]))!=1:continue
            matching=[r for r,f in local.items() if set(f['refs'])==set(candidates[0]['geometry_refs']) and f['part_code']==binding['part_codes'][0]]
            if len(matching)!=1:continue
            root=matching[0]
            tables=[by.get(ref,{}) for ref in binding.get('bom_table_refs',[])]
            rows=[row for table in tables if table.get('bom',{}).get('status')=='verified_template' and sid in table.get('source_sheet_ids',[])
                  for row in table['bom']['rows'] if part_number_key(row['part_number'])==part_number_key(binding['part_number'])]
            if not rows or any(row['part_code']!=local[root]['part_code'] for row in rows):continue
            endpoint=endpoints[0];record=by.get(endpoint['ref'],{})
            if record.get('review_only') or record.get('type') not in ('LINE','LEADER') or not record.get('geometry'):continue
            g=world(record)['geometry'];points=[g['start'],g['end']] if record['type']=='LINE' else g['vertices']
            k=endpoint['vertex_index']
            if k not in (0,len(points)-1):continue
            point=np.asarray(points[k]);possible=[]
            existing_arrow=ops.get(record.get('ref'))
            if binding.get('geometry_owner_verified') and existing_arrow and existing_arrow.action=='replace_geometry':
                # The measured resize kernel can already have moved an
                # interior arrow. Recompute its exact source-bound operation;
                # do not approve an arbitrary point merely inside the body.
                matching_recipes=[r for r in plan.resize_recipes if r.part_code==local[root]['part_code'] and
                    set(r.outline_refs)==set(local[root]['refs']) and r.new_measurement is not None]
                if len(matching_recipes)==1:
                    from cad.parametric import resize
                    from graph.native_instances import equivalent_operation
                    expected=next((op for op in resize(matching_recipes[0],context,matching_recipes[0].new_measurement)
                        if op.ref==record['ref']),None)
                    if expected and equivalent_operation(expected,existing_arrow):
                        after_arrow=world(dict(record,geometry=json.loads(expected.after)))['geometry']
                        after_points=[after_arrow['start'],after_arrow['end']] if record['type']=='LINE' else after_arrow['vertices']
                        possible=[np.asarray(after_points[k])+shifts[root]]
            for edge0,edge1 in edge_maps[root]:
                a,b=np.asarray(edge0[0]),np.asarray(edge0[1]);v=b-a;length2=float(v@v)
                if length2<=TOL*TOL:continue
                t=float((point-a)@v/length2)
                if -TOL<=t<=1+TOL and np.linalg.norm(a+t*v-point)<=TOL:
                    possible.append(np.asarray(edge1[0])+t*(np.asarray(edge1[1])-edge1[0])+shifts[root])
            if not possible and near(old[root].tolist(),new[root].tolist(),TOL) and near(local[root]['points'],profiles[root],TOL):
                # Source index proved a strict material interior. A rigid
                # translation preserves it without guessing a stretch field.
                possible=[point+shifts[root]]
            if not possible or any(not near(q.tolist(),possible[0].tolist(),TOL) for q in possible):continue
            circle=binding.get('circle_ref');label=binding.get('number_text_ref')
            if circle not in by or by[circle].get('review_only') or label not in by:continue
            refs={endpoint['ref'],circle,label}
            annotation_refs.update(refs)
            annotation_proofs.append(dict(sheet_id=sid,part_code=local[root]['part_code'],instance_ref=root,
                leader_ref=endpoint['ref'],circle_ref=circle,number_text_ref=label,vertex_index=k,
                source_hash=context['source_hash'],status='source_bound_assembly_arrow'))
            if near(point.tolist(),possible[0].tolist(),TOL):continue
            updated=copy.deepcopy(g)
            if record['type']=='LINE':updated['start' if k==0 else 'end']=possible[0].tolist()
            else:updated['vertices'][k]=possible[0].tolist()
            from cad.frame_geometry import local_geometry
            from cad.edit_engine import Operation
            from graph.native_instances import equivalent_operation
            op=Operation(ref=record['ref'],action='replace_geometry',before=json.dumps(record['geometry']),
                after=json.dumps(local_geometry(record,updated)),xyz=[],reason='Giữ STT/bóng chú thích; đầu mũi tên theo mặt lắp đã gắn BOM nguồn')
            previous=moves.get(op.ref) or ops.get(op.ref)
            if previous and not equivalent_operation(previous,op):raise ValueError('Mũi tên cụm xung đột với mặt chi tiết sau sửa')
            if previous:continue
            moves[op.ref]=op
        # Bind external assembly measurements to the actual body corners.
        for e in by.values():
            if e['type']!='DIMENSION' or e.get('dimension_type') not in (0,1) or not e.get('geometry') or e['geometry'].get('text') not in ('','<>') or sid not in e.get('source_sheet_ids',[]) or any(e['ref'].startswith(r+'/') for r in local):continue
            g=world(e)['geometry'];mapped={}
            for key in ('defpoint2','defpoint3'):
                possible=[]
                for r,f in local.items():
                    for p,q0 in vertices[r]:
                        if np.linalg.norm(np.asarray(p)-g[key])>TOL:continue
                        q=np.asarray(q0)+shifts[r]
                        possible.append(q)
                    # A true gap/assembly DIM can terminate in the interior of
                    # a straight face, rather than exactly at a CAD vertex.
                    for edge0,edge1 in edge_maps[r]:
                        p0,p1=np.asarray(edge0[0]),np.asarray(edge0[1]);v=p1-p0;length2=float(v@v)
                        if length2<TOL*TOL:continue
                        t=float((np.asarray(g[key])-p0)@v/length2)
                        if -TOL<=t<=1+TOL and np.linalg.norm(p0+t*v-g[key])<TOL:
                            possible.append(np.asarray(edge1[0])+t*(np.asarray(edge1[1])-edge1[0])+shifts[r])
                if not possible or any(not near(q.tolist(),possible[0].tolist(),TOL) for q in possible):break
                mapped[key]=possible[0].tolist()
            if len(mapped)!=2:continue
            dimension_proofs[e['ref']]=sorted({q for f in local.values() for q in f['evidence_refs']})
            if all(near(g[k],mapped[k],TOL) for k in mapped):continue
            from cad.frame_geometry import local_geometry
            updated=copy.deepcopy(g)
            for k,p in mapped.items():updated[k]=p
            delta=np.mean([np.asarray(mapped[k])-g[k] for k in mapped],axis=0)
            updated['defpoint']=(np.asarray(g['defpoint'])+delta).tolist();updated['text']='<>'
            from cad.edit_engine import Operation
            op=Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(local_geometry(e,updated)),xyz=[],reason='Đồng bộ DIM cụm theo góc CAD native đã gắn')
            if e['ref'] in ops:
                existing=ops[e['ref']]
                if existing.action!='replace_geometry' or any(not near(json.loads(existing.after)[k],json.loads(op.after)[k],TOL) for k in ('defpoint2','defpoint3')):
                    raise ValueError('DIM cụm trực tiếp không khớp tiếp xúc native')
                dimension_proofs[e['ref']]=sorted({q for f in local.values() for q in f['evidence_refs']})
                continue
            moves[e['ref']]=op;dimension_proofs[e['ref']]=sorted({q for f in local.values() for q in f['evidence_refs']})
    from backend.services.change_service import DependencyProposal,EditProposal
    for p in proofs:
        if any(d.coordinate_rule==p['rule'] for d in plan.dependencies):continue
        plan.dependencies.append(DependencyProposal(source_part=p['source_part'],target_part=p['target_part'],
            relationship='source-proven planar native end-face contact',evidence_refs=p['evidence_refs'],
            required_change='Dịch instance theo trục '+p['world_axis'].upper()+' để giữ tiếp xúc đầu mặt 2D; giữ nguyên hình dạng chi tiết nhận.',needs_confirmation=True,coordinate_rule=p['rule']))
    for ref,op in moves.items():
        if ref in ops:
            if op.model_dump()!=ops[ref].model_dump():raise ValueError('Thao tác trực tiếp xung đột tiếp xúc native')
            continue
        plan.operations.append(op)
        code=next((p['target_part'] for p in proofs if p['rule'].target_ref==ref),plan.target_part)
        plan.edits.append(EditProposal(entity_ref=ref,part_number=code,purpose='geometry',before=op.before,after=op.after or json.dumps(op.xyz),reason=op.reason))
    if audit is not None:
        audit.update(certified_refs=sorted(set(moves)|set(dimension_proofs)|annotation_refs),sheets=sorted(contact_sheets),annotation_bindings=annotation_proofs,
            contact_dependencies=[dict(sheet_id=p['sheet_id'],source_part=p['source_part'],target_part=p['target_part'],evidence_refs=p['evidence_refs']) for p in proofs])
    return plan


def synchronize(plan,context,audit=None):
    """Solve native contacts in each driven assembly's measured orthogonal basis."""
    if plan.questions or not plan.operations:return plan
    from graph.contact_frames import angles,rotated
    bases=angles(plan,context)
    reports=[];report={}
    plan=_synchronize_axis_aligned(plan,context,report)
    reports.append(report)
    for angle in bases:
        report={}
        previous_dependencies=len(plan.dependencies)
        # Span recipes were compiled once from native geometry above. This
        # pass restores their measured basis for contacts, gaps and DIMs.
        plan=_synchronize_axis_aligned(plan,rotated(context,angle),report,allow_span_fits=False)
        for dep in plan.dependencies[previous_dependencies:]:
            dep.required_change=f'Dịch instance theo mặt tiếp xúc trong hệ trục cụm xoay {math.degrees(angle):g}°; giữ nguyên hình dạng chi tiết nhận.'
        reports.append(report)
    if audit is not None:
        audit.update(certified_refs=sorted({ref for r in reports for ref in r.get('certified_refs',[])}),
            sheets=sorted({sid for r in reports for sid in r.get('sheets',[])}),
            contact_dependencies=[p for r in reports for p in r.get('contact_dependencies',[])],
            annotation_bindings=[p for r in reports for p in r.get('annotation_bindings',[])],
            analysis_angles_degrees=[math.degrees(a) for a in bases])
    return plan


def validate(plan,context):
    if plan.questions or not plan.operations:return
    from graph.native_span_fits import validate as validate_span_fits
    validate_span_fits(plan,context)
    checked=synchronize(plan.model_copy(deep=True),context)
    if len(checked.operations)!=len(plan.operations):
        raise ValueError('Thiếu thao tác giữ tiếp xúc/DIM cụm native 2D')
    rules=[d.coordinate_rule for d in plan.dependencies if d.coordinate_rule]
    if any(d.coordinate_rule and d.coordinate_rule not in rules for d in checked.dependencies):
        raise ValueError('Thiếu ràng buộc giữ tiếp xúc native 2D')


def reviews(plan,context):
    """Recompute contact motion before allowing an assembly certification."""
    from graph.native_instances import inventory as native_inventory,validate_sync
    try:
        from graph.native_span_fits import validate as validate_span_fits
        validate_span_fits(plan,context)
        validate_sync(plan,context);audit={};checked=synchronize(plan.model_copy(deep=True),context,audit)
        if len(checked.operations)!=len(plan.operations):return {}
        rules=[d.coordinate_rule for d in plan.dependencies if d.coordinate_rule]
        if any(d.coordinate_rule and d.coordinate_rule not in rules for d in checked.dependencies):return {}
    except ValueError:return {}
    records,parts,owner=native_inventory(context);result={}
    _,measured_parts,_=inventory(context,allow_profiles=True)
    certified=set(audit.get('certified_refs',[]))
    for sid in audit.get('sheets',[]):
        local=[e for e in records.values() if sid in e.get('source_sheet_ids',[])]
        tables=[e for e in local if e.get('bom',{}).get('status')=='verified_template']
        resources={ref for e in tables if e['type']=='GRAPHIC_TABLE' for ref in [e['ref'],*e.get('source_refs',[])]}
        table_roots={e['ref'] for e in tables if e['type']=='ACAD_TABLE'}
        sheet=next(t for t in context['targets'] if t['id']==sid);frame=sheet.get('frame_insert')
        missing={e['ref']:parts[e['ref']] for e in local if e['ref'] in parts and e['ref'] not in measured_parts
                 and not any(ref.startswith(e['ref']+'/') for ref in measured_parts)}
        if missing:
            result[sid]=dict(sheet_id=sid,status='unverified_native_2d_contacts',verified_views=[],unmeasured_native_parts=missing,
                reason='Có chi tiết native chưa xác định đủ profile/DIM để kiểm tra lắp ghép: '+', '.join(sorted(set(missing.values())))+'.')
            continue
        unknown=[]
        for e in local:
            ref=e['ref']
            if owner(ref) or ref in parts or ref in certified or ref in resources or ref==sid:continue
            if any(ref==r or ref.startswith(r+'/') for r in table_roots) or frame and (ref==frame or ref.startswith(frame+'/')):continue
            if e['type']=='INSERT' and any(r.startswith(ref+'/') for r in parts):continue
            if e['type'] not in ('TEXT','MTEXT','ATTRIB','ATTDEF'):unknown.append(ref)
        if unknown:continue
        result[sid]=dict(sheet_id=sid,status='verified_native_2d_contacts',
            verified_views=[dict(sheet_id=sid,view='Tiếp xúc đầu mặt trong cụm native 2D',status='verified_view',refs=sorted(certified),binding_count=len(certified))],
            reason='Đã giải lại vị trí từ mặt tiếp xúc 2D, kiểm tra khe hở/chồng lấn và DIM cụm. Không chứng nhận tiếp xúc 3D ẩn hoặc độ bền.')
        arrows=[p for p in audit.get('annotation_bindings',[]) if p['sheet_id']==sid]
        if arrows:
            refs=sorted({ref for p in arrows for ref in (p['leader_ref'],p['circle_ref'],p['number_text_ref'])})
            result[sid]['verified_views'].append(dict(sheet_id=sid,view='STT và đầu mũi tên theo mặt chi tiết đã gắn BOM',
                status='verified_view',refs=refs,binding_count=len(refs),arrow_count=len(arrows),source_hash=context['source_hash']))
    return result
