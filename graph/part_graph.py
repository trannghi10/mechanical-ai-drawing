"""Document-wide part identities and source-backed relationship observations.

A BOM association or a note is not an executable engineering constraint.
"""
import re
from collections import defaultdict,deque
from bom.reader import plain,normalized,requested_numbers,part_number_key


def assembly_structure(tables,sheets,table_sheets,parts):
    """BOM membership/hierarchy is source identity, never a contact equation."""
    from cad.part_identity import identity
    try:
        import networkx as nx
    except ImportError:
        import graph.simple_graph as nx
    by_sheet={s['id']:s for s in sheets};groups=[];warnings=[]
    from bom.stage_links import material_input_tables
    inputs=material_input_tables(tables,sheets,table_sheets,parts)
    for table in tables:
        if table.get('bom',{}).get('status')!='verified_template':continue
        rows=table['bom']['rows'];members=[];numbers=defaultdict(set)
        for row in rows:
            code=row.get('part_code','').strip();number=plain(row.get('part_number',''))
            if not code or not number:continue
            members.append(dict(part_number=number,part_code=code,quantity_text=row.get('quantity_text',''),
                                description=row.get('description',''),material=row.get('material','')))
            numbers[part_number_key(number)].add(code)
        if not members:continue
        scopes=sorted(table_sheets.get(table['ref'],[]));codes={m['part_code'] for m in members}
        titles=[plain(t) for sid in scopes for t in by_sheet[sid].get('texts',[])]
        owners={code for code,n in parts.items() if set(scopes).intersection(n.get('detail_sheets',[])) and code not in codes}
        owners.update(t.split(':',1)[1].strip() for t in titles if ':' in t and
                      normalized(t.split(':',1)[0]) in ('ma btp','ma cum','ma chi tiet','assembly code','part code')
                      and t.split(':',1)[1].strip() in parts and t.split(':',1)[1].strip() not in codes)
        native=identity(table.get('container_name',''),table.get('container_attributes',[]),parts)
        # The placed CAD container has stronger identity than a broad frame.
        if native and native not in codes:owners={native}
        products={t for t in titles if re.fullmatch(r'9\.\d+\.\d+',t) and t not in parts}
        products.update(str(by_sheet[sid]['product_code']).strip() for sid in scopes if by_sheet[sid].get('product_code'))
        products.update(t.split(':',1)[1].strip() for t in titles if ':' in t and
                        normalized(t.split(':',1)[0]) in ('ma tp','ma san pham','product code','product id')
                        and re.fullmatch(r'[\w./-]+',t.split(':',1)[1].strip()))
        packaging=any(re.fullmatch(r'(?:ban ve\s+)?dong goi',normalized(t))
                      for sid in scopes for t in by_sheet[sid].get('texts',[]))
        duplicates=sorted(n for n in numbers if sum(part_number_key(m['part_number'])==n for m in members)>1)
        group=dict(id='assembly:'+table['ref'],table_ref=table['ref'],layout=table.get('layout'),scope_ids=scopes,
            instance_ref=table.get('container_ref'),kind='material_bom' if table['ref'] in inputs else 'assembly_bom' if len(members)>=2 else 'part_bom',
            owner_code=next(iter(owners)) if len(owners)==1 else None,owner_candidates=sorted(owners),
            product_codes=sorted(products),domain='packaging' if packaging else 'product',members=members,
            number_index={n:dict(part_codes=sorted(v),status='unique' if len(v)==1 and n not in duplicates else 'ambiguous') for n,v in numbers.items()},
            duplicate_numbers=duplicates,parent_ids=[],child_ids=[],covered_assembly_ids=[],equivalent_bom_ids=[],status='bom_membership_only',executable=False)
        if duplicates:warnings.append(dict(assembly_id=group['id'],code='duplicate_local_number',numbers=duplicates))
        if len(owners)>1:warnings.append(dict(assembly_id=group['id'],code='assembly_owner_ambiguous',part_codes=sorted(owners)))
        groups.append(group)
    by={g['id']:g for g in groups};hierarchy=nx.DiGraph();hierarchy.add_nodes_from(by)
    for parent in groups:
        for child in groups:
            owner=child['owner_code']
            if parent is child or child['kind']!='assembly_bom' or not owner:continue
            if parent['domain']!=child['domain']:continue
            if parent['product_codes'] and child['product_codes'] and not set(parent['product_codes']).intersection(child['product_codes']):continue
            if any(m['part_code']==owner for m in parent['members']):
                hierarchy.add_edge(parent['id'],child['id'])
    cyclic=set().union(*(c for c in nx.strongly_connected_components(hierarchy) if len(c)>1)) if groups else set()
    if cyclic:warnings.append(dict(code='assembly_hierarchy_cycle',assembly_ids=sorted(cyclic)))
    for group in groups:
        gid=group['id'];descendants=nx.descendants(hierarchy,gid)|{gid}
        group['parent_ids']=sorted(hierarchy.predecessors(gid));group['child_ids']=sorted(hierarchy.successors(gid))
        group['descendant_part_codes']=sorted({m['part_code'] for d in descendants for m in by[d]['members']})
        if descendants.intersection(cyclic):group['status']='hierarchy_cycle_unresolved'
    # A broadest BOM is a main-drawing candidate, not a production approval.
    buckets=defaultdict(list)
    for group in groups:
        if len(group['product_codes'])==1:key=(group['domain'],group['product_codes'][0])
        else:
            connected=nx.node_connected_component(hierarchy.to_undirected(),group['id'])
            key=(group['domain'],'unidentified:'+min(connected))
        buckets[key].append(group)
    products=[]
    for (domain,product),items in sorted(buckets.items()):
        owners={g['owner_code'] for g in items if g['kind']=='assembly_bom' and g['owner_code']}
        required={m['part_code'] for g in items if g['kind']!='material_bom' for m in g['members']}-owners
        for group in items:
            group['leaf_part_codes']=sorted(set(group['descendant_part_codes'])-owners) if group['kind']!='material_bom' else []
        for parent in items:
            if parent['status']=='hierarchy_cycle_unresolved' or parent['duplicate_numbers']:continue
            for child in items:
                if child is parent or child['kind']!='assembly_bom' or child['status']=='hierarchy_cycle_unresolved' or child['duplicate_numbers']:continue
                a=set(parent['leaf_part_codes']);b=set(child['leaf_part_codes'])
                if b and b<a:parent['covered_assembly_ids'].append(child['id'])
                elif a and a==b:parent['equivalent_bom_ids'].append(child['id'])
            parent['covered_assembly_ids'].sort();parent['equivalent_bom_ids'].sort()
        candidates=[g['id'] for g in items if g['kind']=='assembly_bom' and not g['duplicate_numbers']
                    and g['status']!='hierarchy_cycle_unresolved' and required<=set(g['descendant_part_codes'])-owners]
        products.append(dict(product_code=None if product.startswith('unidentified:') else product,domain=domain,
            assembly_ids=sorted(g['id'] for g in items),leaf_part_codes=sorted(required),
            main_drawing_candidates=sorted(candidates),status='main_candidate' if len(candidates)==1 else 'ambiguous_main' if candidates else 'main_unresolved'))
    return dict(version=4,assemblies=groups,products=products,warnings=warnings,material_inputs=list(inputs.values()),
        policy='STT is local to table and placed scope. BOM membership/hierarchy locates review candidates; it does not prove contact, anchors, numeric constraints or official drawing approval.')


