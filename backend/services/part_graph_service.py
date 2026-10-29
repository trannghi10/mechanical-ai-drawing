"""Persistent per-document graph; uses existing detection, never changes it."""
import json
from cad.catalog import load_document,CAD_LOCK
from cad.edit_engine import digest
from cad.table_data import table_cells
from cad.table_bindings import bind_cells
from bom.reader import read_bom
from graph.part_graph import build_part_graph
from backend.services import catalog_service as storage

GRAPH_VERSION=35


def bind_row_members(rows,nodes,continuations=None):
    from cad.row_groups import identity_groups
    from bom.reader import part_number_key
    for group in identity_groups(rows):
        ids=set(group['sheet_ids'])
        group['part_codes']=sorted(n['code'] for n in nodes if ids.intersection(n['detail_sheets']) or
                                   any(ids.intersection(o['sheet_ids']) for o in n['bom_occurrences']))
        group['bom_bindings']=[dict(part_code=n['code'],part_number=o['part_number'],table_ref=o['table_ref'],sheet_ids=o['sheet_ids'])
            for n in nodes if n['code'] in group['part_codes'] for o in n['bom_occurrences']
            if o['part_number'].upper()==group['label']]
        group['marker_bindings']=[]
        for marker in group['markers']:
            direct=[];same_row=[];continued=[]
            inherited={ref for sid in marker['sheet_ids'] for link in [(continuations or {}).get(sid,{})]
                if link.get('status')=='explicit_numbered_drawing_series' for ref in link['table_refs']}
            for node in nodes:
                for occurrence in node['bom_occurrences']:
                    if part_number_key(occurrence['part_number'])!=part_number_key(marker['label']):continue
                    binding=dict(part_code=node['code'],table_ref=occurrence['table_ref'])
                    if set(marker['sheet_ids']).intersection(occurrence['sheet_ids']):direct.append(binding)
                    elif group['kind']=='assembly_row' and ids.intersection(occurrence['sheet_ids']):same_row.append(binding)
                    elif occurrence['table_ref'] in inherited:continued.append(binding)
            bindings=direct or same_row or continued
            codes={b['part_code'] for b in bindings}
            group['marker_bindings'].append(dict(number_text_ref=marker['text_ref'],circle_ref=marker['circle_ref'],part_number=marker['label'],
                sheet_ids=marker['sheet_ids'],part_codes=sorted(codes),table_refs=sorted({b['table_ref'] for b in bindings}),leader_refs=marker['leader_refs'],
                status='verified_local_bom_identity' if len(codes)==1 else 'ambiguous_bom_identity' if codes else 'bom_identity_unresolved',
                bom_scope='explicit_numbered_drawing_series' if continued and not (direct or same_row) else 'local_source_bom',geometry_owner_verified=False))
    return rows


def native_tables(doc,cells,sheets,excluded=(),regions=()):
    """Keep placed instance paths for native tables, including nested blocks."""
    from ezdxf.math import Matrix44
    from cad.sheets import discarded
    result=[];excluded=set(excluded)
    def visit(container,prefix,matrix,layout,ancestry=(),attributes=()):
        for entity in container:
            ref=prefix+entity.dxf.handle
            if ref in excluded or ref.split('/')[0] in excluded:continue
            if entity.dxftype()=='ACAD_TABLE':
                position=list(matrix.transform(entity.dxf.insert))
                if discarded([position[0],position[1],position[0],position[1]],layout,regions):continue
                parents=[s['id'] for s in sheets if s.get('layout')==layout and s.get('bbox') and
                         s['bbox'][0]-1e-6<=position[0]<=s['bbox'][2]+1e-6 and s['bbox'][1]-1e-6<=position[1]<=s['bbox'][3]+1e-6]
                values=cells.get(entity.dxf.handle,[]);bindings=bind_cells(entity,values,doc)
                for binding in bindings:binding['mirror_ref']=prefix+binding['mirror_ref']
                result.append(dict(ref=ref,type='ACAD_TABLE',layout=layout,position=position,source_sheet_ids=parents,
                    coordinate_frame='instance:'+prefix[:-1] if prefix else 'layout:'+layout,
                    container_ref=prefix[:-1] or None,container_name=container.name,container_attributes=list(attributes),
                    bom=read_bom(values,bindings)))
            elif entity.dxftype()=='INSERT' and entity.dxf.name in doc.blocks:
                if entity.dxf.name in ancestry or len(ancestry)>=128:raise ValueError('Block tham chiếu vòng/quá sâu khi đọc bảng kê native')
                visit(doc.blocks[entity.dxf.name],ref+'/',entity.matrix44()*matrix,layout,ancestry+(entity.dxf.name,),
                      [(a.dxf.tag,a.dxf.text) for a in entity.attribs])
    for layout in doc.layouts:visit(layout,'',Matrix44(),layout.name)
    return result


