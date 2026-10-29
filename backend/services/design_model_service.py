"""Build a reusable, selection-scoped design registry without running a model."""
from backend.services import catalog_service as storage
from backend.services.change_service import context_for
from backend.services.part_graph_service import document_graph
from cad.measured_features import index
from graph.design_model import build,identity,VERSION


def get(document_id,targets):
    folder=storage.folder(document_id);status=storage.read_status(document_id)
    if status['status']!='ready':raise ValueError('File chưa đọc xong')
    graph=document_graph(document_id)
    context=context_for(folder/status['dxf'],targets)
    from backend.services.design_choices import attach
    attach(context,folder)
    key=identity([VERSION,context['source_hash'],graph['detection_hash'],sorted(t['id'] for t in targets),
                  [v for v in context.get('design_choices',{}).get('confirmed_choices',[]) if v.get('key')=='cuboid_projection_datum']])
    cache=folder/'design-models'/f'{key}.json'
    if cache.exists():
        import json
        return json.loads(cache.read_text(encoding='utf8'))
    context['source_features']=index(context,graph)
    model=build(context,graph);model['detection_hash']=graph['detection_hash']
    cache.parent.mkdir(exist_ok=True);storage.write_json(cache,model)
    return model


def part_map(document_id,targets,include_related=True):
    """Expand reading scope using existing source identities; never edit scope."""
    import json
    from cad.catalog import CAD_LOCK
    folder=storage.folder(document_id);status=storage.read_status(document_id);graph=document_graph(document_id)
    source=folder/status['dxf'];roots=list(targets);links=[]
    if include_related:
        with CAD_LOCK:initial=context_for(source,roots)
        sheets=json.loads((folder/'sheets-v3.json').read_text(encoding='utf8'))['items']+graph.get('linked_details',[])
        targets,links=part_reading_scope(roots,initial,sheets,graph)
        if len(targets)>64:raise ValueError('Có hơn 64 khung liên quan. Chọn một cụm nhỏ hơn để lập Part Map; chưa bỏ qua khung nào.')
    with CAD_LOCK:model=get(document_id,targets)
    result=dict(model['part_map'],root_target_ids=[t['id'] for t in roots],targets=targets,scope_links=links,
        detection_hash=model['detection_hash'],source_parts=model['parts'],selected_scope_only=not include_related,
        cuboid_projections=model.get('cuboid_projections',[]))
    result['id']=identity([VERSION,result['source_hash'],model['detection_hash'],result['root_target_ids'],result['scope_ids']])
    cache=folder/'part-maps';cache.mkdir(exist_ok=True);storage.write_json(cache/(result['id']+'.json'),result)
    return result


def part_reading_scope(roots,context,sheets,graph):
    """Identity matching reads the chosen parts, not every co-process sibling.

    The change planner retains its broader impact review. This reading query
    does not infer that all laser-cut parts represent the same component.
    """
    ids={t['id'] for t in roots};known={n['code'] for n in graph['nodes']}
    codes={r['part_code'] for e in context['entities'] if e.get('bom',{}).get('status')=='verified_template' for r in e['bom']['rows']}
    codes.update(n['code'] for n in graph['nodes'] if ids.intersection(n['detail_sheets']))
    from cad.part_identity import record_identity
    codes.update(c for e in context['entities'] for c in [record_identity(e,known)] if c)
    wanted=set(ids)
    wanted.update(s for link in graph.get('confirmed_representation_links',[]) if link['part_code'] in codes and not link.get('unavailable_scope_ids') for s in link['sheet_ids'])
    # Explicit numbered continuations carry their BOM on another page. Read
    # the complete proven series in either direction before locating members;
    # a shared product/title alone cannot expand the reading scope.
    series_tables=set()
    for sid,series in graph.get('bom_continuations',{}).items():
        pages=set(series.get('page_sheet_ids',{}).values())
        if series.get('status')!='explicit_numbered_drawing_series' or not series.get('table_refs') or not ids.intersection(pages|{sid}):continue
        wanted.update(pages);wanted.update(series.get('evidence_sheet_ids',[]));series_tables.update(series['table_refs'])
    codes.update(n['code'] for n in graph['nodes'] if any(o.get('table_ref') in series_tables for o in n.get('bom_occurrences',[])))
    for node in graph['nodes']:
        if node['code'] not in codes:continue
        wanted.update(node['detail_sheets']);wanted.update(s for i in node.get('native_instances',[]) for s in i['sheet_ids'])
    from cad.row_groups import identity_groups
    wanted.update(s for g in identity_groups(graph.get('drawing_rows',{})) if g['status']=='source_row_group' and ids.intersection(g['sheet_ids']) for s in g['sheet_ids'])
    result=list(roots);links=[]
    for sheet in sheets:
        if sheet['id'] not in wanted or sheet['id'] in ids:continue
        result.append(sheet);ids.add(sheet['id']);links.append(dict(sheet_id=sheet['id'],reason='Đối chiếu hình của cùng mã chi tiết/hàng nguồn; chỉ mở để đọc.'))
    return result,links


