"""Exact planar-face projections, independently identified by local BOM codes.

An affine outline and every enclosed circular bore must agree with the target
ellipses. LINE/straight POLYLINE contours retain their native topology. Fewer
bores are allowed only when all source outline vertices establish a UNIQUE
map; symmetric shapes without sufficient landmarks remain unresolved.
This does not reconstruct hidden depth or an extruded/welded body.
Multiple faces in one INSERT require a complete, unambiguous partition and
consistent motion at every shared vertex. No partly matched INSERT is granted
native-instance ownership. Hidden edges/depth remain outside this adapter.
"""
import copy
import json
import math
from collections import defaultdict

import numpy as np
from cad.geometry import near

TOL=1e-5


def vertices(geometry):
    if not geometry.get('closed') or geometry.get('extrusion',[0,0,1])!=[0,0,1]:return None
    if not math.isfinite(geometry.get('elevation',0)):return None
    raw=geometry.get('points',[])
    if not 3<=len(raw)<=64 or any(any(p[2:]) for p in raw):return None
    points=np.asarray([p[:2] for p in raw],dtype=float)
    if not np.isfinite(points).all():return None
    # Some CAD writers serialize the closing point despite the closed flag.
    # Normalize only that duplicate for matching; output keeps both vertices.
    if len(points)>3 and near(points[0].tolist(),points[-1].tolist(),TOL):points=points[:-1]
    if any(np.linalg.norm(a-b)<=TOL for i,a in enumerate(points) for b in points[i+1:]):return None
    from shapely.geometry import Polygon
    polygon=Polygon(points)
    if not polygon.is_valid or polygon.area<=TOL:return None
    return points


def ellipse_metric(g):
    if not near(g.get('extrusion',[0,0,1]),[0,0,1],TOL):return None
    if not near(g.get('end_param',0)-g.get('start_param',0),2*math.pi,TOL):return None
    a=np.asarray(g['major_axis'][:2],dtype=float)
    b=np.array([-a[1],a[0]])*g['ratio']
    if not np.isfinite(a).all() or not near(g['major_axis'][2],0,TOL) or not 0<g['ratio']<=1 or np.linalg.norm(a)<=TOL:return None
    return np.outer(a,a)+np.outer(b,b)


def straight_faces(local):
    """Partition complete native straight outlines; never bridge gaps."""
    from cad.closed_profiles import contours,segments
    outlines=[e for e in local if e['type'] in ('LINE','LWPOLYLINE','POLYLINE')]
    closed=[];open_records=[]
    for e in outlines:
        g=e.get('geometry',{})
        if not g:return []
        if e['type']!='LINE' and g.get('closed'):
            points=vertices(g)
            if points is None:return []
            closed.append(dict(outline=e,outline_records=[e],outline_refs=[e['ref']],points=points,elevation=g.get('elevation',0)))
        else:
            if not segments(e):return []
            open_records.append(e)
    rings=contours(open_records)
    if {e['ref'] for e in open_records}!={r for ring in rings for r in ring['refs']} and all(e['type']=='LINE' for e in open_records):
        rings=joined_line_faces(open_records)
    if {e['ref'] for e in open_records}!={r for ring in rings for r in ring['refs']}:return []
    by={e['ref']:e for e in open_records}
    representatives={f['outline']['ref'] for f in closed}
    for ring in rings:
        if not 3<=len(ring['points'])<=64:return []
        refs=ring['refs'];representative=next((r for r in refs if r not in representatives),None)
        if representative is None:return []
        representatives.add(representative)
        closed.append(dict(outline=by[representative],outline_records=[by[r] for r in refs],
            outline_refs=refs,points=np.asarray([p[:2] for p in ring['points']]),elevation=ring['points'][0][2]))
    return closed if 1<=len(closed)<=16 else []


