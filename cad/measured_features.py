"""Identify measured closed straight profiles without guessing from pixels.

Feature ownership is separate from contact/assembly ownership. The same part
can have several independent projections; this index never merges them.
"""
import math
from collections import defaultdict
import networkx as nx
import numpy as np
from cad.geometry import near
from cad.part_identity import record_identity
from cad.frame_geometry import world
from cad.closed_profiles import contours,touches

TOL=1e-5


def rectangle(points):
    if len(points)!=4:return None
    p=np.asarray(points,dtype=float)
    if p.shape!=(4,3) or not np.isfinite(p).all() or np.ptp(p[:,2])>TOL:return None
    edges=np.roll(p,-1,axis=0)-p;lengths=np.linalg.norm(edges,axis=1)
    if min(lengths)<=TOL:return None
    axes=edges/lengths[:,None]
    if any(abs(np.dot(axes[i],axes[(i+1)%4]))>1e-7 for i in range(4)):return None
    if not np.allclose(edges[0],-edges[2],atol=TOL,rtol=0) or not np.allclose(edges[1],-edges[3],atol=TOL,rtol=0):return None
    return dict(points=p.tolist(),axes=[axes[0].tolist(),axes[1].tolist()],lengths=lengths[:2].tolist())


def candidates(records):
    result=[];lines=[]
    for e in records:
        g=e.get('geometry',{})
        if e['type'] in ('LWPOLYLINE','POLYLINE') and g.get('closed') and near(g.get('extrusion'),[0,0,1]):
            if any(any(p[2:]) for p in g['points']) or any(g.get('default_widths',[])):continue
            r=rectangle([[p[0],p[1],g['elevation']] for p in g['points']])
            if r:result.append(dict(r,refs=[e['ref']]))
        elif e['type']=='LINE' and g:lines.append(e)
    # Only isolated four-edge cycles are accepted. A branched grid is not a
    # rectangle component, even if four of its lines happen to form a box.
    graph=nx.Graph();segments={}
    def key(p):return tuple(round(v,5) for v in p)
    for e in lines:
        g=e['geometry'];a,b=key(g['start']),key(g['end'])
        if a==b:continue
        k=tuple(sorted((a,b)));segments.setdefault(k,[]).append(e)
        graph.add_edge(a,b)
    for component in nx.connected_components(graph):
        if len(component)!=4 or any(graph.degree(p)!=2 for p in component):continue
        start=min(component);order=[start];previous=None;current=start
        while len(order)<4:
            nxt=next((p for p in sorted(graph.neighbors(current)) if p!=previous and p not in order),None)
            if nxt is None:break
            order.append(nxt);previous,current=current,nxt
        if len(order)!=4 or not graph.has_edge(order[-1],order[0]):continue
        refs=[];points=[]
        for a,b in zip(order,order[1:]+order[:1]):
            matches=segments[tuple(sorted((a,b)))]
            if len(matches)!=1:break
            e=matches[0];refs.append(e['ref']);g=e['geometry']
            points.append(g['start'] if key(g['start'])==a else g['end'])
        else:
            r=rectangle(points)
            if r:result.append(dict(r,refs=refs))
    return result