def build_part_graph(tables,sheets):
    parts={};table_sheets={};sheet_parts=defaultdict(set);warnings=[]
    for table in tables:
        anchor=table.get('position',[])
        parents=[s['id'] for s in sheets if s.get('layout')==table.get('layout') and s.get('bbox') and len(anchor)>=2 and
                 s['bbox'][0]-1e-6<=anchor[0]<=s['bbox'][2]+1e-6 and s['bbox'][1]-1e-6<=anchor[1]<=s['bbox'][3]+1e-6]
        if table.get('type')=='GRAPHIC_TABLE':parents=[sid for sid in parents if sid in table.get('source_sheet_ids',[])]
        table_sheets[table['ref']]=parents
        bom=table.get('bom',{})
        if bom.get('status')!='verified_template':
            warnings.append({'table_ref':table['ref'],'message':'Bảng chưa giải mã chắc chắn; không suy liên kết chi tiết.'});continue
        for row in bom['rows']:
            code=row['part_code'].strip()
            node=parts.setdefault(code,{'id':code,'code':code,'bom_occurrences':[],'detail_sheets':[],
                                       'geometry_ownership':'unverified','definition_conflict':False})
            cells=row.get('cells',{})
            node['bom_occurrences'].append({'table_ref':table['ref'],'part_number':row['part_number'],
                                           'description':row.get('description',''),'material':row.get('material',''),
                                           'source_kind':bom.get('source_kind','native_table'),'description_cell':cells.get('description',{}),
                                           'sheet_ids':parents,'evidence_refs':[c['mirror_ref'] for c in cells.values() if c.get('mirror_ref')]})
            for parent in parents:sheet_parts[parent].add(code)
    product_codes={s['id']:{plain(t) for t in s.get('texts',[]) if re.fullmatch(r'9\.\d+\.\d+',plain(t)) and plain(t) not in parts} for s in sheets}
    materials={normalized(o['material']) for node in parts.values() for o in node['bom_occurrences'] if o['material'].strip()}
    sheet_materials={s['id']:{normalized(t) for t in s.get('texts',[])}&materials for s in sheets}
    product_tables=defaultdict(set)
    for table in tables:
        if table.get('bom',{}).get('status')!='verified_template':continue
        for parent in table_sheets[table['ref']]:
            for product in product_codes.get(parent,set()):product_tables[product].add(table['ref'])
    def sheet_matched_codes(sheet):
        matched = set()
        tokens = {plain(t) for t in sheet.get('texts', [])} | {plain(c) for c in sheet.get('source_codes', [])}
        for token in tokens:
            if not token: continue
            if token in parts:
                matched.add(token)
            if re.fullmatch(r'\d+(?:\.\d+){3,}', token):
                pfx = token.rsplit('.', 1)[0]
                if pfx in parts:
                    matched.add(pfx)
            if '-' in token or '_' in token:
                base = re.split(r'[-_]', token)[0]
                if base in parts:
                    matched.add(base)
            for code in parts:
                if code not in matched:
                    if re.search(r'(?<![\w.])' + re.escape(code) + r'(?:\.[0-9a-zA-Z]+)?(?![\w.])', token):
                        matched.add(code)
        for code in parts:
            if re.fullmatch(r'\d+(?:\.\d+){3,}', code):
                if code.rsplit('.', 1)[0] in tokens:
                    matched.add(code)
        return matched
    for sheet in sheets:
        # A BOM sheet displays many codes; it is not ownership proof for detail geometry.
        matched = sheet_matched_codes(sheet)
        if sheet['id'] in sheet_parts:
            # A distinct assembly code in the frame title can own the BOM;
            # the BOM members themselves never own its assembly geometry.
            owners = (matched & set(parts)) - sheet_parts[sheet['id']]
            if len(owners) == 1:
                owner = next(iter(owners))
                if sheet['id'] not in parts[owner]['detail_sheets']:
                    parts[owner]['detail_sheets'].append(sheet['id'])
            continue
        for code in matched:
            if sheet['id'] not in parts[code]['detail_sheets']:
                parts[code]['detail_sheets'].append(sheet['id'])
    from bom.stage_links import stage_links
    routes=stage_links(parts,sheets)
    for route in routes:
        node=parts[route['bom_part_code']]
        node['detail_sheets'].append(route['sheet_id'])
        node.setdefault('manufacturing_stages',[]).append(route)
    edges=[];seen=set()
    patterns=[('fit',r'(?:vua khit|lap vua|lap khit|lap lot|lot vua)\s*(?:voi|vao|trong)?\s*(?:chi tiet\s*)?(?:so\s*)?([a-z0-9][a-z0-9._/-]*)(?![\w.])'),
              ('weld',r'han\s+(?:voi|vao)\s+(?:chi tiet\s*)?(?:so\s*)?([a-z0-9][a-z0-9._/-]*)(?![\w.])'),
              ('connection',r'(?:lap|gan|bat vit|bat bu\s*long)\s+(?:voi|vao|tren)\s+(?:chi tiet\s*)?(?:so\s*)?([a-z0-9][a-z0-9._/-]*)(?![\w.])')]
    def numbered_codes(number,sheet_id,owners):
        # Balloon numbers are local to a BOM. A detail inherits only BOMs that
        # actually contain its code; unrelated products never share this lookup.
        refs={o['table_ref'] for owner in owners for o in parts[owner]['bom_occurrences']}
        local={t['ref'] for t in tables if sheet_id in table_sheets[t['ref']] and t.get('bom',{}).get('status')=='verified_template'}
        relevant=local or refs
        if not relevant and len(product_codes.get(sheet_id,set()))==1:
            # Repeated BOMs may provide the same unique mapping. A conflict
            # between revisions/products still leaves the number unresolved.
            relevant=product_tables[next(iter(product_codes[sheet_id]))]
            if sheet_materials[sheet_id]:
                # A product can have separate metal and packaging BOMs with
                # the same balloon numbers. An explicit material label on
                # both frames narrows inheritance; never use proximity alone.
                relevant={ref for ref in relevant if any(sheet_materials[sheet_id]&sheet_materials[parent] for parent in table_sheets[ref])}
        return {code for code,node in parts.items() for o in node['bom_occurrences']
                if o['table_ref'] in relevant and o['part_number']==number}
    def add(source,target,kind,sheet,text,extra_evidence=()):
        if source==target:return
        key=(source,target,kind,sheet['id'],plain(text))
        if key in seen:return
        seen.add(key)
        edges.append({'id':'relation-'+str(len(edges)+1),'source':source,'target':target,'kind':kind,
                      'status':'source_note_rule_missing','executable':False,
                      'evidence':[{'sheet_id':sheet['id'],'note':plain(text)},*extra_evidence],
                      'missing':['geometry ownership','contact/anchor mapping','numeric design rule']})
    from bom.stage_links import material_input_tables
    material_inputs=material_input_tables(tables,sheets,table_sheets,parts)
    for sheet in sheets:
        if sheet['id'] not in sheet_parts:continue
        owners={code for code,node in parts.items() if sheet['id'] in node['detail_sheets']}
        non_member_owners = owners - sheet_parts.get(sheet['id'], set())
        if len(non_member_owners) == 1:
            owner = next(iter(non_member_owners))
        elif len(owners) == 1:
            owner = next(iter(owners))
        else:
            continue
        for table in tables:
            if sheet['id'] not in table_sheets[table['ref']] or table.get('bom',{}).get('status')!='verified_template':continue
            for row in table['bom']['rows']:
                relation='manufacturing_input' if material_inputs.get(table['ref'],{}).get('owner_code')==owner else 'assembly_bom'
                note=(f"Bảng kê nguyên liệu {table['ref']}: nguồn {row['part_number']} cấp phôi cho chi tiết {owner}" if relation=='manufacturing_input'
                      else f"Bảng kê {table['ref']}: chi tiết {row['part_number']} thuộc cụm {owner}")
                add(row['part_code'].strip(),owner,relation,sheet,
                    note,
                    [dict(sheet_id=sheet['id'],table_ref=table['ref'],part_number=row['part_number'])])
                if relation=='manufacturing_input' and edges and edges[-1]['source']==row['part_code'].strip() and edges[-1]['target']==owner:
                    edges[-1]['status']='source_material_input'
                    edges[-1]['missing']=['stock specification, single-blank capacity and source quantity check']
                    edges[-1]['evidence'].extend(dict(sheet_id=sheet['id'],note=label) for label in material_inputs[table['ref']]['source_headings'])
    assemblies=defaultdict(list)
    for sheet in sheets:
        owners={code for code,node in parts.items() if sheet['id'] in node['detail_sheets']}
        for text in sheet.get('texts',[]):
            note=normalized(text)
            # Explicit assembly instruction, e.g. "Hàn chi tiết số 2, 6 vào
            # chi tiết số 3". Resolve both sides against this assembly's BOM.
            assembly=r'(han|lap|gan)\s+chi tiet\s*(?:so\s*)?(\d+(?:\s*(?:,|va|&)\s*\d+)*)\s+(?:vao|voi|tren)\s+chi tiet\s*(?:so\s*)?(\d+)\b'
            for match in re.finditer(assembly,note):
                target_codes=numbered_codes(match.group(3),sheet['id'],owners)
                source_sets=[numbered_codes(n,sheet['id'],owners) for n in re.findall(r'\d+',match.group(2))]
                if len(target_codes)!=1 or any(len(c)!=1 for c in source_sets):
                    warnings.append({'sheet_id':sheet['id'],'message':'Số chi tiết trong ghi chú không có BOM duy nhất.', 'note':plain(text)});continue
                for codes in source_sets:add(next(iter(codes)),next(iter(target_codes)),'weld' if match.group(1)=='han' else 'connection',sheet,text)
                labels=[m.group(1).upper() for t in sheet.get('texts',[]) for m in [re.fullmatch(r'yckt\s*1\s*:\s*([a-z]\w*)',normalized(t))] if m]
                labels+=sheet.get('source_row_labels',[])
                members=set(target_codes).union(*source_sets)
                if len(product_codes.get(sheet['id'],set()))==1:
                    product=next(iter(product_codes[sheet['id']]))
                    for label in labels:assemblies[(product,label)].append((members,dict(sheet_id=sheet['id'],note=plain(text))))
            for kind,pattern in patterns:
                for match in re.finditer(pattern,note):
                    code=match.group(1).rstrip('.')
                    targets=numbered_codes(code,sheet['id'],owners) if code.isdigit() else aliases.get(code,set())
                    if len(owners)!=1 or len(targets)!=1:
                        warnings.append({'sheet_id':sheet['id'],'message':'Ghi chú liên kết có mã/chủ thể mơ hồ; cần đối chiếu hình.', 'note':plain(text)});continue
                    source=next(iter(targets));target=next(iter(owners))
                    add(source,target,kind,sheet,text)
    for sheet in sheets:
        if len(product_codes.get(sheet['id'],set()))!=1:continue
        product=next(iter(product_codes[sheet['id']]))
        for text in sheet.get('texts',[]):
            for match in re.finditer(r'(han|lap|gan)\s+cum\s+([a-z]\w*)\s+(?:vao|voi|tren)\s+chi tiet\s*(?:so\s*)?(\d+)\b',normalized(text)):
                candidates=assemblies.get((product,match.group(2).upper()),[])
                definitions={tuple(sorted(members)) for members,_ in candidates}
                target=numbered_codes(match.group(3),sheet['id'],set())
                if len(definitions)!=1 or len(target)!=1:
                    warnings.append(dict(sheet_id=sheet['id'],note=plain(text),message='Cụm lắp không có thành viên/BOM duy nhất.'));continue
                evidence=[e for _,e in candidates]
                for source in next(iter(definitions)):add(source,next(iter(target)),'weld' if match.group(1)=='han' else 'connection',sheet,text,evidence)
    for node in parts.values():
        def _base_desc(text):
            return re.sub(r'\(.*?\)', '', normalized(text)).strip()
        base_descs = {_base_desc(o.get('description', '')) for o in node['bom_occurrences'] if _base_desc(o.get('description', ''))}
        node['definition_conflict'] = len(base_descs) > 1
        node['detail_sheets'] = sorted(set(node['detail_sheets']))
    from bom.processes import process_groups
    groups=process_groups(tables,table_sheets)
    # A shared product retrieves review views. Explicit numbered notes can be
    # mapped through consistent BOMs above; contact surfaces remain unverified.
    for group in groups:
        products=set().union(*(product_codes.get(s,set()) for s in group['sheet_ids']))
        references=[]
        for sheet in sheets:
            if not products.intersection(product_codes[sheet['id']]):continue
            notes=[plain(t) for t in sheet.get('texts',[]) if re.search(r'(?:han|lap|gan)\s+(?:chi tiet|cum)|han bas bit',normalized(t))]
            if notes:
                mapped=any(any(e['sheet_id']==sheet['id'] for e in edge['evidence']) for edge in edges)
                references.append(dict(sheet_id=sheet['id'],notes=notes,status='review_only_contact_unverified' if mapped else 'review_only_numbers_unmapped'))
        group['assembly_references']=references
    from bom.continuations import continuation_links
    continuations=continuation_links(tables,sheets,table_sheets)
    from bom.packaging import groups as packaging_groups
    structure=assembly_structure(tables,sheets,table_sheets,parts)
    return {'version':11,'nodes':list(parts.values()),'edges':edges,'process_groups':groups,'warnings':warnings,
            'material_inputs':list(material_inputs.values()),
            'assembly_structure':structure,
            'bom_continuations':continuations,
            'packaging_groups':packaging_groups(parts,sheets,table_sheets),
            'policy':'Graph observations locate affected parts. They never authorize coordinates or manufacture changes without verified constraints.'}


