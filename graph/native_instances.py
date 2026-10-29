"""Synchronize identical local entities of BOM-coded native part blocks.

Named/attributed INSERTs must equal a verified BOM code. An anonymous alias
also requires an independent source-owned feature of that code and a complete
native-definition match. Geometry alone grants no identity or mechanical fit.
"""
import json
from cad.geometry import near

GEOMETRY_ACTIONS={'replace_geometry','line_end'}
SYNC_ACTIONS=GEOMETRY_ACTIONS|{'replace_text'}


def leader_body_features(context,records,codes,*,allow_curves=False):
    """Recognize a COMPLETE anonymous body from its local BOM/leader/DIM.

    A leader owns one measured contour, never its entire containing assembly.
    Grant the INSERT only when it contains exactly that body, its bound DIMs
    and enclosed bores. Unclassified/nested geometry keeps the old gate.
    """
    from shapely.geometry import Polygon,Point
    from cad.frame_geometry import world
    from cad.part_identity import PART_TAGS
    from bom.reader import normalized,plain,part_number_key
    from bom.continuations import scoped_table_sheets
    bom_scopes=scoped_table_sheets(context)
    features=list(context.get('source_features',{}).get('features',[]))
    bindings=context.get('source_features',{}).get('leader_profile_bindings',[])
    # A receiver that only translates need not carry its own size DIM in this
    # assembly view. A unique closed material region and local BOM marker can
    # establish its complete body, never permission to resize it without a DIM.
    for b in bindings:
        if b.get('status')!='verified_interior_region' or len(b.get('part_codes',[]))!=1 or len(b.get('candidates',[]))!=1:continue
        candidate=b['candidates'][0];refs=candidate.get('geometry_refs',[]);frame=candidate.get('coordinate_frame','')
        if candidate.get('curved') and not allow_curves:continue
        if not frame.startswith('instance:') or not refs or any(set(f['refs'])==set(refs) for f in features):continue
        root=frame[9:]
        if any(ref not in records or ref.rsplit('/',1)[0]!=root for ref in refs):continue
        from cad.closed_profiles import polygon_from
        curve=None
        try:
            source=[world(records[ref]) for ref in refs]
            if candidate.get('curved'):
                from cad.curved_profiles import profile_from
                curve=profile_from(source)
                # Exact circular/straight edges only. A locator polygon alone
                # cannot certify a general spline body or hidden depth.
                if any(edge['kind'] not in ('line','arc') for edge in curve['edges']):continue
                points=curve['points']
            else:points=polygon_from(source)
        except ValueError:continue
        features.append(dict(kind='source_closed_translation_body',refs=refs,points=points,dimensions=[],
            part_code=b['part_codes'][0],ownership_proof='local_bom_leader_profile',instance_ref=root,
            coordinate_frame=frame,layout=records[refs[0]].get('layout'),sheet_ids=b.get('sheet_ids',[]),
            evidence_refs=sorted(set(refs+b.get('evidence_refs',[]))),**({'identity_curve':curve} if curve else {})))
    result={}
    for f in features:
        if f.get('ownership_proof')!='local_bom_leader_profile' or f.get('part_code') not in codes:continue
        root=f.get('instance_ref');code=f['part_code'];refs=set(f.get('refs',[]))
        if not root or not refs or records.get(root,{}).get('type')!='INSERT' or records[root].get('review_only'):continue
        if not all(ref in records and ref.rsplit('/',1)[0]==root for ref in refs):continue
        # Two BOM numbers pointing into one contour do not identify two bodies.
        # This check is independent of which binding was indexed first.
        if any(set(b.get('part_codes',[]))!={code} and any(set(candidate.get('geometry_refs',[]))==refs
                for candidate in b.get('candidates',[])) for b in bindings):continue
        siblings=[s for s in features if s.get('instance_ref')==root]
        if len(siblings)!=1:continue
        declared=records[root].get('attributes',[])
        declared=declared.items() if isinstance(declared,dict) else declared
        if any(normalized(tag).replace('_',' ').replace('-',' ') in PART_TAGS and plain(value) not in ('',code) for tag,value in declared):continue
        owners=[b for b in bindings if
            (b.get('geometry_owner_verified') and b.get('status')=='verified_interior_dimension_chain' or
                not f.get('dimensions') and b.get('status')=='verified_interior_region') and
            b.get('part_codes')==[code] and len(b.get('candidates',[]))==1 and
            set(b['candidates'][0].get('geometry_refs',[]))==refs]
        verified=False
        for b in owners:
            for table_ref in b.get('bom_table_refs',[]):
                table=records.get(table_ref,{})
                if table.get('bom',{}).get('status')!='verified_template' or not bom_scopes.get(table_ref,set()).intersection(b.get('sheet_ids',[])):continue
                rows=[r for r in table['bom']['rows'] if part_number_key(r['part_number'])==part_number_key(b['part_number'])]
                if len(rows)==1 and rows[0]['part_code']==code:verified=True
        if not verified:continue
        polygon=Polygon([p[:2] for p in f['points']])
        if not polygon.is_valid or polygon.area<=1e-8:continue
        curve=f.get('identity_curve')
        # The leader must be strictly in the material, outside the locator's
        # bounded chord-error band. Recheck against current native endpoints.
        if curve:
            from cad.curved_profiles import distance
            endpoints=[ep for b in owners for ep in b.get('leader_endpoints',[])]
            if len(endpoints)!=1:continue
            ep=endpoints[0];leader=records.get(ep['ref'],{})
            try:g=world(leader)['geometry']
            except (ValueError,KeyError):continue
            ps=g.get('vertices',[]) if leader.get('type')=='LEADER' else [g['start'],g['end']] if leader.get('type')=='LINE' else []
            k=ep['vertex_index']
            if k not in (0,len(ps)-1) or not near(ps[k],ep['point'],1e-5):continue
            q=Point(ps[k][:2])
            if not polygon.contains(q) or min(distance(edge,ps[k]) for edge in curve['edges'])<=curve['curve_chord_error']+1e-5:continue
        dimension_refs={d['ref'] for d in f['dimensions']};valid=True
        for ref,e in records.items():
            if not ref.startswith(root+'/'):continue
            if e.get('review_only') or ref.rsplit('/',1)[0]!=root:valid=False;break
            if ref in refs or e['type'] in ('TEXT','MTEXT','ATTRIB','ATTDEF'):continue
            if e['type']=='DIMENSION' and ref in dimension_refs:continue
            if e['type']!='CIRCLE' or not e.get('geometry'):valid=False;break
            try:g=world(e)['geometry']
            except ValueError:valid=False;break
            p=Point(g['center'][:2]);radius=g['radius']
            clearance=min(distance(edge,g['center']) for edge in curve['edges']) if curve else polygon.boundary.distance(p)
            if radius<=0 or abs(g['center'][2]-f['points'][0][2])>1e-5 or not polygon.contains(p) or clearance<=radius+1e-5:
                valid=False;break
        if valid:result[root]=f
    return result


