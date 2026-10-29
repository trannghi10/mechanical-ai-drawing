"""Compact model views; checked compilation always uses the full source store."""


def bom_view(bom,seed_codes):
    result={k:v for k,v in bom.items() if k not in ('rows','warning','header_labels')}
    rows=[]
    for original in bom['rows']:
        row={k:v for k,v in original.items() if k not in ('cells','processes') and v!=''}
        cells=original.get('cells',{})
        if not seed_codes or row.get('part_code') in seed_codes:
            cell=cells.get('description')
            if cell:row['cells']={'description':dict(cell)}
        rows.append(row)
    result['rows']=rows
    result['deferred_cells']='Only selected description bindings supplied. context_requests=[table ref] retrieves every source cell/binding. Never guess missing cell indexes or mirror refs.'
    return result


def impact_view(original,defer_specs=False):
    graph=dict(original);nodes=[]
    rows=original.get('drawing_rows',{})
    from cad.row_groups import identity_groups
    if rows:graph['drawing_rows']=dict(version=rows['version'],scan=rows.get('scan',{}),groups=[dict(id=g['id'],label=g['label'],kind=g['kind'],sheet_ids=g['sheet_ids'],part_codes=g.get('part_codes',[]),status=g['status']) for g in identity_groups(rows)],
        retrieval='Row/frame annotations are stored in the source document index. Retrieve the identified frame CAD/notes before editing; row membership is not a fit rule.')
    structure=original.get('assembly_structure',{})
    if structure:
        groups=[dict({k:g[k] for k in ('id','table_ref','scope_ids','owner_code','kind','parent_ids','child_ids','covered_assembly_ids','duplicate_numbers','status') if k in g},
                     members=[{k:m[k] for k in ('part_number','part_code','quantity_text') if k in m} for m in g['members']]) for g in structure.get('assemblies',[])]
        ids={g['id'] for g in groups}
        graph['assembly_structure']=dict(version=structure.get('version'),policy=structure.get('policy'),assemblies=groups,
            products=[{k:p[k] for k in ('product_code','domain','main_drawing_candidates','status')} for p in structure.get('products',[]) if ids.intersection(p['assembly_ids'])])
    for node in graph.get('nodes',[]):
        n={k:v for k,v in node.items() if k not in ('bom_occurrences','manufacturing_stages')}
        occurrences=node.get('bom_occurrences',[])
        n['source_specs']=[] if defer_specs else list({(o.get('description',''),o.get('material','')):None for o in occurrences})
        n['bom_occurrences']=[{k:o[k] for k in ('table_ref','part_number','sheet_ids') if k in o} for o in occurrences]
        n['manufacturing_stages']=[{k:s[k] for k in ('sheet_id','source_part_code','evidence_table_ref') if k in s} for s in node.get('manufacturing_stages',[])]
        nodes.append(n)
    graph['nodes']=nodes
    if defer_specs:
        graph['source_specs_deferred']='Selected BOM rows retain descriptions/materials. Related part source_specs are deferred, not empty specifications. context_requests=[bom_occurrences.table_ref] retrieves the exact related BOM descriptions/materials/bindings before changing that part; never infer them from a title.'
        graph['edges']=[]
        for original_edge in original.get('edges',[]):
            edge=dict(original_edge);evidence=edge.get('evidence',[])
            redundant=set()
            if edge.get('kind')=='assembly_bom':
                for item in evidence:
                    if all(k in item for k in ('sheet_id','table_ref','part_number')):
                        redundant.add((item['sheet_id'],f"Bảng kê {item['table_ref']}: chi tiết {item['part_number']} thuộc cụm {edge['target']}"))
            edge['evidence']=[item for item in evidence if (item.get('sheet_id'),item.get('note')) not in redundant]
            graph['edges'].append(edge)
        graph['assembly_note_encoding']='For assembly_bom, the generated note Bảng kê TABLE: chi tiết NUMBER thuộc cụm TARGET is represented by its exact structured sheet_id/table_ref/part_number evidence plus edge target; other source notes remain literal.'
    graph['process_groups']=[dict(g,members=[{k:m[k] for k in ('part_code','part_number','process_text') if k in m} for m in g['members']]) for g in graph.get('process_groups',[])]
    graph['stage_link_policy']='Manufacturing stage links require each view to be measured independently; matching specifications do not prove identical geometry or contact rules.'
    graph['packaging_groups']=[{k:g[k] for k in ('product_code','sheet_ids','package_codes','status') if k in g} for g in graph.get('packaging_groups',[])]
    if graph['packaging_groups']:graph['packaging_policy']='Exact product code and packaging purpose establish review scope only. Retrieve carton/pad/pallet geometry, source packing orientation and clearances before resizing; do not infer a fit from title dimensions.'
    return graph


