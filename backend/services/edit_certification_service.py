"""Engineer-issued, bounded edit-family certificates. No built-in certificates.

A certificate binds the current implementation, its numeric envelope and at
least two independently sourced, manually approved native benchmark results.
It is not a model confidence score or a per-revision engineer signature.
"""
import hashlib
import importlib.metadata
import json
import math
import time
import uuid
from pathlib import Path
from filelock import FileLock
from pydantic import BaseModel,ConfigDict,Field,model_validator
from typing import Literal
from backend.services import catalog_service as storage,account_service as accounts
from cad.edit_engine import digest


class Benchmark(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    revision_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    output_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    dwg_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_result_review:str=Field(min_length=12,max_length=2000)


class CertificateRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    family:Literal['linear_profile_resize_2d']
    title:str=Field(min_length=8,max_length=160)
    min_measurement_mm:float=Field(gt=0)
    max_measurement_mm:float=Field(gt=0)
    max_delta_mm:float=Field(gt=0)
    max_operations:int=Field(ge=1,le=2000)
    valid_days:int=Field(ge=1,le=90)
    benchmarks:list[Benchmark]=Field(min_length=2,max_length=40)
    engineer_accepts_expected_results:Literal[True]

    @model_validator(mode='after')
    def bounds(self):
        if self.min_measurement_mm>self.max_measurement_mm:raise ValueError('Khoảng kích thước không hợp lệ')
        if len({(b.document_id,b.revision_id) for b in self.benchmarks})!=len(self.benchmarks):
            raise ValueError('Không lặp cùng ca kiểm chứng')
        return self


def root():return storage.ROOT.parent/'edit-certifications'


def fingerprint():
    """Code and solver dependency identity; no environment secrets included."""
    project=Path(__file__).resolve().parents[2]
    h=hashlib.sha256()
    for directory in ('cad','graph','backend/services'):
        for path in sorted((project/directory).glob('*.py')):
            h.update(path.relative_to(project).as_posix().encode());h.update(path.read_bytes())
    for pattern in ('backend/*.py','autodesk/MechanicalCad/*.cs','autodesk/MechanicalCad/*.csproj',
                    'autodesk/NativePointReference/*.cpp'):
        for path in sorted(project.glob(pattern)):
            h.update(path.relative_to(project).as_posix().encode());h.update(path.read_bytes())
    for name in ('ezdxf','numpy','scipy','shapely','pydantic'):
        try:version=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:version='unavailable'
        h.update((name+':'+version).encode())
    return h.hexdigest()


def integrity(value):
    return hashlib.sha256(json.dumps({k:v for k,v in value.items() if k!='integrity'},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def engineer():
    actor=accounts.ACTOR.get()
    if not actor or actor.get('role') not in ('engineer','admin'):
        raise accounts.AccountError(403,'Cần kỹ sư hoặc quản trị viên đã đăng nhập để chứng nhận loại sửa.')
    return {k:actor[k] for k in ('id','username','role')}


def profile(proposal,context):
    """Narrow family; current CAD validators still check every actual edit."""
    plan=proposal.get('plan',{});recipes=plan.get('resize_recipes',[])
    if proposal.get('planner')!='checked_measured_profile_resize' or not recipes or plan.get('questions') or context.get('units')!=4:
        return None
    if any(value for key,value in plan.items() if key.endswith('_recipes') and key!='resize_recipes'):return None
    records={e['ref']:e for e in context['entities']};values=[]
    from graph.fit_constraints import measurement
    for recipe in recipes:
        dim=records.get(recipe['dimension_ref'],{})
        if dim.get('type')!='DIMENSION' or dim.get('dimension_type') not in (0,1) or dim.get('linear_factor',1)!=1:return None
        for ref in recipe['outline_refs']:
            e=records.get(ref,{})
            if e.get('type') not in ('LINE','LWPOLYLINE','POLYLINE'):return None
            if e['type']!='LINE' and any(any(p[2:]) for p in e.get('geometry',{}).get('points',[])):return None
        old=measurement(dim,dim.get('geometry',{}));new=recipe.get('new_measurement')
        if not all(type(v) in (float,int) and math.isfinite(v) and v>0 for v in (old,new)):return None
        values.append((old,new))
    allowed={'LINE','LWPOLYLINE','POLYLINE','CIRCLE','DIMENSION','TEXT','MTEXT','ATTRIB','ACAD_TABLE','GRAPHIC_TABLE'}
    for op in plan.get('operations',[]):
        if op['action'] not in ('replace_geometry','replace_text','table_cell') or records.get(op['ref'],{}).get('type') not in allowed:return None
    return dict(family='linear_profile_resize_2d',min_measurement_mm=min(min(v) for v in values),
                max_measurement_mm=max(max(v) for v in values),max_delta_mm=max(abs(a-b) for a,b in values),
                operation_count=len(plan['operations']))


def fits(certificate,actual):
    return bool(actual and certificate['family']==actual['family'] and
        certificate['min_measurement_mm']<=actual['min_measurement_mm'] and
        certificate['max_measurement_mm']>=actual['max_measurement_mm'] and
        certificate['max_delta_mm']>=actual['max_delta_mm'] and
        certificate['max_operations']>=actual['operation_count'])


def source_context(document_id,proposal):
    from backend.services.change_service import context_for
    folder=storage.folder(document_id)
    return context_for(folder/storage.read_status(document_id)['dxf'],proposal['targets'],proposal.get('review_only_ids',[]))


def issue(request):
    actor=engineer();request=CertificateRequest.model_validate(request);evidence=[];sources=set();converters=set()
    from backend.services import release_review_service as release,revision_service as revisions
    for benchmark in request.benchmarks:
        # The benchmark review is intentionally the raw evidence report.  Calling
        # the gate here would only re-enter certificate matching while a new
        # certificate is being issued.
        result=release.review(benchmark.document_id,benchmark.revision_id,include_gate=False)
        if any(c['status']!='passed' for c in result['checks'] if c['id']!='certification'):
            raise ValueError('Ca nghiệm thu chưa đạt nguồn, phạm vi, duyệt thủ công và DWG mở lại.')
        path,data=revisions.read_revision(benchmark.document_id,benchmark.revision_id)
        if data.get('approval_kind')=='certified_auto':raise ValueError('Ca chứng nhận phải được kỹ sư duyệt thủ công.')
        if data['validation']['output_hash']!=benchmark.output_hash or data['dwg_validation']['dwg_hash']!=benchmark.dwg_hash:
            raise ValueError('Ca nghiệm thu không khớp hash kỹ sư đã đối chiếu.')
        folder=storage.folder(benchmark.document_id)
        proposal=json.loads((folder/'change-plans'/(data['plan_id']+'.json')).read_text(encoding='utf8'))
        if not fits(request.model_dump(),profile(proposal,source_context(benchmark.document_id,proposal))):
            raise ValueError('Ca nghiệm thu không thuộc loại sửa hoặc khoảng áp dụng của chứng nhận.')
        sources.add(data['validation']['source_hash'])
        converters.add(data['dwg_validation']['converter'])
        evidence.append(dict(benchmark.model_dump(),plan_id=data['plan_id'],source_hash=data['validation']['source_hash'],
                             source_preservation=data['source_preservation']))
    if len(sources)<2:raise ValueError('Cần ít nhất hai nguồn CAD độc lập, không chỉ hai revision của cùng file.')
    if len(converters)!=1:raise ValueError('Các ca chứng nhận phải dùng cùng một backend native.')
    value=dict(request.model_dump(exclude={'benchmarks'}),id=uuid.uuid4().hex,status='active',issuer=actor,
               issued_at=int(time.time()),expires_at=int(time.time())+request.valid_days*86400,
               engine_fingerprint=fingerprint(),native_converter=next(iter(converters)),benchmarks=evidence)
    value['integrity']=integrity(value);root().mkdir(exist_ok=True)
    with FileLock(str(root()/'registry.lock')):storage.write_json(root()/(value['id']+'.json'),value)
    return value


def revoke(certificate_id,reason):
    actor=engineer()
    from backend.services.revision_service import safe_id
    path=root()/(safe_id(certificate_id)+'.json')
    with FileLock(str(root()/'registry.lock')):
        value=json.loads(path.read_text(encoding='utf8'))
        if value.get('integrity')!=integrity(value):raise ValueError('Chứng nhận không còn nguyên vẹn.')
        value.update(status='revoked',revoked_at=int(time.time()),revoked_by=actor,revocation_reason=reason)
        value['integrity']=integrity(value);storage.write_json(path,value)
    return value


def listing():
    result=[]
    for path in sorted(root().glob('*.json')):
        value=json.loads(path.read_text(encoding='utf8'))
        result.append({k:value.get(k) for k in ('id','family','title','status','issuer','issued_at','expires_at','engine_fingerprint')})
    return result


def matching(proposal,context,native_converter=None):
    actual=profile(proposal,context)
    if not actual:return None
    files=sorted(root().glob('*.json'))
    if not files:return None
    current=fingerprint();members={u['id']:u for u in accounts.users()}
    for file in files:
        value=json.loads(file.read_text(encoding='utf8'))
        if (value.get('integrity')!=integrity(value) or value.get('status')!='active' or
            value.get('expires_at',0)<=time.time() or value.get('engine_fingerprint')!=current):continue
        if native_converter is not None and value.get('native_converter')!=native_converter:continue
        issuer=members.get(value.get('issuer',{}).get('id'),{})
        if not issuer.get('active') or issuer.get('role') not in ('engineer','admin') or not fits(value,actual):continue
        try:
            for b in value['benchmarks']:
                from backend.services.revision_service import read_revision
                path,data=read_revision(b['document_id'],b['revision_id']);folder=storage.folder(b['document_id'])
                if (data.get('approval_kind')=='certified_auto' or data.get('approved_hash')!=b['output_hash'] or
                    digest(path/'modified.dxf')!=b['output_hash'] or digest(path/'export/modified.dwg')!=b['dwg_hash']):
                    raise ValueError('Ca nghiệm thu đã đổi')
                for source in b['source_preservation']['files']:
                    candidate=(folder/source['filename']).resolve()
                    if not candidate.is_relative_to(folder.resolve()) or digest(candidate)!=source['sha256']:
                        raise ValueError('Nguồn nghiệm thu đã đổi')
        except (ValueError,OSError,KeyError,TypeError):continue
        return {k:value[k] for k in ('id','family','title','engine_fingerprint','issuer','expires_at')}
    return None