def joined_line_faces(records):
    """Planar face graph with native shared seams, no inferred intersections.

    Every polygon edge must be an entire native LINE; every native LINE must
    belong to a bounded face. Dangles, duplicate edges, crossings requiring
    invented vertices, holes and unknown extra faces remain unbound.
    """
    if not records or len(records)>1024:return []
    from shapely.geometry import LineString
    from shapely.ops import polygonize
    def key(p):return tuple(round(float(v),5) for v in p)
    edges={};points={}
    for e in records:
        g=e['geometry'];a,b=g['start'],g['end'];ka,kb=key(a),key(b)
        if ka==kb:return []
        pair=tuple(sorted((ka,kb)))
        if pair in edges:return []
        edges[pair]=e['ref'];points.setdefault(ka,a);points.setdefault(kb,b)
    if max(p[2] for p in points.values())-min(p[2] for p in points.values())>TOL:return []
    shapes=list(polygonize([LineString([points[a][:2],points[b][:2]]) for a,b in edges]))
    if not 1<=len(shapes)<=16:return []
    by_xy={key(p)[:2]:k for k,p in points.items()}
    if len(by_xy)!=len(points):return []
    result=[]
    for shape in shapes:
        if not shape.is_valid or shape.area<=TOL or shape.interiors:return []
        keys=[by_xy.get(key(p)[:2]) for p in shape.exterior.coords[:-1]]
        if any(k is None for k in keys):return []
        refs=[]
        for a,b in zip(keys,keys[1:]+keys[:1]):
            ref=edges.get(tuple(sorted((a,b))))
            if ref is None:return []
            refs.append(ref)
        result.append(dict(refs=sorted(refs),points=[points[k] for k in keys]))
    return result if set(edges.values())=={r for face in result for r in face['refs']} else []


def face_after(face,operations):
    """Read changed native endpoints in the original contour order."""
    from cad.closed_profiles import segments
    pairs=[]
    for record in face['outline_records']:
        op=operations.get(record['ref']);g=record['geometry']
        if op and (op.action!='replace_geometry' or not near(json.loads(op.before),g,TOL)):return None
        new=json.loads(op.after) if op else g
        before_edges=segments(record);after_edges=segments(dict(record,geometry=new))
        if not before_edges or len(before_edges)!=len(after_edges):return None
        for a,b in zip(before_edges,after_edges):
            if any(not near(p[2],q[2],TOL) for p,q in zip(a,b)):return None
            pairs.extend(zip(a,b))
    result=[]
    for point in face['points']:
        moves=[b[:2] for a,b in pairs if near(a[:2],point.tolist(),TOL) and near(a[2],face['elevation'],TOL)]
        if not moves or any(not near(q,moves[0],TOL) for q in moves):return None
        result.append(moves[0])
    from shapely.geometry import Polygon
    p=Polygon(result)
    return np.asarray(result) if p.is_valid and p.area>TOL else None


def changed_outline(face,new_points):
    """Keep the original LINE/POLYLINE topology and native entity types."""
    result=[]
    def moved(point):
        indices=[i for i,p in enumerate(face['points']) if near(point[:2],p.tolist(),TOL)]
        if len(indices)!=1:raise ValueError('Đỉnh hình chiếu chưa gắn duy nhất với biên nguồn')
        i=indices[0]
        return (np.asarray(point[:2])+new_points[i]-face['points'][i]).tolist()
    for record in face['outline_records']:
        g=copy.deepcopy(record['geometry'])
        if record['type']=='LINE':
            for k in ('start','end'):g[k][:2]=moved(g[k])
        else:
            for point in g['points']:point[:2]=moved(point)
        result.append((record,g))
    return result


