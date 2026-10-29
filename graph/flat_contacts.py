"""Source-bound 2D contact solving for loose LINE/polyline part drawings.

Identity comes from a re-read local BOM/balloon/leader chain, never proximity,
file names or matching silhouettes. Source closed faces and real DIMs determine
the equations; geometry stays on its original handles and layout.
"""
import copy
import json
import math
from collections import defaultdict
import numpy as np
import networkx as nx
from cad.geometry import near
from cad.frame_geometry import world
from cad.closed_profiles import polygon_from,segments

TOL=1e-5
RELATION='source-proven loose 2D end-face contact'
PREFIX='Liên động biên rời: '


def inventory(context):
    from cad.measured_features import index
    from graph.part_map import outline_shape
    report=context.get('source_features') or index(context,context.get('part_graph'))
    records={e['ref']:e for e in context['entities']};physical=defaultdict(list)
    if not any(f.get('ownership_proof')=='local_bom_leader_profile' and not f.get('instance_ref') for f in report.get('features',[])):
        return records,{}
    annotations={r for b in report.get('leader_profile_bindings',[]) for r in
                 [b.get('circle_ref'),b.get('number_text_ref'),*[p['ref'] for p in b.get('leader_endpoints',[])]]}
    for e in records.values():
        if e.get('geometry'):
            try:physical[(e.get('layout'),'flat')].append(world(e))
            except ValueError:pass
    circles={key:[e for e in values if e['type']=='CIRCLE' and e['ref'] not in annotations] for key,values in physical.items()}
    assembly_ids={sid for e in records.values() if e.get('bom',{}).get('status')=='verified_template' and
                  len(e['bom']['rows'])>1 for sid in e.get('source_sheet_ids',[])}
    bodies={}
    for f in report.get('features',[]):
        refs=f['refs'];sids=set(f.get('sheet_ids',[]))&assembly_ids
        if not sids or f.get('ownership_proof')!='local_bom_leader_profile' or f.get('instance_ref') or not refs:
            continue
        if any('/' in r or r not in records or records[r].get('review_only') or records[r]['type'] not in ('LINE','LWPOLYLINE','POLYLINE') for r in refs):continue
        bindings=[b for b in report.get('leader_profile_bindings',[]) if b.get('geometry_owner_verified') and
                  b.get('part_codes')==[f['part_code']] and len(b.get('candidates',[]))==1 and
                  set(b['candidates'][0]['geometry_refs'])==set(refs)]
        if not bindings:continue
        # Re-read the exact local row so a saved feature label cannot supply an
        # invented purchasing code or an STT from a different assembly.
        from bom.reader import part_number_key
        if not any(any(records.get(t,{}).get('bom',{}).get('status')=='verified_template' and
            {r['part_code'] for r in records[t]['bom']['rows'] if part_number_key(r['part_number'])==part_number_key(b['part_number'])}=={f['part_code']}
            for t in b.get('bom_table_refs',[])) for b in bindings):continue
        try:points=polygon_from([world(records[r]) for r in refs])
        except ValueError:continue
        view=dict(geometry_refs=refs,layout=f['layout'],coordinate_frame='flat',dimensions=f['dimensions'])
        shape=outline_shape(view,records,circles,physical,annotations)
        if not shape or shape['unexpected_refs'] or shape['factor']!=1 or context.get('units')!=4:continue
        members=set(refs)|{d['ref'] for d in f['dimensions']}|{e['ref'] for e in shape['circles']}
        if any('/' in r or records[r].get('review_only') for r in members):continue
        key='loose:'+','.join(sorted(refs))
        bodies[key]=dict(f,points=points,members=sorted(members),sheet_ids=sorted(sids),bindings=bindings)
    # One geometric object cannot be silently carried by two physical bodies.
    owners=defaultdict(set)
    for key,f in bodies.items():
        for ref in f['members']:owners[ref].add(key)
    return records,{key:f for key,f in bodies.items() if all(len(owners[r])==1 for r in f['members'])}


def _mapped_point(before,after,point):
    possible=[];q=np.asarray(point)
    for p0,p1,a0,a1 in zip(before,before[1:]+before[:1],after,after[1:]+after[:1]):
        p0,p1,a0,a1=map(np.asarray,(p0,p1,a0,a1));v=p1-p0;length2=float(v@v)
        if length2<=TOL*TOL:continue
        t=float((q-p0)@v/length2)
        if -TOL<=t<=1+TOL and np.linalg.norm(q-p0-t*v)<=TOL:possible.append((a0+t*(a1-a0)).tolist())
    if not possible:return None
    if any(not near(p,possible[0],TOL) for p in possible):raise ValueError('Các mặt cùng điểm nguồn cho chuyển vị khác nhau')
    return possible[0]


