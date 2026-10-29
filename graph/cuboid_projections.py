"""Source-owned metric cuboid depictions; fixed ends require source choices.

Partial bodies never grant native-root ownership or assembly completeness.
Only a centered source recipe or an explicit hash-bound depiction datum may
drive edits. Every target edge, source DIM and BOM size is re-read each time.
"""
import hashlib
import itertools
import json
import math
import re
from collections import defaultdict

import numpy as np
from bom.reader import plain
from cad.cuboid_projection import components,cameras,resize,TOL
from cad.frame_geometry import world,matrix
from cad.geometry import near


def specification(text):
    raw=plain(text)
    if re.search(r'\binch\b|["″]',raw,re.I):return None
    matches=list(re.finditer(r'(?<![\d.,x×])(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)(?![\d.,])',raw))
    if len(matches)!=1 or re.match(r'\s*[x×]\s*\d',raw[matches[0].end():]):return None
    sizes=[float(v.replace(',','.')) for v in matches[0].groups()]
    return sizes if all(math.isfinite(v) and v>TOL for v in sizes) else None


def conservative_bounds(record):
    """Reject only definitely remote metadata, including native HATCH logos."""
    from backend.services.geometry_retrieval import local_bounds
    g=record.get('geometry',{});metadata=record.get('read_only_geometry',{})
    bounds=None
    if record['type']=='HATCH':
        from ezdxf.math import OCS,Vec3
        plane=metadata.get('extrusion') or record.get('hatch_translation_geometry',{}).get('extrusion')
        elevation=metadata.get('elevation')
        if plane is None or elevation is None:return None
        try:
            if not np.isfinite([*plane,*elevation]).all() or len(elevation)!=3:return None
            ocs=OCS(Vec3(plane));z=float(elevation[2])
            if Vec3(plane).magnitude<TOL:return None
        except (ValueError,TypeError,ZeroDivisionError):return None
        paths=metadata.get('analytic_boundary_paths') or metadata.get('boundary_paths',[]);points=[]
        for path in paths:
            if path.get('edges'):
                for edge in path['edges']:
                    if edge['type']=='LINE':points.extend([[*edge[k],z] for k in ('start','end')])
                    elif edge['type'] in ('ARC','ELLIPSE'):
                        center=np.asarray(edge['center'])
                        if edge['type']=='ARC':r=np.array([edge['radius']]*2)
                        else:
                            major=np.asarray(edge['major_axis']);minor=np.array([-major[1],major[0]])*edge['ratio']
                            r=np.sqrt(major*major+minor*minor)
                        points.extend([[x,y,z] for x,y in itertools.product(*zip(center-r,center+r))])
                    else:return None
                continue
            vertices=path.get('vertices',[])
            if not vertices:return None
            for a,b in zip(vertices,vertices[1:]+vertices[:1]):
                points.append([a[0],a[1],z]);bulge=a[2] if len(a)>2 else 0
                if bulge:
                    delta=np.asarray(b[:2])-a[:2];length=np.linalg.norm(delta)
                    if length<=TOL:return None
                    center=(np.asarray(a[:2])+b[:2])/2+np.array([-delta[1],delta[0]])*(1-bulge*bulge)/(4*bulge)
                    radius=length*(1+bulge*bulge)/(4*abs(bulge))
                    # All four OCS corners are needed before an oblique or
                    # reversed plane is transformed into the entity frame.
                    points.extend([[x,y,z] for x,y in itertools.product(*zip(center-radius,center+radius))])
        points=[list(ocs.to_wcs(Vec3(p))) for p in points]
        if points:bounds=[[min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)]]
    elif record['type'] in ('LWPOLYLINE','POLYLINE') and g and not near(g.get('extrusion',[0,0,1]),[0,0,1],TOL):return None
    elif record['type']=='POLYLINE' and not g and metadata.get('points'):
        points=metadata['points'];bounds=[[min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)]]
    elif record['type'] in ('LWPOLYLINE','POLYLINE') and any(p[4] for p in g.get('points',[])):
        if not near(g.get('extrusion',[0,0,1]),[0,0,1],TOL):return None
        points=[[p[0],p[1],g['elevation']] for p in g['points']]
        vertices=g['points'];pairs=list(zip(vertices,vertices[1:]+vertices[:1])) if g['closed'] else list(zip(vertices,vertices[1:]))
        for a,b in pairs:
            bulge=a[4]
            if not bulge:continue
            delta=np.asarray(b[:2])-a[:2];length=np.linalg.norm(delta)
            if length<=TOL:return None
            center=(np.asarray(a[:2])+b[:2])/2+np.array([-delta[1],delta[0]])*(1-bulge*bulge)/(4*bulge)
            radius=length*(1+bulge*bulge)/(4*abs(bulge));points.extend([[*(center-radius),g['elevation']],[*(center+radius),g['elevation']]])
        bounds=[[min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)]]
    elif record['type']=='ELLIPSE':
        from cad.curve_bounds import ellipse_bounds
        bounds=ellipse_bounds(g)
    elif record['type']=='SPLINE':
        from cad.curve_bounds import positive_control_hull
        # Native control points/knots/positive weights define the evaluated
        # curve; auxiliary fit points do not expand it beyond that hull.
        if not positive_control_hull(dict(g,fit_points=[])):return None
        bounds=local_bounds(record)
    elif record['type'] in ('CIRCLE','ARC') and g:
        from ezdxf.math import Vec3,OCS
        center=OCS(Vec3(g.get('extrusion',[0,0,1]))).to_wcs(Vec3(g['center']));radius=g['radius']
        bounds=[[v-radius for v in center],[v+radius for v in center]]
    else:bounds=local_bounds(record)
    if bounds is None:return None
    points=[matrix(record).transform(p) for p in itertools.product(*zip(*bounds))]
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]