def leader_owned_instances(context,records,codes):
    # Curved aliases identify complete definitions for exact native reuse;
    # they are NOT the straight-body inventory used by the contact solver.
    return {root:f['part_code'] for root,f in leader_body_features(context,records,codes,allow_curves=True).items()}


def geometry_snapshot(record):
    return record.get('geometry') or record.get('radial_geometry') or record.get('hatch_translation_geometry')


def equivalent_operation(a,b):
    if a.action!=b.action or not near(a.xyz,b.xyz):return False
    if a.action=='replace_geometry':return near(json.loads(a.before),json.loads(b.before)) and near(json.loads(a.after),json.loads(b.after))
    if a.action=='line_end':return near(json.loads(a.before),json.loads(b.before)) and a.after==b.after
    return a.before==b.before and a.after==b.after


def equivalent_flat_refs(records,source_root,target_root):
    """A complete one-to-one native geometry match survives cloned handles and anonymous block names."""
    allowed={'LINE','LWPOLYLINE','POLYLINE','CIRCLE','ARC','ELLIPSE','SPLINE','DIMENSION','TEXT','MTEXT','HATCH'}
    def children(root):
        return [e for r,e in records.items() if r.startswith(root+'/') and e['type'] in allowed]
    first,second=children(source_root),children(target_root)
    if not first or not second or len(first)!=len(second):return None
    def same(a,b):
        if a['type']!=b['type'] or a.get('layer')!=b.get('layer'):return False
        if a['type'] in ('TEXT','MTEXT'):return a.get('raw_text',a.get('text'))==b.get('raw_text',b.get('text')) and near(a.get('text_placement'),b.get('text_placement'))
        ga=geometry_snapshot(a);gb=geometry_snapshot(b)
        return bool(ga) and near(ga,gb) and a.get('dimension_type')==b.get('dimension_type') and near(a.get('linear_factor',1),b.get('linear_factor',1))
    result={};used=set()
    for a in first:
        matches=[b['ref'] for b in second if same(a,b)]
        if len(matches)!=1 or matches[0] in used:return None
        result[a['ref']]=matches[0];used.add(matches[0])
    return result