def describe(context):
    """Build the mechanical equations from this source, before any edit exists."""
    from graph.planar_face_relations import source_relations
    records,bodies=inventory(context);contacts=source_relations(context,bodies,records)
    return dict(version=2,source_hash=context.get('source_hash'),
        bodies=[dict(id=key,part_code=f['part_code'],layout=f['layout'],sheet_ids=f['sheet_ids'],geometry_refs=f['refs'],
            member_refs=f['members'],dimension_refs=[d['ref'] for d in f['dimensions']],identity_proof=f['ownership_proof']) for key,f in sorted(bodies.items())],
        contacts=contacts,complete_design_understanding=False,
        policy='Local source BOM, interior leader, real DIM and complete straight faces. Preserve measured 2D end-face contacts and explicit DIM clearances; never infer an unmeasured gap or an unidentified receiver.')


def guard_unclassified(context,records,bodies,changes,shifts):
    """Unknown neighbors remain stationary obstacles, never invisible bodies."""
    from shapely.geometry import Polygon,Point,LineString,box
    from graph.part_map import locator_bounds
    allowed={r for f in bodies.values() for r in f['members']}
    allowed.update(t['id'] for t in context.get('targets',[]))
    for e in records.values():
        if e.get('bom',{}).get('status')=='verified_template':allowed.update([e['ref'],*e.get('source_refs',[])])
    for b in (context.get('source_features') or {}).get('leader_profile_bindings',[]):
        allowed.update([b.get('circle_ref'),b.get('number_text_ref'),*[p['ref'] for p in b.get('leader_endpoints',[])]])
    for key,f in bodies.items():
        if near(f['points'],changes[key],TOL) and np.linalg.norm(shifts[key])<=TOL:continue
        polygon=Polygon([(p[0]+shifts[key][0],p[1]+shifts[key][1]) for p in changes[key]]).buffer(-TOL)
        for ref,e in records.items():
            if ref in allowed or e['type'] in ('DIMENSION','TEXT','MTEXT','ATTRIB','ATTDEF','GRAPHIC_TABLE','ACAD_TABLE'):continue
            if e.get('layout')!=f['layout'] or not set(f['sheet_ids']).intersection(e.get('source_sheet_ids',[])):continue
            if not e.get('geometry'):
                raise ValueError('Còn đối tượng chưa định vị trong cụm biên rời: '+ref)
            try:r=world(e)
            except ValueError:raise ValueError('Chưa kiểm được hệ tọa độ của chi tiết lân cận: '+ref)
            bounds=locator_bounds(r)
            if bounds and not polygon.intersects(box(*bounds)):continue
            if e['type']=='CIRCLE':
                g=r['geometry'];hit=polygon.intersects(Point(g['center'][:2]).buffer(g['radius']))
            else:
                edges=segments(r)
                hit=any(polygon.intersection(LineString([a[:2],b[:2]])).length>TOL for a,b in edges) if edges else True
            if hit:raise ValueError('Chuyển vị va vào hình học chưa gắn quan hệ cơ khí: '+ref)


