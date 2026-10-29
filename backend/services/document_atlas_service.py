"""Persistent, paged whole-document reading jobs, separate from CAD editing."""
import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from backend.services import catalog_service as storage
from cad.document_atlas import VERSION, scan, parts_directory
from cad.edit_engine import digest
from cad.catalog import CAD_LOCK, load_document

POOL = ThreadPoolExecutor(max_workers=2)
LOCK = threading.RLock()
ACTIVE = set()
PAGE_SIZE = 500


def signature(document_id):
    folder = storage.folder(document_id); status = storage.read_status(document_id)
    if status['status'] != 'ready': raise ValueError('File chưa đọc xong')
    source = folder/status['dxf']
    from backend.services.part_graph_service import GRAPH_VERSION
    from cad.sheets import SHEET_VERSION
    dependencies = [(name, digest(folder/name) if (folder/name).exists() else None) for name in
                    ('sheets-v3.json', 'exclusions-v1.json', 'parameter-links-v1.json', 'design-decisions-v1.json')]
    value = [VERSION, (GRAPH_VERSION,SHEET_VERSION), digest(source), storage.source_fingerprint(folder), dependencies]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(), value[2]


def job_folder(document_id, job_id):
    from backend.services.revision_service import safe_id
    return storage.folder(document_id)/'document-atlas'/safe_id(job_id)


def public(data):
    return {k: v for k, v in data.items() if k not in ('signature',)}


def read(document_id, job_id):
    with LOCK:
        path = job_folder(document_id, job_id)/'job.json'
        data = json.loads(path.read_text(encoding='utf8'))
        if data['status'] in ('queued', 'running') and (document_id, job_id) not in ACTIVE:
            data.update(status='failed', message='Server đã khởi động lại khi đọc. Bấm đọc lại toàn file.', finished_at=time.time())
            storage.write_json(path, data)
    if data['status'] == 'ready' and data['signature'] != signature(document_id)[0]:
        raise ValueError('Nguồn hoặc phạm vi nhận diện đã thay đổi; cần đọc lại toàn file.')
    return public(data)


