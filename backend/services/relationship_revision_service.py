"""Local repair revisions with evidence and a non-destructive undo/redo cursor."""
import json,shutil,subprocess,sys,threading,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from backend.services import catalog_service as storage,relationship_repair_service as proposals,aps_jobs
from cad.edit_engine import digest

ROOT=Path(__file__).resolve().parents[2];POOL=ThreadPoolExecutor(max_workers=1);LOCK=threading.RLock()


def recover_interrupted():
    """The local single-process backend never resumes a half-written DWG job."""
    for path in storage.ROOT.glob('*/revisions/*/revision.json'):
        try:
            r=json.loads(path.read_text(encoding='utf8'))
            if r.get('kind')=='relationship_repair' and r.get('status') in ('queued','running'):
                r.update(status='failed',dwg_ready=False,error='Backend restarted during repair; create a fresh revision. Original is preserved.')
                storage.write_json(path,r)
        except (ValueError,OSError):continue


def _path(document_id,revision_id):
    return storage.folder(document_id)/'revisions'/proposals._id(revision_id)


def history(document_id):
    folder=storage.folder(document_id);source_hash=digest(folder/'original.dwg');path=folder/'relationship-history.json'
    result=json.loads(path.read_text()) if path.exists() else dict(version=0,cursor=-1,entries=[],source_sha256=source_hash)
    if result['source_sha256']!=source_hash:raise ValueError('Source changed; relationship history is stale')
    result['active_revision_id']=result['entries'][result['cursor']] if result['cursor']>=0 else None
    result['pending_revision']=_pending_revision(document_id)
    return result


def read(document_id,revision_id):
    folder=_path(document_id,revision_id);r=json.loads((folder/'revision.json').read_text())
    if r.get('kind')!='relationship_repair' or r.get('id')!=revision_id or r.get('document_id')!=document_id:raise ValueError('Invalid relationship revision')
    if digest(storage.folder(document_id)/'original.dwg')!=r['source_hash']:raise ValueError('Revision source changed')
    if r['status']=='ready':
        for name,expected in r['artifact_hashes'].items():
            if digest(folder/name)!=expected:raise ValueError('Revision artifact changed: '+name)
    return r


def _pending_revision(document_id):
    for p in sorted((storage.folder(document_id)/'revisions').glob('*/revision.json')):
        r=json.loads(p.read_text(encoding='utf8'))
        if r.get('kind')=='relationship_repair' and r.get('status') in ('queued','running'):
            return dict(id=p.parent.name,status=r['status'])
    return None


def _pending(document_id):
    return _pending_revision(document_id) is not None


def move(document_id,direction,expected_version):
    with LOCK:
        h=history(document_id)
        if h['version']!=expected_version:raise ValueError('History changed; refresh before undo/redo')
        if _pending(document_id):raise ValueError('Wait for the running repair before undo/redo')
        target=h['cursor']+(-1 if direction=='undo' else 1)
        if direction not in ('undo','redo') or target< -1 or target>=len(h['entries']):raise ValueError('No revision to '+direction)
        if target>=0:read(document_id,h['entries'][target])
        h.update(cursor=target,version=h['version']+1)
        h.pop('active_revision_id',None);h.pop('pending_revision',None);storage.write_json(storage.folder(document_id)/'relationship-history.json',h)
        return history(document_id)


def start(document_id,proposal_id,expected_version):
    proposal,_=proposals.read(document_id,proposal_id)
    if proposal.get('adapter')=='native_pointrefs' and proposal.get('schema_version')!=3:
        raise ValueError('Recreate native proposal to derive the current execution scope')
    from backend.services import autocad_host
    autocad_host.ready()
    with LOCK:
        h=history(document_id)
        if h['version']!=expected_version:raise ValueError('History changed; refresh before applying')
        if proposal.get('adapter')=='native_pointrefs' and h['active_revision_id']!=proposal['base']['revision_id']:
            raise ValueError('Select the proposal base revision before applying native references')
        if _pending(document_id):raise ValueError('A relationship repair is already running')
        revision_id=uuid.uuid4().hex;folder=_path(document_id,revision_id);folder.mkdir(parents=True)
        r=dict(id=revision_id,document_id=document_id,kind='relationship_repair',plan_id=proposal_id,status='queued',
               source_hash=proposal['source_sha256'],proposal_scope_sha256=proposal['scope_sha256'],base_history_version=h['version'],
               targets=[],root_target_ids=[],complete_product_backup=False,dwg_ready=False,
               preview_only_reason='Bản sửa liên kết để kiểm tra; chưa xác nhận ý đồ cơ khí và hình thức OLE/dung sai.',
               release_gate=dict(allowed=False),artifact_hashes={})
        if proposal.get('adapter')=='native_pointrefs':r.update(adapter='native_pointrefs',base_revision_id=proposal['base']['revision_id'])
        storage.write_json(folder/'revision.json',r)
        from backend.services.job_context import submit
        submit(POOL,_work,document_id,revision_id,proposal)
        return r