def native_curve_endpoints(record):
    """Read elliptical endpoints without granting its plane edit support."""
    if record['type']!='ELLIPSE':return []
    from ezdxf.math import Vec3
    g=record.get('geometry',{})
    try:
        a=Vec3(g['major_axis']);b=Vec3(g.get('extrusion',[0,0,1])).normalize().cross(a)*g['ratio'];c=Vec3(g['center'])
        return [list(matrix(record).transform(c+a*math.cos(t)+b*math.sin(t))) for t in (g['start_param'],g['end_param'])]
    except (KeyError,ValueError,ZeroDivisionError):return []


def clear_after(context,body,changes):
    """Keep source contacts and reject new overlap with any external stroke."""
    from shapely.geometry import MultiPoint,Point,LineString,box
    records={e['ref']:e for e in context['entities']};points=[]
    for ref in body['refs']:
        g=world(dict(records[ref],geometry=changes.get(ref,records[ref]['geometry'])))['geometry'];points.extend([g['start'],g['end']])
    polygon=MultiPoint([p[:2] for p in points]).convex_hull;interior=polygon.buffer(-TOL);z=points[0][2]
    for contact in body.get('boundary_contacts',[]):
        if any(polygon.boundary.distance(Point(p[:2]))>TOL for p in contact['points']):return False
    for e in records.values():
        if e['ref'] in body['refs'] or e.get('review_only') or e.get('layout')!=body['layout'] or not set(body['sheet_ids']).intersection(e.get('source_sheet_ids',[])):continue
        if e['type'] in ('TEXT','MTEXT','ATTRIB','ATTDEF','LEADER','DIMENSION','INSERT','ACAD_TABLE','GRAPHIC_TABLE'):continue
        bounds=conservative_bounds(e)
        if bounds and (bounds[2]<polygon.bounds[0]-TOL or bounds[0]>polygon.bounds[2]+TOL or bounds[3]<polygon.bounds[1]-TOL or bounds[1]>polygon.bounds[3]+TOL):continue
        if bounds and bounds[2]-bounds[0]>TOL and bounds[3]-bounds[1]>TOL and not interior.intersects(box(*bounds)):continue
        try:w=world(e)
        except ValueError:return False
        g=w.get('geometry',{})
        if e['type']=='LINE' and g:
            if max(abs(g[k][2]-z) for k in ('start','end'))>TOL:continue
            if interior.intersects(LineString([g['start'][:2],g['end'][:2]])):return False
        elif e['type'] in ('LWPOLYLINE','POLYLINE') and g and not any(p[4] for p in g['points']):
            path=[p[:2] for p in g['points']]
            if g['closed']:path=path+path[:1]
            if interior.intersects(LineString(path)):return False
        elif not bounds or interior.intersects(box(*bounds)):return False
    return True


