"""Inspect and confirm exact native cuboid identity/datum without editing CAD."""
import hashlib,html,json,re
from backend.services import catalog_service as storage
from cad.edit_engine import digest


def context(document_id,targets):
    from cad.catalog import CAD_LOCK
    from backend.services.change_service import context_for
    from backend.services.part_graph_service import document_graph
    from backend.services.design_choices import attach
    from cad.measured_features import index
    folder=storage.folder(document_id);status=storage.read_status(document_id)
    if status['status']!='ready':raise ValueError('Cần đọc xong DWG trước khi gắn hình hộp')
    source=folder/status['dxf']
    graph=document_graph(document_id)
    with CAD_LOCK:c=context_for(source,targets)
    from backend.services.design_model_service import part_reading_scope
    sheets=json.loads((folder/'sheets-v3.json').read_text(encoding='utf8'))['items']+graph.get('linked_details',[])
    expanded,_=part_reading_scope(targets,c,sheets,graph)
    if len(expanded)>64:raise ValueError('Có quá nhiều khung liên quan; chọn cụm nhỏ hơn để gắn hình')
    excluded=folder/'exclusions-v1.json'
    if excluded.exists() and {t['id'] for t in expanded}.intersection(json.loads(excluded.read_text(encoding='utf8')).get('ids',[])):
        raise ValueError('Phạm vi có khung đã bỏ; cần khôi phục hoặc chọn lại trước khi gắn hình')
    if len(expanded)!=len(targets):
        with CAD_LOCK:c=context_for(source,expanded)
    attach(c,folder);c['part_graph']=graph;c['source_features']=index(c,graph)
    return c,graph


def candidates(document_id,targets,dimension_ref):
    from graph.parameter_links import feature
    from graph.cuboid_projections import inventory,specification,clear_after
    from cad.cuboid_projection import resize
    from cad.measured_features import rectangle
    c,graph=context(document_id,targets);f=feature(c,dimension_ref)
    if rectangle(f['points']) is None:raise ValueError('DIM nguồn cần gắn với một bản chi tiết hình chữ nhật')
    code=f['part_code'];sizes=[specification(r['description']) for e in c['entities'] if e.get('bom',{}).get('status')=='verified_template' for r in e['bom']['rows'] if r['part_code']==code]
    if not sizes or any(v is None or v!=sizes[0] for v in sizes):raise ValueError('Cần BOM có duy nhất một quy cách ba chiều cho mã đã chọn')
    d=next(e for e in c['entities'] if e['ref']==dimension_ref);value=d.get('scaled_measurement')
    if sum(abs(v-value)<1e-5 for v in sizes[0])!=1:raise ValueError('DIM nguồn chưa xác định duy nhất một chiều trong BOM')
    bodies=inventory(c,proposed_part_code=code)
    records={e['ref']:e for e in c['entities']};probe=list(sizes[0]);probe[next(i for i,v in enumerate(probe) if abs(v-value)<1e-5)]*=.99
    result=dict(source_hash=c['source_hash'],detection_hash=graph['detection_hash'],dimension_ref=dimension_ref,part_code=code,
        before_spec_mm=sizes[0],measurement_mm=value,targets=c['targets'],candidates=[])
    for body in bodies:
        def allowed(anchor,point=None):
            try:return clear_after(c,body,resize(body,records,sizes[0],probe,anchor,point))
            except ValueError:return False
        result['candidates'].append(dict(body,center_datum_available=allowed('center'),
            vertices=[dict(label=chr(65+i),point=v['point'],datum_available=allowed('vertex',v['point'])) for i,v in enumerate(body['maps'][0]['vertices'])]))
    result['id']=hashlib.sha256(json.dumps([c['source_hash'],graph['detection_hash'],dimension_ref,sorted(t['id'] for t in c['targets'])],sort_keys=True).encode()).hexdigest()[:24]
    file=storage.folder(document_id)/'cuboid-candidates'/(result['id']+'.json');file.parent.mkdir(exist_ok=True);storage.write_json(file,result)
    return public(result)


