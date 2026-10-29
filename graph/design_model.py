"""Source-bound part/representation registry. Observations never grant edit permission.

Part numbers are local to a table. Geometry measured in two views is two
representations, not two physical parts or proof that their contacts are known.
"""
import copy
import hashlib
import json
from collections import defaultdict
from bom.stage_links import physical_spec

VERSION=25


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf8')).hexdigest()[:24]


def build(context,graph=None):
    graph=graph or context.get('part_graph',{});source=context['source_hash']
    if graph.get('source_hash') and graph['source_hash']!=source:
        raise ValueError('Part graph and design registry must refer to the same immutable CAD source')
    targets={t['id'] for t in context.get('targets',[])}
    records={e['ref']:e for e in context['entities']}
    features=context.get('source_features',{}).get('features',[])
    selected_codes={r['part_code'].strip() for e in records.values()
                    if e.get('bom',{}).get('status')=='verified_template' for r in e['bom']['rows']}
    selected_codes.update(f['part_code'] for f in features if f.get('part_code'))
    selected_codes.update(n['code'] for n in graph.get('nodes',[]) if targets.intersection(n.get('detail_sheets',[])))
    parts={};representations=[];unresolved=[];ref_owners=defaultdict(set)
    for node in graph.get('nodes',[]):
        if node['code'] not in selected_codes:continue
        occurrences=copy.deepcopy(node.get('bom_occurrences',[]))
        definitions={(physical_spec(o.get('description','')),o.get('material','').strip().casefold()) for o in occurrences}
        parts[node['code']]=dict(id=node['code'],identity_kind='bom_code',bom_occurrences=occurrences,
            definition_conflict=bool(node.get('definition_conflict') or len(definitions)>1),
            detail_sheet_ids=sorted(set(node.get('detail_sheets',[]))),
            manufacturing_stages=copy.deepcopy(node.get('manufacturing_stages',[])),representation_ids=[])
    # A verified selected table remains useful even when a document graph is
    # unavailable. Keep each source row/cell, including quantity, without an
    # invented purchasing code or global balloon-number lookup.
    for e in records.values():
        if e.get('bom',{}).get('status')!='verified_template':continue
        for row in e['bom']['rows']:
            code=row['part_code'].strip()
            p=parts.setdefault(code,dict(id=code,identity_kind='bom_code',bom_occurrences=[],definition_conflict=False,
                detail_sheet_ids=[],manufacturing_stages=[],representation_ids=[]))
            occurrence=dict(table_ref=e['ref'],sheet_ids=e.get('source_sheet_ids',[]),**copy.deepcopy(row))
            p.setdefault('selected_bom_rows',[]).append(occurrence)
    for f in features:
        code=f.get('part_code');proof=f.get('ownership_proof','unverified')
        known=bool(code and proof in ('native_part_identity','unique_source_detail_sheet','selected_native_instance','local_bom_leader_profile'))
        rid='view-'+identity([source,f.get('layout'),f.get('coordinate_frame'),sorted(f['refs']),code])
        # Feature coordinates are kept in the authoritative source-feature
        # store. This registry holds references and measured parameters only.
        r=dict(id=rid,part_id=code if known else None,ownership_proof=proof,
            kind=f['kind'],layout=f.get('layout'),coordinate_frame=f.get('coordinate_frame'),
            instance_ref=f.get('instance_ref'),
            measurement_space=f.get('measurement_space'),sheet_ids=sorted(f.get('sheet_ids',[])),
            geometry_refs=sorted(f['refs']),evidence_refs=sorted(f.get('evidence_refs',[])),
            parameters=[dict(id='parameter-'+identity([source,b['ref']]),dimension_ref=b['ref'],anchor_points=[copy.deepcopy(records[b['ref']]['geometry'][k]) for k in ('defpoint2','defpoint3')] if b['ref'] in records and records[b['ref']].get('geometry') else [],
                             **copy.deepcopy({k:v for k,v in b.items() if k!='ref'})) for b in f.get('dimensions',[])],
            contact_constraints_verified=False)
        representations.append(r)
        if known:
            p=parts.setdefault(code,dict(id=code,identity_kind='selected_instance' if proof=='selected_native_instance' else 'source_owned_code',
                bom_occurrences=[],definition_conflict=False,detail_sheet_ids=[],manufacturing_stages=[],representation_ids=[]))
            p['representation_ids'].append(rid)
            for ref in f['refs']:ref_owners[ref].add(code)
        else:unresolved.append(dict(kind='feature_owner',representation_id=rid,evidence_refs=r['evidence_refs']))
    for p in parts.values():
        measured={sid for r in representations if r['part_id']==p['id'] for sid in r['sheet_ids']}
        p['unmapped_detail_sheet_ids']=sorted(set(p['detail_sheet_ids'])-measured)
        for sid in p['unmapped_detail_sheet_ids']:
            unresolved.append(dict(kind='unmapped_detail_view',part_id=p['id'],sheet_id=sid))
        p['representation_ids']=sorted(set(p['representation_ids']))
        definitions={(physical_spec(o.get('description','')),o.get('material','').strip().casefold())
                     for o in p.get('selected_bom_rows',[])+p['bom_occurrences']}
        p['definition_conflict']=p['definition_conflict'] or len(definitions)>1
        if p['definition_conflict']:unresolved.append(dict(kind='part_definition_conflict',part_id=p['id']))
    owners={ref:dict(part_ids=sorted(codes),status='source_owned' if len(codes)==1 else 'conflict') for ref,codes in sorted(ref_owners.items())}
    for ref,o in owners.items():
        if o['status']=='conflict':unresolved.append(dict(kind='geometry_owner_conflict',ref=ref,part_ids=o['part_ids']))
    relations=[]
    for edge in graph.get('edges',[]):
        if edge['source'] not in parts or edge['target'] not in parts:continue
        relations.append(dict(id=edge.get('id') or 'relation-'+identity([source,edge]),source=edge['source'],target=edge['target'],kind=edge['kind'],
            evidence=copy.deepcopy(edge.get('evidence',[])),source_status=edge.get('status'),
            executable=False,missing=copy.deepcopy(edge.get('missing',[]))))
        unresolved.append(dict(kind='manufacturing_input_check' if edge['kind']=='manufacturing_input' else 'relationship_constraint',relation_id=relations[-1]['id'],
            missing=relations[-1]['missing'] or ['contact/anchor and numeric design rule']))
    for a in context.get('source_features',{}).get('ambiguous_dimensions',[]):
        unresolved.append(dict(kind='ambiguous_dimension',**copy.deepcopy(a)))
    if not parts and not representations:unresolved.append(dict(kind='scope_identity_and_measured_geometry_missing'))
    from graph.part_graph import assembly_structure
    structure=copy.deepcopy(graph.get('assembly_structure',{}))
    tables=[e for e in records.values() if e.get('bom',{}).get('status')=='verified_template']
    if not structure.get('assemblies'):
        known={n['code']:n for n in graph.get('nodes',[])}
        for table in tables:
            for row in table['bom']['rows']:known.setdefault(row['part_code'],dict(code=row['part_code'],detail_sheets=[]))
        local_tables=copy.deepcopy(tables)
        for table in local_tables:
            frame=table.get('coordinate_frame','')
            if frame.startswith('instance:'):
                owner=records.get(frame[9:],{})
                table.update(container_ref=frame[9:],container_name=owner.get('name',''),container_attributes=owner.get('attributes',[]))
        structure=assembly_structure(local_tables,context.get('targets',[]),{e['ref']:e.get('source_sheet_ids',[]) for e in local_tables},known)
    groups=structure.get('assemblies',[])
    selected={g['id'] for g in groups if targets.intersection(g['scope_ids']) or g.get('owner_code') in selected_codes}
    if not selected:selected={g['id'] for g in groups if selected_codes.intersection(g.get('descendant_part_codes',[]))}
    while True:
        expanded=selected|{child for g in groups if g['id'] in selected for child in [*g['child_ids'],*g.get('covered_assembly_ids',[])]}
        if expanded==selected:break
        selected=expanded
    structure['assemblies']=[g for g in groups if g['id'] in selected]
    structure['products']=[p for p in structure.get('products',[]) if selected.intersection(p['assembly_ids'])]
    main_ids={gid for p in structure['products'] for gid in p['main_drawing_candidates']}
    structure['main_drawings']=[{k:g[k] for k in ('id','table_ref','scope_ids','owner_code','product_codes')} for g in groups if g['id'] in main_ids]
    visible_tables={g['table_ref'] for g in structure['assemblies']}
    evidence=context.get('drawing_evidence',{})
    structure['warnings']=[w for w in structure.get('warnings',[]) if w.get('assembly_id') in selected or selected.intersection(w.get('assembly_ids',[]))]
    unresolved.extend(dict(kind='assembly_structure',**w) for w in structure['warnings'])
    unresolved.extend(dict(kind='local_balloon_number',**w) for w in evidence.get('unresolved_number_markers',[]) if visible_tables.intersection(w['table_refs']))
    from rules.mechanical_bom import reading_brief
    result=dict(version=VERSION,source_hash=source,scope_ids=sorted(targets),parts=sorted(parts.values(),key=lambda p:p['id']),
        reading_profile=reading_brief(context,graph),
        assembly_structure=structure,bom_balloon_links=copy.deepcopy([l for l in evidence.get('bom_links',[]) if l['table_ref'] in visible_tables]),
        drawing_rows=copy.deepcopy(graph.get('drawing_rows',{})),
        leader_profile_bindings=copy.deepcopy(context.get('source_features',{}).get('leader_profile_bindings',[])),
        representations=sorted(representations,key=lambda r:r['id']),geometry_owners=owners,
        relationship_observations=relations,unresolved=unresolved,complete_product_coverage=False,
        policy='Source identities and DIM bindings only. Unmapped views remain unresolved. BOM notes, manufacturing stages and measured parameters do not establish an executable contact rule, perspective projection or permission to edit.')
    result['summary']=summary(result)
    from graph.part_map import build as build_part_map
    result['part_map']=build_part_map(context,graph)
    result['summary']['part_map']=result['part_map']['summary']
    from graph.cuboid_projections import inventory as cuboid_inventory
    result['cuboid_projections']=[{k:v for k,v in body.items() if k!='maps'} for body in cuboid_inventory(context)]
    result['summary']['metric_cuboid_count']=len(result['cuboid_projections'])
    from graph.flat_contacts import describe as describe_loose_contacts
    result['loose_planar_relationships']=describe_loose_contacts(context)
    result['summary']['loose_body_count']=len(result['loose_planar_relationships']['bodies'])
    result['summary']['loose_contact_count']=len(result['loose_planar_relationships']['contacts'])
    for contact in result['loose_planar_relationships']['contacts']:
        result['relationship_observations'].append(dict(id='contact-'+identity([source,contact['source_body'],contact['target_body'],contact['axis'],contact['analysis_angle_degrees'],contact['dimension_refs']]),
            source=contact['source_part'],target=contact['target_part'],kind=contact['kind'],source_status='source_closed_faces_2d',
            equation=contact['equation'],source_gap_mm=contact['source_gap_mm'],sheet_ids=contact['sheet_ids'],dimension_refs=contact['dimension_refs'],
            evidence_refs=contact['evidence_refs'],executable=False,
            missing=['Yêu cầu thay đổi, mốc giữ và phạm vi ảnh hưởng 2D cần được giải lại trên nguồn hiện tại.']))
    result['summary']['relationship_observation_count']=len(result['relationship_observations'])
    return result


def summary(model):
    return dict(version=VERSION,source_hash=model['source_hash'],scope_ids=model['scope_ids'],
        part_count=len(model['parts']),measured_representation_count=len(model['representations']),
        part_map=model.get('part_map',{}).get('summary',{}),
        relationship_observation_count=len(model['relationship_observations']),unresolved_count=len(model['unresolved']),
        verified_leader_chain_count=sum(b['status'] in ('verified_endpoint_dimension_chain','verified_interior_dimension_chain') for b in model.get('leader_profile_bindings',[])),
        verified_leader_region_count=sum(b['status'] in ('verified_interior_region','verified_interior_dimension_chain') for b in model.get('leader_profile_bindings',[])),
        assembly_count=sum(g['kind']=='assembly_bom' for g in model.get('assembly_structure',{}).get('assemblies',[])),
        main_drawing_candidate_count=sum(len(p['main_drawing_candidates']) for p in model.get('assembly_structure',{}).get('products',[])),
        unmapped_detail_sheet_count=len({s for p in model['parts'] for s in p['unmapped_detail_sheet_ids']}),
        complete_product_coverage=False,policy=model['policy'])