def inventory(context):
    from cad.part_identity import record_identity,PART_TAGS
    from bom.reader import normalized,part_number_key
    records={e['ref']:e for e in context['entities']}
    codes={r['part_code'] for e in records.values() if e.get('bom',{}).get('status')=='verified_template' for r in e['bom']['rows']}
    children=defaultdict(list)
    for ref,e in records.items():
        if '/' in ref:children[ref.rsplit('/',1)[0]].append(e)
    result={}
    for root,e in records.items():
        if e.get('type')!='INSERT' or e.get('review_only'):continue
        code=record_identity(e,codes)
        local=children[root]
        if not local or any(c.get('review_only') or c.get('coordinate_frame')!='instance:'+root or
            c['type'] not in ('LINE','LWPOLYLINE','POLYLINE','CIRCLE','ELLIPSE','DIMENSION','TEXT','MTEXT','ATTRIB','ATTDEF') for c in local):continue
        faces=straight_faces(local)
        if not faces:continue
        points_by_ref={f['outline']['ref']:f['points'] for f in faces}
        if any(binding.get('status')=='owner_identity_conflict' and any(
                set(c.get('geometry_refs',[]))==set(f['outline_refs']) for c in binding.get('candidates',[]) for f in faces)
                for binding in context.get('source_features',{}).get('leader_profile_bindings',[])):continue
        if not code:
            attributes=e.get('attributes',[])
            attributes=attributes.items() if isinstance(attributes,dict) else attributes
            if any(normalized(tag).replace('_',' ').replace('-',' ') in PART_TAGS and str(value).strip() for tag,value in attributes):continue
            face_owners=[]
            for face in faces:
                owners=set()
                for binding in context.get('source_features',{}).get('leader_profile_bindings',[]):
                    if binding.get('status') not in ('verified_interior_region','verified_interior_dimension_chain','verified_endpoint_dimension_chain'):continue
                    candidates=binding.get('candidates',[])
                    if len(binding.get('part_codes',[]))!=1 or len(candidates)!=1 or set(candidates[0]['geometry_refs'])!=set(face['outline_refs']):continue
                    if not set(binding.get('sheet_ids',[])).intersection(e.get('source_sheet_ids',[])):continue
                    from bom.continuations import scoped_table_sheets
                    bom_scopes=scoped_table_sheets(context)
                    rows=[row for ref in binding.get('bom_table_refs',[]) for table in [records.get(ref,{})]
                        if table.get('bom',{}).get('status')=='verified_template' and bom_scopes.get(ref,set()).intersection(binding['sheet_ids'])
                        for row in table['bom']['rows'] if part_number_key(row['part_number'])==part_number_key(binding['part_number'])]
                    if rows and {row['part_code'] for row in rows}==set(binding['part_codes']):owners.update(binding['part_codes'])
                face_owners.append(owners)
            if any(len(owners)!=1 for owners in face_owners) or len(set.union(*face_owners))!=1:continue
            code=next(iter(face_owners[0]))
        holes=[c for c in local if c['type'] in ('CIRCLE','ELLIPSE')]
        if len(holes)>32*len(faces) or any(not c.get('geometry') for c in holes):continue
        dims=[c for c in local if c['type']=='DIMENSION']
        from shapely.geometry import Polygon,Point
        polygons={ref:Polygon(p) for ref,p in points_by_ref.items()}
        if any(a.intersection(b).area>TOL*TOL for i,a in enumerate(polygons.values()) for b in list(polygons.values())[i+1:]):continue
        assigned={f['outline']['ref']:dict(holes=[],dimensions=[]) for f in faces}
        valid=True
        for hole in holes:
            matches=[ref for ref,p in polygons.items() if p.contains(Point(hole['geometry']['center'][:2]))]
            if len(matches)!=1:valid=False;break
            assigned[matches[0]]['holes'].append(hole)
        if not valid or any(len(v['holes'])>32 for v in assigned.values()):continue
        for dim in dims:
            g=dim.get('geometry',{})
            matches=[]
            for ref,v in assigned.items():
                anchors=list(points_by_ref[ref])+[h['geometry']['center'][:2] for h in v['holes']]
                face=next(f for f in faces if f['outline']['ref']==ref)
                if all(k in g and near(g[k][2],face['elevation'],TOL) and
                       any(near(g[k][:2],list(p),TOL) for p in anchors) for k in ('defpoint2','defpoint3')):matches.append(ref)
            if not matches:valid=False;break
            # A DIM of a shared seam can bind both faces. Both independent
            # projection computations must later produce the SAME operation.
            for ref in matches:assigned[ref]['dimensions'].append(dim)
        if not valid:continue
        for face in faces:
            key=root if len(faces)==1 else face['outline']['ref']
            result[key]=dict(root=root,code=code,**face,**assigned[face['outline']['ref']],
                face_count=len(faces),face_outline_refs=[f['outline']['ref'] for f in faces],
                texts=[c for c in local if c['type'] in ('TEXT','MTEXT')],sheet_ids=e.get('source_sheet_ids',[]))
    return records,result