def submit(document_id):
    key, source_hash = signature(document_id)
    root = storage.folder(document_id)/'document-atlas'; root.mkdir(exist_ok=True)
    with LOCK:
        for path in sorted(root.glob('*/job.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            data = json.loads(path.read_text(encoding='utf8'))
            if data['signature'] != key: continue
            if data['status'] == 'ready' or (data['status'] in ('queued', 'running') and (document_id, data['id']) in ACTIVE):
                return public(data)
        job_id = uuid.uuid4().hex; folder = root/job_id; folder.mkdir()
        data = dict(id=job_id, document_id=document_id, signature=key, source_hash=source_hash,
                    status='queued', phase='queued', created_at=time.time(), visited_count=0,
                    message='Đang chờ đọc toàn bản vẽ; không phụ thuộc khung đang chọn.')
        storage.write_json(folder/'job.json', data); ACTIVE.add((document_id, job_id))
        from backend.services.job_context import submit as submit_worker
        submit_worker(POOL, run, document_id, job_id)
        return public(data)


def run(document_id, job_id):
    folder = job_folder(document_id, job_id); path = folder/'job.json'
    data = json.loads(path.read_text(encoding='utf8')); pages = []; batch = []
    def update(**values):
        with LOCK:
            data.update(values); storage.write_json(path, data)
    def flush():
        if not batch: return
        name = f'entities-{len(pages):05d}.json'
        storage.write_json(folder/name, list(batch)); pages.append(dict(file=name, count=len(batch), sha256=digest(folder/name))); batch.clear()
    def emit(record):
        batch.append(record)
        if len(batch) >= PAGE_SIZE: flush()
    try:
        update(status='running', phase='structure', message='Đang lập danh mục cụm, BOM và bản chi tiết trong toàn file.')
        from backend.main import get_sheets, get_catalog
        get_catalog(document_id); sheets = get_sheets(document_id)['items']
        key, source_hash = signature(document_id)
        if source_hash != data['source_hash']: raise ValueError('Nguồn CAD đã đổi khi đang đọc.')
        from backend.services.part_graph_service import document_graph
        graph_error = None
        try: graph = document_graph(document_id)
        except ValueError as error:
            graph = {}; graph_error = str(error)
        # Detection initialization can create caches; pin their final identity.
        if signature(document_id)[0] != key: raise ValueError('Danh mục CAD đã đổi khi đang đọc cấu trúc; cần đọc lại.')
        update(signature=key, phase='geometry', message='Đang đọc mọi layout, hình học, DIM và đường dẫn block lồng.')
        source = storage.folder(document_id)/storage.read_status(document_id)['dxf']
        with CAD_LOCK:
            report = scan(load_document(str(source)), emit, codes={n['code'] for n in graph.get('nodes', [])},
                          progress=lambda count, layout: update(visited_count=count, current_layout=layout))
        flush()
        if signature(document_id)[0] != key: raise ValueError('Nguồn hoặc danh mục CAD đã đổi trong khi đọc; cần đọc lại.')
        all_sheets = {s['id']: s for s in sheets+graph.get('linked_details', [])}
        report.update(document_id=document_id, source_hash=source_hash,
                      original_source_hash=storage.source_fingerprint(storage.folder(document_id)),
                      detection_hash=graph.get('detection_hash'), parts=parts_directory(graph, list(all_sheets.values())),
                      frames=list(all_sheets.values()), assembly_structure=graph.get('assembly_structure', {}),
                      drawing_rows=graph.get('drawing_rows', {}), graph_error=graph_error,
                      graph_warnings=graph.get('warnings', []), pages=pages,
                      policy='Toàn bộ thực thể được đặt trong các layout được duyệt theo đường dẫn instance, gồm phần ngoài khung và khung loại khỏi phạm vi sửa. Hình học giữ hệ tọa độ nguồn. BOM/cụm là bằng chứng danh mục; quan hệ lắp ghép và quyền sửa cần kiểm chứng riêng. Không tự suy mã từ hình giống nhau.')
        storage.write_json(folder/'report.json', report)
        update(status='ready', phase='ready', finished_at=time.time(), visited_count=report['placed_record_count'],
               report_sha256=digest(folder/'report.json'),
               summary={k: report[k] for k in ('placed_record_count', 'traversal_complete', 'all_placed_data_read', 'gap_count', 'metadata_only_types', 'partial_types')},
               part_count=len(report['parts']), frame_count=len(report['frames']),
               message='Đã lập hồ sơ toàn file. Xem mức bao phủ và các phần cần bổ sung trước khi sửa.')
    except Exception as error:
        update(status='failed', phase='failed', finished_at=time.time(), message='Chưa hoàn tất đọc toàn file: '+str(error))
    finally:
        with LOCK: ACTIVE.discard((document_id, job_id))


def report(document_id, job_id):
    data = read(document_id, job_id)
    if data['status'] != 'ready': raise ValueError('Hồ sơ toàn file chưa sẵn sàng.')
    path = job_folder(document_id, job_id)/'report.json'
    if digest(path) != data['report_sha256']: raise ValueError('Hồ sơ toàn file không còn khớp bằng chứng đã lưu; cần đọc lại.')
    return json.loads(path.read_text(encoding='utf8'))


def entities(document_id, job_id, *, offset=0, limit=50, layout='', kind='', query=''):
    if offset < 0 or not 1 <= limit <= 200: raise ValueError('Trang dữ liệu không hợp lệ.')
    result = report(document_id, job_id); matches = 0; records = []; text = query.casefold().strip()
    for page in result['pages']:
        path = job_folder(document_id, job_id)/page['file']
        if digest(path) != page['sha256']: raise ValueError('Dữ liệu hình học không còn khớp hồ sơ; cần đọc lại.')
        for record in json.loads(path.read_text(encoding='utf8')):
            if layout and record['layout'] != layout or kind and record['type'] != kind.upper(): continue
            if text and text not in json.dumps([record['ref'], record.get('native_part_code'), record.get('container_part_code'), record['facts']], ensure_ascii=False).casefold(): continue
            if offset <= matches < offset+limit: records.append(record)
            matches += 1
    return dict(source_hash=result['source_hash'], items=records, match_count=matches,
                next_offset=offset+limit if offset+limit < matches else None)


def planning_evidence(document_id, source_hash):
    """Expose checked inventory coverage to planning without enlarging edit scope.

    A missing/stale/failed scan must never become an implicit assertion that AI
    has seen the complete document. Large entity pages remain retrievable.
    """
    root = storage.folder(document_id)/'document-atlas'
    base = dict(status='not_read', complete_design_understanding=False, edit_authorized=False)
    for path in sorted(root.glob('*/job.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding='utf8'))
        if data.get('source_hash') != source_hash: continue
        try:
            state = read(document_id, data['id'])
            if state['status'] != 'ready': return dict(base, status=state['status'], job_id=data['id'])
            value = report(document_id, data['id'])
        except ValueError:
            return dict(base, status='stale', job_id=data['id'])
        return dict(base, status='ready', job_id=data['id'], source_hash=source_hash,
                    traversal_complete=value['traversal_complete'], all_placed_data_read=value['all_placed_data_read'],
                    placed_record_count=value['placed_record_count'], frame_count=len(value['frames']),
                    part_count=len(value['parts']), gap_count=value['gap_count'],
                    metadata_only_types=value['metadata_only_types'], partial_types=value['partial_types'],
                    graph_error=value['graph_error'],
                    retrieval_url=f'/documents/{document_id}/atlas/{data["id"]}/entities',
                    policy='Whole-file inventory coverage only. Inventory completion does not prove design intent, mechanical contact or permission to edit.')
    return base
