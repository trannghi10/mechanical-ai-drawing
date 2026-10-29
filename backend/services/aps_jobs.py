"""APS jobs survive browser reloads and resume submitted work after restart.

Existing geometric planning remains local. APS supplies native extraction,
bounded edits, DWG save and DXF readback, never an inferred design guarantee.
"""
import hashlib
from dataclasses import replace
import json
import re
import shutil
import threading
import time
import uuid
import zipfile
import httpx
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.services import aps_repository as repository
from backend.services import catalog_service as storage
from backend.services.aps_client import APSClient, APSError, Settings
from cad.edit_engine import digest

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='aps')
_lock = threading.RLock()
_active = set()
ARTIFACTS = {'modified.dwg', 'roundtrip.dxf', 'receipt.json', 'inventory.json'}
TERMINAL = {'ready', 'failed'}


class NativeOperation(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    action: Literal['replace_text', 'set_dynamic_property', 'table_cell', 'translate_centermark', 'stretch_rectangle']
    handle: str = Field(pattern=r'^[0-9A-F]{1,16}$')
    owner_handle: str = Field(pattern=r'^[0-9A-F]{1,16}$')
    expected_type: str = Field(pattern=r'^[A-Za-z0-9_]{1,80}$')
    before: str | float
    after: str | float
    property: str = Field(default='', max_length=160)
    row: int = Field(default=-1, ge=-1, le=100000)
    column: int = Field(default=-1, ge=-1, le=1000)
    instance_path: list[str] = Field(default_factory=list, max_length=8)
    mark_handle: str = Field(default='', pattern=r'^(?:[0-9A-F]{1,16})?$')
    action_handle: str = Field(default='', pattern=r'^(?:[0-9A-F]{1,16})?$')
    dimension_handle: str = Field(default='', pattern=r'^(?:[0-9A-F]{1,16})?$')
    association_handle: str = Field(default='', pattern=r'^(?:[0-9A-F]{1,16})?$')

    @model_validator(mode='after')
    def shape(self):
        if self.action=='stretch_rectangle':
            from cad.rectangle_stretch import validate_operation
            validate_operation(self.model_dump())
        elif self.dimension_handle or self.association_handle:
            raise ValueError('Rectangle handles only apply to rectangle stretch.')
        if self.instance_path and (self.action!='set_dynamic_property' or len(self.instance_path)<2
                or self.instance_path[-1]!=self.handle or len(set(self.instance_path))!=len(self.instance_path)
                or any(not re.fullmatch(r'[0-9A-F]{1,16}',h) for h in self.instance_path)):
            raise ValueError('Đường dẫn instance lồng không hợp lệ; chỉ dùng cho tham số block động.')
        if any(isinstance(value,str) and len(value)>20000 for value in (self.before,self.after)):
            raise ValueError('Giá trị text native vượt giới hạn 20.000 ký tự.')
        if self.action == 'set_dynamic_property':
            if not self.property or type(self.before) is not type(self.after):
                raise ValueError('Tham số block động phải có tên, cùng kiểu giá trị trước và sau.')
        elif not isinstance(self.before, str) or not isinstance(self.after, str):
            raise ValueError('Text/ô bảng phải dùng chuỗi trước và sau.')
        if self.action == 'table_cell' and (self.row < 0 or self.column < 0):
            raise ValueError('Cần chỉ rõ hàng và cột của ô bảng.')
        if self.action == 'translate_centermark':
            import math
            try:
                points = [json.loads(v) for v in (self.before, self.after)]
                if not all(isinstance(p,list) and len(p)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in p) for p in points):
                    raise ValueError()
                if abs(points[0][2]-points[1][2])>1e-10 or math.dist(*points)<=1e-10:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('CenterMark cần tâm trước/sau hữu hạn, dịch trong mặt phẳng XY và khác nhau.')
            if not self.mark_handle or not self.action_handle or len({self.handle,self.mark_handle,self.action_handle})!=3 or self.expected_type!='CIRCLE':
                raise ValueError('CenterMark cần đúng handle đường tròn, dấu tâm và action khác nhau.')
        elif self.mark_handle or self.action_handle:
            raise ValueError('Handle CenterMark chỉ dùng cho phép dịch CenterMark.')
        return self