def public(data):
    return {**{k:v for k,v in data.items() if k!='candidates'},'candidates':[{k:v for k,v in b.items() if k!='maps'} for b in data['candidates']],
        'policy':'Candidate geometry is not a confirmed part identity. Confirm the exact source picture and depiction datum before saving. No CAD is modified.'}


def cached(document_id,candidate_id,source_hash):
    if not re.fullmatch('[0-9a-f]{24}',candidate_id):raise ValueError('Danh sách hình hộp không hợp lệ')
    folder=storage.folder(document_id);data=json.loads((folder/'cuboid-candidates'/(candidate_id+'.json')).read_text(encoding='utf8'))
    status=storage.read_status(document_id)
    if status['status']!='ready':raise ValueError('Cần đọc xong DWG trước khi dùng danh sách hình hộp')
    source=folder/status['dxf']
    if data['source_hash']!=source_hash or digest(source)!=source_hash:raise ValueError('Danh sách thuộc nguồn CAD cũ; cần đọc lại')
    return data


def preview(document_id,candidate_id,body_id,source_hash):
    data=cached(document_id,candidate_id,source_hash);body=next((b for b in data['candidates'] if b['id']==body_id),None)
    if body is None:raise ValueError('Hình không thuộc danh sách đã đọc')
    # Every stroke is an original LINE endpoint in the saved source snapshot;
    # this preview is not a model-generated or reconstructed hidden surface.
    from cad.cuboid_projection import components
    from cad.frame_geometry import world,matrix
    c,_=context(document_id,data['targets']);bodies=components(c['entities'])
    current=next((b for b in bodies if b['refs']==body['refs']),None)
    if current is None:raise ValueError('Cạnh hình hộp đã thay đổi')
    by={e['ref']:e for e in c['entities']};geometry={ref:world(by[ref])['geometry'] for ref in body['refs']};points=[geometry[r][k] for r in body['refs'] for k in ('start','end')]
    x0=min(p[0] for p in points);x1=max(p[0] for p in points);y0=min(p[1] for p in points);y1=max(p[1] for p in points);pad=max(x1-x0,y1-y0)*.12
    stroke=max(x1-x0,y1-y0)/350;font=stroke*8;lines=[]
    for ref in body['refs']:
        a,b=[geometry[ref][k] for k in ('start','end')];lines.append(f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}"/>')
    labels=''
    for v in body['vertices']:
        p=matrix(by[body['refs'][0]]).transform(v['point']);labels+=f'<text x="{p[0]+font*.3}" y="{-p[1]-font*.3}">{v["label"]}</text>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0-pad} {-y1-pad} {x1-x0+2*pad} {y1-y0+2*pad}"><title>{html.escape(data["part_code"])} — hình CAD cần đối chiếu</title><rect x="{x0-pad}" y="{-y1-pad}" width="{x1-x0+2*pad}" height="{y1-y0+2*pad}" fill="white"/><g stroke="#1767b2" stroke-width="{stroke}" fill="none">{"".join(lines)}</g><g fill="#17436b" font-size="{font}" font-family="sans-serif">{labels}</g></svg>'


