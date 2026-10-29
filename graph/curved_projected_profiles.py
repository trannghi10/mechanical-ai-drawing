"""Complete circular-edge faces mapped to native circular or elliptical edges.

Every edge and bore must establish one affine map under independent native
part identities. Occluded/open faces, mixed owners and partial block matches
cannot authorize edits. Curves remain analytic native entities in the output.
"""
import copy,json,math
from collections import defaultdict
import numpy as np
from cad.geometry import near

TOL=1e-5
TAU=math.tau


def curve(g,kind,t):
    if kind=='ARC':
        angle=math.radians(g['start_angle'])+t*(math.radians(g['end_angle']-g['start_angle'])%TAU)
        return np.asarray(g['center'][:2])+g['radius']*np.array([math.cos(angle),math.sin(angle)])
    angle=g['start_param']+t*((g['end_param']-g['start_param'])%TAU)
    a=np.asarray(g['major_axis'][:2]);b=np.array([-a[1],a[0]])*g['ratio']
    return np.asarray(g['center'][:2])+a*math.cos(angle)+b*math.sin(angle)


def metric(e):
    g=e['geometry']
    if e['type'] in ('CIRCLE','ARC'):return np.eye(2)*g['radius']**2
    from graph.projected_profiles import ellipse_metric
    return ellipse_metric(dict(g,start_param=0,end_param=TAU))


def holes_fit(shape,holes,error):
    """Whiten each native conic; include the locator's transformed error."""
    from shapely.affinity import affine_transform
    from shapely.geometry import Point
    for hole in holes:
        values,vectors=np.linalg.eigh(metric(hole))
        if min(values)<=TOL*TOL:return False
        inverse=vectors@np.diag(1/np.sqrt(values))@vectors.T
        offset=-inverse@np.asarray(hole['geometry']['center'][:2])
        local=affine_transform(shape,[*inverse[0],*inverse[1],*offset])
        zero=Point(0,0)
        if not local.contains(zero) or local.boundary.distance(zero)<=1+np.linalg.norm(inverse,2)*error+TOL:return False
    return True


def inventory(context):
    from cad.part_identity import record_identity
    from cad.frame_geometry import planar_similarity,matrix
    from cad.curved_profiles import profile_from
    from shapely.geometry import Polygon,Point
    records={e['ref']:e for e in context['entities']};children=defaultdict(list);result=[]
    codes={r['part_code'] for e in records.values() if e.get('bom',{}).get('status')=='verified_template' for r in e['bom']['rows']}
    for ref,e in records.items():
        if '/' in ref:children[ref.rsplit('/',1)[0]].append(e)
    for root,parent in records.items():
        if parent['type']!='INSERT' or parent.get('review_only'):continue
        code=record_identity(parent,codes);local=children[root]
        if not code or not local or len(local)>64 or any(e.get('review_only') or e.get('coordinate_frame')!='instance:'+root or e['type'] not in ('LINE','ARC','CIRCLE','ELLIPSE','TEXT','MTEXT','ATTRIB','ATTDEF') for e in local):continue
        try:planar_similarity(matrix(parent))
        except ValueError:continue
        edges=[];holes=[];valid=True
        for e in local:
            if e['type'] not in ('LINE','ARC','CIRCLE','ELLIPSE'):continue
            g=e.get('geometry',{})
            if not g:valid=False;break
            if e['type']!='LINE' and not near(g.get('extrusion',[0,0,1]),[0,0,1],TOL):valid=False;break
            full=e['type']=='CIRCLE' or e['type']=='ELLIPSE' and near(g['end_param']-g['start_param'],TAU,TOL)
            if full:
                if metric(e) is None:valid=False;break
                holes.append(e);continue
            if e['type']=='LINE':pts=[np.asarray(g[k][:2]) for k in ('start','end')];middle=(pts[0]+pts[1])/2;z=[g[k][2] for k in ('start','end')]
            else:
                if metric(e) is None or (e['type']=='ARC' and g['radius']<=TOL):valid=False;break
                pts=[curve(g,e['type'],t) for t in (0,1)];middle=curve(g,e['type'],.5);z=[g['center'][2]]
            if not np.isfinite(np.asarray([*pts,middle])).all() or near(pts[0].tolist(),pts[1].tolist(),TOL):valid=False;break
            edges.append(dict(record=e,start=pts[0],end=pts[1],middle=middle,z=z))
        if not valid or not 3<=len(edges)<=24 or not any(e['record']['type'] in ('ARC','ELLIPSE') for e in edges):continue
        zs=[z for e in edges for z in e['z']]+[h['geometry']['center'][2] for h in holes]
        if max(zs)-min(zs)>TOL:continue
        chain=[dict(edges[0],reverse=False)];unused=edges[1:]
        while unused:
            point=chain[-1]['end'];matches=[(i,rev) for i,e in enumerate(unused) for rev in (False,True) if near(point.tolist(),e['end' if rev else 'start'].tolist(),TOL)]
            if len(matches)!=1:break
            i,rev=matches[0];edge=unused.pop(i);chain.append(dict(edge,start=edge['end'] if rev else edge['start'],end=edge['start'] if rev else edge['end'],reverse=rev))
        if unused or not near(chain[-1]['end'].tolist(),chain[0]['start'].tolist(),TOL):continue
        # Native circle/ellipse primitives are closed and not self crossing;
        # locator chords are only used to reject holes outside this face.
        try:
            profile=profile_from([e['record'] for e in chain]);shape=Polygon([p[:2] for p in profile['points']])
            if not shape.is_valid or shape.area<=TOL:continue
            valid=holes_fit(shape,holes,profile.get('curve_chord_error',0))
        except (ValueError,KeyError):continue
        if valid:result.append(dict(root=root,code=code,chain=chain,holes=holes,texts=[e for e in local if e['type'] in ('TEXT','MTEXT')],sheet_ids=parent.get('source_sheet_ids',[]),source=all(e['record']['type'] in ('LINE','ARC') for e in chain)))
    return records,result


