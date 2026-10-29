"""Persist explicitly confirmed relationships against immutable source geometry."""
import threading,uuid
from backend.services import catalog_service as storage
from cad.edit_engine import digest
from graph.parameter_links import ParameterLink,read,validate_binding

LOCK=threading.RLock()


def get(document_id):
    folder=storage.folder(document_id);status=storage.read_status(document_id)
    if status['status']!='ready':raise ValueError('Cần đọc xong DWG trước khi gắn liên kết')
    source_hash=digest(folder/status['dxf'])
    return dict(source_hash=source_hash,links=read(folder,source_hash))


def save(document_id,targets,source_hash,rule):
    from backend.services.change_service import context_for
    from backend.services.part_graph_service import document_graph
    from cad.measured_features import index
    folder=storage.folder(document_id);status=storage.read_status(document_id)
    context=context_for(folder/status['dxf'],targets)
    if context['source_hash']!=source_hash:raise ValueError('File nguồn đã thay đổi; cần đọc và chọn lại DIM')
    graph=document_graph(document_id);context['source_features']=index(context,graph)
    link=ParameterLink.model_validate(rule);features=validate_binding(link,context)
    known={n['code'] for n in graph['nodes']}
    if not {f['part_code'] for f in features}<=known:raise ValueError('Liên kết cần mã chi tiết xác định từ BOM nguồn')
    driver,receiver=features[:2]
    entry=dict(id=uuid.uuid4().hex,rule=link.model_dump(),driver_code=driver['part_code'],receiver_code=receiver['part_code'],
        targets=targets,confirmation='user_confirmed_dimension_relationship',evidence_refs=sorted({r for f in features for r in f['evidence_refs']}))
    with LOCK:
        links=read(folder,source_hash)
        old=next((e for e in links if e['rule']==entry['rule']),None)
        if old:return old
        if len(links)>=64:raise ValueError('Giới hạn 64 liên kết mỗi file; cần chia nhóm thiết kế')
        links.append(entry);storage.write_json(folder/'parameter-links-v1.json',dict(version=1,source_hash=source_hash,links=links))
    return entry


def remove(document_id,link_id,source_hash):
    folder=storage.folder(document_id)
    with LOCK:
        current=get(document_id)
        if current['source_hash']!=source_hash:raise ValueError('File nguồn đã thay đổi')
        found=[e for e in current['links'] if e['id']==link_id]
        if not found:raise ValueError('Không có liên kết này trong file đang chọn')
        storage.write_json(folder/'parameter-links-v1.json',dict(version=1,source_hash=source_hash,links=[e for e in current['links'] if e['id']!=link_id]))
    return dict(removed=link_id)