def inventory(context,audit=None,proposed_part_code=None):
    if context.get('units')!=4 or not context.get('source_hash'):return []
    from shapely.geometry import MultiPoint,Point,LineString,box
    from graph.part_map import locator_bounds
    from cad.part_identity import record_identity
    records={e['ref']:e for e in context['entities']};bodies=components(records.values());result=[]
    rows=defaultdict(list)
    for e in records.values():
        if e.get('bom',{}).get('status')=='verified_template':
            for row in e['bom']['rows']:rows[row['part_code']].append((e,row))
    markers=context.get('source_features',{}).get('leader_profile_bindings',[])
    choices=context.get('design_choices',{})
    confirmed=choices.get('confirmed_choices',[]) if choices.get('source_hash')==context['source_hash'] else []
    candidates=[]
    for body in bodies:
        if not body['maps']:continue
        representative=records[body['refs'][0]]
        try:
            verts=body['maps'][0]['vertices']
            world_points=[world(dict(representative,type='LINE',geometry=dict(start=v['point'],end=v['point'])))['geometry']['start'] for v in verts]
        except ValueError:continue
        polygon=MultiPoint([p[:2] for p in world_points]).convex_hull
        if polygon.area<=TOL:continue
        z=world_points[0][2];codes=set();evidence=[]
        # Native identity is a whole-body claim only for a root containing
        # precisely this body, with no other physical component inside it.
        root=representative['ref'].rsplit('/',1)[0] if '/' in representative['ref'] else None
        if root and root in records:
            children=[e for e in records.values() if e['ref'].startswith(root+'/') and e['type'] not in ('TEXT','MTEXT','ATTRIB','ATTDEF')]
            code=record_identity(records[root],set(rows))
            if code and {e['ref'] for e in children}==set(body['refs']):codes.add(code);evidence.append(root)
        for marker in markers:
            if len(marker.get('part_codes',[]))!=1 or not set(body['sheet_ids']).intersection(marker.get('sheet_ids',[])):continue
            code=marker['part_codes'][0];number=marker.get('part_number')
            tables=[records.get(r,{}) for r in marker.get('bom_table_refs',[])]
            if not tables or any(t.get('bom',{}).get('status')!='verified_template' for t in tables):continue
            local={r['part_code'] for t in tables for r in t['bom']['rows'] if str(r['part_number']).lstrip('0')==str(number).lstrip('0')}
            if local!={code}:continue
            for endpoint in marker.get('leader_endpoints',[]):
                leader=records.get(endpoint['ref'],{})
                if leader.get('type')!='LEADER' or leader.get('review_only'):continue
                try:
                    points=world(leader)['geometry']['vertices'];point=points[endpoint['vertex_index']]
                except (ValueError,KeyError,IndexError):continue
                if not near(point,endpoint['point'],TOL) or abs(point[2]-z)>TOL:continue
                if polygon.buffer(-TOL).contains(Point(point[:2])):
                    codes.add(code);evidence.extend(marker.get('evidence_refs',[]))
        source_codes=set(codes)
        for choice in confirmed:
            if choice.get('key')!='cuboid_projection_datum' or choice.get('confirmation')!='user_confirmed_cuboid_identity_and_datum' or sorted(choice.get('target_refs',[]))!=body['refs']:continue
            code=choice.get('part_code')
            signature=hashlib.sha256(json.dumps([context['source_hash'],body['refs'],code],sort_keys=True).encode()).hexdigest()[:24]
            if code in rows and choice.get('body_id')==signature:
                codes.add(code);evidence.append(choice['dimension_ref'])
        if proposed_part_code in rows:codes.add(proposed_part_code)
        if len(codes)!=1:continue
        code=next(iter(codes));specs=[specification(row['description']) for _,row in rows[code]]
        if not specs or any(v is None or not near(v,specs[0],TOL) for v in specs):continue
        fits=cameras(body,specs[0])
        if not fits:continue
        # Other physical strokes or unclassified curves inside the depiction
        # keep it unresolved. Leaders, labels and BOM text are annotations.
        blocked=[];contacts=[]
        for e in records.values():
            if e['ref'] in body['refs'] or e.get('review_only') or e.get('layout')!=body['layout'] or not set(body['sheet_ids']).intersection(e.get('source_sheet_ids',[])):continue
            if e['type'] in ('TEXT','MTEXT','ATTRIB','ATTDEF','LEADER','DIMENSION','INSERT','ACAD_TABLE','GRAPHIC_TABLE'):continue
            bounds=conservative_bounds(e)
            if bounds and (bounds[2]<polygon.bounds[0]-TOL or bounds[0]>polygon.bounds[2]+TOL or bounds[3]<polygon.bounds[1]-TOL or bounds[1]>polygon.bounds[3]+TOL):continue
            straight=e['type']=='LINE' or e['type'] in ('LWPOLYLINE','POLYLINE') and e.get('geometry') and not any(p[4] for p in e['geometry']['points'])
            if not straight and bounds and bounds[2]-bounds[0]>TOL and bounds[3]-bounds[1]>TOL and not polygon.buffer(-TOL).intersects(box(*bounds)):
                if polygon.boundary.distance(box(*bounds))<=TOL:
                    touching=[p for p in native_curve_endpoints(e) if abs(p[2]-z)<=TOL and polygon.boundary.distance(Point(p[:2]))<=TOL]
                    if touching:contacts.append(dict(ref=e['ref'],points=touching))
                    else:blocked.append(e['ref'])
                continue
            try:w=world(e)
            except ValueError:blocked.append(e['ref']);continue
            g=w.get('geometry',{})
            if e['type']=='LINE' and g:
                if max(abs(g[k][2]-z) for k in ('start','end'))>TOL:continue
                path=LineString([g['start'][:2],g['end'][:2]])
                if polygon.buffer(-TOL).intersects(path):blocked.append(e['ref'])
                else:
                    intersection=path.intersection(polygon.boundary)
                    paths=list(intersection.geoms) if hasattr(intersection,'geoms') else [intersection]
                    touching=[[p[0],p[1],z] for item in paths if hasattr(item,'coords') for p in item.coords]
                    if touching:contacts.append(dict(ref=e['ref'],points=touching))
            elif e['type'] in ('LWPOLYLINE','POLYLINE') and g and not any(p[4] for p in g['points']):
                points=[p[:2] for p in g['points']]
                if g['closed']:points=points+points[:1]
                if polygon.buffer(-TOL).intersects(LineString(points)):blocked.append(e['ref'])
            else:
                bounds=bounds or locator_bounds(w)
                if bounds is None or polygon.buffer(-TOL).intersects(box(*bounds)):blocked.append(e['ref'])
        if blocked:
            if audit is not None:audit.append(dict(part_code=code,refs=body['refs'],unclassified_refs=blocked))
            continue
        signature=hashlib.sha256(json.dumps([context['source_hash'],body['refs'],code],sort_keys=True).encode()).hexdigest()[:24]
        candidates.append(dict(body,part_code=code,before_spec_mm=specs[0],id=signature,evidence_refs=sorted(set(evidence+[t['ref'] for t,_ in rows[code]])),
            source_hash=context['source_hash'],orthographic_scale=fits[0]['scale'],metric_error=max(f['relative_metric_error'] for f in fits),
            boundary_contacts=contacts,
            status='candidate_cuboid_identity' if proposed_part_code and not source_codes else 'verified_metric_cuboid_identity',complete_assembly=False))
    # One leader can point into overlapping projected bodies. Unique shape
    # fitting does not rescue ambiguous source ownership.
    for body in candidates:
        if any(set(body['evidence_refs']).intersection(other['evidence_refs'])-set(t['ref'] for t,_ in rows[body['part_code']])
               for other in candidates if other is not body and body['part_code']==other['part_code']):continue
        result.append(body)
    return result


