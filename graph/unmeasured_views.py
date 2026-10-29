"""Copy complete identical native detail definitions without inventing DIMs.

Source detail ownership, native identities or source-checked local BOM balloons
establish the part. A complete one-to-one definition match proves correspondence.
Existing dimensions are updated only at source vertices with a unique motion.
"""
import copy
import json
from collections import defaultdict
from cad.geometry import near
from cad.frame_geometry import world,local_geometry,matrix,planar_similarity
from graph.native_instances import equivalent_flat_refs
from graph.measured_views import OWNED_PROOFS


def expand(operations,recipes,context,owners):
    records={e['ref']:e for e in context['entities']};out={o.ref:o for o in operations}
    feature_report=context.get('source_features',{});features=feature_report.get('features',[])
    # STT is local to a BOM, never a global part identity. A source-bound
    # interior balloon provides an identity candidate; only a complete native
    # definition match below allows geometry to propagate to that instance.
    bindings=[];region_codes=defaultdict(set)
    for b in feature_report.get('leader_profile_bindings',[]):
        if b.get('status') not in ('verified_interior_region','verified_interior_dimension_chain') or len(b.get('part_codes',[]))!=1 or len(b.get('candidates',[]))!=1:continue
        candidate=b['candidates'][0];frame=candidate.get('coordinate_frame','') or ''
        root=frame[9:] if frame.startswith('instance:') else None
        if root not in records or records[root]['type']!='INSERT':continue
        code=b['part_codes'][0]
        bom=[row for ref in b.get('bom_table_refs',[]) for row in records.get(ref,{}).get('bom',{}).get('rows',[])
             if records[ref].get('bom',{}).get('status')=='verified_template' and str(row['part_number']).upper()==b['part_number'].upper()]
        if not bom or {row['part_code'] for row in bom}!={code}:continue
        if not candidate.get('geometry_refs') or any(not ref.startswith(root+'/') or ref not in records for ref in candidate['geometry_refs']):continue
        region_codes[root].add(code);bindings.append((root,b))
    sheet_owners=defaultdict(set)
    assembly_sheets={sid for a in context.get('part_graph',{}).get('assembly_structure',{}).get('assemblies',[])
                     if a.get('kind')=='assembly_bom' and len(a.get('members',[]))>1 for sid in a.get('scope_ids',[])}
    assembly_sheets.update(sid for e in records.values() if len(e.get('bom',{}).get('rows',[]))>1 for sid in e.get('source_sheet_ids',[]))
    for n in context.get('part_graph',{}).get('nodes',[]):
        for sid in n.get('detail_sheets',[]):
            if sid not in assembly_sheets:sheet_owners[sid].add(n['code'])
    from cad.part_identity import record_identity
    codes={n['code'] for n in context.get('part_graph',{}).get('nodes',[])}
    def code_for(root):
        r=records[root];native=record_identity(r,codes)
        sids=set(r.get('source_sheet_ids',[]));owned=set().union(*(sheet_owners[s] for s in sids))
        owned.update(region_codes[root])
        owned.update(f['part_code'] for f in features if f.get('coordinate_frame')=='instance:'+root and f.get('ownership_proof') in OWNED_PROOFS and f.get('part_code'))
        if native:owned.add(native)
        return next(iter(owned)) if len(owned)==1 else None
    sources=[];receiving_sheets=set()
    for recipe in recipes:
        feature=next((f for f in features if f.get('part_code')==recipe.part_code and
            f.get('ownership_proof') in OWNED_PROOFS and set(f['refs'])==set(recipe.outline_refs)),None)
        frame=feature.get('coordinate_frame','') if feature else ''
        root=frame.removeprefix('instance:') if frame.startswith('instance:') else None
        if root in records and code_for(root)==recipe.part_code:sources.append((root,recipe.part_code))
    for source,code in set(sources):
        for target,r in records.items():
            if target==source or r['type']!='INSERT' or r.get('review_only') or code_for(target)!=code:continue
            # Measured receiving views are handled by their own recipes.
            if any(f.get('coordinate_frame')=='instance:'+target for f in features):continue
            mapping=equivalent_flat_refs(records,source,target)
            if not mapping or any(records[ref].get('review_only') for ref in mapping.values()):continue
            try:
                for ref in (next(iter(mapping)),next(iter(mapping.values()))):planar_similarity(matrix(records[ref]))
            except (ValueError,StopIteration):continue
            for ref,received in mapping.items():
                op=out.get(ref)
                if not op or op.action!='replace_geometry':continue
                if records[received].get('review_only'):continue
                copied=op.model_copy(update=dict(ref=received,reason='Đồng bộ định nghĩa native đầy đủ của cùng chi tiết: '+op.reason))
                if received in out and not near(json.loads(out[received].after),json.loads(copied.after),1e-6):
                    raise ValueError('Hình native không DIM có thay đổi xung đột: '+received)
                out[received]=copied;owners[received]=code
                receiving_sheets.update(records[received].get('source_sheet_ids',[]))
            for root,binding in bindings:
                if root!=target:continue
                for recipe in recipes:
                    if recipe.part_code==code and {mapping.get(ref) for ref in recipe.outline_refs}==set(binding['candidates'][0]['geometry_refs']):
                        sync_leader(out,records,binding,recipe,mapping,owners,code)
    if not receiving_sheets:return list(out.values())
    # Native receiving views can have clearance DIMs outside the outline.
    # Both endpoints must be actual CAD vertices, and every coincident source
    # vertex must agree about its displacement (including unchanged stock).
    vertices=defaultdict(list)
    def points(e):
        g=e.get('geometry',{})
        if e['type']=='LINE':return [g['start'],g['end']]
        if e['type'] in ('LWPOLYLINE','POLYLINE'):return [[p[0],p[1],g['elevation']] for p in g['points']]
        return []
    for ref,e in records.items():
        if not receiving_sheets.intersection(e.get('source_sheet_ids',[])):continue
        if not e.get('geometry') or e['type'] not in ('LINE','LWPOLYLINE','POLYLINE'):continue
        try:
            before=points(world(e));updated=copy.deepcopy(e)
            if ref in out:updated['geometry']=json.loads(out[ref].after)
            after=points(world(updated))
        except ValueError:continue
        for sid in e.get('source_sheet_ids',[]):
            for p,q in zip(before,after):vertices[(e.get('layout'),sid)].append((p,q,owners.get(ref)))
    from cad.edit_engine import Operation
    for ref,e in records.items():
        if not receiving_sheets.intersection(e.get('source_sheet_ids',[])):continue
        if ref in out or e['type']!='DIMENSION' or not e.get('geometry') or e.get('review_only'):continue
        if e.get('dimension_type')!=0 or e['geometry'].get('text') not in ('','<>'):continue
        g=world(e)['geometry'];moves=[];codes_changed=set()
        for key in ('defpoint2','defpoint3'):
            hits=[(q,code) for sid in e.get('source_sheet_ids',[]) for p,q,code in vertices[(e.get('layout'),sid)] if near(p,g[key],1e-5)]
            if not hits or any(not near(q,hits[0][0],1e-5) for q,_ in hits):break
            moves.append(hits[0][0]);codes_changed.update(code for _,code in hits if code)
        if len(moves)!=2 or len(codes_changed)!=1 or near(moves,[g['defpoint2'],g['defpoint3']],1e-6):continue
        after=copy.deepcopy(g)
        for key,p in zip(('defpoint2','defpoint3'),moves):after[key]=p
        after['text']='<>'
        out[ref]=Operation(ref=ref,action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(local_geometry(e,after)),xyz=[],reason='Đồng bộ DIM khe hở theo hai đỉnh CAD nguồn có chuyển động duy nhất')
        owners[ref]=next(iter(codes_changed))
    return list(out.values())