def _job_dir(document_id, job_id):
    if not re.fullmatch('[a-f0-9]{32}', job_id):
        raise ValueError('ID tác vụ APS không hợp lệ.')
    return storage.folder(document_id) / 'aps-jobs' / job_id


def public(job):
    result = {key: job.get(key) for key in (
        'id', 'document_id', 'mode', 'status', 'message', 'created', 'revision_id',
        'source_hash', 'derivative_status', 'native_summary', 'artifact_hashes')}
    result['target_ids']=job.get('target_ids',[])
    result['provider']=job.get('provider','aps')
    for key in ('created_by','updated_by'):
        if key in job:result[key]=job[key]
    result['complete_product_backup'] = False
    route='autocad' if job.get('provider')=='autocad' else 'aps'
    result['download_url'] = (
        f'/documents/{job["document_id"]}/{route}/jobs/{job["id"]}/files/modified.dwg'
        if job['status'] == 'ready' and job['mode'] != 'inspect' else None)
    result['inventory_url'] = (
        f'/documents/{job["document_id"]}/{route}/jobs/{job["id"]}/files/inventory.json'
        if job['status'] == 'ready' else None)
    return result


def rectangle_settings():
    """Dedicated registered rectangle activity; preserve the ordinary cloud alias."""
    cfg=Settings.load()
    return replace(cfg,activity=cfg.activity.rsplit('+',1)[0]+'+rectangle_mvp')