def synchronize(plan,context,audit=None):
    if plan.questions or not plan.operations:return plan
    records,bodies=inventory(context)
    if not bodies:return plan
    from backend.services.change_service import DependencyProposal,EditProposal
    from graph.change_dependencies import CoordinateRule,propagate
    from cad.edit_engine import Operation
    generated={o.ref for o in plan.operations if o.reason.startswith(PREFIX)}
    plan.operations=[o for o in plan.operations if o.ref not in generated]
    plan.edits=[e for e in plan.edits if e.entity_ref not in generated]
    plan.dependencies=[d for d in plan.dependencies if d.relationship!=RELATION]
    ops={o.ref:o for o in plan.operations};changes={};drivers={}
    for key,f in bodies.items():
        changed=[]
        for ref in f['refs']:
            record=copy.deepcopy(records[ref]);op=ops.get(ref)
            if op:
                if op.action!='replace_geometry':raise ValueError('Liên động biên rời cần snapshot hình học đầy đủ')
                record['geometry']=json.loads(op.after)
            changed.append(world(record))
        changes[key]=polygon_from(changed)
        if not near(changes[key],f['points'],TOL):
            source=[d['ref'] for d in f['dimensions'] if d['ref'] in ops and ops[d['ref']].action=='replace_geometry']
            if not source:raise ValueError('Biên rời thay đổi nhưng thiếu DIM thật làm biến điều khiển')
            drivers[key]=source
    if not drivers:return plan
    from graph.native_contacts import profile_contact,bounds
    from graph.planar_face_relations import source_relations,matches_gap
    constraints=source_relations(context,bodies,records)
    all_shifts={key:np.zeros(3) for key in bodies};relations=[];active_sheets=set()
    for sid in sorted({s for f in bodies.values() for s in f['sheet_ids']}):
        local={k:f for k,f in bodies.items() if sid in f['sheet_ids']}
        if not set(local)&drivers.keys():continue
        # Every independent measured basis is derived from the source, allowing
        # a newly uploaded assembly to be rotated anywhere in the layout.
        local_constraints=[r for r in constraints if sid in r['sheet_ids'] and r['source_body'] in local and r['target_body'] in local]
        angles=[]
        for angle in sorted({math.radians(r['analysis_angle_degrees']) for r in local_constraints}):
            if not angles or angle-angles[-1]>1e-9:angles.append(angle)
        local_shift={k:np.zeros(3) for k in local};contacts=[]
        for angle in sorted(angles):
            c,s=math.cos(angle),math.sin(angle);rotation=np.array([[c,s,0],[-s,c,0],[0,0,1]])
            before={k:(np.asarray(f['points'])@rotation.T).tolist() for k,f in local.items()}
            after={k:(np.asarray(changes[k])@rotation.T).tolist() for k in local}
            pairs=[(r['source_body'],r['target_body'],'xy'.index(r['axis']),r['source_side'],r['target_side'])
                   for r in local_constraints if abs(math.radians(r['analysis_angle_degrees'])-angle)<1e-9]
            for axis in (0,1):
                graph=nx.Graph()
                for a,b,k,fa,fb in pairs:
                    if k==axis:graph.add_edge(a,b)
                for component in nx.connected_components(graph):
                    anchored=sorted(component&drivers.keys())
                    if not anchored:continue
                    names=sorted(component);rows=[];rhs=[]
                    for a,b,k,fa,fb in pairs:
                        if k!=axis or a not in component:continue
                        rows.append([(-1. if n==a else 1. if n==b else 0.) for n in names])
                        rhs.append(float((bounds(after[a])[fa,k]-bounds(before[a])[fa,k])-(bounds(after[b])[fb,k]-bounds(before[b])[fb,k])))
                    for a in anchored:rows.append([1. if n==a else 0. for n in names]);rhs.append(0.)
                    if np.linalg.matrix_rank(rows)!=len(names):raise ValueError('Mặt lắp biên rời chưa có nghiệm duy nhất')
                    result=np.linalg.lstsq(rows,rhs,rcond=None)[0]
                    if not np.allclose(np.asarray(rows)@result,rhs,atol=TOL,rtol=0):raise ValueError('Mặt lắp biên rời xung đột mốc giữ')
                    for key,value in zip(names,result):local_shift[key]+=rotation.T[:,axis]*value
                    solved=[r for r in local_constraints if r['source_body'] in component and r['axis']=='xy'[axis]
                            and abs(math.radians(r['analysis_angle_degrees'])-angle)<1e-9]
                    contacts.extend((r,rotation) for r in solved)
                    evidence=tuple(sorted({ref for r in solved for ref in r['evidence_refs']}))
                    for key in component:
                        if key not in drivers:relations.append((key,anchored[0],sid,evidence))
        placed={k:(np.asarray(changes[k])+local_shift[k]).tolist() for k in local}
        for relation,rotation in contacts:
            a,b=relation['source_body'],relation['target_body'];k='xy'.index(relation['axis']);fa,fb=relation['source_side'],relation['target_side']
            first=(np.asarray(placed[a])@rotation.T).tolist();second=(np.asarray(placed[b])@rotation.T).tolist()
            valid=matches_gap(first,second,k,fa,fb,relation['source_gap_mm']) if relation['dimension_refs'] else profile_contact(first,second)==(k,fa,fb)
            if not valid:raise ValueError('Không giữ được mặt tiếp xúc hoặc DIM khe hở nguồn sau sửa')
        from shapely.geometry import Polygon
        keys=sorted(local)
        for i,a in enumerate(keys):
            for b in keys[i+1:]:
                if abs(placed[a][0][2]-placed[b][0][2])<=TOL and Polygon([p[:2] for p in placed[a]]).intersection(Polygon([p[:2] for p in placed[b]])).area>TOL*TOL:
                    raise ValueError('Các chi tiết biên rời bị chồng lấn sau sửa')
        for key,value in local_shift.items():
            if np.linalg.norm(all_shifts[key])>TOL and not near(all_shifts[key].tolist(),value.tolist(),TOL):raise ValueError('Hai khung yêu cầu chuyển vị khác nhau')
            all_shifts[key]=value
        if contacts:active_sheets.add(sid)
    guard_unclassified(context,records,bodies,changes,all_shifts)
    required=[];carried=set();proofs=[]
    for key,driver,sid,relation_evidence in sorted(set(relations)):
        shift=all_shifts[key]
        if np.linalg.norm(shift)<=TOL:continue
        f=bodies[key];source=bodies[driver];source_ref=drivers[driver][0];g0=records[source_ref]['geometry'];g1=json.loads(ops[source_ref].after)
        for ref in f['members']:
            for axis in (0,1):
                if abs(shift[axis])<=TOL:continue
                field=next((k for k in ('defpoint2','defpoint3') if abs(g1[k][axis]-g0[k][axis])>TOL),None)
                if field is None:raise ValueError('Thiếu chuyển vị DIM nguồn theo trục mặt lắp')
                rule=CoordinateRule(source_ref=source_ref,source_field=field,target_ref=ref,target_action='translate_geometry',axis='xy'[axis],
                    multiplier=float(shift[axis]/(g1[field][axis]-g0[field][axis])),composition='orthogonal')
                evidence=sorted(set(f['evidence_refs']+source['evidence_refs']+[ref,source_ref]+list(relation_evidence)))
                dependency=DependencyProposal(source_part=source['part_code'],target_part=f['part_code'],relationship=RELATION,
                    evidence_refs=evidence,required_change='Giữ mặt lắp/DIM khe hở 2D; dịch nguyên biên, lỗ và DIM của chi tiết nhận.',needs_confirmation=True,coordinate_rule=rule)
                if rule not in [d.coordinate_rule for d in required]:required.append(dependency)
            carried.add(ref)
        proofs.append(dict(sheet_id=sid,part_code=f['part_code'],source_part=source['part_code'],member_refs=f['members'],displacement_mm=shift.tolist()))
    expanded=propagate(plan.operations,[d.coordinate_rule for d in required],context)
    for op in expanded:
        if op.ref not in carried:continue
        if op.ref in ops and not near(json.loads(ops[op.ref].after),json.loads(op.after),TOL):raise ValueError('Chi tiết nhận có thay đổi trực tiếp xung đột')
        op.reason=PREFIX+'giữ biên, lỗ và DIM của chi tiết nhận theo mặt lắp nguồn'
    plan.operations=expanded;plan.dependencies.extend(required)
    final={o.ref:o for o in expanded};certified=set(carried)
    annotation_proofs=[]
    for key,f in bodies.items():
        shift=all_shifts[key]
        if np.linalg.norm(shift)<=TOL:continue
        for binding in f['bindings']:
            for endpoint in binding.get('leader_endpoints',[]):
                ref=endpoint['ref'];record=records[ref];g=record['geometry'];changed=copy.deepcopy(g)
                if record['type']=='LEADER':changed['vertices'][endpoint['vertex_index']]=(np.asarray(endpoint['point'])+shift).tolist()
                elif record['type']=='LINE':changed['start' if endpoint['vertex_index']==0 else 'end']=(np.asarray(endpoint['point'])+shift).tolist()
                else:raise ValueError('Đầu leader chưa có adapter giữ liên kết biên rời')
                op=Operation(ref=ref,action='replace_geometry',before=json.dumps(g),after=json.dumps(changed),xyz=[],reason=PREFIX+'đầu leader theo chi tiết; giữ vòng STT và chữ')
                if ref in final and not near(json.loads(final[ref].after),changed,TOL):raise ValueError('Đầu leader có hai chuyển vị xung đột')
                if ref not in final:plan.operations.append(op);final[ref]=op
                certified.update([ref,binding['circle_ref'],binding['number_text_ref']])
                annotation_proofs.append(dict(leader_ref=ref,part_code=f['part_code'],circle_ref=binding['circle_ref'],number_text_ref=binding['number_text_ref']))
    # Total/clearance DIMs belong to the assembly, not an individual body.
    for ref,e in records.items():
        if e['type']!='DIMENSION' or ref in {r for f in bodies.values() for r in f['members']} or not active_sheets.intersection(e.get('source_sheet_ids',[])):
            continue
        g=e.get('geometry',{})
        if e.get('dimension_type') not in (0,1) or g.get('text') not in ('','<>'):continue
        changed=copy.deepcopy(g);mapped={}
        for field in ('defpoint2','defpoint3'):
            possible=[]
            for key,f in bodies.items():
                if not set(f['sheet_ids']).intersection(e.get('source_sheet_ids',[])):continue
                q=_mapped_point(f['points'],(np.asarray(changes[key])+all_shifts[key]).tolist(),g[field])
                if q is not None:possible.append(q)
            if not possible:break
            if any(not near(q,possible[0],TOL) for q in possible):raise ValueError('Đầu DIM cụm có nhiều mặt nguồn với chuyển vị khác nhau')
            mapped[field]=possible[0]
        if len(mapped)!=2:continue
        certified.add(ref)
        if all(near(g[k],mapped[k],TOL) for k in mapped):continue
        changed.update(mapped);delta=np.mean([np.asarray(mapped[k])-g[k] for k in mapped],axis=0)
        changed['defpoint']=(np.asarray(g['defpoint'])+delta).tolist()
        op=Operation(ref=ref,action='replace_geometry',before=json.dumps(g),after=json.dumps(changed),xyz=[],reason=PREFIX+'DIM tổng theo đúng các mặt nguồn')
        if ref in final and not near(json.loads(final[ref].after),changed,TOL):raise ValueError('DIM tổng trực tiếp xung đột với mặt lắp')
        if ref not in final:plan.operations.append(op);final[ref]=op
    existing={e.entity_ref for e in plan.edits}
    for ref,op in final.items():
        if ref in existing:continue
        owner=next((f['part_code'] for f in bodies.values() if ref in f['members']),plan.target_part)
        plan.edits.append(EditProposal(entity_ref=ref,part_number=owner,purpose='geometry',before=op.before,after=op.after,reason=op.reason))
    if audit is not None:audit.update(bodies=bodies,motions=proofs,sheet_ids=sorted(active_sheets),certified_refs=sorted(certified),annotation_bindings=annotation_proofs)
    return plan