def impact_graph(graph,seed_codes):
    """Mechanical influence is bidirectional; stock provenance has typed flow."""
    nodes={n['id']:n for n in graph['nodes']};seeds=set(seed_codes)&set(nodes)
    adjacency=defaultdict(set)
    for edge in graph['edges']:
        adjacency[edge['source']].add(edge['target'])
        if edge['kind'] != 'manufacturing_input':adjacency[edge['target']].add(edge['source'])
    # Co-process membership is a review scope, not a mechanical edge. It does
    # not authorize scaling every laser-cut part or merging unrelated products.
    groups=[g for g in graph.get('process_groups',[]) if any(m['part_code'] in seeds for m in g['members'])]
    process_codes={m['part_code'] for group in groups for m in group['members']}
    reached=set(seeds)|process_codes;queue=deque(sorted(reached));paths={code:[] for code in reached}
    while queue:
        code=queue.popleft()
        for target in sorted(adjacency[code]):
            if target in reached:continue
            reached.add(target);queue.append(target);paths[target]=paths[code]+[code]
    # An unchanged stock code shared by several parts is provenance, not a
    # mechanical connection between those parts. Still retrieve its source BOM.
    inputs={edge['source'] for edge in graph['edges'] if edge['kind']=='manufacturing_input' and edge['target'] in reached}
    for code in inputs-reached:paths[code]=[]
    reached.update(inputs)
    incident={code for edge in graph['edges'] if edge['source'] in reached and edge['target'] in reached for code in (edge['source'],edge['target'])}
    packaging=[g for g in graph.get('packaging_groups',[]) if reached.intersection(g['product_part_codes'])]
    packing_codes={c for g in packaging for c in g['package_codes']} & nodes.keys()
    structure=graph.get('assembly_structure',{});assemblies=structure.get('assemblies',[])
    review=[g for g in assemblies if g.get('owner_code') in reached or
            g.get('kind')!='material_bom' and reached.intersection(g.get('descendant_part_codes',[]))]
    review_codes={c for g in review for c in g.get('descendant_part_codes',[])}&nodes.keys()
    return {**{k:graph[k] for k in ('source_hash','document_id','detection_hash','version') if k in graph},
            'seed_codes':sorted(seeds),'nodes':[nodes[k] for k in sorted(reached|packing_codes|review_codes)],
            'assembly_structure':dict(structure,assemblies=review),
            'assembly_candidate_codes':sorted(review_codes-reached),
            'edges':[e for e in graph['edges'] if e['source'] in reached and e['target'] in reached],
            'affected_codes':sorted(((reached-process_codes)|incident)-seeds),'impact_paths':paths,
            'process_groups':groups,'process_candidate_codes':sorted(process_codes-seeds),
            'packaging_groups':packaging,'drawing_rows':graph.get('drawing_rows',{}),
            'bom_continuations':graph.get('bom_continuations',{}),
            'confirmed_representation_links':[r for r in graph.get('confirmed_representation_links',[]) if r['part_code'] in reached|packing_codes|review_codes],
            'material_inputs':[r for r in graph.get('material_inputs',[]) if r['owner_code'] in reached],
            'warnings':graph.get('warnings',[]),'policy':graph['policy']}