def equivalent_body_refs(records,source_root,target_root):
    """A dimensioned detail and an undimensioned assembly can share a body.

    Identity must already be established independently. Compare EVERY physical
    primitive, not merely an outline or its bounding box. This map never grants
    permission to copy, remove, or synthesize dimensions absent in a view.
    """
    physical={'LINE','LWPOLYLINE','POLYLINE','CIRCLE','ARC','ELLIPSE','SPLINE'}
    metadata={'DIMENSION','TEXT','MTEXT','ATTRIB','ATTDEF'}
    def body(root):
        children=[e for ref,e in records.items() if ref.startswith(root+'/')]
        if any(e.get('review_only') or e['ref'].rsplit('/',1)[0]!=root or e['type'] not in physical|metadata for e in children):return None
        return [e for e in children if e['type'] in physical]
    a,b=body(source_root),body(target_root)
    if not a or not b or len(a)!=len(b):return None
    result={};used=set()
    for first in a:
        matches=[second['ref'] for second in b if first['type']==second['type'] and first.get('layer')==second.get('layer')
            and geometry_snapshot(first) and near(geometry_snapshot(first),geometry_snapshot(second))]
        if len(matches)!=1 or matches[0] in used:return None
        result[first['ref']]=matches[0];used.add(matches[0])
    return result


def inventory(context):
    records={e['ref']:e for e in context['entities']}
    codes={r['part_code'] for e in records.values() if e.get('bom',{}).get('status')=='verified_template'
           for r in e['bom']['rows']}
    from cad.part_identity import record_identity
    parts={ref:code for ref,e in records.items() for code in [record_identity(e,codes)] if code}
    aliases=leader_owned_instances(context,records,codes)
    for root,code in aliases.items():
        if root in parts and parts[root]!=code:raise ValueError('Block và chuỗi STT/BOM xác định hai mã khác nhau: '+root)
        parts[root]=code

    # Equal geometry proves a transform/correspondence only after identity is
    # known. Two different BOM items may have the same outline. Anonymous
    # blocks therefore need an independently source-owned measured feature;
    # never choose the first geometrically matching part in this document.
    bindings={}
    for feature in context.get('source_features',{}).get('features',[]):
        if feature.get('ownership_proof') not in ('native_part_identity','unique_source_detail_sheet','local_bom_leader_profile'):continue
        code=feature.get('part_code');frame=feature.get('coordinate_frame','')
        root=frame.removeprefix('instance:') if frame.startswith('instance:') else None
        refs=feature.get('refs',[])
        if code not in codes or not root or records.get(root,{}).get('type')!='INSERT' or not refs:continue
        if not all(ref in records and ref.startswith(root+'/') for ref in refs):continue
        bindings.setdefault(root,set()).add(code)
    named=list(parts.items())
    for root,owners in bindings.items():
        if len(owners)!=1:continue
        code=next(iter(owners))
        if root in parts and parts[root]!=code:
            raise ValueError('Mã block và chủ sở hữu hình nguồn mâu thuẫn: '+root)
        # A section/detail of the same item may have a different definition;
        # its own measured-view adapter must handle it, not native copying.
        if root in parts or any(owner_code==code and equivalent_flat_refs(records,known,root) for known,owner_code in named):
            parts[root]=code

    def owner(ref):
        current=ref.rsplit('/',1)[0] if '/' in ref else None
        while current:
            if current in parts:return current
            current=current.rsplit('/',1)[0] if '/' in current else None
        return None
    return records,parts,owner


