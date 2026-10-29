"""Dataset ingestion uses the existing local CAD pipeline; never APS/cloud."""
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from cad_dataset import store
from cad_dataset.models import Asset, Evidence, Record, Rights, Label
from cad_dataset.collect import asset

COMPANY_IDS=('51ec94944c4443b19fb8d5bd7930a6dd','1c7d831296ff402bb1a838479063a99d',
             '17466fcb1c59489985408c027ef56611','baf461e9c2764a5ba9000a48772f846c')


def register_company(root=store.ROOT):
    from backend.services import catalog_service as storage
    root=Path(root);results=[]
    for did in COMPANY_IDS:
        rid='company-'+did
        if (root/'records'/(rid+'.json')).exists():continue
        folder=storage.folder(did);status=storage.read_status(did);original=folder/'original.dwg'
        if not original.is_file():continue
        source=store.sha256(original);metadata=root/'source-evidence'/('company-'+did+'.json')
        store.write_json(metadata,dict(document_id=did,source_sha256=source,read_backend=status.get('read_backend'),
            native_dxf_hash=status.get('native_dxf_hash'),permission='Existing company drawings authorized for local project evaluation in this conversation. No training or redistribution permission inferred.'))
        assets=[Asset(id='original',path='original.dwg',sha256=source,bytes=original.stat().st_size,format='DWG',role='original',storage='document',document_id=did,
            validation='native_opened' if status.get('read_backend')=='autocad' and status.get('status')=='ready' else 'signature_checked'),
            asset(root,metadata,'local-provenance','JSON','source_metadata')]
        record=Record(id=rid,title=status.get('filename',did),source_id='company_internal',source_url='internal://documents/'+did,
            lineage_id='company:'+source,leakage_group='company:'+source,origin='company',assets=assets,
            evidence=[Evidence(id='internal-permission',asset_id='local-provenance',kind='license')],
            rights=Rights(status='internal_evaluation',evidence_ids=['internal-permission'],evaluation=True),
            notes=['Tham chiếu CAD gốc trong kho nội bộ; không sao chép vào gói công khai.','Chưa có nhãn kỹ sư hoặc đáp án chỉnh sửa được nghiệm thu cho dataset này.'])
        store.write(record,root);results.append(rid)
    return results