def seed_codes(context,request,graph=None):
    tables=[e for e in context['entities'] if e.get('bom',{}).get('status')=='verified_template']
    roots=set(context.get('root_target_ids',[]))
    if roots:
        local=[e for e in tables if roots.intersection(e.get('source_sheet_ids',[]))]
        if local:tables=local
    rows=[row for e in tables for row in e['bom']['rows']]
    if not rows and graph:
        inherited={ref for t in context.get('targets',[]) for ref in graph.get('bom_continuations',{}).get(t['id'],{}).get('table_refs',[])}
        rows=[dict(part_code=n['code'],part_number=o['part_number'],description=o.get('description',''))
              for n in graph['nodes'] for o in n['bom_occurrences'] if o.get('table_ref') in inherited]
    from cad.part_identity import record_identity
    known={n['code'] for n in graph['nodes']} if graph else {r['part_code'].strip() for r in rows}
    native_codes={code for e in context['entities'] for code in [record_identity(e,known)] if code}
    text=normalized(request)
    # An overall product dimension has no balloon number. Review the whole
    # selected product BOM, including nested assemblies, rather than seeding
    # only the separate material clause and omitting finished/painted frames.
    if re.search(r'chieu\s+(?:cao|rong|dai)\s+(?:tong\s+the(?:\s+san\s+pham)?|san\s+pham)\b',text):
        products={plain(t) for target in context.get('targets',[]) for t in target.get('texts',[])
                  if re.fullmatch(r'9\.\d+\.\d+',plain(t)) and plain(t) not in known}
        if len(products)==1 and rows:return {r['part_code'].strip() for r in rows}
        return set()
    # A global material instruction must seed every matching row in this BOM,
    # rather than requiring the user to repeat each part code separately.
    if re.search(r'\b(?:tat ca|toan bo)\b',text) and 'sat tam' in text and re.search(r'cat\s+la[sz]er',text):
        clause=text[text.index('sat tam'):]
        change=re.search(r'(\d+(?:[.,]\d+)?)\s*(?:mm\s*)?(?:thanh|xuong|sang|->)\s*(\d+(?:[.,]\d+)?)',clause)
        if change:
            before=float(change.group(1).replace(',','.'))
            from bom.processes import process_tags
            matches=[]
            for row in rows:
                material=re.search(r'sat tam\s*(\d+(?:[.,]\d+)?)\s*[x×]',normalized(row['description']))
                if material and float(material.group(1).replace(',','.'))==before and any(t['id']=='cut_laser' for t in process_tags(row['description'])):
                    matches.append(row['part_code'].strip())
            if matches:return set(matches)
    # A dotted part code after "chi tiết" is not a balloon number. Treating
    # 8.1.05417.258 as STT 8 redirected the request to a different BOM row.
    numbers=list(dict.fromkeys(part_number_key(n) for n in requested_numbers(request)))
    exact={c for c in known if re.search(r'(?<![\w.])'+re.escape(c)+r'(?![\w.])',request)}
    if exact:
        if numbers and graph:
            matched={n['code'] for n in graph['nodes'] if any(part_number_key(o['part_number']) in numbers for o in n['bom_occurrences'])}
            if not exact<=matched:return set()
        return exact
    if len(numbers)>1:return set()
    if numbers:
        number=numbers[0]
        codes={r['part_code'].strip() for r in rows if part_number_key(r['part_number'])==number}
        # Repeated balloon numbers across assemblies are deliberately not merged.
        if codes:return codes if len(codes)==1 else set()
        # Selecting a detail sheet must still reach its assembly BOM. The
        # number in the request must belong to its exact, source-owned code.
        if graph:
            targets={t['id'] for t in context.get('targets',[])}
            owned={n['code'] for n in graph['nodes'] if targets.intersection(n['detail_sheets'])
                   or n['code'] in native_codes}
            owned={n['code'] for n in graph['nodes'] if n['code'] in owned
                   and any(part_number_key(o['part_number'])==number for o in n['bom_occurrences'])}
            if len(owned)==1:return owned
            doc_matched={n['code'] for n in graph['nodes'] if any(part_number_key(o['part_number'])==number for o in n['bom_occurrences'])}
            if len(doc_matched)==1:return doc_matched
        return set()
    codes={r['part_code'].strip() for r in rows if re.search(r'(?<![\w.])'+re.escape(r['part_code'].strip())+r'(?![\w.])',request)}
    mentioned={c for c in known if re.search(r'(?<![\w.])'+re.escape(c)+r'(?![\w.])',request)}
    explicit_code=bool(re.search(r'\bma\b',text))
    if not codes and explicit_code and not mentioned:return set()
    if not codes and not explicit_code and not mentioned:
        from backend.services.tube_planner import specification_codes
        specified=specification_codes(rows,request)
        if specified is not None:return specified
        desc_matches = set()
        for r in rows:
            desc = normalized(r.get('description', ''))
            name = desc.split('(')[0].split('-')[0].strip()
            clean_name = re.sub(r'\b\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)*\b', '', name).strip()
            words = [w for w in clean_name.split() if len(w) > 1]
            if clean_name and len(clean_name) >= 4 and (clean_name in text or (words and all(w in text for w in words))):
                desc_matches.add(r['part_code'].strip())
        if len(desc_matches) == 1:return desc_matches
        if graph:
            doc_desc_matches = set()
            for n in graph['nodes']:
                for o in n.get('bom_occurrences', []):
                    desc = normalized(o.get('description', ''))
                    name = desc.split('(')[0].split('-')[0].strip()
                    clean_name = re.sub(r'\b\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)*\b', '', name).strip()
                    words = [w for w in clean_name.split() if len(w) > 1]
                    if clean_name and len(clean_name) >= 4 and (clean_name in text or (words and all(w in text for w in words))):
                        doc_desc_matches.add(n['code'])
            if len(doc_desc_matches) == 1:return doc_desc_matches
    if not codes and graph:
        targets={t['id'] for t in context.get('targets',[])}
        owned={n['code'] for n in graph['nodes'] if targets.intersection(n['detail_sheets']) or n['code'] in native_codes}
        explicit={c for c in owned if re.search(r'(?<![\w.])'+re.escape(c)+r'(?![\w.])',request)}
        return explicit or (owned if len(owned)==1 and not mentioned and not explicit_code else set())
    return codes