def binds(dimension,profile):
    g=dimension.get('geometry',{})
    from cad.dimensions import linear_axis
    try:axis=np.asarray(linear_axis(dimension))
    except ValueError:return None
    p=np.asarray(profile['points']);a=np.asarray(g['defpoint2']);b=np.asarray(g['defpoint3'])
    if max(abs(a[2]-p[0,2]),abs(b[2]-p[0,2]))>TOL:return None
    normal=np.array([-axis[1],axis[0],0.])
    if profile.get('edges'):
        from cad.curved_profiles import direction_points
        p=np.asarray(direction_points(profile,axis))
    if 'axes' in profile and not any(abs(abs(np.dot(axis,unit))-1)<1e-7 for unit in profile['axes']):return None
    us=p@axis;vs=p@normal;low,high=float(min(us)),float(max(us));bottom,top=float(min(vs)),float(max(vs))
    if not near(sorted([float(a@axis),float(b@axis)]),[low,high],TOL):return None
    # Extension points must touch this actual outline, not merely share its
    # X/Y extents. This excludes dimensions belonging to a neighboring view.
    for q in (a,b):
        u,v=float(q@axis),float(q@normal)
        if profile.get('edges'):
            from cad.curved_profiles import touches as curve_touches
            on_outline=curve_touches(profile,q)
            if not on_outline:
                on_outline=fillet_tangent_corner(profile,q)
        else:on_outline=touches(profile['points'],q)
        if v<bottom-TOL or v>top+TOL or min(abs(u-low),abs(u-high))>TOL or not on_outline:return None
    factor=abs(dimension.get('linear_factor',1))
    if factor<=0 or not math.isclose((high-low)*factor,dimension.get('scaled_measurement',-1),abs_tol=TOL):return None
    return dict(ref=dimension['ref'],measurement=dimension['scaled_measurement'],axis=axis.tolist(),
                first_is_low=abs(float(a@axis)-low)<TOL,linear_factor=factor)


def fillet_tangent_corner(profile,point):
    """A DIM may originate at the exact virtual corner of a quarter fillet.

    Require both incident source straight edges to be tangent and connected.
    Bounding-box coincidence alone cannot bind an extension point.
    """
    edges=profile.get('edges',[]);q=np.asarray(point)
    for arc in edges:
        if arc['kind']!='arc':continue
        a,b,c=(np.asarray(arc[k]) for k in ('start','end','center'))
        ra,rb=a-c,b-c;r=arc['radius']
        from cad.curved_profiles import sweep
        if abs(sweep(arc)-math.pi/2)>1e-7 or abs(float(ra@rb))>TOL*r:continue
        corner=a+b-c
        if not near(corner.tolist(),q.tolist(),TOL):continue
        def tangent(endpoint,radius):
            for line in edges:
                if line['kind']!='line':continue
                p,s=(np.asarray(line[k]) for k in ('start','end'))
                if not (near(p.tolist(),endpoint.tolist(),TOL) or near(s.tolist(),endpoint.tolist(),TOL)):continue
                v=s-p;length=float(np.linalg.norm(v))
                if length>TOL and abs(float(v@radius))/length<TOL:return True
            return False
        if tangent(a,ra) and tangent(b,rb):return True
    return False