def drivers(plan,context,body):
    from graph.parameter_links import feature
    records={e['ref']:e for e in context['entities']};ops={o.ref:o for o in plan.operations};old=body['before_spec_mm'];found=[]
    for recipe in getattr(plan,'resize_recipes',[]):
        if recipe.part_code!=body['part_code'] or recipe.new_measurement is None or recipe.hole_refs:continue
        try:f=feature(context,recipe.dimension_ref)
        except ValueError:continue
        from cad.measured_features import rectangle
        shape=rectangle(f['points'])
        if set(f['refs'])!=set(recipe.outline_refs) or shape is None:continue
        d=records.get(recipe.dimension_ref);op=ops.get(recipe.dimension_ref)
        if not d or not op or op.action!='replace_geometry' or not near(json.loads(op.before),d['geometry'],TOL):continue
        before=d.get('scaled_measurement');indices=[i for i,value in enumerate(old) if near(value,before,TOL)]
        if len(indices)!=1:continue
        remaining=[v for i,v in enumerate(old) if i!=indices[0]]
        factor=abs(next((b['linear_factor'] for b in f['dimensions'] if b['ref']==recipe.dimension_ref),1))
        lengths=[float(length)*factor for length in shape['lengths']]
        if not any(near(length,v,TOL) for length in lengths if not near(length,before,TOL) for v in remaining):continue
        # Recompile the measured source recipe and compare every operation,
        # so a BOM label or recipe alone never authorizes a depiction edit.
        try:
            from cad.multi_resize import resize_many
            from graph.native_instances import equivalent_operation
            expected=resize_many([recipe],context,{recipe.dimension_ref:recipe.new_measurement})
            if any(o.ref not in ops or not equivalent_operation(o,ops[o.ref]) for o in expected):continue
        except ValueError:continue
        after=list(old);after[indices[0]]=recipe.new_measurement
        # An independent executed BOM edit must agree with the measured DIM.
        values={tuple(specification(e.after) or []) for e in getattr(plan,'edits',[]) if e.part_number==body['part_code'] and e.purpose=='bom' and specification(e.before)==old}
        if values!={tuple(after)}:continue
        from bom.operations import cell_operations
        valid=True
        for table in records.values():
            for row in table.get('bom',{}).get('rows',[]):
                if row['part_code']!=body['part_code']:continue
                cell=row.get('cells',{}).get('description',{});mirror=ops.get(cell.get('mirror_ref'))
                if table['bom'].get('status')!='verified_template' or not mirror or specification(mirror.after)!=after:
                    valid=False;break
                try:expected_cells=cell_operations(table,cell,mirror.after,records,'Source check')
                except ValueError:valid=False;break
                if any(not any(equivalent_operation(expected,actual) for actual in plan.operations) for expected in expected_cells):valid=False;break
        if not valid:continue
        found.append((recipe,after))
    return found