def save(document_id,candidate_id,body_id,source_hash,anchor,vertex=None):
    from backend.services.design_choices import CHOICE_LOCK
    from graph.cuboid_projections import inventory,clear_after
    from cad.cuboid_projection import resize
    data=cached(document_id,candidate_id,source_hash)
    # Re-run source identity, camera, blockers and current scope. Cached
    # candidates or client-supplied coordinates can never grant edit rights.
    current=candidates(document_id,data['targets'],data['dimension_ref'])
    if current['source_hash']!=source_hash or current['detection_hash']!=data['detection_hash']:raise ValueError('Phạm vi CAD đã thay đổi; cần đọc lại danh sách')
    target=next((b for b in current['candidates'] if b['id']==body_id),None)
    if target is None:raise ValueError('Hình hộp chưa được kiểm chứng trong phạm vi hiện tại')
    if anchor not in ('center','vertex') or (anchor=='vertex')!=(vertex is not None):raise ValueError('Chọn giữ tâm hoặc một đỉnh nguồn')
    fixed=None
    if anchor=='vertex':
        found=[v['point'] for v in target['vertices'] if v['label']==vertex]
        if len(found)!=1:raise ValueError('Đỉnh không thuộc hình CAD đã đọc')
        fixed=found[0]
    c,_=context(document_id,data['targets']);body=next(b for b in inventory(c,proposed_part_code=data['part_code']) if b['id']==body_id)
    after=list(body['before_spec_mm']);axis=next(i for i,v in enumerate(after) if abs(v-data['measurement_mm'])<1e-5);after[axis]*=.99
    changed=resize(body,{e['ref']:e for e in c['entities']},body['before_spec_mm'],after,anchor,fixed)
    if not clear_after(c,body,changed):raise ValueError('Mốc giữ làm thay đổi tiếp nối nét hoặc chồng hình nguồn; chọn mốc khác')
    entry=dict(key='cuboid_projection_datum',body_id=body_id,target_refs=body['refs'],part_code=data['part_code'],dimension_ref=data['dimension_ref'],
               anchor=anchor,fixed_point=fixed,targets=data['targets'],confirmation='user_confirmed_cuboid_identity_and_datum')
    folder=storage.folder(document_id);file=folder/'design-decisions-v1.json'
    with CHOICE_LOCK:
        status=storage.read_status(document_id)
        if status['status']!='ready' or digest(folder/status['dxf'])!=source_hash:raise ValueError('File nguồn đã thay đổi hoặc đang được đọc lại')
        choices=json.loads(file.read_text(encoding='utf8')) if file.exists() else dict(source_hash=source_hash,confirmed_choices=[])
        if choices.get('source_hash')!=source_hash:raise ValueError('Quyết định đã lưu thuộc CAD cũ; cần đối chiếu lại')
        old=[v for v in choices['confirmed_choices'] if v.get('key')=='cuboid_projection_datum' and v.get('body_id')==body_id]
        if not old and sum(v.get('key')=='cuboid_projection_datum' for v in choices['confirmed_choices'])>=64:raise ValueError('Giới hạn 64 hình đã gắn trong mỗi file')
        if any(v.get('part_code')!=entry['part_code'] or v.get('dimension_ref')!=entry['dimension_ref'] for v in old):raise ValueError('Hình này đã gắn với nguồn khác; cần xóa liên kết trước')
        choices['confirmed_choices']=[v for v in choices['confirmed_choices'] if v not in old]+[entry];storage.write_json(file,choices)
    return entry


def get(document_id):
    from graph.cuboid_links import read
    folder=storage.folder(document_id);status=storage.read_status(document_id)
    if status['status']!='ready':raise ValueError('Cần đọc xong DWG trước khi xem các hình đã gắn')
    source=folder/status['dxf'];fingerprint=digest(source)
    return dict(source_hash=fingerprint,links=read(folder,fingerprint))


def remove(document_id,body_id,source_hash):
    from backend.services.design_choices import CHOICE_LOCK
    folder=storage.folder(document_id);file=folder/'design-decisions-v1.json'
    with CHOICE_LOCK:
        current=get(document_id)
        if current['source_hash']!=source_hash:raise ValueError('Nguồn CAD đã thay đổi')
        if not any(v['body_id']==body_id for v in current['links']):raise ValueError('Không có hình đã gắn này')
        choices=json.loads(file.read_text(encoding='utf8'));choices['confirmed_choices']=[v for v in choices['confirmed_choices'] if not(v.get('key')=='cuboid_projection_datum' and v.get('body_id')==body_id)]
        storage.write_json(file,choices)
    return dict(removed=body_id)