def start(document_id, *, mode='inspect', source=None, revision_id=None, operations=(), scope_handles=(), expected_source_hash=None, target_ids=(),provider='aps'):
    if provider not in ('aps','autocad'):raise ValueError('Native CAD provider không hợp lệ.')
    if mode=='recover' and provider!='autocad':raise ValueError('Phục hồi nguồn chỉ hỗ trợ AutoCAD trên máy.')
    if provider=='aps':
        Settings.load().check()  # Check BEFORE creating jobs or moving files.
        cfg=Settings.load();runtime=dict(bucket=cfg.bucket,region=cfg.region,activity=cfg.activity)
    else:
        from backend.services.autocad_host import ready
        runtime={'runtime_key':ready()['runtime_key']}
    path = storage.folder(document_id)
    if source is None:
        source = next((p for p in (path / 'original.dwg', path / 'original.dxf') if p.is_file()), None)
    if source is None:
        raise FileNotFoundError('Không có CAD nguồn.')
    source = Path(source).resolve()
    if not source.is_relative_to(path.resolve()) or source.suffix.lower() not in ('.dwg', '.dxf'):
        raise ValueError('Nguồn APS nằm ngoài tài liệu.')
    if mode not in ('inspect', 'convert', 'edit','recover') or (mode == 'edit' and not operations):
        raise ValueError('Chế độ APS không hợp lệ.')
    if mode=='recover' and source.suffix.lower()!='.dwg':raise ValueError('Chỉ phục hồi nguồn DWG; DXF không dùng luồng này.')
    if mode != 'edit' and operations:
        raise ValueError('Chế độ này không nhận lệnh sửa.')
    ops = [NativeOperation.model_validate(op).model_dump() for op in operations]
    scopes = sorted(set(scope_handles))
    center_ops=[op for op in ops if op['action']=='translate_centermark']
    rectangle_ops=[op for op in ops if op['action']=='stretch_rectangle']
    if rectangle_ops:
        if len(ops)!=1 or source.suffix.lower()!='.dwg' or set(scopes)!={ops[0]['handle'],ops[0]['dimension_handle']}:
            raise ValueError('Rectangle stretch requires one DWG operation with exactly polyline and DIM selected.')
        if provider=='aps':
            cfg=rectangle_settings();cfg.check();runtime=dict(bucket=cfg.bucket,region=cfg.region,activity=cfg.activity)
    if center_ops:
        from cad.native_centermark import validate_group
        if provider!='autocad':raise ValueError('Dịch CenterMark chỉ hỗ trợ AutoCAD local.')
        validate_group(ops,scopes)
    def ref(op):return '/'.join(op['instance_path']) if op['instance_path'] else op['handle']
    if any(ref(op) not in scopes for op in ops):
        raise ValueError('Lệnh sửa native nằm ngoài phạm vi đã chọn.')
    if len({(ref(op), op['action'], op['property'], op['row'], op['column']) for op in ops}) != len(ops):
        raise ValueError('Lệnh sửa native trùng lặp.')
    snapshot = digest(source)
    if expected_source_hash is not None and snapshot != expected_source_hash:
        raise ValueError('Nguồn native đã đổi từ khi đọc; cần đọc lại trước khi sửa.')
    contract = dict(schema_version=1, mode=mode, source_sha256=snapshot,
                    input_name='input' + source.suffix.lower(), scope_handles=scopes, operations=ops,
                    target_ids=sorted(set(target_ids)))
    contract_bytes = json.dumps(contract, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf8')
    command_hash = hashlib.sha256(contract_bytes).hexdigest()
    with _lock:
        for job in repository.list_jobs(document_id):
            if (job.get('command_hash') == command_hash and job.get('revision_id') == revision_id
                    and job.get('provider','aps')==provider and all(job.get(key)==value for key,value in runtime.items())
                    and job['status'] != 'failed'):
                if job['status'] == 'ready':
                    try:
                        artifact(document_id, job['id'], 'receipt.json')
                    except (ValueError, FileNotFoundError):
                        continue
                _schedule(job)
                return public(job)
        job_id = uuid.uuid4().hex
        folder = _job_dir(document_id, job_id)
        folder.mkdir(parents=True)
        shutil.copyfile(source, folder / contract['input_name'])
        if digest(folder / contract['input_name']) != snapshot:
            raise ValueError('Nguồn đã đổi trong lúc tạo tác vụ APS.')
        (folder / 'commands.json').write_bytes(contract_bytes)
        job = dict(id=job_id, document_id=document_id, mode=mode, status='queued',
                   message='Đang chờ AutoCAD trên máy.' if provider=='autocad' else 'Đang chờ gửi CAD lên Autodesk.', source_hash=snapshot,
                   source_relative=str(source.relative_to(path.resolve())), input_name=contract['input_name'],
                   command_hash=command_hash, revision_id=revision_id,
                   target_ids=contract['target_ids'],
                   provider=provider,**runtime)
        repository.save(job)
        _schedule(job)
        return public(job)


def _schedule(job):
    if job['status'] not in TERMINAL and job['id'] not in _active:
        _active.add(job['id'])
        from backend.services.job_context import submit
        submit(_pool,_advance_local if job.get('provider')=='autocad' else _advance, job['document_id'], job['id'],actor=job.get('created_by'))


def _advance_local(document_id,job_id):
    try:
        from backend.services.autocad_host import ready,execute
        job=repository.read(document_id,job_id);folder=_job_dir(document_id,job_id)
        if ready()['runtime_key']!=job['runtime_key']:raise ValueError('AutoCAD/plugin đã đổi sau khi tạo tác vụ; cần tạo lại.')
        if digest(folder/job['input_name'])!=job['source_hash'] or digest(folder/'commands.json')!=job['command_hash']:
            raise ValueError('Snapshot/lệnh AutoCAD trên máy đã đổi; cần tạo lại.')
        if job.get('execution_started'):
            if not (folder/'result.zip').is_file():
                raise ValueError('Server ngắt khi AutoCAD đang chạy. Kiểm tra tiến trình/log tác vụ trước khi tạo lại; chưa chạy trùng lần nữa.')
        else:
            job['execution_started']=True;_save(job,'processing','AutoCAD Core Console đang xử lý trên máy; CAD không gửi ra cloud.')
            job['local_execution']=execute(folder)
        _save(job,'validating','Đang kiểm tra DWG/DXF do AutoCAD trên máy mở lại.')
        _accept_result(job,folder)
        _save(job,'ready','Đã có DWG phục hồi riêng. Cần tải và đối chiếu với nguồn trước khi dùng làm đầu vào chỉnh sửa; đây chưa phải bản sửa thiết kế.' if job['mode']=='recover' else 'Đã có kết quả AutoCAD trên máy; phần liên kết chưa kiểm chứng vẫn chưa được duyệt.')
    except Exception as error:
        job=repository.read(document_id,job_id)
        _save(job,'failed',str(error) if isinstance(error,ValueError) else 'AutoCAD trên máy chưa hoàn tất; xem log tác vụ và kiểm tra plugin/license.')
    finally:
        with _lock:_active.discard(job_id)


def _save(job, status, message):
    job.update(status=status, message=message)
    repository.save(job)


def _advance(document_id, job_id):
    client = None
    try:
        job = repository.read(document_id, job_id)
        folder = _job_dir(document_id, job_id)
        commands=json.loads((folder/'commands.json').read_text(encoding='utf8'))
        is_rectangle=any(op.get('action')=='stretch_rectangle' for op in commands.get('operations',[]))
        cfg = rectangle_settings() if is_rectangle else Settings.load()
        if any(job[key] != getattr(cfg, key) for key in ('bucket', 'region', 'activity')):
            raise APSError('Cấu hình APS đã đổi; tạo tác vụ mới thay vì dùng workitem của cấu hình cũ.')
        client = APSClient(cfg)
        if digest(folder / job['input_name']) != job['source_hash'] or digest(folder / 'commands.json') != job['command_hash']:
            raise ValueError('Snapshot/lệnh APS đã đổi; cần tạo lại tác vụ.')
        if not job.get('workitem_id'):
            # An interrupted submit is ambiguous: never submit twice and bill twice.
            if job.get('submit_started'):
                raise ValueError('Server ngắt khi gửi workitem. Kiểm tra APS trước khi tạo lại để tránh tính phí hai lần.')
            _save(job, 'uploading', 'Đang tải bản sao CAD và lệnh đã kiểm tra lên Autodesk.')
            prefix = document_id + '/' + job_id + '/'
            job.update(input_key=prefix + job['input_name'], command_key=prefix + 'commands.json',
                       output_key=prefix + 'result.zip')
            client.bucket()
            object_id = client.upload(job['input_key'], folder / job['input_name'])
            client.upload(job['command_key'], folder / 'commands.json')
            # Derivatives are viewer data. Native inventory is the edit authority.
            if job['mode'] == 'inspect' and not job.get('derivative_urn'):
                try:
                    job['derivative_urn'] = client.translate(object_id)
                    job['derivative_status'] = 'submitted'
                except APSError:
                    job['derivative_status'] = 'failed; native extraction continues'
            job['submit_started'] = True
            _save(job, 'submitting', 'Đang gửi tác vụ AutoCAD Automation.')
            job['workitem_id'] = client.submit(job['input_key'], job['command_key'], job['output_key'])
            _save(job, 'processing', 'AutoCAD đang đọc/sửa và lưu bản sao CAD.')
        remote = client.workitem(job['workitem_id'])
        state = remote.get('status', '')
        if state == 'success':
            _save(job, 'validating', 'Đang tải và kiểm tra kết quả AutoCAD.')
            client.download(job['output_key'], folder / 'result.zip')
            _accept_result(job, folder)
            if job.get('derivative_urn'):
                try:
                    response = client.manifest(job['derivative_urn'])
                    job['derivative_status'] = response.json().get('status', 'pending') if response.is_success else 'pending'
                except (APSError,httpx.HTTPError):
                    # A failed viewer translation must not invalidate native CAD.
                    job['derivative_status']='pending; native CAD ready'
            _save(job, 'ready', 'Đã có kết quả native. Bản sửa vẫn cần kiểm chứng đầy đủ trước khi dùng sản xuất.')
        elif state not in ('pending', 'inprogress'):
            raise APSError('AutoCAD Automation không hoàn tất (' + str(state)[:60] + '). Kiểm tra workitem trên APS.')
        else:
            _save(job, 'processing', 'AutoCAD Automation đang xử lý; có thể đóng trang rồi mở lại.')
    except Exception as error:
        try:
            job = repository.read(document_id, job_id)
            message = str(error) if isinstance(error, ValueError) and not isinstance(error, httpx.HTTPError) else 'Không kết nối/đọc được APS. Kiểm tra mạng và cấu hình; chưa có DWG mới.'
            _save(job, 'failed', message)
        except FileNotFoundError:
            pass
    finally:
        if client:
            client.close()
        with _lock:
            _active.discard(job_id)


def _accept_result(job, folder):
    with zipfile.ZipFile(folder / 'result.zip') as archive:
        files = archive.infolist()
        if (len(files) != len(ARTIFACTS) or {entry.filename for entry in files} != ARTIFACTS
                or sum(entry.file_size for entry in files) > 600 * 1024 * 1024
                or any(entry.flag_bits & 1 for entry in files)):
            raise ValueError('Gói APS thiếu file hoặc có đường dẫn/kích thước không hợp lệ.')
        candidate = folder / 'candidate'
        candidate.mkdir(exist_ok=True)
        for entry in files:
            with archive.open(entry) as source, (candidate / entry.filename).open('wb') as target:
                shutil.copyfileobj(source, target)
    receipt = json.loads((candidate / 'receipt.json').read_text(encoding='utf-8-sig'))
    inventory = json.loads((candidate / 'inventory.json').read_text(encoding='utf-8-sig'))
    commands = json.loads((folder / 'commands.json').read_text(encoding='utf8'))
    if (receipt.get('schema_version') != 1 or receipt.get('source_sha256') != job['source_hash']
            or receipt.get('commands_sha256') != job['command_hash'] or receipt.get('status') != 'validated'
            or receipt.get('mode') != job['mode']
            or receipt.get('applied_operations') != len(commands['operations'])):
        raise ValueError('Biên bản AutoCAD không khớp nguồn hoặc lệnh đã gửi.')
    with (candidate / 'modified.dwg').open('rb') as stream:
        if stream.read(6) != b'AC1032':
            raise ValueError('Kết quả APS không phải DWG 2018.')
    for name in ('modified.dwg', 'roundtrip.dxf', 'inventory.json'):
        if digest(candidate / name) != receipt.get('hashes', {}).get(name):
            raise ValueError('Hash file kết quả APS không khớp biên bản.')
    if not isinstance(inventory.get('blocks'), list) or not isinstance(inventory.get('entities'), list):
        raise ValueError('Thiếu inventory native của AutoCAD.')
    center_ops=[op for op in commands['operations'] if op['action']=='translate_centermark']
    if any(op['action']=='stretch_rectangle' for op in commands['operations']):
        from cad.rectangle_stretch import verify_result
        if job.get('provider') not in ('autocad','aps') or (job.get('provider')=='aps' and not job.get('activity','').endswith('+rectangle_mvp')):
            raise ValueError('Rectangle result requires the dedicated registered rectangle provider.')
        verify_result(commands['operations'],inventory,candidate/'roundtrip.dxf',job['source_hash'],digest(candidate/'modified.dwg'))
    if center_ops:
        from cad.native_centermark import verify_results
        if job.get('provider')!='autocad':
            raise ValueError('Kết quả CenterMark không thuộc thao tác local riêng biệt.')
        verify_results(commands['operations'],inventory,candidate/'roundtrip.dxf',job['source_hash'],digest(candidate/'modified.dwg'))
    if job['mode']=='recover' and (receipt.get('source_recovered') is not True or receipt.get('recovery_review_required') is not True):
        raise ValueError('Bản phục hồi thiếu cờ đối chiếu dữ liệu nguồn.')
    if job['mode'] == 'convert':
        # Conversion itself must not turn an incomplete plan into a complete one.
        from cad.catalog import load_document
        from cad.geometry import snapshot, near
        from collections import Counter
        original = load_document(str(folder / job['input_name']))
        reopened = load_document(str(candidate / 'roundtrip.dxf'))
        if Counter((layout.name, entity.dxftype()) for layout in original.layouts for entity in layout) != Counter(
                (layout.name, entity.dxftype()) for layout in reopened.layouts for entity in layout):
            raise ValueError('AutoCAD làm thay đổi inventory layout trong bước lưu DWG.')
        # Full edit-specific checks also run in revision_service.export_dwg.
        for entity in original.modelspace():
            if entity.dxftype() in ('LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE'):
                actual = reopened.entitydb.get(entity.dxf.handle)
                if actual is None or not near(snapshot(entity), snapshot(actual), 1e-6):
                    raise ValueError('AutoCAD làm thay đổi hình học trong bước chuyển định dạng.')
    job['artifact_hashes'] = {name: digest(candidate / name) for name in ARTIFACTS}
    job['native_summary'] = {key: inventory.get(key) for key in ('summary', 'warnings', 'dynamic_effects','centermark_effects')}
    rectangle=inventory.get('rectangle_stretch_effects')
    rectangle_op=next((op for op in commands['operations'] if op['action']=='stretch_rectangle'),None)
    if rectangle and rectangle_op:
        effect=dict(rectangle)
        before=json.loads(rectangle_op['before'])
        effect['source_width_mm']=before[1][0]-before[0][0]
        job['native_summary']['rectangle_stretch_effects']=effect
    result = folder / 'result'
    if result.exists():
        raise ValueError('Kết quả APS đã tồn tại; không ghi đè phiên bản đã lưu.')
    candidate.rename(result)
    for name, sha256 in job['artifact_hashes'].items():
        repository.artifact(job['id'], name, result / name, sha256)


def read(document_id, job_id):
    with _lock:
        job = repository.read(document_id, job_id)
        _schedule(job)
        return public(job)


def artifact(document_id, job_id, name):
    if name not in ARTIFACTS:
        raise ValueError('Tên file APS không hợp lệ.')
    job = repository.read(document_id, job_id)
    if job['status'] != 'ready':
        raise ValueError('Tác vụ APS chưa hoàn tất kiểm tra.')
    source = storage.folder(document_id) / job['source_relative']
    if not source.resolve().is_relative_to(storage.folder(document_id).resolve()):
        raise ValueError('Đường dẫn nguồn APS không hợp lệ.')
    if not source.is_file() or digest(source) != job['source_hash']:
        raise ValueError('Nguồn CAD đã đổi; không dùng kết quả APS của phiên bản cũ.')
    file = _job_dir(document_id, job_id) / 'result' / name
    if not file.is_file() or digest(file) != job.get('artifact_hashes', {}).get(name):
        raise ValueError('File APS đã đổi hoặc không còn; không cho tải bản sai hash.')
    return file


def convert_revision(document_id, revision_id, source, output, check, timeout=1200,provider='aps'):
    from cad.edit_engine import separate_output
    separate_output(source,Path(output)/'modified.dwg',Path(check)/'modified.dxf')
    conversion_source=source
    normalization=None
    if provider=='autocad':
        from backend.services.autocad_dxf_input import conversion_input
        conversion_source,normalization=conversion_input(document_id,source)
    job = start(document_id, mode='inspect' if normalization else 'convert', source=conversion_source, revision_id=revision_id,provider=provider)
    job=wait(document_id,job['id'],timeout=timeout)
    if normalization:
        from cad.catalog import load_document
        from cad.empty_ole import verify
        original=load_document(str(source));actual=load_document(str(artifact(document_id,job['id'],'roundtrip.dxf')))
        from collections import Counter
        if Counter((l.name,e.dxf.handle,e.dxftype()) for l in original.layouts for e in l)!=Counter((l.name,e.dxf.handle,e.dxftype()) for l in actual.layouts for e in l):
            raise ValueError('CAD bridge changed layout inventory')
        verify(original,actual,normalization)
    shutil.copyfile(artifact(document_id, job['id'], 'modified.dwg'), Path(output) / 'modified.dwg')
    shutil.copyfile(artifact(document_id, job['id'], 'roundtrip.dxf'), Path(check) / 'modified.dxf')
    return job['id']


def wait(document_id, job_id, timeout=1200):
    deadline = time.monotonic() + timeout
    while True:
        job = read(document_id, job_id)
        if job['status'] == 'failed':
            raise APSError(job['message'])
        if job['status'] == 'ready':
            return job
        if time.monotonic() > deadline:
            raise APSError('APS chưa xong trong thời gian chờ. Tác vụ đã lưu; bấm xuất lại để tiếp tục theo dõi.')
        time.sleep(0.5 if job.get('provider') == 'autocad' else 2)


def import_source(document_id, source, progress=None,provider='aps'):
    """Native cloud read -> immutable readback DXF used by the existing gallery."""
    source=Path(source)
    job=start(document_id,mode='inspect',source=source,provider=provider)
    if progress:progress(job['id'])
    job=wait(document_id,job['id'])
    native_dxf=artifact(document_id,job['id'],'roundtrip.dxf')
    output=storage.folder(document_id)/('autocad-converted' if provider=='autocad' else 'aps-converted')/job['id']/'original.dxf'
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        if digest(output)!=digest(native_dxf):raise ValueError('DXF native đã lưu bị thay đổi; không ghi đè.')
    else:
        temporary=output.with_suffix('.part')
        shutil.copyfile(native_dxf,temporary)
        if digest(temporary)!=digest(native_dxf):raise ValueError('DXF native sao chép không khớp hash.')
        temporary.replace(output)
    return output,job['id']


def refresh_derivative(document_id,job_id):
    """Explicit refresh after native job completion; no new translation/billing job."""
    with _lock:
        job=repository.read(document_id,job_id)
        if job['status']!='ready' or not job.get('derivative_urn'):
            raise ValueError('Chưa có kết quả native/Model Derivative để kiểm tra.')
        artifact(document_id,job_id,'receipt.json')
        client=APSClient()
        try:
            if any(job[key]!=getattr(client.cfg,key) for key in ('bucket','region','activity')):
                raise APSError('Cấu hình APS đã đổi từ khi gửi tác vụ.')
            response=client.manifest(job['derivative_urn'])
            job['derivative_status']=response.json().get('status','pending') if response.is_success else 'pending'
            if job['derivative_status']=='success':
                metadata=client.metadata(job['derivative_urn'])
                if metadata.status_code==200:
                    raw=metadata.content
                    if len(raw)>8*1024*1024:raise ValueError('Metadata viewer vượt giới hạn 8 MB.')
                    result=metadata.json()
                    views=result.get('data',{}).get('metadata',[])
                    job['derivative_views']=[{key:row.get(key) for key in ('guid','name','role')} for row in views]
            repository.save(job)
            return dict(status=job['derivative_status'],views=job.get('derivative_views',[]),
                        note='Viewer metadata không thay thế native handles hoặc bằng chứng lắp ghép.')
        finally:client.close()