def evidence_view(original,visible_refs,table_refs):
    links=[]
    for link in original.get('bom_links',[]):
        if link.get('table_ref') not in table_refs:continue
        item=dict(link)
        item['code_evidence_refs']=[r for r in link.get('code_evidence_refs',[]) if r in visible_refs]
        item['number_markers']=[m for m in link.get('number_markers',[]) if m['number_text_ref'] in visible_refs and m['circle_ref'] in visible_refs]
        links.append(item)
    return dict(bom_links=links,instruction=original.get('instruction',''),
                deferred_evidence='Other frames remain source-scoped and retrievable by geometry_queries; no geometric ownership is inferred from this subset.')


def pack_focused_metadata(context):
    """Encode repeated metadata as named column tables, with no ref guessing."""
    result=dict(context)
    result['metadata_encoding']='cad_metadata_tables_v1: zip each *_rows row with *_columns. BOM description bindings are [cell_index,mirror_ref,raw_text,storage]. null raw_text means exactly description; a two-string raw_text array [prefix,suffix] means prefix + description + suffix, with no added spaces. These tables are source metadata, never editable synthetic entities.'
    result['targets']=[{k:t[k] for k in ('id','kind','layout') if k in t} for t in context['targets']]
    result.pop('scope_links',None)
    entities=[]
    for original in context['entities']:
        record=dict(original);bom=record.get('bom')
        if record.get('source_sheet_ids')==context.get('root_target_ids'):
            record.pop('source_sheet_ids',None)
        if bom and 'deferred_cells' in bom:
            b={k:v for k,v in bom.items() if k!='rows'}
            b['row_columns']=['part_number','part_code','description','material','quantity_text','notes','description_binding']
            b['row_values']=[]
            for row in bom['rows']:
                cell=row.get('cells',{}).get('description');binding=None
                if cell:
                    raw=cell.get('raw_text');encoded_raw=raw if raw!=row['description'] else None
                    description=row['description']
                    if encoded_raw and description and raw.count(description)==1:
                        prefix,suffix=raw.split(description)
                        encoded_raw=[prefix,suffix]
                    binding=[cell['index'],cell.get('mirror_ref'),encoded_raw,cell.get('storage','native')]
                b['row_values'].append([row.get(k,'') for k in b['row_columns'][:-1]]+[binding])
            record['bom']=b
        entities.append(record)
    result['entities']=entities
    graph=context.get('part_graph')
    if graph:
        g={k:v for k,v in graph.items() if k not in ('nodes','edges','process_groups')}
        g['part_columns']=['code','source_specs','detail_sheets','bom_occurrences','manufacturing_stages','definition_conflict']
        g['part_symbols']=[n['code'] for n in graph['nodes']]
        code_index={code:i for i,code in enumerate(g['part_symbols'])}
        g['part_rows']=[[n['code'],n.get('source_specs',[]),n.get('detail_sheets',[]),
            [[o.get('table_ref'),o.get('part_number'),o.get('sheet_ids',[])] for o in n.get('bom_occurrences',[])],
            [[s.get('sheet_id'),s.get('source_part_code'),s.get('evidence_table_ref')] for s in n.get('manufacturing_stages',[])],
            n.get('definition_conflict',False)] for n in graph['nodes']]
        g['part_nested_columns']={'source_specs':['description','material'],'bom_occurrences':['table_ref','part_number','sheet_ids'],
                                  'manufacturing_stages':['sheet_id','source_part_code','evidence_table_ref']}
        g['edge_columns']=['source','target','kind','status','evidence']
        g['edge_rows']=[[code_index[e['source']],code_index[e['target']],e.get('kind'),e.get('status'),e.get('evidence')] for e in graph.get('edges',[])]
        g['process_columns']=['id','stage_id','label','table_ref','sheet_ids','members','assembly_references']
        g['member_columns']=['part_code','part_number','process_text']
        g['process_rows']=[[p.get('id'),p.get('stage_id'),p.get('label'),p.get('table_ref'),p.get('sheet_ids',[]),
                           [[code_index.get(m['part_code'],m['part_code']),m.get('part_number'),m.get('process_text')] for m in p['members']],p.get('assembly_references',[])] for p in graph.get('process_groups',[])]
        g['part_index_encoding']='Integer source/target in edge_rows and part_code in process members index part_symbols. Decode to the actual code before proposing edits/dependencies.'
        result['part_graph']=g
    evidence=context.get('drawing_evidence',{})
    result['drawing_evidence']={'columns':['table_ref','part_number','part_code','code_evidence_refs','number_markers'],
        'rows':[[link.get('table_ref'),link.get('part_number'),link.get('part_code'),link.get('code_evidence_refs',[]),
                 [[m['number_text_ref'],m['circle_ref'],m.get('leader_refs',[])] for m in link.get('number_markers',[])]] for link in evidence.get('bom_links',[])],
        'marker_columns':['number_text_ref','circle_ref','leader_refs'],'status':'source_candidates_not_geometry_ownership'}
    discovery=dict(context.get('geometry_discovery',{}))
    scopes=discovery.pop('scopes',[])
    kinds=sorted({k for s in scopes for k in s['types']})
    discovery['scope_columns']=['target_id',*kinds]
    discovery['scope_rows']=[[s['target_id'],*[s['types'].get(k,0) for k in kinds]] for s in scopes]
    result['geometry_discovery']=discovery
    return result