def leader_profiles(context,graph,profiles,features):
    """Trace local BOM -> balloon -> native leader -> source outline -> DIM.

    A unique straight material interior, native BOM row and real DIM can own
    that measured contour. Other associations remain reading evidence only.
    No balloon establishes a mechanical contact or a cross-view rule.
    """
    from cad.row_groups import identity_groups
    groups=identity_groups(graph.get('drawing_rows',{}))
    if not groups:return []
    if graph.get('source_hash') and graph['source_hash']!=context.get('source_hash'):
        raise ValueError('Leader index and CAD must have the same source hash')
    records={e['ref']:e for e in context['entities']};world_by={}
    from bom.continuations import scoped_table_sheets
    bom_scopes=scoped_table_sheets(context)
    for e in records.values():
        if e.get('geometry'):
            try:world_by[e['ref']]=world(e)
            except ValueError:pass
    measured={tuple(sorted(f['refs'])):f for f in features};rows=[];seen=set()
    from shapely.geometry import Polygon,Point,box
    targets={t['id']:t for t in context.get('targets',[]) if t.get('bbox')}
    tables={e['ref'] for e in records.values() if e.get('bom')}
    holes_by_frame=defaultdict(list)
    for ref,e in world_by.items():
        if e['type']=='CIRCLE' and e['geometry']['radius']>0:
            holes_by_frame[(e.get('layout'),records[ref].get('coordinate_frame'))].append(e['geometry'])
    regions=[]
    for item in profiles:
        outline=item['profile']
        pts = [p[:2] for p in outline.get('points', [])]
        if len(pts) < 3:
            continue
        try:
            polygon=Polygon(pts)
        except Exception:
            continue
        # Paper borders and table cells are not material faces. Recognition is
        # confined to this index and does not change the accepted sheet list.
        structural=any(r in targets or any(r.startswith(t+'/') for t in tables) for r in outline['refs'])
        if rectangle(outline['points']):
            for sid in item['sheet_ids']:
                target=targets.get(sid)
                if target:
                    b=target['bbox'];inset=.05*min(b[2]-b[0],b[3]-b[1])
                    if polygon.buffer(TOL).covers(box(*b).buffer(-inset)):structural=True
        regions.append(dict(item,polygon=polygon,structural=structural))
    # Open assembly drawings often have no closed part contour. Preserve exact
    # edge contacts as a separate reading result, never promote them to owners.
    from cad.closed_profiles import segments
    leader_refs={r for group in groups for b in group.get('marker_bindings',[]) for r in b['leader_refs']}
    source_segments=[(e,a,b) for e in world_by.values() if e['ref'] not in leader_refs for a,b in segments(e)]
    segment_starts=np.asarray([a for _,a,_ in source_segments]);segment_ends=np.asarray([b for _,_,b in source_segments])
    segment_low=np.minimum(segment_starts,segment_ends);segment_high=np.maximum(segment_starts,segment_ends)
    from cad.row_groups import plain
    for group in groups:
        if group.get('status')!='source_row_group':continue
        markers={m['text_ref']:m for m in group.get('markers',[])}
        for binding in group.get('marker_bindings',[]):
            ref=binding['number_text_ref'];marker=markers.get(ref)
            if not marker or ref in seen:continue
            if not set(marker['sheet_ids']).intersection(t['id'] for t in context.get('targets',[])):continue
            seen.add(ref)
            row=dict(row_group_id=group['id'],number_text_ref=ref,circle_ref=binding['circle_ref'],
                part_number=binding['part_number'],part_codes=binding['part_codes'],sheet_ids=marker['sheet_ids'],
                candidates=[],edge_contact_refs=[],edge_contact_verified=False,bom_table_refs=binding['table_refs'],
                evidence_refs=[],status='leader_source_unavailable',geometry_owner_verified=False,executable=False)
            rows.append(row)
            if binding['status']!='verified_local_bom_identity' or len(binding['part_codes'])!=1:
                row['status']='bom_identity_unresolved';continue
            from bom.reader import part_number_key
            source_rows=[r for ref in binding['table_refs'] if set(marker['sheet_ids']).intersection(bom_scopes.get(ref,set()))
                for r in records.get(ref,{}).get('bom',{}).get('rows',[]) if part_number_key(r['part_number'])==part_number_key(binding['part_number'])]
            if not source_rows or {r['part_code'] for r in source_rows}!=set(binding['part_codes']):
                row['status']='bom_identity_unresolved';continue
            row['bom_scope']=binding.get('bom_scope','local_source_bom')
            text=records.get(ref,{});circle=world_by.get(binding['circle_ref'],{});cg=circle.get('geometry',{})
            if text.get('type') not in ('TEXT','MTEXT','ATTRIB') or plain(text.get('text','')).upper()!=binding['part_number'].upper():continue
            if circle.get('type')!='CIRCLE' or not cg or not near(cg['center'],marker['center']) or abs(cg['radius']-marker['radius'])>TOL:continue
            from cad.frame_geometry import matrix
            from ezdxf.math import Vec3
            placement=text.get('text_placement',{});center=placement.get('label_center')
            if center is None or text.get('layout')!=marker['layout']:continue
            if math.dist(list(matrix(text).transform(Vec3(center))),cg['center'])>.85*cg['radius']+TOL:continue
            endpoints=[];valid_leaders=[];endpoint_bindings=[]
            for leader_ref in binding['leader_refs']:
                leader=world_by.get(leader_ref,{});g=leader.get('geometry',{})
                if leader.get('layout')!=marker['layout'] or not set(leader.get('source_sheet_ids',[])).intersection(marker['sheet_ids']):continue
                points=[g['start'],g['end']] if leader.get('type')=='LINE' and g else g.get('vertices',[]) if leader.get('type')=='LEADER' else []
                if len(points)<2:continue
                ends=[points[0],points[-1]];on=[abs(math.dist(p,cg['center'])-cg['radius'])<=max(TOL,.02*cg['radius']) for p in ends]
                if sum(on)!=1:continue
                point=ends[1] if on[0] else ends[0]
                endpoints.append(point);valid_leaders.append(leader_ref)
                endpoint_bindings.append(dict(ref=leader_ref,vertex_index=len(points)-1 if on[0] else 0,point=point))
            row['leader_endpoints']=endpoint_bindings
            row['evidence_refs']=sorted(set([ref,binding['circle_ref']]+valid_leaders+binding['table_refs']))
            if not endpoints:continue
            edge_refs=set()
            if source_segments:
                allowed=np.asarray([e.get('layout')==marker['layout'] and bool(set(e.get('source_sheet_ids',[])).intersection(marker['sheet_ids'])) for e,_,_ in source_segments])
                for endpoint in endpoints:
                    q=np.asarray(endpoint);eligible=np.flatnonzero(allowed & np.all(q>=segment_low-TOL,axis=1) & np.all(q<=segment_high+TOL,axis=1))
                    for k in eligible:
                        a,b=segment_starts[k],segment_ends[k];v=b-a;length=float(v@v)
                        if length>TOL*TOL and np.linalg.norm(q-(a+np.clip(float((q-a)@v)/length,0,1)*v))<=TOL:
                            edge_refs.add(source_segments[k][0]['ref'])
            row['edge_contact_refs']=sorted(edge_refs)
            row['edge_contact_verified']=len(edge_refs)==1 and len(endpoints)==1
            row['evidence_refs']=sorted(set(row['evidence_refs'])|edge_refs)
            matches={}
            for p in regions:
                if p['layout']!=marker['layout'] or not set(p['sheet_ids']).intersection(marker['sheet_ids']):continue
                outline=p['profile'];points=np.asarray(outline['points']);low,high=points.min(axis=0),points.max(axis=0)
                for endpoint in endpoints:
                    q=np.asarray(endpoint)
                    if not np.all(q>=low-TOL) or not np.all(q<=high+TOL):continue
                    if outline.get('edges'):
                        from cad.curved_profiles import touches as curve_touches
                        contact=curve_touches(outline,q)
                    else:contact=touches(outline['points'],q)
                    polygon=p['polygon'];inside=not p['structural'] and polygon.contains(Point(q[:2]))
                    clearance=polygon.boundary.distance(Point(q[:2]));error=outline.get('curve_chord_error',0)
                    # A bounded curve locator only certifies a point well away
                    # from its error band. Keep borderline candidates ambiguous.
                    interior=inside and clearance>error+TOL
                    hole=False
                    if inside:
                        for g in holes_by_frame[(marker['layout'],p.get('coordinate_frame'))]:
                            center=Point(g['center'][:2])
                            if polygon.contains(center) and polygon.boundary.distance(center)>=g['radius']-TOL and math.dist(q,g['center'])<=g['radius']+TOL:
                                hole=True;break
                    if hole:continue
                    if contact or inside:
                        key=tuple(sorted(outline['refs']));feature=measured.get(key)
                        matches[key]=dict(geometry_refs=list(key),dimension_refs=[d['ref'] for d in feature['dimensions']] if feature else [],
                            source_part_code=feature.get('part_code') if feature else None,
                            curved=bool(outline.get('edges')),endpoint=list(endpoint),
                            contact_mode='interior' if interior else 'boundary' if contact else 'uncertain_curve_boundary',
                            interior_clearance_mm=clearance,locator_error_mm=error,coordinate_frame=p.get('coordinate_frame'))
            row['candidates']=list(matches.values())
            if len(matches)>1:row['status']='ambiguous_profile_endpoint'
            elif not matches:row['status']='profile_endpoint_unresolved'
            else:
                candidate=next(iter(matches.values()));code=candidate['source_part_code']
                row['evidence_refs']=sorted(set(row['evidence_refs']+candidate['geometry_refs']+candidate['dimension_refs']))
                row['status']=('owner_identity_conflict' if code and code!=binding['part_codes'][0] else
                    'verified_interior_dimension_chain' if candidate['contact_mode']=='interior' and candidate['dimension_refs'] and not candidate['curved'] and len(endpoints)==1 else
                    'verified_interior_region' if candidate['contact_mode']=='interior' and len(endpoints)==1 else
                    'uncertain_curve_boundary' if candidate['contact_mode']=='uncertain_curve_boundary' else
                    'curved_endpoint_candidate' if candidate['curved'] else
                    'verified_endpoint_dimension_chain' if candidate['dimension_refs'] and len(endpoints)==1 else
                    'outline_without_verified_dimension' if not candidate['dimension_refs'] else 'ambiguous_leader_endpoints')
    # Interior balloon identity grants only the measured contour in this view.
    # Re-read its native BOM row; another balloon/code on the same contour blocks
    # promotion. It does not establish a fit, contact or cross-view relationship.
    for row in rows:
        if row['status']!='verified_interior_dimension_chain':continue
        candidate=row['candidates'][0];key=tuple(candidate['geometry_refs']);feature=measured[key];code=row['part_codes'][0]
        conflicts=[b for b in rows if set(b['part_codes'])!={code} and any(tuple(x['geometry_refs'])==key for x in b['candidates'])]
        if conflicts:
            row['status']='owner_identity_conflict'
            for b in conflicts:b['status']='owner_identity_conflict'
            continue
        bom=[]
        for ref in row['bom_table_refs']:
            table=records.get(ref,{})
            if table.get('bom',{}).get('status')!='verified_template':continue
            from bom.reader import part_number_key
            local=[r for r in table['bom']['rows'] if part_number_key(r['part_number'])==part_number_key(row['part_number'])]
            if len(local)==1 and local[0]['part_code']==code:bom.append(ref)
        if not bom:continue
        if feature.get('part_code') and feature['part_code']!=code:continue
        if feature['ownership_proof']=='unverified':
            feature.update(part_code=code,ownership_proof='local_bom_leader_profile',
                instance_ref=candidate['coordinate_frame'][9:] if candidate['coordinate_frame'].startswith('instance:') else None,
                evidence_refs=sorted(set(feature['evidence_refs']+row['evidence_refs'])))
        row['geometry_owner_verified']=True
    return rows


