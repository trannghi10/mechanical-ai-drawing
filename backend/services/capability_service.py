"""Capability discovery independent of frame detection or AI inference."""
from cad.capabilities import report,public,VERSION
from backend.services import catalog_service as storage


def get(document_id,offset=0,limit=50):
    folder=storage.folder(document_id);status=storage.read_status(document_id)
    if status['status']!='ready':raise ValueError('Cần đọc xong tài liệu trước khi kiểm kê khả năng CAD')
    result=report(folder/status['dxf'])
    cache=folder/'cad-capabilities-v1.json'
    if not cache.exists():storage.write_json(cache,result)
    else:
        import json
        old=json.loads(cache.read_text(encoding='utf8'))
        if old.get('version')!=VERSION or old.get('source_hash')!=result['source_hash']:storage.write_json(cache,result)
    return public(result,offset,limit)