def matches(source,target):
    a=source['chain'];b=target['chain'];results=[]
    if len(a)!=len(b) or len(source['holes'])!=len(target['holes']):return []
    for reverse in (False,True):
        sequence=b if not reverse else [dict(e,start=e['end'],end=e['start'],reverse=not e['reverse']) for e in reversed(b)]
        for offset in range(len(b)):
            paired=sequence[offset:]+sequence[:offset]
            if any((s['record']['type']=='LINE')!=(t['record']['type']=='LINE') for s,t in zip(a,paired)):continue
            points=np.asarray([p for e in a for p in (e['start'],e['end'],e['middle'])]);targets=np.asarray([p for e in paired for p in (e['start'],e['end'],e['middle'])])
            design=np.column_stack([points,np.ones(len(points))]);fit,_,rank,_=np.linalg.lstsq(design,targets,rcond=None)
            if rank!=3 or np.max(np.abs(design@fit-targets))>TOL:continue
            mat=fit[:2].T;origin=fit[2]
            if abs(np.linalg.det(mat))<1e-8 or np.linalg.cond(mat)>1000:continue
            if any(s['record']['type']!='LINE' and (not near((mat@np.asarray(s['record']['geometry']['center'][:2])+origin).tolist(),t['record']['geometry']['center'][:2],TOL) or not np.allclose(mat@metric(s['record'])@mat.T,metric(t['record']),atol=TOL,rtol=1e-9)) for s,t in zip(a,paired)):continue
            hole_map={};used=set()
            for h in source['holes']:
                g=h['geometry'];found=[t for t in target['holes'] if t['ref'] not in used and near((mat@np.asarray(g['center'][:2])+origin).tolist(),t['geometry']['center'][:2],TOL) and np.allclose(mat@metric(h)@mat.T,metric(t),atol=TOL,rtol=1e-9)]
                if len(found)!=1:break
                hole_map[h['ref']]=found[0];used.add(found[0]['ref'])
            if len(hole_map)!=len(source['holes']):continue
            if any(np.allclose(mat,r['matrix'],atol=1e-8,rtol=0) and near(origin.tolist(),r['origin'].tolist(),TOL) for r in results):continue
            results.append(dict(matrix=mat,origin=origin,paired=paired,hole_map=hole_map))
    return results