def bindings(plan,context):
    if getattr(plan,'questions',[]) or not plan.operations or not getattr(plan,'resize_recipes',[]):return []
    from cad.edit_engine import Operation
    records={e['ref']:e for e in context['entities']};removed={o.ref for o in plan.operations if o.action=='remove_insert'};result=[]
    choices=context.get('design_choices',{})
    saved=choices.get('confirmed_choices',[]) if choices.get('source_hash')==context.get('source_hash') else []
    for body in inventory(context):
        if any(ref==r or ref.startswith(r+'/') for ref in body['refs'] for r in removed):continue
        source=drivers(plan,context,body)
        if len(source)!=1:continue
        recipe,after=source[0]
        decisions=[d for d in saved if d.get('key')=='cuboid_projection_datum' and d.get('body_id')==body['id'] and d.get('part_code')==body['part_code'] and d.get('dimension_ref')==recipe.dimension_ref]
        if len(decisions)>1:raise ValueError('Hình hộp có nhiều mốc giữ đã xác nhận mâu thuẫn')
        decision=decisions[0] if decisions else dict(anchor='center') if recipe.anchor=='center' else None
        if decision is None:continue
        try:changed=resize(body,records,body['before_spec_mm'],after,decision.get('anchor'),decision.get('fixed_point'))
        except ValueError:continue
        if not clear_after(context,body,changed):continue
        operations=[Operation(ref=ref,action='replace_geometry',before=json.dumps(records[ref]['geometry']),after=json.dumps(g),xyz=[],
                    reason='Hình hộp chiếu trực giao: đủ cạnh, mã BOM, ba kích thước và mốc giữ đã xác định; giữ camera nguồn') for ref,g in changed.items() if not near(g,records[ref]['geometry'],TOL)]
        # A dedicated coded root owns its notes. A sub-body inside a larger
        # anonymous assembly never borrows neighboring text by proximity.
        from cad.part_identity import record_identity
        root=body['coordinate_frame'][9:] if (body['coordinate_frame'] or '').startswith('instance:') else None
        children=[e for e in records.values() if root and e['ref'].startswith(root+'/')]
        confirmed_body=any(v.get('body_id')==body['id'] and v.get('confirmation')=='user_confirmed_cuboid_identity_and_datum' for v in saved)
        if root and (record_identity(records.get(root,{}),{body['part_code']})==body['part_code'] or confirmed_body) and {e['ref'] for e in children if e['type'] not in ('TEXT','MTEXT','ATTRIB','ATTDEF')}==set(body['refs']):
            for text in children:
                if text['type'] not in ('TEXT','MTEXT'):continue
                raw=text.get('raw_text',text.get('text',''))
                values={e.after for e in getattr(plan,'edits',[]) if e.part_number==body['part_code'] and e.purpose in ('bom','annotation') and e.before==raw}
                if len(values)>1:raise ValueError('Mô tả hình hộp có nhiều kết quả mâu thuẫn')
                if values:operations.append(Operation(ref=text['ref'],action='replace_text',before=raw,after=next(iter(values)),xyz=[],reason='Đồng bộ mô tả trong block hình hộp có mã nguồn độc lập'))
        if operations:result.append(dict(part_code=body['part_code'],source_dimension_ref=recipe.dimension_ref,source_hash=context['source_hash'],
            body_id=body['id'],sheet_ids=body['sheet_ids'],target_refs=body['refs']+[o.ref for o in operations if o.action=='replace_text'],before_spec_mm=body['before_spec_mm'],after_spec_mm=after,
            datum=decision,operations=operations,status='verified_metric_cuboid_projection',complete_assembly=False))
    return result


