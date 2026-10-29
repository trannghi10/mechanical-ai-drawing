"""Local registry. Counts never equate downloads with engineering acceptance."""
import hashlib
import json
import threading
from collections import Counter
from pathlib import Path
from cad_dataset.models import Record, GROUPS

ROOT = Path(__file__).resolve().parents[1]/'storage/datasets/mechanical-dwg-v1'
LOCK=threading.RLock()


def sha256(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def safe_path(root, relative):
    root=Path(root).resolve();result=(root/relative).resolve()
    if result == root or root not in result.parents: raise ValueError('Đường dẫn ra ngoài thư mục dữ liệu.')
    return result


def asset_path(asset, root=None):
    root=ROOT if root is None else Path(root)
    if asset.storage == 'document':
        from backend.services.catalog_service import folder
        return safe_path(folder(asset.document_id),asset.path)
    return safe_path(root,asset.path)


def write_json(path,value):
    from backend.services.catalog_service import write_json as atomic
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);atomic(path,value)


def write(record, root=None):
    root=ROOT if root is None else Path(root)
    record=Record.model_validate(record)
    path=Path(root)/'records'/(record.id+'.json')
    if path.exists():
        previous=Record.model_validate_json(path.read_text(encoding='utf8'))
        if previous != record: raise ValueError('Hồ sơ đã tồn tại với nội dung khác; cần tạo phiên bản rõ ràng, không ghi đè nhãn/review.')
    else: write_json(path,record.model_dump())
    return record


def read_all(root=None):
    root=ROOT if root is None else Path(root)
    return [Record.model_validate_json(p.read_text(encoding='utf8')) for p in sorted((Path(root)/'records').glob('*.json'))]


def revise(record,expected_manifest_sha256,root=None):
    root=ROOT if root is None else Path(root)
    record=Record.model_validate(record);path=Path(root)/'records'/(record.id+'.json')
    with LOCK:
        if sha256(path)!=expected_manifest_sha256:raise ValueError('Hồ sơ đã thay đổi; cần đọc phiên bản mới trước cập nhật.')
        previous=Record.model_validate_json(path.read_text(encoding='utf8'))
        if (record.lineage_id,record.source_id)!=(previous.lineage_id,previous.source_id):raise ValueError('Không đổi nguồn/dòng gốc của hồ sơ hiện có.')
        before={a.id:a.sha256 for a in previous.assets if a.role=='original'}
        after={a.id:a.sha256 for a in record.assets if a.role=='original'}
        if before!=after:raise ValueError('CAD gốc bất biến; không ghi đè bằng file sau sửa.')
        write_json(Path(root)/'history'/record.id/(expected_manifest_sha256+'.json'),previous.model_dump())
        write_json(path,record.model_dump())
    return record


def verify_files(record,root=None):
    root=ROOT if root is None else Path(root)
    errors=[]
    for asset in record.assets:
        path=asset_path(asset,root)
        if not path.is_file():errors.append(asset.id+': missing')
        elif path.stat().st_size != asset.bytes or sha256(path) != asset.sha256:errors.append(asset.id+': hash/size mismatch')
    return errors


def accepted(record):
    return (record.dossier_review.status == 'approved' and record.group != 'unclassified'
            and record.group_review.status == 'approved' and record.rights.evaluation
            and any(a.role=='original' and a.format=='DWG' and a.validation in ('native_opened','native_roundtrip') for a in record.assets)
            and bool(record.labels) and all(l.review.status=='approved' for l in record.labels)
            and bool(record.relationships) and all(r.review.status=='approved' for r in record.relationships)
            and bool(record.edit_cases) and all(c.review.status=='approved' for c in record.edit_cases)
            and any(c.expected_outcome=='edit' and c.native_roundtrip=='passed' for c in record.edit_cases))


def split_errors(records):
    errors=[];groups={};hashes={};lineages={}
    for record in records:
        for table,key in ((groups,record.leakage_group),(lineages,record.lineage_id)):
            if record.split!='unassigned':table.setdefault(key,set()).add(record.split)
        if record.split!='unassigned':
            for asset in record.assets:
                if asset.format in ('DWG','DXF','STEP') and asset.role in ('original','before','after'):
                    hashes.setdefault(asset.sha256,set()).add(record.split)
    for kind,table in [('leakage_group',groups),('lineage',lineages),('cad_content',hashes)]:
        for key,splits in table.items():
            if len(splits)>1:errors.append(f'{kind} {key}: nằm ở nhiều split {sorted(splits)}')
    return errors


def status(root=None,verify=True):
    root=ROOT if root is None else Path(root)
    records=read_all(root);errors=split_errors(records);integrity={}
    if verify:
        for record in records:
            issues=verify_files(record,root)
            if issues:integrity[record.id]=issues
    # Same original bytes (including mirrors) count once. Views, layouts,
    # derivatives and generated variants never inflate the 500-DWG target.
    unique={};accepted_unique={}
    for record in records:
        dwgs=[a.sha256 for a in record.assets if a.role=='original' and a.format=='DWG']
        for digest in dwgs:
            unique.setdefault(digest,record)
            if verify and accepted(record) and record.id not in integrity:accepted_unique.setdefault(digest,record)
    accepted_lineages={r.lineage_id:r for r in accepted_unique.values()}
    accepted_groups=Counter(r.group for r in accepted_lineages.values())
    return dict(name='Mechanical DWG Intelligence Dataset – V1',target_dossiers=500,
        record_count=len(records),unique_dwg_files=len(unique),accepted_dwg_dossiers=len(accepted_lineages),
        origins=dict(Counter(r.origin for r in records)),splits=dict(Counter(r.split for r in records)),
        rights_pending=sum(r.rights.status in ('pending','restricted') for r in records),
        training_permission_unavailable=sum(not r.rights.training for r in records),
        redistribution_permission_unavailable=sum(not r.rights.redistribution for r in records),
        label_count=sum(len(r.labels) for r in records),relationship_count=sum(len(r.relationships) for r in records),
        edit_case_count=sum(len(r.edit_cases) for r in records),engineer_approved_edit_cases=sum(c.review.status=='approved' for r in records for c in r.edit_cases),
        dwg_roundtrip_cases=sum(c.native_roundtrip=='passed' for r in records for c in r.edit_cases),
        groups=[dict(id=k,name=v,target=50,records=sum(r.group==k for r in records),accepted=accepted_groups[k]) for k,v in GROUPS.items()],
        split_errors=errors,integrity_checked=verify,integrity_errors=integrity,
        training_ready=sum(verify and not errors and r.split=='train' and r.rights.training and r.dossier_review.status=='approved' and r.id not in integrity for r in records),
        engineering_acceptance_complete=len(accepted_lineages)>=500 and all(accepted_groups[k]>=50 for k in GROUPS) and not errors and verify and not integrity,
        note='500 là chỉ tiêu hồ sơ DWG được nghiệm thu. STEP/ảnh/nhãn tổng hợp, bản tải trùng và bản sửa không được đếm thành DWG nghiệm thu mới.')