def synchronize(plan,context):
    if plan.questions or not plan.operations:return plan
    from graph.projected_profiles import synchronize as sync_projected
    projection_audit={}
    plan=sync_projected(plan,context,projection_audit)
    projected={p['target_root'] for p in projection_audit.get('bindings',[])}
    from graph.cuboid_projections import synchronize as sync_cuboids,bindings as cuboid_bindings
    plan=sync_cuboids(plan,context)
    cuboids=cuboid_bindings(plan,context)
    records,parts,owner=inventory(context)
    cuboid_refs={ref for proof in cuboids for ref in proof['target_refs']}
    for root in parts:
        physical={e['ref'] for e in records.values() if e['ref'].startswith(root+'/') and e['type'] not in ('TEXT','MTEXT','ATTRIB','ATTDEF')}
        if physical and physical<=cuboid_refs:projected.add(root)
    # A local STT/leader can identify an uncoded complete planar face. Grant
    # the alias only inside this independently recomputed projection proof;
    # it is not a generic permission to copy differing anonymous definitions.
    for proof in projection_audit.get('bindings',[]):
        parts[proof['source_root']]=proof['part_code'];parts[proof['target_root']]=proof['part_code']
    if not parts:return plan
    removed={o.ref for o in plan.operations if o.action=='remove_insert'}
    # Materialize checked dependency rules first, so their downstream geometry
    # receives the same native-instance propagation as the user's direct edit.
    from graph.change_dependencies import propagate
    rules=[d.coordinate_rule for d in plan.dependencies if d.coordinate_rule]
    if rules:
        previous={o.ref for o in plan.operations}
        expanded=propagate(plan.operations,rules,context)
        from backend.services.change_service import EditProposal
        existing_edits={e.entity_ref for e in plan.edits}
        for op in expanded:
            if op.ref in previous or op.ref in existing_edits:continue
            root=owner(op.ref)
            if root is None:continue
            plan.edits.append(EditProposal(entity_ref=op.ref,part_number=parts[root],purpose='geometry',
                before=op.before,after=op.after or json.dumps(op.xyz),reason=op.reason))
        plan.operations=expanded
    by={o.ref:o for o in plan.operations}
    additions=[];edits=[];processed={};instances={};equivalences={};body_equivalences={}
    for instance,code in parts.items():instances.setdefault(code,[]).append(instance)
    for op in list(plan.operations):
        if op.action not in SYNC_ACTIONS:continue
        root=owner(op.ref)
        if root is None:continue
        # These complete planar faces have independently checked affine
        # correspondences. Their local coordinates differ from the measured
        # view, so copying its raw local snapshot would corrupt the projection.
        if root in projected:continue
        relative=op.ref[len(root):]
        source=records[op.ref]
        if any(op.ref.startswith(ref+'/') for ref in removed):
            raise ValueError('Không sửa hình học bên trong instance đã bỏ khỏi bản cắt')
        # ATTRIBs are owned by individual instances and have different handles;
        # only definition-owned TEXT/MTEXT have a reusable local identity.
        if op.action=='replace_text' and source['type'] not in ('TEXT','MTEXT'):continue
        key=(parts[root],relative)
        if key in processed:
            if not equivalent_operation(processed[key],op):raise ValueError('Các hình chiếu native của '+parts[root]+' có thay đổi xung đột')
            continue
        processed[key]=op
        for instance in instances[parts[root]]:
            code=parts[root]
            if instance==root:continue
            if instance in projected:continue
            if any(instance==ref or instance.startswith(ref+'/') for ref in removed):continue
            ref=instance+relative;target=records.get(ref)
            if target is None:
                pair=(root,instance)
                if pair not in equivalences:equivalences[pair]=equivalent_flat_refs(records,root,instance)
                mapping=equivalences[pair]
                if mapping:ref=mapping.get(op.ref,ref);target=records.get(ref)
                else:
                    if pair not in body_equivalences:body_equivalences[pair]=equivalent_body_refs(records,root,instance)
                    mapping=body_equivalences[pair]
                    if mapping:
                        ref=mapping.get(op.ref,ref);target=records.get(ref)
                        # No source DIM/text is copied into an assembly that
                        # has none. A different existing DIM retains its gate.
                        if source['type'] in ('DIMENSION','TEXT','MTEXT') and op.ref not in mapping and not any(
                                r.startswith(instance+'/') and e['type']==source['type'] for r,e in records.items()):continue
            if target is None or target.get('review_only'):
                raise ValueError('Block chi tiết '+code+' chưa được mở đủ trong khung liên quan: '+instance)
            if source['type']!=target['type'] or not near(geometry_snapshot(source),geometry_snapshot(target)):
                raise ValueError('Các instance cùng mã có hình học nguồn khác nhau: '+code)
            if op.action=='replace_geometry' and not near(json.loads(op.before),geometry_snapshot(target)):
                raise ValueError('Hình học trước sửa không khớp block chi tiết: '+ref)
            if op.action=='replace_text' and op.before!=target.get('raw_text',target.get('text','')):
                raise ValueError('Chữ trước sửa không khớp block chi tiết: '+ref)
            if ref in by:
                candidate=by[ref]
                if not equivalent_operation(candidate,op):
                    raise ValueError('Các hình chiếu native của '+code+' có thay đổi xung đột')
                continue
            copied=op.model_copy(update={'ref':ref,'reason':'Đồng bộ block native cùng mã '+code+': '+op.reason})
            additions.append(copied);by[ref]=copied
            from backend.services.change_service import EditProposal
            edits.append(EditProposal(entity_ref=ref,part_number=code,purpose='annotation' if op.action=='replace_text' else 'geometry',
                                      before=op.before,after=op.after or json.dumps(op.xyz),reason=copied.reason))
    if additions:
        plan.operations.extend(additions);plan.edits.extend(edits)
    return plan