def _run(script,args,folder,label):
    with (folder/(label+'.log')).open('w',encoding='utf8') as log:
        done=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts'/script),*map(str,args)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                            timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    lines=(folder/(label+'.log')).read_text(encoding='utf8').splitlines()
    if done.returncode:raise ValueError(label+' failed; see revision evidence log')
    result=json.loads(next(line for line in reversed(lines) if line.startswith('{')))
    output=Path(result['output']).resolve();fixtures=(ROOT/'storage/validation-fixtures').resolve()
    if not output.is_relative_to(fixtures):raise ValueError('Worker output outside evidence storage')
    return output


def _work(document_id,revision_id,proposal):
    folder=_path(document_id,revision_id);path=folder/'revision.json';r=json.loads(path.read_text())
    try:
        r['status']='running';storage.write_json(path,r)
        current,_=proposals.read(document_id,proposal['id'])
        if current['scope_sha256']!=proposal['scope_sha256']:raise ValueError('Proposal changed before execution')
        if proposal.get('adapter')=='native_pointrefs':
            _native_work(document_id,revision_id,proposal,r,folder)
            return
        args=[document_id,proposal['plan']['polyline_handle'],'--inspection-job',proposal['inspection_id']]
        native_report=_run('probe_native_polyline_dimensions.py',[*args,'--inspect-subentities'],folder,'native-endpoints')
        from scripts.probe_native_polyline_dimensions import inspection_group
        from cad.native_action_review import review as native_review
        baseline,group=inspection_group(document_id,proposal['inspection_id'],proposal['plan']['polyline_handle'],proposal['source_sha256'])
        group['source_sha256']=proposal['source_sha256']
        native_data=json.loads((native_report/'poly-dim-subentities.json').read_text())
        r['native_endpoint_review']=native_review(baseline,group,native_data)
        control=_run('repair_native_dimension_relationships.py',[*args,'--control-only'],folder,'control')
        control_receipt=json.loads((control/'repair-receipt.json').read_text())
        if control_receipt['source_sha256']!=proposal['source_sha256'] or control_receipt['status']!='validated_noop_control':raise ValueError('Control receipt mismatch')
        source_dxf=aps_jobs.artifact(document_id,proposal['inspection_id'],'roundtrip.dxf')
        with (folder/'outside-source-audit.log').open('w',encoding='utf8') as log:
            audit=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/audit_relationship_control.py'),str(source_dxf),str(control)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if audit.returncode:raise ValueError('Outside source/control content audit failed')
        repaired=_run('repair_native_dimension_relationships.py',[*args,'--control-evidence',control],folder,'repair')
        receipt=json.loads((repaired/'repair-receipt.json').read_text())
        if receipt['source_sha256']!=proposal['source_sha256'] or receipt['repaired_endpoint_count']!=2:raise ValueError('Repair receipt does not match proposal')
        for name,destination in [('relationship-repair.dwg','modified.dwg'),('relationship-repair.dxf','modified.dxf')]:shutil.copyfile(repaired/name,folder/destination)
        evidence=folder/'evidence';evidence.mkdir()
        for label,directory in [('control',control),('repair',repaired)]:
            dest=evidence/label;dest.mkdir()
            for source in directory.glob('*.json'):shutil.copyfile(source,dest/source.name)
        storage.write_json(evidence/'proposal.json',proposal)
        storage.write_json(evidence/'native-subentities.json',native_data)
        storage.write_json(evidence/'native-endpoint-review.json',r['native_endpoint_review'])
        for name in ('modified.dwg','modified.dxf'):r['artifact_hashes'][name]=digest(folder/name)
        for source in evidence.rglob('*.json'):r['artifact_hashes'][source.relative_to(folder).as_posix()]=digest(source)
        if digest(folder/'modified.dwg')!=receipt['output_sha256']:raise ValueError('Repair output hash mismatch')
        proposals.read(document_id,proposal['id'])
        with LOCK:
            h=history(document_id)
            if h['version']!=r['base_history_version']:raise ValueError('History changed during repair')
            r.update(status='ready',dwg_ready=True,source_unchanged=True,validation=receipt)
            storage.write_json(path,r)
            entries=h['entries'][:h['cursor']+1]+[revision_id]
            storage.write_json(storage.folder(document_id)/'relationship-history.json',dict(version=h['version']+1,cursor=len(entries)-1,entries=entries,source_sha256=h['source_sha256']))
    except Exception as error:
        r.update(status='failed',dwg_ready=False,error=str(error));storage.write_json(path,r)


