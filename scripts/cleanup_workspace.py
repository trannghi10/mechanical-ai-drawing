"""Archive disposable investigation code and receipt-proven synthetic uploads.

Regression tests, verifier scripts, original customer documents and backups
remain active. Dry-run by default; every removal has a verified ZIP copy.
"""
import argparse,hashlib,json,re,shutil,zipfile
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def checked(path):
    resolved=path.resolve()
    if resolved==ROOT or not resolved.is_relative_to(ROOT):raise ValueError('Outside workspace: '+str(path))
    if any(p.is_symlink() for p in [path,*path.parents] if p!=ROOT and p.is_relative_to(ROOT)):
        raise ValueError('Symlink target is not eligible: '+str(path))
    return resolved


def candidates():
    runtime='\n'.join(p.read_text(encoding='utf8',errors='replace') for group in ['backend','cad','bom','graph','ai','preview','frontend'] for p in (ROOT/group).rglob('*') if p.suffix in ('.py','.html','.js'))
    runtime+='\n'+'\n'.join(p.read_text(encoding='utf8',errors='replace') for p in (ROOT/'scripts').glob('*') if p.suffix in ('.py','.js') and p.name.startswith(('verify_','start_')))
    protected_ids=set()
    for group in ['backend','cad','bom','graph','ai','preview','frontend','scripts','tests']:
        for p in (ROOT/group).rglob('*'):
            if p.suffix in ('.py','.js','.html'):protected_ids.update(re.findall(r'\b[0-9a-f]{32}\b',p.read_text(encoding='utf8',errors='replace')))
    paths=[]
    # Keep current native host proof and compact published evidence accessible.
    for proof in [ROOT/'storage/autocad-host-check.json',*(ROOT/'storage/validation-fixtures').glob('*.json')]:
        if proof.is_file() and proof.stat().st_size<2_000_000:
            protected_ids.update(re.findall(r'\b[0-9a-f]{32}\b',proof.read_text(encoding='utf8',errors='replace')))
    for group in ['backend','cad','bom','graph','ai','preview','rules','scripts','tests']:
        paths.extend((ROOT/group).rglob('__pycache__'))
    if (ROOT/'.pytest_cache').is_dir():paths.append(ROOT/'.pytest_cache')
    logs=sorted((ROOT/'storage').glob('server-*.log'),key=lambda p:p.stat().st_mtime,reverse=True)
    paths.extend(logs[6:]) # keep recent/live server logs; never touch model/runtime files
    if (ROOT/'scratch').exists():paths.append(ROOT/'scratch')
    prefixes=('audit_','check_','debug_','inspect_','probe_','register_','recover_','render_','test_','trace_','find_')
    extras={'build_current_preview.py','build_projection_template.py','compile_current_backup.py','publish_checked_preview.py','print_sheet_texts.py','run_debug_measured.py'}
    for p in (ROOT/'scripts').glob('*.py'):
        referenced=p.name in runtime or re.search(r'(?:import\s+|from\s+(?:scripts\.)?)'+re.escape(p.stem)+r'\b',runtime)
        if (p.name.startswith(prefixes) or p.name in extras) and not referenced:paths.append(p)
    # Only uploads attested as synthetic by a stored receipt are eligible.
    receipts=[]
    for p in (ROOT/'storage/validation-fixtures').rglob('*receipt*.json'):
        try:
            data=json.loads(p.read_text(encoding='utf8'))
            rows=data if isinstance(data,list) else [data]
            for row in rows:
                if isinstance(row,dict) and row.get('synthetic') is True and re.fullmatch('[0-9a-f]{32}',row.get('document_id','')):
                    receipts.append((p,row['document_id']))
        except (ValueError,OSError):continue
    # Keep the newest evidence batch for each verification family available.
    latest={}
    for p,did in receipts:
        batch=next((x for x in p.parents if x.parent==ROOT/'storage/validation-fixtures'),None)
        if batch is None:continue
        family=re.sub(r'-[0-9a-f]{8}$','',batch.name)
        if family not in latest or batch.stat().st_mtime>latest[family].stat().st_mtime:latest[family]=batch
    keep={did for p,did in receipts if any(batch in p.parents for batch in latest.values())}
    for did in sorted({did for _,did in receipts}-keep-protected_ids):
        folder=ROOT/'storage/documents'/did
        if not (folder/'status.json').is_file():continue
        status=json.loads((folder/'status.json').read_text(encoding='utf8'))
        if status.get('status')!='ready':continue
        # Independent second check, not a loose "test" substring in a customer name.
        name=Path(status.get('filename','')).name.lower()
        if not re.fullmatch(r'(?:unseen(?:-[a-z-]+)?|synthetic-general|new-hole)-[0-9a-f]{8,32}\.(?:dwg|dxf)',name):continue
        if any(json.loads(p.read_text(encoding='utf8')).get('status') in ('queued','running') for p in (folder/'planning-jobs').glob('*.json')):continue
        paths.append(folder)
    # Old native host checks and repeated Autodesk sample runs have two explicit
    # attestations: a synthetic status flag AND an exact known generator name.
    for folder in (ROOT/'storage/documents').iterdir():
        if folder.name in protected_ids or not re.fullmatch('[0-9a-f]{32}',folder.name):continue
        status_file=folder/'status.json'
        if not status_file.is_file():continue
        status=json.loads(status_file.read_text(encoding='utf8'))
        if status.get('status') not in ('ready','failed'):continue
        if status.get('source_kind')!='synthetic_test' and status.get('synthetic_test') is not True:continue
        if status.get('filename') not in ('synthetic-autocad-host-check.dxf','synthetic-autodesk-dynamic.dwg'):continue
        paths.append(folder)
    # Avoid archiving/removing a child twice when its parent is also disposable.
    unique=sorted({checked(p) for p in paths},key=lambda p:len(p.parts))
    selected=[]
    for p in unique:
        if not any(p.is_relative_to(parent) for parent in selected):selected.append(p)
    return selected


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    paths=candidates()
    if args.apply:
        import sys
        sys.path.insert(0,str(ROOT))
        from backend.services.database_service import connection,decode
        with connection() as db:
            active={did for did,payload in db.execute('SELECT document_id,payload FROM aps_jobs')
                    if decode(payload).get('status') not in ('ready','failed')}
        paths=[p for p in paths if p.parent!=ROOT/'storage/documents' or p.name not in active]
    files=[f for p in paths for f in (p.rglob('*') if p.is_dir() else [p]) if f.is_file()]
    report=dict(paths=[str(p.relative_to(ROOT)) for p in paths],file_count=len(files),bytes=sum(f.stat().st_size for f in files),regression_tests_preserved=True,customer_documents_preserved=True)
    if not args.apply:print(json.dumps(report,ensure_ascii=False,indent=2));return
    if not paths:
        report['retained_synthetic_uploads_hidden']=mark_retained_synthetic()
        print(json.dumps(report,ensure_ascii=False));return
    folder=ROOT/'storage/archives'/('cleanup-'+datetime.now().strftime('%Y%m%d-%H%M%S'));folder.mkdir(parents=True)
    archive=folder/'recoverable.zip';manifest=[]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in files:
            checked(f);entry=str(f.relative_to(ROOT)).replace('\\','/')
            content=f.read_bytes();manifest.append(dict(path=entry,size=len(content),sha256=hashlib.sha256(content).hexdigest()));z.writestr(entry,content)
    with zipfile.ZipFile(archive) as z:
        for entry in manifest:
            if hashlib.sha256(z.read(entry['path'])).hexdigest()!=entry['sha256']:raise ValueError('Archive verification failed')
    report.update(archive=str(archive.relative_to(ROOT)),manifest=manifest,retained_synthetic_uploads_hidden=mark_retained_synthetic())
    (folder/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    for p in paths:
        checked(p)
        if p.is_dir():shutil.rmtree(p)
        else:p.unlink()
    # Remove only indexes belonging to the synthetic folders just archived.
    deleted_ids=[p.name for p in paths if p.parent==ROOT/'storage/documents']
    if deleted_ids:
        import sys
        sys.path.insert(0,str(ROOT))
        from backend.services.database_service import connection
        index_backup=[]
        with connection() as db:
            for did in deleted_ids:
                rows={}
                for table,column in [('aps_jobs','document_id'),('cad_files','document_id'),('cad_revisions','document_id'),('cad_documents','id')]:
                    rows[table]=[list(row) for row in db.execute(f'SELECT * FROM {table} WHERE {column}=?',(did,))]
                job_ids=[row[0] for row in rows['aps_jobs']]
                rows['aps_artifacts']=[list(row) for jid in job_ids for row in db.execute('SELECT * FROM aps_artifacts WHERE job_id=?',(jid,))]
                for jid in job_ids:db.execute('DELETE FROM aps_artifacts WHERE job_id=?',(jid,))
                for table,column in [('aps_jobs','document_id'),('cad_files','document_id'),('cad_revisions','document_id'),('cad_documents','id')]:
                    db.execute(f'DELETE FROM {table} WHERE {column}=?',(did,))
                index_backup.append(dict(document_id=did,rows=rows))
            (folder/'database-index.json').write_text(json.dumps(index_backup,ensure_ascii=False,indent=2),encoding='utf8')
        report['synthetic_document_indexes_removed']=len(deleted_ids)
        (folder/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('manifest','paths')},ensure_ascii=False))


def mark_retained_synthetic():
    """Hide receipt-proven test uploads via the existing show-tests toggle."""
    ids=set()
    for p in (ROOT/'storage/validation-fixtures').rglob('*receipt*.json'):
        try:
            data=json.loads(p.read_text(encoding='utf8'))
            for row in data if isinstance(data,list) else [data]:
                if isinstance(row,dict) and row.get('synthetic') is True and re.fullmatch('[0-9a-f]{32}',row.get('document_id','')):ids.add(row['document_id'])
        except (OSError,ValueError):continue
    marked=[]
    for did in sorted(ids):
        file=ROOT/'storage/documents'/did/'status.json'
        if not file.is_file():continue
        checked(file);data=json.loads(file.read_text(encoding='utf8'))
        if data.get('synthetic_test') is True:continue
        data['synthetic_test']=True
        temp=file.with_suffix('.cleanup.tmp');temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8');temp.replace(file);marked.append(did)
    return marked


if __name__=='__main__':main()