def correspondences(source,target):
    a,b=source['points'],target['points']
    if len(a)!=len(b) or len(source['holes'])!=len(target['holes']):return []
    if any(h['type']!='CIRCLE' for h in source['holes']) or any(h['type']!='ELLIPSE' for h in target['holes']):return []
    from shapely.geometry import Polygon,Point
    polygon=Polygon(a)
    z=source['elevation']
    for h in source['holes']:
        g=h['geometry']
        if not near(g.get('extrusion',[0,0,1]),[0,0,1],TOL) or not near(g['center'][2],z,TOL) or not math.isfinite(g['radius']) or g['radius']<=0:return []
        point=Point(g['center'][:2])
        if not polygon.contains(point) or polygon.boundary.distance(point)<=g['radius']+TOL:return []
    metrics={h['ref']:ellipse_metric(h['geometry']) for h in target['holes']}
    target_z=target['elevation']
    if any(v is None for v in metrics.values()) or any(not near(h['geometry']['center'][2],target_z,TOL) for h in target['holes']):return []
    design=np.column_stack((a,np.ones(len(a))))
    if np.linalg.matrix_rank(design)!=3:return []
    result=[]
    for reverse in (False,True):
        ordered=b[::-1] if reverse else b
        for offset in range(len(b)):
            paired=np.roll(ordered,-offset,axis=0)
            transform=np.linalg.lstsq(design,paired,rcond=None)[0]
            matrix=transform[:2].T;origin=transform[2]
            if not np.isfinite(transform).all() or abs(np.linalg.det(matrix))<1e-8 or np.linalg.cond(matrix)>100:continue
            if not np.allclose(design@transform,paired,atol=TOL,rtol=0):continue
            hole_map={};used=set()
            for hole in source['holes']:
                g=hole['geometry'];center=matrix@np.asarray(g['center'][:2])+origin
                metric=matrix@matrix.T*g['radius']**2
                matches=[h for h in target['holes'] if np.allclose(h['geometry']['center'][:2],center,atol=TOL,rtol=0) and
                    np.allclose(metrics[h['ref']],metric,atol=TOL,rtol=1e-8)]
                if len(matches)!=1 or matches[0]['ref'] in used:break
                hole_map[hole['ref']]=matches[0]['ref'];used.add(matches[0]['ref'])
            if len(hole_map)!=len(source['holes']):continue
            indices=[next(i for i,p in enumerate(b) if near(p.tolist(),q.tolist(),TOL)) for q in paired]
            if any(np.allclose(matrix,r['matrix'],atol=1e-8,rtol=0) and np.allclose(origin,r['origin'],atol=TOL,rtol=0) for r in result):continue
            result.append(dict(matrix=matrix,origin=origin,indices=indices,hole_map=hole_map))
    return result