def _native_work(document_id,revision_id,proposal,r,folder):
    """Run a fresh repair plus 8 endpoint and 4 isolated native-B challenges."""
    with (folder/'native-repair.log').open('w',encoding='utf8') as log:
        done=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/probe_native_point_references.py'),
            '--customer-copy','--base-ready-revision','--document-id',document_id,'--base-revision-id',proposal['base']['revision_id'],'--proposal-id',proposal['id']],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if done.returncode:raise ValueError('Native point-reference repair failed; see revision log')
    result=json.loads(next(line for line in reversed((folder/'native-repair.log').read_text().splitlines()) if line.startswith('{')))
    run=Path(result['evidence']).resolve()
    if not run.is_relative_to((ROOT/'storage/acwork').resolve()):raise ValueError('Unexpected native repair evidence location')
    validation=json.loads((run/'validation.json').read_text())
    if validation['source_sha256']!=proposal['base']['dwg_sha256'] or validation['bridge_sha256']!=proposal['base']['bridge_sha256']:
        raise ValueError('Native adapter/base receipt mismatch')
    batch=[];challenge_paths=[];first=None
    for dimension in validation['bindings']:
        for endpoint in ('A','B'):
            for step in (10,-10):
                args=[run,'--dimension',dimension,'--check-native-pointrefs','--endpoint',endpoint,'--step',step]
                output=_run('challenge_repaired_dimensions.py',args,folder,f'challenge-{dimension}-{endpoint}-{step}')
                challenge_paths.append(output)
                if first is None:first=output
                else:batch.append(dict(returncode=0,output=json.dumps(dict(output=str(output)))))
    storage.write_json(run/'challenge-batch.json',batch)
    verified=_run('finalize_native_point_reference_probe.py',[run,'--first-challenge',first],folder,'native-finalize')
    isolated=[];isolation_first=None
    for dimension in validation['bindings']:
        for step in (10,-10):
            output=_run('challenge_repaired_dimensions.py',[run,'--dimension',dimension,'--check-native-pointrefs','--endpoint','B','--step',step,'--native-b-only'],
                        folder,f'native-b-only-{dimension}-{step}')
            challenge_paths.append(output)
            if isolation_first is None:isolation_first=output
            else:isolated.append(dict(returncode=0,output=json.dumps(dict(output=str(output)))))
    storage.write_json(run/'native-b-isolation-batch.json',isolated)
    _run('finalize_native_b_isolation.py',[run,verified/'verification.json','--first-challenge',isolation_first],folder,'native-b-finalize')
    receipt=json.loads((verified/'verification.json').read_text())
    if receipt['native_b_isolation']['challenge_count']!=4 or len(receipt['challenges'])!=8:raise ValueError('Incomplete dynamic native reference validation')
    evidence=folder/'evidence';evidence.mkdir()
    storage.write_json(evidence/'proposal.json',proposal)
    for source in verified.glob('*.json'):shutil.copyfile(source,evidence/source.name)
    for source in run.glob('*.json'):shutil.copyfile(source,evidence/('probe-'+source.name))
    for i,directory in enumerate(challenge_paths):
        dest=evidence/('challenge-'+str(i));dest.mkdir()
        for source in directory.glob('*.json'):shutil.copyfile(source,dest/source.name)
    for name,destination in [('native-dim-links-verified.dwg','modified.dwg'),('native-dim-links-verified.dxf','modified.dxf')]:
        shutil.copyfile(verified/name,folder/destination)
        if digest(folder/destination)!=receipt['artifact_sha256'][name]:raise ValueError('Native artifact changed')
        r['artifact_hashes'][destination]=digest(folder/destination)
    for source in evidence.rglob('*.json'):r['artifact_hashes'][source.relative_to(folder).as_posix()]=digest(source)
    proposals.read(document_id,proposal['id'])
    with LOCK:
        h=history(document_id)
        if h['version']!=r['base_history_version'] or h['active_revision_id']!=proposal['base']['revision_id']:
            raise ValueError('History/base changed during native reference repair')
        receipt.update(revision_integration_complete=True,customer_revision_created=True)
        r.update(status='ready',dwg_ready=True,source_unchanged=True,validation=receipt,
                 native_endpoint_review=dict(unresolved_count=0,endpoints=[],coverage='Two new A references verified with native B retained; design intent remains unconfirmed.'))
        storage.write_json(folder/'revision.json',r)
        entries=h['entries'][:h['cursor']+1]+[revision_id]
        storage.write_json(storage.folder(document_id)/'relationship-history.json',dict(version=h['version']+1,cursor=len(entries)-1,entries=entries,source_sha256=h['source_sha256']))


def artifact(document_id,revision_id,name):
    r=read(document_id,revision_id)
    if r['status']!='ready' or name not in ('modified.dwg','modified.dxf'):raise ValueError('Revision file unavailable')
    return _path(document_id,revision_id)/name


def preview(document_id,revision_id):
    import ezdxf
    r=read(document_id,revision_id)
    if r['status']!='ready':raise ValueError('Revision preview unavailable')
    folder=_path(document_id,revision_id)
    proposal=json.loads((folder/'evidence/proposal.json').read_text(encoding='utf8'))
    return proposals.render_group(ezdxf.readfile(folder/'modified.dxf'),proposal['plan'])