def resolve_part_selection(document_id,targets,selection,request):
    """A selected source view pins identity, never coordinates or edit rights."""
    import json,re
    from cad.edit_engine import digest
    from graph.part_map import VERSION as MAP_VERSION
    if not selection:return None
    value=selection.model_dump() if hasattr(selection,'model_dump') else dict(selection)
    if not re.fullmatch('[a-f0-9]{24}',value.get('map_id','')):raise ValueError('Bản đồ chi tiết không hợp lệ')
    folder=storage.folder(document_id);file=folder/'part-maps'/(value['map_id']+'.json')
    if not file.is_file():raise ValueError('Cần đọc lại bản đồ chi tiết trong file đang mở')
    data=json.loads(file.read_text(encoding='utf8'));source=folder/storage.read_status(document_id)['dxf']
    if data.get('version')!=MAP_VERSION or data['source_hash']!=value.get('source_hash') or digest(source)!=data['source_hash']:
        raise ValueError('Hình đã chọn thuộc nguồn hoặc bộ nhận diện cũ; cần gắn hình lại')
    if set(data['root_target_ids'])!={t['id'] for t in targets}:raise ValueError('Hình đã chọn không thuộc phạm vi bản vẽ đang sửa')
    graph=document_graph(document_id)
    if data['detection_hash']!=graph['detection_hash']:raise ValueError('Phạm vi khung đã đổi; cần chọn lại chi tiết')
    view=next((v for v in data['views'] if v['id']==value.get('view_id')),None)
    code=value.get('part_code')
    if not view or view['identity_status']!='verified_source_identity' or view['part_codes']!=[code]:
        raise ValueError('Chỉ chọn hình đã xác minh đúng một mã chi tiết từ CAD nguồn')
    parts=[p for p in data.get('source_parts',[]) if p['id']==code]
    if len(parts)!=1 or parts[0].get('identity_kind')!='bom_code' or parts[0].get('definition_conflict'):
        raise ValueError('Mã chi tiết chưa có BOM duy nhất hoặc mô tả nguồn đang mâu thuẫn')
    from bom.reader import normalized
    from graph.part_graph import requested_numbers
    text=normalized(request)
    if re.search(r'\b(?:tat ca|toan bo|tong the|(?:chieu cao|chieu dai|chieu rong|kich thuoc)\s+(?:cua\s+)?san pham)\b',text):
        raise ValueError('Đang chọn một chi tiết. Bỏ chọn chi tiết trước khi yêu cầu sửa toàn sản phẩm hoặc tất cả vật tư')
    known={n['code'] for n in graph['nodes']}
    mentioned={c for c in known if re.search(r'(?<![\w.])'+re.escape(c)+r'(?![\w.])',request)}
    if mentioned-{code}:raise ValueError('Mã trong yêu cầu khác hình đã chọn; hãy đổi lựa chọn hoặc sửa yêu cầu')
    explicit=re.findall(r'\bma\s+(?:chi tiet\s+|vat tu\s+)?([\w.-]+)',text)
    if explicit and any(c!=normalized(code) for c in explicit):raise ValueError('Mã được nhập không khớp hình chi tiết đã chọn')
    roots={t['id'] for t in targets};numbers=requested_numbers(request)
    local={str(r['part_number']).strip().upper() for r in parts[0].get('selected_bom_rows',[]) if roots.intersection(r.get('sheet_ids',[]))}
    if numbers and (len(numbers)!=1 or numbers[0] not in local):raise ValueError('STT trong yêu cầu không khớp chi tiết đã chọn ở bảng kê của khung này')
    return dict(value,source_hash=data['source_hash'],root_target_ids=sorted(roots),geometry_refs=view['geometry_refs'],
        identity_proofs=view['identity_proofs'],policy='Selected part identity only; geometry, anchors, fit and affected parts require independent validation.')


def part_view_preview(document_id,map_id,view_id,source_hash):
    """Render exact source entities from their instance paths, without mutations."""
    import json,re
    from cad.edit_engine import digest
    from cad.catalog import CAD_LOCK,load_document
    from cad.frame_geometry import matrix
    if not re.fullmatch('[a-f0-9]{24}',map_id):raise ValueError('Part Map không hợp lệ')
    folder=storage.folder(document_id);file=folder/'part-maps'/(map_id+'.json')
    data=json.loads(file.read_text(encoding='utf8'));source=folder/storage.read_status(document_id)['dxf']
    if source_hash!=data['source_hash'] or digest(source)!=source_hash:raise ValueError('Part Map thuộc nguồn CAD cũ; cần đọc lại')
    graph=document_graph(document_id)
    if graph['detection_hash']!=data['detection_hash']:raise ValueError('Phạm vi khung đã đổi; cần lập lại Part Map')
    view=next((v for v in data['views'] if v['id']==view_id),None)
    if view is None:raise ValueError('Hình không thuộc Part Map đã đọc')
    allowed={'LINE','LWPOLYLINE','POLYLINE','ARC','CIRCLE','SPLINE','ELLIPSE'}
    with CAD_LOCK:
        context=context_for(source,data['targets']);records={e['ref']:e for e in context['entities']}
        doc=load_document(str(source));entities=[]
        for ref in view['geometry_refs']+view['circle_refs']:
            record=records.get(ref,{})
            if record.get('type') not in allowed:raise ValueError('Hình có entity chưa hỗ trợ xem riêng')
            entity=doc.entitydb.get(ref.split('/')[-1])
            if entity is None or entity.dxftype()!=record['type']:raise ValueError('Entity nguồn đã thay đổi')
            clone=entity.copy();clone.transform(matrix(record));clone.dxf.color=5;clone.dxf.true_color=0x1767B2;entities.append(clone)
        if not entities:raise ValueError('Chưa có hình học nguồn để xem riêng')
        from ezdxf.addons.drawing import RenderContext,Frontend,svg,layout
        from ezdxf.addons.drawing.config import Configuration,ColorPolicy,BackgroundPolicy
        backend=svg.SVGBackend();renderer=Frontend(RenderContext(doc),backend,config=Configuration(color_policy=ColorPolicy.COLOR,background_policy=BackgroundPolicy.WHITE,
            lineweight_scaling=0,min_lineweight=12))
        renderer.set_background('#ffffff');renderer.draw_entities(entities);backend.finalize()
        return backend.get_string(layout.Page(240,160))