def index(context,graph=None):
    records=context['entities'];by={e['ref']:e for e in records}
    codes={r['part_code'] for e in records for r in e.get('bom',{}).get('rows',[])}
    codes.update(n['code'] for n in (graph or {}).get('nodes',[]))
    native={e['ref']:code for e in records for code in [record_identity(e,codes)] if code}
    # A standalone selected INSERT does not need a purchasing/BOM code for a
    # measured geometry edit. This identity is deliberately instance-specific:
    # it proves the selected ownership scope, never a contact or equivalence
    # with other copies of that definition. Unreadable tables still block it.
    selected_instances={}
    if not codes and not any(e.get('type') in ('ACAD_TABLE','GRAPHIC_TABLE') for e in records):
        selected={t['id'] for t in context.get('targets',[]) if t.get('kind')=='block'}
        selected_instances={e['ref']:'BLOCK@'+e['ref'] for e in records
                            if e['ref'] in selected and e.get('type')=='INSERT' and not e.get('review_only')}
        native.update(selected_instances)
    owners=defaultdict(set)
    # A frame naming an assembly does not own every child silhouette. The
    # multi-member BOM is explicit source evidence against detail-sheet-only
    # ownership; coded native instances and checked balloons can still own parts.
    assembly_sheets={sid for a in (graph or {}).get('assembly_structure',{}).get('assemblies',[])
                     if a.get('kind')=='assembly_bom' and len(a.get('members',[]))>1 for sid in a.get('scope_ids',[])}
    assembly_sheets.update(sid for e in records if e.get('bom',{}).get('status')=='verified_template' and
                           len(e['bom'].get('rows',[]))>1 for sid in e.get('source_sheet_ids',[]))
    for n in (graph or {}).get('nodes',[]):
        for sid in n.get('detail_sheets',[]):
            if sid not in assembly_sheets:owners[sid].add(n['code'])
    groups=defaultdict(list)
    for e in records:
        if e.get('geometry') and not e.get('review_only'):
            groups[(e.get('layout'),e.get('coordinate_frame'))].append(e)
    features=[];ambiguous=[];profile_catalog=[]
    world_records=[]
    for e in records:
        if e.get('geometry') and not e.get('review_only'):
            try:world_records.append(world(e))
            except ValueError:pass
    world_by={e['ref']:e for e in world_records}
    annotation_bounds=defaultdict(list)
    from cad.row_groups import identity_groups
    for group in identity_groups((graph or {}).get('drawing_rows',{})):
        if group.get('status')!='source_row_group':continue
        leader_by_marker={b['number_text_ref']:b.get('leader_refs',[]) for b in group.get('marker_bindings',[])}
        for marker in group.get('markers',[]):
            for ref in set(marker.get('leader_refs',[]))|set(leader_by_marker.get(marker['text_ref'],[])):
                e=world_by.get(ref,{});g=e.get('geometry',{})
                pts=g.get('vertices',[]) if e.get('type')=='LEADER' else [g['start'],g['end']] if e.get('type')=='LINE' and g else []
                for point in pts[:1]+pts[-1:]:
                    if abs(math.dist(point,marker['center'])-marker['radius'])>max(TOL,.02*marker['radius']):
                        annotation_bounds[e['layout']].append([point,point])
    def native_owner(ref):
        current=ref
        while current:
            if current in native:return current
            current=current.rsplit('/',1)[0] if '/' in current else None
        return None
    dims_by_layout=defaultdict(list)
    for e in world_records:
        g=e.get('geometry',{})
        if e['type']=='DIMENSION' and e.get('dimension_type') in (0,1) and g.get('text') in ('','<>'):
            dims_by_layout[e.get('layout')].append(e)
    dim_index={}
    for layout,dimensions in dims_by_layout.items():
        endpoints=np.asarray([[e['geometry']['defpoint2'],e['geometry']['defpoint3']] for e in dimensions])
        dim_index[layout]=(dimensions,endpoints.min(axis=1),endpoints.max(axis=1),[native_owner(e['ref']) for e in dimensions])
    for (layout,frame),items in groups.items():
        source_records=[world_by[e['ref']] for e in items if e['ref'] in world_by]
        if layout not in dim_index and layout not in annotation_bounds:continue
        profiles=contours(source_records)
        from cad.curved_profiles import contours as curved_contours
        profiles+=curved_contours(source_records,measurement_bounds=[
            [d['geometry']['defpoint2'],d['geometry']['defpoint3']] for d in dims_by_layout[layout]]+annotation_bounds[layout])
        if not profiles:continue
        for p in profiles:
            sids=set.intersection(*(set(by[r].get('source_sheet_ids',[])) for r in p['refs']))
            profile_catalog.append(dict(layout=layout,coordinate_frame=frame,sheet_ids=sorted(sids),profile=p))
        if layout not in dim_index:continue
        group_owner=native_owner(frame.removeprefix('instance:')) if frame and frame.startswith('instance:') else None
        dimensions,dmin,dmax,dimension_owners=dim_index[layout]
        allowed=np.asarray([not (group_owner and owner and owner!=group_owner) for owner in dimension_owners],dtype=bool)
        associations=defaultdict(list)
        for i,p in enumerate(profiles):
            pts=np.asarray(p['points']);low,high=pts.min(axis=0),pts.max(axis=0)
            # Both extension points must touch the source contour. A vectorized
            # necessary bounds test avoids comparing every dimension with each
            # of thousands of repeated laser-cut instances.
            matches=np.flatnonzero(allowed & np.all(dmin>=low-TOL,axis=1) & np.all(dmax<=high+TOL,axis=1))
            for k in matches:
                d=dimensions[k]
                binding=binds(d,p)
                if binding:associations[d['ref']].append((i,binding))
        bound=defaultdict(list)
        for ref,matches in associations.items():
            if len(matches)==1:bound[matches[0][0]].append(matches[0][1])
            else:ambiguous.append(dict(dimension_ref=ref,candidate_count=len(matches)))
        for i,bindings in bound.items():
            p=profiles[i];refs=p['refs'];sids=set.intersection(*(set(by[r].get('source_sheet_ids',[])) for r in refs))
            root=frame.removeprefix('instance:') if frame and frame.startswith('instance:') else None
            instance=root
            while instance and instance not in native:instance=instance.rsplit('/',1)[0] if '/' in instance else None
            code=native.get(instance)
            proof=('selected_native_instance' if instance in selected_instances else 'native_part_identity') if code else 'unverified'
            detail_owners=set().union(*(owners[s] for s in sids)) if sids else set()
            if not code and len(detail_owners)==1:
                code=next(iter(detail_owners));proof='unique_source_detail_sheet'
            features.append(dict(kind='measured_curved_profile' if p.get('edges') else 'measured_straight_profile',refs=refs,dimensions=bindings,
                coordinate_frame=frame,layout=layout,sheet_ids=sorted(sids),part_code=code,
                ownership_proof=proof,instance_ref=instance,points=p['points'],measurement_space='layout',
                evidence_refs=sorted(set(refs+[b['ref'] for b in bindings]+([instance] if instance else []))),
                **({'curve_policy':'Rigid source curves; only straight bridges parallel to the measured axis may stretch. General NURBS/ellipses require exact OCC face validation.'} if p.get('edges') else {})))
    bindings=leader_profiles(context,graph or {},profile_catalog,features)
    return dict(version=7,features=features,ambiguous_dimensions=ambiguous,
        leader_profile_bindings=bindings,
        policy='Source contour closure and real linear/aligned DIM extension points bind a measured feature. General clamped positive-weight NURBS and planar ellipses use bounded locator chords and require independent exact OCC face validation before export. Source curves move rigidly; only straight bridges parallel to the measured axis may stretch. Part ownership requires native identity, a unique source detail sheet, explicit selection of a standalone INSERT without a BOM, or a unique straight material interior identified by a source balloon/leader and re-read local BOM row. Boundaries, holes, overlapping regions and uncertain curve locator bands cannot grant balloon ownership. This does not imply an assembly contact or cross-view correspondence.')


def model_view(report,visible_refs):
    visible=set(visible_refs);selected=[]
    for feature in report.get('features',[]):
        if not visible.intersection(feature['evidence_refs']):continue
        selected.append({k:v for k,v in feature.items() if k not in ('points',)})
    return dict(version=report.get('version',1),features=selected,total_features=len(report.get('features',[])),
                leader_profile_bindings=[b for b in report.get('leader_profile_bindings',[]) if visible.intersection(b['evidence_refs'])],
                ambiguous_dimension_count=len(report.get('ambiguous_dimensions',[])),policy=report['policy'])