def with_readiness(result):
    available=bool(result.get('nodes'))
    readable=len(result.get('readable_schedules',[]))
    result['bom_readiness']={'status':'verified_bom_available' if available else 'unresolved',
        'part_count':len(result.get('nodes',[])),
        'readable_schedule_count':readable,
        'message':'Đã xác định các dòng vật tư từ bảng CAD nguồn. Liên kết hình học cần kiểm chứng riêng.' if available else
                  'Đã đọc danh mục CAD nhưng chưa xác định được bảng kê đủ mã, mô tả, vật liệu và số lượng. Chưa thể cam kết đồng bộ vật tư và các chi tiết liên quan cho file này.'}
    if readable:
        result['bom_readiness']['message']+=f' Đã đọc thêm {readable} bảng 4 cột; các bảng này chưa đủ căn cứ xác nhận mã chi tiết.'
    if not available and not any(w.get('code')=='bom_unresolved' for w in result.get('warnings',[])):
        result.setdefault('warnings',[]).append({'code':'bom_unresolved','message':result['bom_readiness']['message']})
    return result


def _document_graph(document_id):
    path=storage.folder(document_id);status=storage.read_status(document_id)
    if status['status']!='ready':raise ValueError('File chưa đọc xong')
    source=path/status['dxf'];fingerprint=digest(source)
    sheets_file=path/'sheets-v3.json';excluded_file=path/'exclusions-v1.json'
    if not sheets_file.exists() or not excluded_file.exists():raise ValueError('Cần đọc danh mục và nhận diện khung trước')
    sheets=json.loads(sheets_file.read_text(encoding='utf-8'))['items']
    excluded=set(json.loads(excluded_file.read_text(encoding='utf-8'))['ids'])
    # Invalidate also if the active sheet/exclusion cache changes.
    detection_hash=digest(sheets_file)+digest(excluded_file)
    cache=path/'part-graph-v1.json'
    if cache.exists():
        result=json.loads(cache.read_text(encoding='utf-8'))
        if result.get('version')==GRAPH_VERSION and result.get('source_hash')==fingerprint and result.get('detection_hash')==detection_hash:return with_readiness(result)
    storage.catalog(document_id)
    with CAD_LOCK:
        # UI preflight and planning may request the same whole-file index.
        if cache.exists():
            cached=json.loads(cache.read_text(encoding='utf8'))
            if cached.get('version')==GRAPH_VERSION and cached.get('source_hash')==fingerprint and cached.get('detection_hash')==detection_hash:return with_readiness(cached)
        doc=load_document(str(source));cells=table_cells(source)
        active_sheets=[s for s in sheets if s['id'] not in excluded]
        from cad.sheets import excluded_regions
        regions=excluded_regions(doc)+[dict(layout=s['layout'],bbox=s['bbox']) for s in sheets if s['id'] in excluded and s.get('bbox')]
        tables=native_tables(doc,cells,active_sheets,excluded,regions)
        from cad.graphic_tables import document_tables
        graphic_tables=document_tables(doc,active_sheets)
        tables.extend(graphic_tables)
        from cad.linked_details import linked_details
        codes={row['part_code'] for table in tables if table.get('bom',{}).get('status')=='verified_template' for row in table['bom']['rows']}
        supplemental=linked_details(source,sheets,codes)
        from cad.row_groups import document_rows
        rows=document_rows(doc,active_sheets+supplemental,regions)
        drawing_sheets=[dict(s,source_row_labels=[g['label'] for g in rows['groups'] if g['status']=='source_row_group' and s['id'] in g['sheet_ids']],
                             source_row_ids=[g['id'] for g in rows['groups'] if g['status']=='source_row_group' and s['id'] in g['sheet_ids']]) for s in active_sheets+supplemental]
        graph=build_part_graph(tables,drawing_sheets)
        rows=bind_row_members(rows,graph['nodes'],graph.get('bom_continuations'))
        graph['drawing_rows']=rows
        from cad.native_parts import native_part_scopes
        instances=native_part_scopes(source,active_sheets+supplemental,codes)
        for node in graph['nodes']:
            node['native_instances']=[i for i in instances if i['part_code']==node['code']]
        graph['readable_schedules']=[dict(table_ref=t['ref'],sheet_ids=t.get('source_sheet_ids',[]),
            row_count=len(t['bom']['rows']),status=t['bom']['status'],message=t['bom']['warning'])
            for t in tables if t.get('bom',{}).get('status')=='readable_schedule']
        graph['version']=GRAPH_VERSION
    result={**graph,'document_id':document_id,'source_hash':fingerprint,'detection_hash':detection_hash,
            'table_count':len(tables),'graphic_table_count':len(graphic_tables),'sheet_count':len(sheets),'linked_details':supplemental}
    result=with_readiness(result)
    storage.write_json(cache,result)
    return result


def document_graph(document_id):
    result=_document_graph(document_id)
    from graph.parameter_links import read,inject
    folder=storage.folder(document_id);links=read(folder,result['source_hash'])
    if links:
        result=inject(result,links)
        result['detection_hash']+=':'+digest(folder/'parameter-links-v1.json')
    from graph.cuboid_links import read as read_cuboids,inject as inject_cuboids
    cuboids=read_cuboids(folder,result['source_hash'])
    if cuboids:
        result=inject_cuboids(result,cuboids)
        result['detection_hash']+=':'+digest(folder/'design-decisions-v1.json')
    return result