def bindings(plan,context):
    """Recompute projection operations from source recipes; no stored trust flag."""
    from graph.curved_projected_profiles import bindings as curved_bindings
    curved=curved_bindings(plan,context)
    if not getattr(plan,'resize_recipes',[]) or getattr(plan,'questions',[]) or not plan.operations or context.get('units')!=4:return curved
    records,views=inventory(context);by={o.ref:o for o in plan.operations};results=[]
    removed={o.ref for o in plan.operations if o.action=='remove_insert'}
    from cad.edit_engine import Operation
    for recipe in plan.resize_recipes:
        sources=[v for v in views.values() if v['code']==recipe.part_code and
            set(recipe.outline_refs)==set(v['outline_refs']) and set(recipe.hole_refs)=={h['ref'] for h in v['holes']} and
            any(d['ref']==recipe.dimension_ref for d in v['dimensions'])]
        if len(sources)!=1:continue
        source=sources[0];outline=source['outline']
        if any(source['root']==r or source['root'].startswith(r+'/') for r in removed):
            raise ValueError('Không sửa hình chiếu từ instance nguồn đã bỏ')
        features=context.get('source_features',{}).get('features',[])
        owned=[f for f in features if f.get('part_code')==recipe.part_code and f.get('ownership_proof') in
               ('native_part_identity','unique_source_detail_sheet','local_bom_leader_profile') and
               set(f['refs'])==set(recipe.outline_refs) and any(d['ref']==recipe.dimension_ref for d in f['dimensions'])]
        if len(owned)!=1:continue
        if not any(r in by for r in source['outline_refs']):continue
        new_points=face_after(source,by)
        if new_points is None or len(new_points)!=len(source['points']):continue
        source_after={};valid=True
        for h in source['holes']:
            op=by.get(h['ref'])
            if op and (op.action!='replace_geometry' or not near(json.loads(op.before),h['geometry'],TOL)):
                valid=False;break
            source_after[h['ref']]=json.loads(op.after) if op else h['geometry']
            g=source_after[h['ref']]
            if not math.isfinite(g['radius']) or g['radius']<=0 or not near(g['center'][2],h['geometry']['center'][2],TOL):valid=False;break
        if not valid:continue
        for target in views.values():
            if target['root']==source['root'] or target['code']!=source['code']:continue
            if any(target['root']==r or target['root'].startswith(r+'/') for r in removed):continue
            matches=correspondences(source,target)
            if len(matches)!=1:continue
            match=matches[0];matrix,origin=match['matrix'],match['origin'];operations=[];target_valid=True
            def operation(record,updated):
                if near(record['geometry'],updated,TOL):return
                operations.append(Operation(ref=record['ref'],action='replace_geometry',before=json.dumps(record['geometry']),
                    after=json.dumps(updated),xyz=[],reason='Đồng bộ mặt phẳng chiếu đã đối chiếu toàn biên dạng và lỗ; giữ phép chiếu nguồn'))
            target_points=target['points'].copy();anchors=[]
            for i,j in enumerate(match['indices']):
                delta=matrix@(new_points[i]-source['points'][i]);old=target_points[j].tolist()
                target_points[j]+=delta;anchors.append((old,target_points[j].tolist()))
            from shapely.geometry import Polygon
            shape=Polygon(target_points)
            if not shape.is_valid or shape.area<=TOL:raise ValueError('Biên dạng chiếu sau sửa không hợp lệ')
            for record,g in changed_outline(target,target_points):operation(record,g)
            target_holes={h['ref']:h for h in target['holes']}
            for h in source['holes']:
                receiver=target_holes[match['hole_map'][h['ref']]];old=h['geometry'];new=source_after[h['ref']]
                g=copy.deepcopy(receiver['geometry']);previous=list(g['center'][:2]);delta=matrix@(np.asarray(new['center'][:2])-old['center'][:2])
                g['center'][0]+=float(delta[0]);g['center'][1]+=float(delta[1])
                g['major_axis']=[v*new['radius']/old['radius'] for v in g['major_axis']]
                anchors.append((previous,list(g['center'][:2])));operation(receiver,g)
            for dim in target['dimensions']:
                g=copy.deepcopy(dim.get('geometry',{}));updated={}
                if dim.get('dimension_type') not in (0,1) or g.get('text') not in ('','<>'):target_valid=False;break
                from graph.fit_constraints import measurement
                original_length=np.linalg.norm(np.linalg.solve(matrix,np.asarray(g['defpoint3'][:2])-g['defpoint2'][:2]))
                # An inclined-face DIM must represent its true physical
                # length, calibrated against the source drawing's DIM factor.
                factor=abs(records[recipe.dimension_ref].get('linear_factor',1))
                if not near(measurement(dim,g),original_length*factor,TOL):target_valid=False;break
                for key in ('defpoint2','defpoint3'):
                    moves=[b for a,b in anchors if near(g[key][:2],a,TOL)]
                    if not moves or any(not near(m,moves[0],TOL) for m in moves):break
                    updated[key]=[moves[0][0],moves[0][1],g[key][2]]
                if len(updated)!=2:target_valid=False;break
                shift=np.mean([np.asarray(updated[k][:2])-g[k][:2] for k in updated],axis=0)
                for key,p in updated.items():g[key]=p
                for i in (0,1):g['defpoint'][i]+=float(shift[i])
                actual_length=np.linalg.norm(np.linalg.solve(matrix,np.asarray(g['defpoint3'][:2])-g['defpoint2'][:2]))
                if not near(measurement(dim,g),actual_length*factor,TOL):target_valid=False;break
                operation(dim,g)
            if not target_valid:continue
            text_ops=[by[t['ref']] for t in source['texts'] if t['ref'] in by and by[t['ref']].action=='replace_text']
            for text in target['texts']:
                raw=text.get('raw_text',text.get('text',''))
                updates={o.after for o in text_ops if o.before==raw}
                if len(updates)>1:raise ValueError('Mô tả cùng mã có nhiều kết quả khác nhau trong hình chiếu')
                if updates:
                    operations.append(Operation(ref=text['ref'],action='replace_text',before=raw,after=next(iter(updates)),xyz=[],
                        reason='Đồng bộ mô tả cùng mã và cùng văn bản nguồn trong mặt chiếu đã gắn'))
            if operations:results.append(dict(source_root=source['root'],target_root=target['root'],part_code=source['code'],
                source_dimension_ref=recipe.dimension_ref,source_hash=context['source_hash'],sheet_ids=target['sheet_ids'],
                target_refs=[*target['outline_refs'],*[h['ref'] for h in target['holes']],*[d['ref'] for d in target['dimensions']]],
                matrix=matrix.tolist(),origin=origin.tolist(),hole_count=len(source['holes']),operations=operations,
                target_outline_ref=target['outline']['ref'],target_outline_refs=target['outline_refs'],face_count=target['face_count'],
                status='verified_planar_face_projection'))
    # A native root is skipped by ordinary instance copying only when EVERY
    # physical face is covered exactly once. Partial correspondence cannot
    # hide an unidentified side/edge or grant ownership to the rest of a block.
    groups=defaultdict(list)
    for proof in results:groups[proof['target_root']].append(proof)
    complete=[]
    for root,proofs in groups.items():
        faces=[v for v in views.values() if v['root']==root]
        expected={v['outline']['ref'] for v in faces}
        if len(proofs)!=len(expected) or {p['target_outline_ref'] for p in proofs}!=expected:continue
        vertices_after=[];consistent=True;by_ref={}
        for proof in proofs:
            from graph.native_instances import equivalent_operation
            for op in proof['operations']:
                if op.ref in by_ref and not equivalent_operation(by_ref[op.ref],op):consistent=False;break
                by_ref[op.ref]=op
            face=next(f for f in faces if f['outline']['ref']==proof['target_outline_ref'])
            updated=face_after(face,{o.ref:o for o in proof['operations']})
            if updated is None:consistent=False;break
            for old,new in zip(face['points'],updated):
                if any(near(old.tolist(),a,TOL) and not near(new.tolist(),b,TOL) for a,b in vertices_after):consistent=False;break
                vertices_after.append((old.tolist(),new.tolist()))
        if consistent:complete.extend(proofs)
    return complete+curved


def synchronize(plan,context,audit=None):
    checked=bindings(plan,context);by={o.ref:o for o in plan.operations}
    from graph.native_instances import equivalent_operation
    from backend.services.change_service import EditProposal
    additions=[]
    for proof in checked:
        for op in proof['operations']:
            if op.ref in by:
                if not equivalent_operation(by[op.ref],op):raise ValueError('Hình chiếu xung đột với thao tác nguồn: '+op.ref)
            else:
                additions.append((op,proof['part_code']));by[op.ref]=op
    for op,code in additions:
        plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,
            purpose='annotation' if op.action=='replace_text' else 'geometry',before=op.before,after=op.after,reason=op.reason))
    if audit is not None:audit['bindings']=checked
    return plan