def valid_changed_face(view):
    from cad.curved_profiles import profile_from
    from shapely.geometry import Polygon,Point
    try:
        profile=profile_from([e['record'] for e in view['chain']]);shape=Polygon([p[:2] for p in profile['points']])
        if not shape.is_valid or shape.area<=TOL:return False
        return holes_fit(shape,view['holes'],profile.get('curve_chord_error',0))
    except (ValueError,TypeError,KeyError,np.linalg.LinAlgError):return False


def bindings(plan,context):
    if context.get('units')!=4 or getattr(plan,'questions',[]) or not plan.operations:return []
    recipes=[*getattr(plan,'resize_recipes',[]),*getattr(plan,'curved_wall_recipes',[])]
    if not recipes:return []
    records,views=inventory(context);actual={o.ref:o for o in plan.operations};result=[]
    removed={o.ref for o in plan.operations if o.action=='remove_insert'}
    from cad.edit_engine import Operation
    for source in views:
        if not source['source'] or any(source['root']==r or source['root'].startswith(r+'/') for r in removed):continue
        refs={e['record']['ref'] for e in source['chain']}
        drivers=[r for r in recipes if r.part_code==source['code'] and set(r.outline_refs)==refs]
        if not drivers or not refs.intersection(actual):continue
        changed={};valid=True
        for e in [*[v['record'] for v in source['chain']],*source['holes']]:
            op=actual.get(e['ref'])
            if op and (op.action!='replace_geometry' or not near(json.loads(op.before),e['geometry'],TOL)):valid=False;break
            changed[e['ref']]=json.loads(op.after) if op else e['geometry']
            old=e['geometry'];new=changed[e['ref']]
            if old.keys()!=new.keys():valid=False;break
            if e['type']=='LINE':
                if any(not near(old[k][2],new[k][2],TOL) for k in ('start','end')):valid=False;break
            elif not near(old['center'][2],new['center'][2],TOL) or not near(old.get('extrusion',[0,0,1]),new.get('extrusion',[0,0,1]),TOL):valid=False;break
        if not valid:continue
        for target in views:
            if target['root']==source['root'] or target['code']!=source['code'] or any(target['root']==r or target['root'].startswith(r+'/') for r in removed):continue
            candidates=matches(source,target)
            if len(candidates)!=1:continue
            fit=candidates[0];mat=fit['matrix'];origin=fit['origin'];operations=[];valid=True
            def add(e,g):
                if not near(g,e['geometry'],1e-7):operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(g),xyz=[],reason='Mặt cong chiếu: đối chiếu toàn biên/cung/lỗ bằng phép affine duy nhất; giữ đường cong native'))
            for edge,receiver in zip(source['chain'],fit['paired']):
                e=edge['record'];t=receiver['record'];old=e['geometry'];new=changed[e['ref']];g=copy.deepcopy(t['geometry'])
                if e['type']=='LINE':
                    for source_key,target_key in zip(('start','end'),('end','start') if edge['reverse']!=receiver['reverse'] else ('start','end')):
                        delta=mat@(np.asarray(new[source_key][:2])-old[source_key][:2]);g[target_key][:2]=(np.asarray(g[target_key][:2])+delta).tolist()
                else:
                    # A nonuniform projection must remain ELLIPSE, never be
                    # approximated by a circular ARC or a flattened polyline.
                    if t['type'] not in ('ARC','ELLIPSE') or new['radius']<=TOL:valid=False;break
                    if near(old,new,1e-7):continue
                    ratio=new['radius']/old['radius'];delta=mat@(np.asarray(new['center'][:2])-old['center'][:2]);g['center'][:2]=(np.asarray(g['center'][:2])+delta).tolist()
                    if t['type']=='ARC':
                        # Circular receivers require a similarity, including
                        # reflection. Never force a nonuniform map into ARC.
                        scale2=np.trace(mat@mat.T)/2
                        if not np.allclose(mat@mat.T,np.eye(2)*scale2,atol=TOL,rtol=1e-9):valid=False;break
                        g['radius']*=ratio;angles=[]
                        for index in ((1,0) if edge['reverse']!=receiver['reverse'] else (0,1)):
                            point=mat@curve(new,'ARC',index)+origin-g['center'][:2]
                            angles.append(math.degrees(math.atan2(point[1],point[0]))%360)
                        g['start_angle'],g['end_angle']=angles
                        add(t,g);continue
                    g['major_axis']=[v*ratio for v in g['major_axis']]
                    a=np.asarray(g['major_axis'][:2]);b=np.array([-a[1],a[0]])*g['ratio'];basis=np.column_stack([a,b]);parameters=[]
                    for index in ((1,0) if edge['reverse']!=receiver['reverse'] else (0,1)):
                        p=mat@curve(new,'ARC',index)+origin;uv=np.linalg.solve(basis,p-g['center'][:2]);parameters.append(math.atan2(uv[1],uv[0])%TAU)
                    g['start_param'],g['end_param']=parameters
                    if g['end_param']<=g['start_param']:g['end_param']+=TAU
                add(t,g)
            if not valid:continue
            for h in source['holes']:
                t=fit['hole_map'][h['ref']];old=h['geometry'];new=changed[h['ref']];g=copy.deepcopy(t['geometry'])
                if t['type'] not in ('CIRCLE','ELLIPSE') or new['radius']<=TOL:valid=False;break
                g['center'][:2]=(np.asarray(g['center'][:2])+mat@(np.asarray(new['center'][:2])-old['center'][:2])).tolist()
                if t['type']=='CIRCLE':
                    scale2=np.trace(mat@mat.T)/2
                    if not np.allclose(mat@mat.T,np.eye(2)*scale2,atol=TOL,rtol=1e-9):valid=False;break
                    g['radius']*=new['radius']/old['radius']
                else:g['major_axis']=[v*new['radius']/old['radius'] for v in g['major_axis']]
                add(t,g)
            if not valid or not operations:continue
            # Verify the complete changed face and every bore again using the
            # same exact map; a stale connector or phase cannot escape.
            after_source=copy.deepcopy(source);after_target=copy.deepcopy(target);updated={o.ref:json.loads(o.after) for o in operations}
            for view,changes in ((after_source,changed),(after_target,updated)):
                for edge in view['chain']:
                    e=edge['record'];g=changes.get(e['ref'],e['geometry']);e['geometry']=g
                    pts=[np.asarray(g[k][:2]) for k in ('start','end')] if e['type']=='LINE' else [curve(g,e['type'],t) for t in (0,1)]
                    edge['start'],edge['end']=pts[::-1] if edge['reverse'] else pts;edge['middle']=(pts[0]+pts[1])/2 if e['type']=='LINE' else curve(g,e['type'],.5)
                for h in view['holes']:h['geometry']=changes.get(h['ref'],h['geometry'])
            check=matches(after_source,after_target)
            if len(check)!=1 or not np.allclose(check[0]['matrix'],mat,atol=1e-8,rtol=0) or not near(check[0]['origin'].tolist(),origin.tolist(),TOL) or not valid_changed_face(after_source) or not valid_changed_face(after_target):continue
            text_refs=[]
            for text in target['texts']:
                raw=text.get('raw_text',text.get('text',''))
                candidates={e.after for e in getattr(plan,'edits',[]) if e.part_number==source['code'] and e.purpose in ('bom','annotation') and e.before==raw}
                if len(candidates)>1:raise ValueError('Mô tả cùng mã có nhiều kết quả khác nhau trong mặt cong chiếu')
                if candidates:
                    operations.append(Operation(ref=text['ref'],action='replace_text',before=raw,after=next(iter(candidates)),xyz=[],reason='Đồng bộ mô tả cùng mã/văn bản nguồn trong mặt cong chiếu đã gắn'))
                    text_refs.append(text['ref'])
            result.append(dict(source_root=source['root'],target_root=target['root'],part_code=source['code'],source_hash=context['source_hash'],sheet_ids=target['sheet_ids'],
                source_dimension_ref=getattr(drivers[0],'dimension_ref',None),target_refs=[*[e['record']['ref'] for e in target['chain']],*[h['ref'] for h in target['holes']],*text_refs],
                target_outline_ref=target['chain'][0]['record']['ref'],target_outline_refs=[e['record']['ref'] for e in target['chain']],face_count=1,hole_count=len(source['holes']),
                matrix=mat.tolist(),origin=origin.tolist(),status='verified_analytic_curved_face_projection',operations=operations))
    counts=defaultdict(int)
    for proof in result:counts[proof['target_root']]+=1
    return [p for p in result if counts[p['target_root']]==1]