def validate(plan,context):
    if plan.questions or not plan.operations:return
    checked=synchronize(plan.model_copy(deep=True),context)
    actual={o.ref:o for o in plan.operations};expected={o.ref:o for o in checked.operations}
    if actual.keys()!=expected.keys() or any(actual[r].action!=op.action or
        (op.action=='replace_geometry' and (not near(json.loads(actual[r].before),json.loads(op.before),TOL) or not near(json.loads(actual[r].after),json.loads(op.after),TOL))) for r,op in expected.items()):
        raise ValueError('Thiếu hoặc sai thao tác giữ quan hệ giữa các biên chi tiết rời')
    rules=[d.coordinate_rule for d in plan.dependencies if d.relationship==RELATION]
    if any(d.relationship==RELATION and d.coordinate_rule not in rules for d in checked.dependencies):
        raise ValueError('Thiếu phương trình mặt lắp biên rời')


def reviews(plan,context):
    """Credit a planar frame only when every non-text object is accounted for."""
    if not hasattr(plan,'model_copy'):return {}
    try:
        validate(plan,context);audit={};synchronize(plan.model_copy(deep=True),context,audit)
    except ValueError:return {}
    records={e['ref']:e for e in context['entities']};result={}
    for sid in audit.get('sheet_ids',[]):
        local=[e for e in records.values() if sid in e.get('source_sheet_ids',[])]
        bodies=[f for f in audit['bodies'].values() if sid in f['sheet_ids']]
        allowed={sid,*audit['certified_refs']}
        for f in bodies:
            allowed.update(f['members'])
            for b in f['bindings']:
                allowed.update([b['circle_ref'],b['number_text_ref'],*[p['ref'] for p in b.get('leader_endpoints',[])]])
        table_roots=[]
        for e in local:
            if e.get('bom',{}).get('status')!='verified_template':continue
            allowed.update([e['ref'],*e.get('source_refs',[])])
            if e['type']=='ACAD_TABLE':table_roots.append(e['ref'])
        unknown=[e['ref'] for e in local if e['ref'] not in allowed and e['type'] not in ('TEXT','MTEXT','ATTRIB','ATTDEF') and
                 not any(e['ref'].startswith(root+'/') for root in table_roots)]
        if unknown:continue
        result[sid]=dict(sheet_id=sid,status='verified_loose_2d_contacts',
            verified_views=[dict(sheet_id=sid,status='verified_view',view='Biên rời: mặt lắp, lỗ, DIM và leader theo BOM nguồn',
                refs=sorted(allowed&records.keys()),binding_count=len(allowed&records.keys()))],
            motions=[p for p in audit['motions'] if p['sheet_id']==sid],
            reason='Đã giải mặt tiếp xúc và khe hở có DIM từ biên kín; kiểm lại hình học, DIM và phạm vi ảnh hưởng 2D.')
    return result