def inspect_dwgs(root=store.ROOT):
    from backend.services import catalog_service as storage
    from cad.catalog import load_document,CAD_LOCK
    from cad.document_atlas import scan
    root=Path(root);results=[]
    for record in store.read_all(root):
        if record.origin=='company' or not record.rights.evaluation:continue
        original=next((a for a in record.assets if a.role=='original' and a.format=='DWG'),None)
        if not original or original.validation in ('native_opened','native_roundtrip'):continue
        failures=store.verify_files(record,root)
        if failures:raise ValueError('Hồ sơ không khớp hash: '+record.id)
        manifest=root/'records'/(record.id+'.json');previous=store.sha256(manifest)
        state_file=root/'ingestion'/(record.id+'.json')
        if state_file.exists():
            state=json.loads(state_file.read_text(encoding='utf8'));did=state['document_id']
            if state['original_sha256']!=original.sha256:raise ValueError('Snapshot nhập dataset thay đổi.')
        else:
            did=uuid.uuid4().hex;folder=storage.ROOT/did;folder.mkdir(parents=True)
            shutil.copyfile(store.asset_path(original,root),folder/'original.dwg')
            if store.sha256(folder/'original.dwg')!=original.sha256:raise ValueError('Bản sao nhập AutoCAD sai hash.')
            storage.write_json(folder/'status.json',dict(id=did,filename=record.title,status='queued',read_backend='autocad',auxiliary=True,dataset_record_id=record.id))
            store.write_json(state_file,dict(document_id=did,original_sha256=original.sha256))
        status=storage.read_status(did)
        if status['status']!='ready':
            # Explicit provider, not the configured default (which may be APS).
            storage.process(did,storage.folder(did)/'original.dwg');status=storage.read_status(did)
        if status['status']!='ready':
            results.append(dict(record_id=record.id,status='failed',message=status.get('error','Read failed')));continue
        if status.get('read_backend')!='autocad':raise ValueError('Dataset chỉ cho phép đọc CAD trên máy.')
        dxf=storage.folder(did)/status['dxf'];destination=root/'assets'/record.id/'native.dxf'
        if destination.exists() and store.sha256(destination)!=store.sha256(dxf):raise ValueError('DXF dataset có sẵn khác bản đọc mới; không ghi đè.')
        if not destination.exists():shutil.copyfile(dxf,destination)
        readback=asset(root,destination,'native-dxf','DXF','native_dxf');records=[]
        with CAD_LOCK:reading=scan(load_document(dxf),records.append)
        report_path=root/'assets'/record.id/'reading-report.json'
        reading.update(original_sha256=original.sha256,native_dxf_sha256=readback.sha256,provider='autocad',document_id=did,
                       design_intent_confirmed=False,engineering_review='pending',customer_data_sent_to_cloud=False)
        store.write_json(report_path,reading)
        verification=asset(root,report_path,'native-reading','JSON','verification')
        record.assets.extend([readback,verification])
        record.evidence.append(Evidence(id='native-reading-evidence',asset_id=verification.id,kind='source_metadata'))
        for i,entity in enumerate(e for e in records if e['type']=='DIMENSION' and e['role']=='drawing'):
            eid=f'native-dim-{i}'
            record.evidence.append(Evidence(id=eid,asset_id=readback.id,kind='native_ref',ref=entity['ref']))
            facts=entity['facts'];value=facts.get('scaled_measurement',facts.get('actual_measurement'))
            record.labels.append(Label(id=eid,kind='dimension',value=str(value) if value is not None else facts.get('text','') or 'Native DIM, measurement unavailable',evidence_ids=[eid]))
        original.validation='native_opened'
        if store.sha256(store.asset_path(original,root))!=original.sha256:raise ValueError('CAD gốc thay đổi sau đọc.')
        record.notes.append('Đã mở bằng AutoCAD local và đọc DXF. Chưa có đáp án kỹ sư, chưa tạo cặp before/after hoặc chứng nhận sửa liên động.')
        store.revise(record,previous,root)
        results.append(dict(record_id=record.id,status='native_opened',placed_records=reading['placed_record_count'],dimensions=sum(e['type']=='DIMENSION' for e in records)))
    store.write_json(root/'native-ingestion-report.json',dict(results=results,provider='autocad',cad_uploaded_to_cloud=False))
    return results


def pack(root=store.ROOT):
    root=Path(root);eligible=[r for r in store.read_all(root) if r.origin!='company' and r.rights.redistribution]
    for record in eligible:
        if store.verify_files(record,root):raise ValueError('Không đóng gói file sai hash: '+record.id)
    files={name for name in ('README.md','sources.json','targets.json','record.schema.json','edit-task-templates.json') if (root/name).is_file()}
    for record in eligible:
        files.add('records/'+record.id+'.json')
        for entry in record.assets:
            if entry.storage!='dataset':raise ValueError('Không đóng gói tham chiếu CAD nội bộ.')
            files.add(entry.path)
    output=root/'mechanical-dwg-v1-starter.zip';temporary=output.with_suffix('.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(files):archive.write(store.safe_path(root,relative),relative)
        archive.writestr('PACKAGE.json',json.dumps(dict(exported_records=[r.id for r in eligible],
            contains_company_files=False,contains_engineering_ground_truth=any(r.dossier_review.status=='approved' for r in eligible),
            note='Chỉ dữ liệu ngoài có quyền phân phối được ghi nhận. Các record và nhãn vẫn chờ nghiệm thu kỹ sư.'),ensure_ascii=False,indent=2))
    temporary.replace(output)
    return dict(path=str(output),sha256=store.sha256(output),bytes=output.stat().st_size,exported_records=len(eligible),excluded_records=len(store.read_all(root))-len(eligible))
