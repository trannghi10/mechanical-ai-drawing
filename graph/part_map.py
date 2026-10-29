"""Source identities and bounded view correspondence; never edit authorization.

An interior balloon identifies a region even without a DIM. Independent source
identity is required on both sides of a verified SAME_PART_AS observation.
Similar shapes with missing identity remain candidates, including unique ones.
"""
import copy
import hashlib
import json
import math
from collections import defaultdict
from itertools import combinations
from cad.geometry import near
from cad.frame_geometry import world,matrix,planar_similarity

VERSION=6
OWNED={'native_part_identity','selected_native_instance','local_bom_leader_profile'}
REGIONS={'verified_interior_region','verified_interior_dimension_chain'}


def key(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf8')).hexdigest()[:24]


def locator_bounds(record):
    """Conservative rejection only; no sampled curve or endpoint-only bulge box."""
    from cad.curve_bounds import projected_simple_bounds,positive_control_hull
    simple=projected_simple_bounds(record,(1,0,0),(0,1,0))
    if simple:return [simple[0],simple[2],simple[1],simple[3]]
    g=record.get('geometry',{})
    if record['type']=='SPLINE' and positive_control_hull(g):
        points=g['control_points'];return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    if record['type']=='ELLIPSE' and g:
        center=g['center'];radius=math.dist(g['major_axis'],[0,0,0])
        if radius>0 and 0<g['ratio']<=1 and all(math.isfinite(v) for v in (*center,radius)):
            return [center[0]-radius,center[1]-radius,center[0]+radius,center[1]+radius]
    return None


def outline_shape(view,records,circles,physical,annotations,bounds=None):
    """Read exact line/arc primitives; bounded chords are used only for holes."""
    from cad.curved_profiles import primitives,profile_from
    from cad.closed_profiles import polygon_from
    from shapely.geometry import Polygon,Point,LineString
    try:
        source=[world(records[r]) for r in view['geometry_refs']]
        edges=[edge for e in source for edge in primitives(e)]
        if not edges or len(edges)>128 or any(e['kind'] not in ('line','arc') for e in edges):return None
        curved=any(e['kind']=='arc' for e in edges)
        profile=profile_from(source) if curved else dict(points=polygon_from(source),curve_chord_error=0)
        polygon=Polygon([p[:2] for p in profile['points']]);error=profile.get('curve_chord_error',0)
        inside=[]
        for e in circles.get((view['layout'],view['coordinate_frame']),[]):
            g=e['geometry'];point=Point(g['center'][:2])
            if abs(g['center'][2]-profile['points'][0][2])>1e-5:continue
            if polygon.contains(point) and polygon.boundary.distance(point)>g['radius']+error+1e-5:inside.append(e)
        factors={round(d['linear_factor'],10) for d in view['dimensions'] if d.get('linear_factor',0)>0}
        factor=next(iter(factors)) if len(factors)==1 else None
        unexpected=[];allowed=set(view['geometry_refs'])|{e['ref'] for e in inside}|annotations
        interior=polygon.buffer(-max(error,1e-5))
        region=polygon.bounds
        from cad.curved_profiles import edge_points
        for e in physical.get((view['layout'],view['coordinate_frame']),[]):
            if e['ref'] in allowed:continue
            box=bounds.get(e['ref']) if bounds is not None else locator_bounds(e)
            if box and (box[2]<region[0]-error-1e-5 or box[0]>region[2]+error+1e-5 or box[3]<region[1]-error-1e-5 or box[1]>region[3]+error+1e-5):continue
            if e['type']=='CIRCLE':
                if Point(e['geometry']['center'][:2]).buffer(e['geometry']['radius']).intersects(interior):unexpected.append(e['ref'])
                continue
            extra=primitives(e)
            if any(edge['kind']=='nurbs' for edge in extra):
                # An unclassified rational curve inside the region keeps a
                # contour-only match from being presented as a complete view.
                from backend.services.geometry_retrieval import local_bounds
                box=local_bounds(e)
                if box and polygon.intersects(Polygon([(box[0][0],box[0][1]),(box[1][0],box[0][1]),(box[1][0],box[1][1]),(box[0][0],box[1][1])])):unexpected.append(e['ref'])
            elif any(LineString([p[:2] for p in edge_points(edge,True)]).intersects(interior) for edge in extra):unexpected.append(e['ref'])
        return dict(edges=edges,circles=inside,factor=factor,unexpected_refs=unexpected)
    except (ValueError,KeyError,TypeError):return None


def outline_matches(first,second):
    """Exact planar rotation/translation after DIM-calibrated scaling.

    This covers exploded LINE/ARC and polyline outlines. No reflection, nearest
    neighbor assignment, curve sampling equality or inferred projection.
    """
    if not first or not second or first['factor'] is None or second['factor'] is None or first['unexpected_refs'] or second['unexpected_refs']:return []
    a,b=first['edges'],second['edges'];fa,fb=first['factor'],second['factor']
    if len(a)!=len(b) or len(first['circles'])!=len(second['circles']) or len(a)>128:return []
    if sorted(e['kind'] for e in a)!=sorted(e['kind'] for e in b):return []
    from cad.curved_profiles import angle,sweep,arc_point
    def point(p,f):return [p[0]*f,p[1]*f]
    def normalized(edge,f):
        item=dict(kind=edge['kind'],start=point(edge['start'],f),end=point(edge['end'],f))
        if edge['kind']=='arc':
            middle=angle(edge,edge['start'])+(1 if edge['ccw'] else -1)*sweep(edge)/2
            item.update(center=point(edge['center'],f),radius=edge['radius']*f,middle=point(arc_point(edge,middle),f))
        return item
    a=[normalized(e,fa) for e in a];b=[normalized(e,fb) for e in b]
    anchor=max(a,key=lambda e:math.dist(e['start'],e['end']));length=math.dist(anchor['start'],anchor['end'])
    if length<1e-5:return []
    results=[];seen=set()
    def equal(e,f):
        if e['kind']!=f['kind']:return False
        if not (near([e['start'],e['end']],[f['start'],f['end']],1e-5) or near([e['start'],e['end']],[f['end'],f['start']],1e-5)):return False
        return e['kind']=='line' or all(near(e[k],f[k],1e-5) for k in ('center','radius','middle'))
    for target in b:
        if target['kind']!=anchor['kind'] or abs(math.dist(target['start'],target['end'])-length)>1e-5:continue
        for start,end in ((target['start'],target['end']),(target['end'],target['start'])):
            theta=math.atan2(end[1]-start[1],end[0]-start[0])-math.atan2(anchor['end'][1]-anchor['start'][1],anchor['end'][0]-anchor['start'][0])
            cosine,sine=math.cos(theta),math.sin(theta)
            def transform(p):
                x,y=p[0]-anchor['start'][0],p[1]-anchor['start'][1]
                return [start[0]+cosine*x-sine*y,start[1]+sine*x+cosine*y]
            moved=[dict(e,**{k:transform(e[k]) for k in ('start','end','center','middle') if k in e}) for e in a]
            used=set();valid=True
            for edge in moved:
                matches=[i for i,e in enumerate(b) if equal(edge,e)]
                if len(matches)!=1 or matches[0] in used:valid=False;break
                used.add(matches[0])
            if not valid:continue
            used=set()
            for circle in first['circles']:
                g=circle['geometry'];center=transform(point(g['center'],fa));radius=g['radius']*fa
                matches=[i for i,e in enumerate(second['circles']) if near(center,point(e['geometry']['center'],fb),1e-5) and near(radius,e['geometry']['radius']*fb,1e-5)]
                if len(matches)!=1 or matches[0] in used:valid=False;break
                used.add(matches[0])
            if valid:
                translation=transform([0,0]);signature=(round(cosine,9),round(sine,9),round(translation[0],5),round(translation[1],5))
                if signature in seen:continue
                seen.add(signature);results.append(dict(rotation_degrees=math.degrees(theta),source_mm_per_layout_unit=fa,target_mm_per_layout_unit=fb,
                    source_origin_mm=anchor['start'],target_origin_mm=start,scope='closed_outline_and_enclosed_circles'))
    return results


def outline_match(first,second):
    matches=outline_matches(first,second)
    return dict(matches[0],transform_count=len(matches)) if matches else None


def build(context,graph=None):
    graph=graph or context.get('part_graph',{});source=context['source_hash']
    if graph.get('source_hash') and graph['source_hash']!=source:raise ValueError('Part Map source hash không khớp CAD')
    records={e['ref']:e for e in context['entities']};report=context.get('source_features',{});views={};unresolved=[]
    def add(refs,layout,frame,sheets):
        refs=sorted(set(refs));vid='part-view-'+key([source,layout,refs])
        if not refs or not all(r in records and records[r].get('geometry') for r in refs):return None
        view=views.setdefault(vid,dict(id=vid,layout=layout,coordinate_frame=frame,geometry_refs=refs,circle_refs=[],sheet_ids=[],
            part_codes=[],candidate_part_codes=[],identity_proofs=[],bom_bindings=[],dimensions=[],evidence_refs=[],executable=False))
        view['sheet_ids']=sorted(set(view['sheet_ids'])|set(sheets));return view
    for f in report.get('features',[]):
        view=add(f['refs'],f['layout'],f['coordinate_frame'],f.get('sheet_ids',[]))
        if not view:continue
        view['dimensions']=copy.deepcopy(f.get('dimensions',[]))
        view['evidence_refs']=sorted(set(view['evidence_refs'])|set(f.get('evidence_refs',[])))
        if f.get('part_code') and f.get('ownership_proof') in OWNED:
            view['part_codes'].append(f['part_code']);view['identity_proofs'].append(f['ownership_proof'])
        elif f.get('part_code') and f.get('ownership_proof')=='unique_source_detail_sheet':
            # A named detail frame can also contain a stock sheet, cutting
            # layout, side section or a neighboring profile. Its title alone
            # cannot identify every contour as the finished part.
            view['candidate_part_codes'].append(f['part_code']);view['identity_proofs'].append('source_sheet_identity_candidate')
    from bom.continuations import scoped_table_sheets
    bom_scopes=scoped_table_sheets(context)
    for binding in report.get('leader_profile_bindings',[]):
        accepted=binding.get('status') in REGIONS and len(binding.get('part_codes',[]))==1 and len(binding.get('candidates',[]))==1
        rows=[]
        if accepted:
            for ref in binding.get('bom_table_refs',[]):
                table=records.get(ref,{})
                if table.get('bom',{}).get('status')!='verified_template' or not bom_scopes.get(ref,set()).intersection(binding.get('sheet_ids',[])):continue
                from bom.reader import part_number_key
                matches=[r for r in table['bom']['rows'] if part_number_key(r['part_number'])==part_number_key(binding['part_number'])]
                if len(matches)==1 and matches[0]['part_code']==binding['part_codes'][0]:rows.append(dict(table_ref=ref,part_number=binding['part_number'],part_code=matches[0]['part_code'],number_text_ref=binding['number_text_ref']))
        if not rows:
            if binding.get('status')=='owner_identity_conflict':
                for candidate in binding.get('candidates',[]):
                    for view in views.values():
                        if set(view['geometry_refs'])==set(candidate['geometry_refs']):view['conflicting_part_codes']=binding.get('part_codes',[])
            unresolved.append(dict(kind='balloon_identity',part_number=binding.get('part_number'),part_codes=binding.get('part_codes',[]),sheet_ids=binding.get('sheet_ids',[]),
                                   source_status=binding.get('status'),evidence_refs=binding.get('evidence_refs',[])));continue
        candidate=binding['candidates'][0]
        view=add(candidate['geometry_refs'],records[candidate['geometry_refs'][0]]['layout'],candidate['coordinate_frame'],binding['sheet_ids'])
        if not view:continue
        view['part_codes'].extend(binding['part_codes']);view['identity_proofs'].append('source_local_bom_interior')
        view['bom_bindings'].extend(rows);view['evidence_refs']=sorted(set(view['evidence_refs'])|set(binding['evidence_refs']))
    from graph.native_instances import equivalent_flat_refs
    native_children=defaultdict(dict)
    for ref,e in records.items():
        if '/' in ref:native_children[ref.rsplit('/',1)[0]][ref]=e
    # A detail's repeated native outline need not have a DIM to be recognized.
    # Generate it only from a verified source region into a uniquely labelled
    # detail scope, with a complete definition correspondence at native level.
    detail_owners=defaultdict(set)
    assembly_scopes={sid for e in records.values() if len(e.get('bom',{}).get('rows',[]))>1 for sid in e.get('source_sheet_ids',[])}
    for node in graph.get('nodes',[]):
        if node.get('definition_conflict'):continue
        for sid in node.get('detail_sheets',[]):
            if sid not in assembly_scopes:detail_owners[sid].add(node['code'])
    generated=0;representatives={}
    for source_view in list(views.values()):
        codes=set(source_view['part_codes']);frame=source_view.get('coordinate_frame','') or ''
        if len(codes)!=1 or not frame.startswith('instance:'):continue
        root=frame[9:]
        for target,e in records.items():
            if e.get('type')!='INSERT' or target==root:continue
            owners=set().union(*(detail_owners[s] for s in e.get('source_sheet_ids',[])))
            if owners!=codes or max(len(native_children[r]) for r in (root,target))>256:continue
            if generated>=1000:break
            mapping=equivalent_flat_refs({**native_children[root],**native_children[target]},root,target)
            if not mapping or not all(ref in mapping for ref in source_view['geometry_refs']):continue
            group=(source_view['id'],tuple(sorted(e.get('source_sheet_ids',[]))))
            if group in representatives:
                representatives[group].setdefault('equivalent_instance_refs',[]).append(target);generated+=1;continue
            candidate=add([mapping[r] for r in source_view['geometry_refs']],e['layout'],'instance:'+target,e.get('source_sheet_ids',[]))
            if candidate:
                candidate['candidate_part_codes'].extend(codes);candidate['identity_proofs'].append('source_sheet_identity_candidate')
                candidate['evidence_refs']=sorted(set(candidate['evidence_refs'])|set(candidate['geometry_refs'])|{target});generated+=1
                candidate.setdefault('equivalent_instance_refs',[]).append(target);representatives[group]=candidate
    marker_refs={b.get('circle_ref') for b in report.get('leader_profile_bindings',[])};circles=defaultdict(list);physical=defaultdict(list)
    annotations=marker_refs|{p['ref'] for b in report.get('leader_profile_bindings',[]) for p in b.get('leader_endpoints',[])}
    for e in records.values():
        if e.get('geometry'):
            try:
                transformed=world(e);physical[(e.get('layout'),e.get('coordinate_frame'))].append(transformed)
                if e.get('type')=='CIRCLE' and e['ref'] not in marker_refs:circles[(e.get('layout'),e.get('coordinate_frame'))].append(transformed)
            except ValueError:pass
    broad_bounds={e['ref']:locator_bounds(e) for items in physical.values() for e in items}
    shapes={}
    for vid,v in views.items():
        v['part_codes']=sorted(set(v['part_codes']));v['candidate_part_codes']=sorted(set(v['candidate_part_codes']));v['identity_proofs']=sorted(set(v['identity_proofs']))
        conflict=v.get('conflicting_part_codes') or len(set(v['part_codes']+v['candidate_part_codes']))>1
        v['identity_status']='identity_conflict' if conflict else 'verified_source_identity' if len(v['part_codes'])==1 else 'sheet_identity_candidate' if v['candidate_part_codes'] else 'unassigned'
        try:
            from backend.services.geometry_retrieval import local_bounds
            from cad.frame_geometry import matrix
            from itertools import product
            points=[]
            for ref in v['geometry_refs']:
                box=local_bounds(records[ref])
                if box:points.extend(matrix(records[ref]).transform(p) for p in product(*zip(*box)))
            if points:v['bbox']=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
        except ValueError:pass
        shapes[vid]=outline_shape(v,records,circles,physical,annotations,broad_bounds)
        if shapes[vid] and context.get('units')!=4:shapes[vid]['factor']=None
        if shapes[vid]:
            v['circle_refs']=sorted(e['ref'] for e in shapes[vid]['circles']);v['unclassified_interior_refs']=shapes[vid]['unexpected_refs']
        v['measurement_status']='measured_source' if v['dimensions'] else 'missing_bound_dimension'
        v['equivalent_instance_refs']=sorted(set(v.get('equivalent_instance_refs',[])));v['equivalent_instance_count']=len(v['equivalent_instance_refs']) or 1
    relationships=[];attempts=0;deferred=generated>=1000
    for a,b in combinations(views.values(),2):
        if a['identity_status']=='identity_conflict' or b['identity_status']=='identity_conflict':continue
        codes_a=a['part_codes'] or a['candidate_part_codes'];codes_b=b['part_codes'] or b['candidate_part_codes']
        if codes_a and codes_b and codes_a!=codes_b:continue
        if not codes_a and not codes_b:continue
        if attempts>=2000:deferred=True;break
        attempts+=1;proof=None;mapping=None
        roots=[v['coordinate_frame'][9:] if v.get('coordinate_frame','').startswith('instance:') else None for v in (a,b)]
        if all(roots) and roots[0]!=roots[1]:
            if max(len(native_children[r]) for r in roots)<=256:
                mapping=equivalent_flat_refs({**native_children[roots[0]],**native_children[roots[1]]},*roots)
            if mapping and {mapping.get(r) for r in a['geometry_refs']}==set(b['geometry_refs']):proof='complete_native_definition'
            if proof and shapes[a['id']] and shapes[b['id']]:
                factors=[shapes[v['id']]['factor'] for v in (a,b)]
                if all(f is not None for f in factors):
                    try:scales=[planar_similarity(matrix(records[v['geometry_refs'][0]]))[0] for v in (a,b)]
                    except ValueError:proof=None
                    else:
                        if not near(factors[0]*scales[0],factors[1]*scales[1],1e-5):proof=None;continue
        transform=None
        if proof is None:
            transform=outline_match(shapes[a['id']],shapes[b['id']])
            if transform:proof='exact_outline_and_circles'
        if not proof:continue
        verified=bool(a['part_codes'] and a['part_codes']==b['part_codes'])
        relationships.append(dict(type='SAME_PART_AS',source_view_id=a['id'],target_view_id=b['id'],
            part_codes=codes_a or codes_b,status='verified_source_correspondence' if verified else 'candidate_identity_missing',
            proof=proof,transform=transform,executable=False,
            evidence_refs=sorted(set(a['evidence_refs']+b['evidence_refs']+a['geometry_refs']+b['geometry_refs']+a['circle_refs']+b['circle_refs'])),
            scope='complete_native_definition' if proof=='complete_native_definition' else 'closed_outline_and_enclosed_circles'))
    # Propagate reading identity only into independently labelled source
    # sheets along a checked geometry correspondence. A bare identical shape
    # never receives a code, even when there is only one matching candidate.
    changed=True
    while changed:
        changed=False
        for relation in relationships:
            a,b=[views[relation[k]] for k in ('source_view_id','target_view_id')]
            for known,receiving in ((a,b),(b,a)):
                if known['identity_status']=='verified_source_identity' and receiving['identity_status']=='sheet_identity_candidate' and known['part_codes']==receiving['candidate_part_codes']:
                    receiving['part_codes']=list(known['part_codes']);receiving['identity_status']='verified_source_identity'
                    receiving['identity_proofs'].append('source_correspondence_with_sheet_identity');changed=True
            if a['identity_status']==b['identity_status']=='verified_source_identity' and a['part_codes']==b['part_codes']:relation['status']='verified_source_correspondence'
    parts=defaultdict(list)
    for view in views.values():
        if view['identity_status']=='verified_source_identity':parts[view['part_codes'][0]].append(view['id'])
    return dict(version=VERSION,source_hash=source,scope_ids=sorted(t['id'] for t in context.get('targets',[])),
        parts=[dict(part_code=code,view_ids=sorted(ids)) for code,ids in sorted(parts.items())],views=sorted(views.values(),key=lambda v:v['id']),
        correspondences=relationships,unresolved_markers=unresolved,matching_deferred=deferred,
        summary=dict(assigned_view_count=sum(v['identity_status']=='verified_source_identity' for v in views.values()),
            part_count=len(parts),unassigned_view_count=sum(v['identity_status']!='verified_source_identity' for v in views.values()),
            verified_correspondence_count=sum(r['status']=='verified_source_correspondence' for r in relationships),
            candidate_correspondence_count=sum(r['status']!='verified_source_correspondence' for r in relationships),unresolved_marker_count=len(unresolved)),
        policy='Source-local identities and SAME_PART_AS reading evidence. Shape equality alone never assigns a part code. A bounded outline match does not certify the complete internal geometry, projection/contact constraints or permission to edit. Matching budget/deferred state is explicit; no confidence percentage is fabricated.')