def validate_sync(plan,context):
    from graph.cuboid_projections import validate as validate_cuboids
    validate_cuboids(plan,context)
    checked=synchronize(plan.model_copy(deep=True),context)
    if len(checked.operations)!=len(plan.operations):
        raise ValueError('Thiếu thao tác đồng bộ các instance block cùng mã vật tư')


def assembly_reviews(plan,context):
    """Only certify assemblies whose physical geometry belongs to coded blocks.

    Loose dimensions, leaders and unidentified geometry keep the existing gate:
    their relation to edited components has not been established.
    """
    records,parts,owner=inventory(context)
    from graph.projected_profiles import bindings as projected_bindings
    projected=projected_bindings(plan,context)
    for proof in projected:
        parts[proof['source_root']]=proof['part_code'];parts[proof['target_root']]=proof['part_code']
    changed={parts[root] for o in plan.operations if o.action in GEOMETRY_ACTIONS
             for root in [owner(o.ref)] if root is not None}
    geometric=[o for o in plan.operations if o.action in ('replace_geometry','line_end','move_insert','append_geometry')]
    if not changed or any(owner(o.ref) is None for o in geometric):return {}
    try:validate_sync(plan,context)
    except ValueError:return {}
    result={}
    for sheet in context.get('targets',[]):
        sid=sheet['id']
        local=[e for e in records.values() if sid in e.get('source_sheet_ids',[])]
        tables=[e for e in local if e.get('bom',{}).get('status')=='verified_template' and len(e['bom']['rows'])>1]
        if not tables:continue
        codes={r['part_code'] for e in tables for r in e['bom']['rows']}
        affected=codes & changed
        if not affected:continue
        native={parts[e['ref']] for e in local if e['ref'] in parts}
        if not affected<=native:continue
        table_roots={e['ref'] for e in local if e['type']=='ACAD_TABLE'}
        graphic_refs={ref for e in tables if e.get('type')=='GRAPHIC_TABLE' for ref in [e['ref'],*e.get('source_refs',[])]}
        frame_root=sheet.get('frame_insert')
        def belongs_to_resource(ref):
            return any(ref==r or ref.startswith(r+'/') for r in table_roots) or bool(frame_root and (ref==frame_root or ref.startswith(frame_root+'/')))
        unknown=[]
        for e in local:
            ref=e['ref']
            if owner(ref) is not None or ref in parts or belongs_to_resource(ref) or ref==sid or ref in graphic_refs:continue
            # Text cannot be mistaken for physical assembly geometry. All
            # other unknown shapes/measurements, including balloons, block
            # automatic certification until their ownership is established.
            if e['type'] not in ('TEXT','MTEXT','ATTRIB','ATTDEF'):
                unknown.append(ref)
        if unknown:continue
        refs=[o.ref for o in plan.operations if o.ref in records and sid in records[o.ref].get('source_sheet_ids',[]) and o.action in GEOMETRY_ACTIONS]
        if not refs:continue
        result[sid]=dict(sheet_id=sid,status='verified_native_instances',
            verified_views=[dict(sheet_id=sid,view='Cụm lắp dùng block native cùng mã vật tư',status='verified_view',refs=refs,binding_count=len(refs))],
            reason='Toàn bộ hình cụm thuộc block có mã BOM; mọi instance của chi tiết thay đổi đã nhận cùng thao tác trong hệ tọa độ cục bộ.')
        for proof in projected:
            if sid not in proof['sheet_ids']:continue
            result[sid]['verified_views'].append(dict(sheet_id=sid,view='Mặt chi tiết vẽ nghiêng: toàn biên dạng và lỗ đã đối chiếu',
                status='verified_view',refs=proof['target_refs'],binding_count=len(proof['target_refs']),
                source_dimension_ref=proof['source_dimension_ref'],source_hash=proof['source_hash'],
                part_code=proof['part_code'],hole_count=proof['hole_count'],face_count=proof['face_count'],
                target_outline_ref=proof['target_outline_ref'],projection_matrix=proof['matrix']))
            result[sid]['reason']='Đã đồng bộ block cùng mã và mặt chiếu phẳng có đối chiếu biên dạng/lỗ. Chưa suy diễn chiều sâu hay tiếp xúc 3D ẩn.'
    return result