def sync_leader(out,records,binding,recipe,mapping,owners,code):
    """Transfer the measured end-zone motion into the receiving native frame.

    Only the source-bound arrow endpoint moves. A changed source, ambiguous
    region or tip leaving the final material region rejects the entire edit.
    """
    from ezdxf.math import Vec3
    from cad.dimensions import linear_axis
    from shapely.geometry import Polygon,Point
    dim=records[recipe.dimension_ref];dim_op=out.get(recipe.dimension_ref)
    if not dim_op:return
    source=records[recipe.outline_refs[0]];m=matrix(source);planar_similarity(m);m.inverse()
    old=world(dim);new=copy.deepcopy(dim);new['geometry']=json.loads(dim_op.after);new=world(new)
    axis=m.transform_direction(Vec3(linear_axis(old))).normalize()
    def projection(p):return Vec3(p).dot(axis)
    ends=[m.transform(Vec3(old['geometry'][key])) for key in ('defpoint2','defpoint3')]
    shifts=[projection(m.transform(Vec3(new['geometry'][key]))-p) for key,p in zip(('defpoint2','defpoint3'),ends)]
    order=sorted(range(2),key=lambda i:projection(ends[i]));mid=sum(projection(p) for p in ends)/2
    target=records[mapping[recipe.outline_refs[0]]];tm=matrix(target);planar_similarity(tm);inverse=tm.copy();inverse.inverse()
    outlines=[]
    for ref in recipe.outline_refs:
        received=mapping[ref];e=copy.deepcopy(records[received])
        if received in out:e['geometry']=json.loads(out[received].after)
        outlines.append(e)
    if binding['candidates'][0].get('curved'):
        from cad.curved_profiles import profile_from
        profile=profile_from(outlines);polygon=Polygon([p[:2] for p in profile['points']]);error=profile.get('curve_chord_error',0)
    else:
        from cad.closed_profiles import polygon_from
        polygon=Polygon([p[:2] for p in polygon_from(outlines)]);error=0
    from cad.edit_engine import Operation
    for tip in binding.get('leader_endpoints',[]):
        e=records.get(tip['ref'],{})
        if e.get('review_only') or e.get('layout')!=target.get('layout'):raise ValueError('Leader nhận chưa thuộc phạm vi sửa đã kiểm chứng')
        before=world(e)['geometry'];points=before.get('vertices') if e['type']=='LEADER' else [before['start'],before['end']]
        i=tip['vertex_index']
        if not 0<=i<len(points) or not near(points[i],tip['point'],1e-5):raise ValueError('Leader nhận đã khác bằng chứng CAD nguồn')
        # Earlier recipes can move this endpoint along the other DIM axis.
        current=copy.deepcopy(e)
        if tip['ref'] in out:current['geometry']=json.loads(out[tip['ref']].after)
        after=world(current)['geometry'];current_points=after.get('vertices') if e['type']=='LEADER' else [after['start'],after['end']]
        local=inverse.transform(Vec3(points[i]));u=projection(local)
        shift=shifts[order[0]] if u<mid-1e-6 else shifts[order[1]] if u>mid+1e-6 else sum(shifts)/2
        moved=inverse.transform(Vec3(current_points[i]))+axis*shift;point=Point(moved.x,moved.y)
        if not polygon.contains(point) or polygon.boundary.distance(point)<=error+1e-6:raise ValueError('Mũi tên nhận sau sửa rời khỏi vùng vật liệu')
        position=list(tm.transform(moved))
        if e['type']=='LEADER':after['vertices'][i]=position
        else:after['start' if i==0 else 'end']=position
        out[tip['ref']]=Operation(ref=tip['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(local_geometry(e,after)),xyz=[],reason='Đồng bộ mũi tên STT theo biên dạng native cùng mã BOM đã đối chiếu')
        owners[tip['ref']]=code