def synchronize(plan,context):
    from graph.native_instances import equivalent_operation
    from backend.services.change_service import EditProposal
    by={o.ref:o for o in plan.operations}
    for proof in bindings(plan,context):
        for op in proof['operations']:
            if op.ref in by:
                if not equivalent_operation(op,by[op.ref]):raise ValueError('Hình hộp chiếu có thao tác xung đột: '+op.ref)
            else:
                by[op.ref]=op;plan.operations.append(op)
                plan.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['part_code'],purpose='annotation' if op.action=='replace_text' else 'geometry',before=op.before,after=op.after,reason=op.reason))
    return plan


def validate(plan,context):
    from graph.native_instances import equivalent_operation
    if getattr(plan,'questions',[]) or not plan.operations or not getattr(plan,'resize_recipes',[]):return []
    checked=bindings(plan,context);checked_ids={p['body_id'] for p in checked}
    choices=context.get('design_choices',{})
    if choices.get('source_hash')==context.get('source_hash'):
        active=[v for v in choices.get('confirmed_choices',[]) if v.get('key')=='cuboid_projection_datum' and v.get('confirmation')=='user_confirmed_cuboid_identity_and_datum' and
                any(r.part_code==v['part_code'] and r.dimension_ref==v['dimension_ref'] and r.new_measurement is not None and
                    any(e['ref']==r.dimension_ref and not near(r.new_measurement,e.get('scaled_measurement'),TOL) for e in context['entities'])
                    for r in getattr(plan,'resize_recipes',[]))]
        for link in active:
            if link.get('unavailable_scope_ids') or link['body_id'] not in checked_ids:raise ValueError('Hình hộp đã gắn thiếu phạm vi, nguồn hoặc thao tác; cần đọc và gắn lại: '+link['body_id'])
    # Deleting a confirmation must also invalidate old saved plans, even
    # though those plans still contain the previously generated target ops.
    edited={o.ref for o in plan.operations if o.action=='replace_geometry'}
    raw=[b for b in components(context['entities']) if edited.intersection(b['refs'])]
    if raw:
        source_codes={r.part_code for r in getattr(plan,'resize_recipes',[])}
        possible={r['part_code'] for e in context['entities'] for r in e.get('bom',{}).get('rows',[]) if r['part_code'] in source_codes and
                  specification(r['description']) and any(cameras(b,specification(r['description'])) for b in raw)}
        for code in possible:
            for body in inventory(context,proposed_part_code=code):
                if edited.intersection(body['refs']) and body['id'] not in checked_ids:raise ValueError('Hình hộp đã sửa không còn liên kết danh tính/mốc giữ hợp lệ: '+body['id'])
    if not checked:return []
    actual={o.ref:o for o in plan.operations}
    for proof in checked:
        for op in proof['operations']:
            if op.ref not in actual or not equivalent_operation(op,actual[op.ref]):raise ValueError('Thiếu/sai thao tác hình hộp chiếu: '+op.ref)
    return checked
