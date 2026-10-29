"""Company DWG regression on isolated copies; local AutoCAD, never production release."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from cad.edit_engine import digest

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8765'
CASES=[
    dict(key='mr106',source_document_id='1c7d831296ff402bb1a838479063a99d',part_code='8.1.05940.126',
         request='Mã 8.1.05940.126 giảm chiều dài thành 15 mm; sửa cả hai chiều, giữ tâm lỗ, áp dụng trực tiếp cho DIM thực tế',
         intent_evidence='source document design-decisions-v1.json: c271d55d243e42c08860001dfe727ae0, user answer: DIM thuc te phai con dung 15 mm. Ca hai DIM -> 15 mm, giu tam lo.'),
    dict(key='leg6949',source_document_id='baf461e9c2764a5ba9000a48772f846c',part_code='8.1.07011.002',
         request='Mã 8.1.07011.002 đổi độ dày hộp từ 2 thành 1.2 mm, giữ kích thước ngoài và chiều dài; đồng bộ các chi tiết lắp bên trong theo khe hở nguồn',
         intent_evidence='Existing company request: tube 30x60 wall 2 -> 1.2 mm, keep outside size and fit. No unknown foam identity/datum approved.'),
]


def api(method,path,**kwargs):
    response=requests.request(method,BASE+path,timeout=900,**kwargs)
    if not response.ok:raise RuntimeError(f'{response.status_code}: {response.text[:1800]}')
    return response.json()


def require_local():
    capabilities=api('GET','/cad/capabilities');ai=api('GET','/ai/status')
    if capabilities.get('read_backend')!='autocad' or capabilities.get('export_backend')!='autocad' or ai.get('local_only') is not True:
        raise ValueError('Company regression requires local CAD import/export and local-only AI; no cloud fallback permitted')
    return dict(read_backend='autocad',export_backend='autocad',ai_local_only=True)


def save(path,value):
    path=Path(path);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)


def save_case(path,case):
    from filelock import FileLock
    path=Path(path)
    with FileLock(str(path)+'.lock'):
        run=json.loads(path.read_text(encoding='utf8'))
        run['cases']=[case if c['key']==case['key'] else c for c in run['cases']]
        save(path,run)


def wait_document(did):
    deadline=time.monotonic()+900;previous=None
    while time.monotonic()<deadline:
        state=api('GET',f'/documents/{did}')
        if state['status']!=previous:
            print(json.dumps(dict(document_id=did,status=state['status'])),flush=True);previous=state['status']
        if state['status']=='ready':
            if state.get('read_backend')!='autocad':raise ValueError('Company test must use local AutoCAD')
            return state
        if state['status']=='failed':raise ValueError(state.get('error',state.get('message','Native import failed')))
        time.sleep(2)
    raise ValueError('Local AutoCAD import timed out; job retained')


def prepare():
    require_local()
    host=api('GET','/autocad/status')
    if not host['configured'] or host.get('read_backend')!='autocad':raise ValueError('Local AutoCAD required')
    root=ROOT/'storage/validation-fixtures'/('company-whole-file-'+uuid.uuid4().hex[:12]);root.mkdir(parents=True)
    run=dict(id=root.name,status='preparing',cloud_used=False,synthetic=False,production_release=False,cases=[])
    save(root/'run.json',run);print(str(root),flush=True)
    from backend.services import catalog_service as storage
    for spec in CASES:
        source=ROOT/'storage/documents'/spec['source_document_id']/'original.dwg'
        case=dict(spec,source_sha256=digest(source),source_bytes=source.stat().st_size,status='uploading')
        run['cases'].append(case);save(root/'run.json',run)
        try:
            with source.open('rb') as stream:
                uploaded=api('POST','/documents',files={'file':('COMPANY-TEST-'+spec['key']+'.dwg',stream,'application/octet-stream')})
            case['document_id']=uploaded['id'];save(root/'run.json',run)
            state=wait_document(uploaded['id']);folder=storage.folder(uploaded['id'])
            state.update(auxiliary=True,company_regression=True,source_document_id=spec['source_document_id']);storage.write_json(folder/'status.json',state)
            assert digest(folder/'original.dwg')==case['source_sha256']
            case.update(status='imported',native_import_job_id=state['native_import_job_id'],dxf=state['dxf'],dxf_sha256=digest(folder/state['dxf']))
            api('GET',f'/documents/{uploaded["id"]}/catalog');frames=api('GET',f'/documents/{uploaded["id"]}/sheets')['items']
            case['detected_frame_count']=len(frames)
            job=api('POST',f'/documents/{uploaded["id"]}/planning-jobs',json=dict(whole_document=True,request=spec['request']))
            case.update(status='planning',planning_job_id=job['id'])
        except Exception as error:case.update(status='failed',message=str(error))
        save(root/'run.json',run)
    run['status']='prepared';save(root/'run.json',run)
    print(json.dumps(dict(run=str(root.relative_to(ROOT)),cases=run['cases']),ensure_ascii=True),flush=True)


def inspect(run_path):
    run_path=Path(run_path).resolve();run=json.loads(run_path.read_text(encoding='utf8'))
    for case in run['cases']:
        if not case.get('planning_job_id'):continue
        job=api('GET',f'/documents/{case["document_id"]}/planning-jobs/{case["planning_job_id"]}')
        case['planning_status']=job['status'];case['planning_message']=job['message']
        if case['status'] not in ('applying','exporting','exported','verified','execute_failed','reopen_failed'):case['status']=job['status']
        if job['status']=='ready':
            plan=api('GET',f'/documents/{case["document_id"]}/change-plans/{job["plan_id"]}')
            case.update(plan_id=plan['id'],execution_available=plan['execution_available'],preview_available=plan.get('preview_execution_available',False),
                        planner=plan.get('planner'),questions=plan['plan']['questions'],seed_codes=plan.get('impact_graph',{}).get('seed_codes'),
                        root_target_ids=plan['root_target_ids'],expanded_target_ids=plan['target_ids'],operation_count=len(plan['plan']['operations']))
        print(json.dumps(case,ensure_ascii=True),flush=True)
    save(run_path,run)


def replan(run_path,key=None):
    require_local()
    run_path=Path(run_path).resolve();run=json.loads(run_path.read_text(encoding='utf8'))
    for case in run['cases']:
        if key and case['key']!=key:continue
        if not case.get('document_id') or not case.get('dxf'):continue
        if case.get('planning_job_id'):
            old=api('GET',f'/documents/{case["document_id"]}/planning-jobs/{case["planning_job_id"]}')
            if old['status'] in ('queued','running'):raise ValueError('Previous job still running')
            case.setdefault('attempts',[]).append(old)
        job=api('POST',f'/documents/{case["document_id"]}/planning-jobs',json=dict(whole_document=True,request=case['request']))
        case.update(status='planning',planning_job_id=job['id'])
        save(run_path,run);print(json.dumps(dict(case=case['key'],job_id=job['id'])),flush=True)


def execute(run_path,key,partial=False,scope='document'):
    require_local()
    run_path=Path(run_path).resolve();run=json.loads(run_path.read_text(encoding='utf8'))
    case=next(c for c in run['cases'] if c['key']==key);did=case['document_id']
    job=api('GET',f'/documents/{did}/planning-jobs/{case["planning_job_id"]}')
    if job['status']!='ready':raise ValueError('Planning not ready: '+job['message'])
    plan=api('GET',f'/documents/{did}/change-plans/{job["plan_id"]}')
    if partial:
        if plan['execution_available'] or not plan.get('preview_execution_available'):raise ValueError('No separate checked partial preview')
    elif not plan['execution_available']:raise ValueError('Full request blocked: '+'; '.join(plan['plan']['questions']))
    if plan['target_resolution']['part_codes']!=[case['part_code']]:raise ValueError('Wrong source identity')
    case.update(plan_id=plan['id'],status='applying');save_case(run_path,case)
    if partial:revision=api('POST',f'/documents/{did}/change-plans/{plan["id"]}/apply-checked-preview')
    else:revision=api('POST',f'/documents/{did}/change-plans/{plan["id"]}/apply',json=dict(preview_only=True))
    case.update(revision_id=revision['id'],status='exporting',applied_plan_kind='checked_partial_preview' if partial else 'request_plan');save_case(run_path,case)
    path=f'/documents/{did}/revisions/{revision["id"]}'
    job=api('POST',path+'/exports',json=dict(format='dwg',scope=scope,preview=True))
    case['export_job_id']=job['id'];save_case(run_path,case)
    deadline=time.monotonic()+1200;previous=None
    while job['status'] not in ('ready','failed') and time.monotonic()<deadline:
        if job['status']!=previous:print(json.dumps(dict(case=key,stage='export',status=job['status'])),flush=True);previous=job['status']
        time.sleep(3);job=api('GET',path+'/exports/'+job['id'])
    if job['status']!='ready':raise ValueError('DWG export not ready: '+job['message'])
    output=run_path.parent/(key+'-'+scope+'-after.dwg')
    response=requests.get(BASE+job['download_url'],timeout=180);response.raise_for_status();output.write_bytes(response.content)
    assert output.read_bytes()[:6]==b'AC1032'
    case.update(status='exported',export_scope=scope,output=str(output.relative_to(ROOT)),output_sha256=digest(output),download_url=job['download_url'])
    save_case(run_path,case);print(json.dumps(case,ensure_ascii=True),flush=True)


def download_existing(run_path,key,scope):
    run_path=Path(run_path).resolve();run=json.loads(run_path.read_text(encoding='utf8'));case=next(c for c in run['cases'] if c['key']==key)
    path=f'/documents/{case["document_id"]}/revisions/{case["revision_id"]}'
    jobs=api('GET',path+'/exports')['items'];job=next(j for j in jobs if j['status']=='ready' and j['scope']==scope and j['preview'])
    response=requests.get(BASE+job['download_url'],timeout=180);response.raise_for_status()
    output=run_path.parent/(key+'-'+scope+'-after.dwg');output.write_bytes(response.content)
    case.update(status='exported',export_scope=scope,output=str(output.relative_to(ROOT)),output_sha256=digest(output),download_url=job['download_url'])
    save_case(run_path,case);print(json.dumps(dict(case=key,scope=scope,output=case['output'],sha256=case['output_sha256'])),flush=True)


def export_existing(run_path,key,scope):
    """Retry a saved revision's export; never apply its geometry twice."""
    require_local();run_path=Path(run_path).resolve();run=json.loads(run_path.read_text(encoding='utf8'))
    case=next(c for c in run['cases'] if c['key']==key)
    if case.get('output'):
        case.setdefault('exports',{})[case['export_scope']]={k:case.get(k) for k in ('output','output_sha256','download_url','export_job_id','reopened_document_id','verification')}
    path=f'/documents/{case["document_id"]}/revisions/{case["revision_id"]}'
    job=api('POST',path+'/exports',json=dict(format='dwg',scope=scope,preview=True))
    case.update(status='exporting',export_job_id=job['id']);save_case(run_path,case)
    deadline=time.monotonic()+1200
    while job['status'] not in ('ready','failed') and time.monotonic()<deadline:
        time.sleep(3);job=api('GET',path+'/exports/'+job['id'])
    if job['status']!='ready':raise ValueError('DWG export not ready: '+job['message'])
    download_existing(run_path,key,scope)


def audit_outside(before,after,operations,retained=None,export_clones=(),omitted_nested=()):
    from cad.geometry import snapshot,near
    from collections import Counter
    changed={o['ref'].split('/')[0] for o in operations};checked=Counter();skipped=Counter();failures=[];excluded=0;anonymous=[];isolated=[]
    clones={path:clone for clone in export_clones for path in clone.get('instance_paths',[clone['instance_path']])}
    for layout in before.layouts:
        for old in layout:
            if retained is not None and old.dxf.handle not in retained:excluded+=1;continue
            if old.dxf.handle in changed:continue
            actual=after.entitydb.get(old.dxf.handle);kind=old.dxftype()
            if actual is None or actual.dxftype()!=kind:
                failures.append(dict(ref=old.dxf.handle,type=kind,reason='missing_or_changed_type'));continue
            if kind in ('LINE','LWPOLYLINE','ARC','CIRCLE','DIMENSION','ELLIPSE','SPLINE'):
                try:ok=near(snapshot(old),snapshot(actual),1e-6)
                except ValueError:skipped[kind]+=1;continue
            elif kind=='INSERT':
                same_name=old.dxf.name==actual.dxf.name
                if not same_name and same_anonymous_definition(old,actual):
                    same_name=True;anonymous.append(dict(ref=old.dxf.handle,before=old.dxf.name,after=actual.dxf.name,block_record_handle=before.blocks[old.dxf.name].block_record_handle))
                if not same_name and old.dxf.handle in clones and same_isolated_definition(old,actual,clones[old.dxf.handle],omitted_nested):
                    same_name=True;isolated.append(dict(ref=old.dxf.handle,before=old.dxf.name,after=actual.dxf.name,source_member_count=len(before.blocks[old.dxf.name]),retained_member_count=len(after.blocks[actual.dxf.name])))
                ok=same_name and old.dxf.insert.isclose(actual.dxf.insert,abs_tol=1e-6)
                ok=ok and all(abs(old.dxf.get(k,0 if k=='rotation' else 1)-actual.dxf.get(k,0 if k=='rotation' else 1))<1e-6 for k in ('rotation','xscale','yscale','zscale'))
            elif kind in ('TEXT','MTEXT'):
                ok=(old.text if kind=='MTEXT' else old.dxf.text)==(actual.text if kind=='MTEXT' else actual.dxf.text)
                ok=ok and old.dxf.insert.isclose(actual.dxf.insert,abs_tol=1e-6)
            else:skipped[kind]+=1;continue
            if not ok:failures.append(dict(ref=old.dxf.handle,type=kind,reason='outside_changed'))
            else:checked[kind]+=1
    return dict(checked=dict(checked),checked_count=sum(checked.values()),metadata_or_unsupported=dict(skipped),anonymous_renames_verified=anonymous,export_clones_verified=isolated,excluded_by_export_scope=excluded,failures=failures,passed=not failures)


def same_anonymous_definition(before,after):
    """AutoCAD can renumber *U names; require the same native definition/data."""
    if not before.dxf.name.startswith('*U') or not after.dxf.name.startswith('*U'):return False
    return same_mapped_definition(before,after,{})


def same_isolated_definition(before,after,clone,omitted=()):
    """A recorded export clone needs an exact source/member/geometry proof."""
    paths=clone.get('instance_paths',[clone['instance_path']])
    if before.dxf.handle not in paths or before.dxf.name!=clone['original_block'] or after.dxf.name!=clone['new_block']:return False
    return same_mapped_definition(before,after,clone['handle_map'],omitted)


def same_mapped_definition(before,after,handle_map,omitted=()):
    from cad.nested_scope_export import copy_snapshot
    from cad.geometry import near
    verified=set();omitted=set(omitted)
    def same(left_insert,right_insert,trail=()):
        a=before.doc.blocks.get(left_insert.dxf.name);b=after.doc.blocks.get(right_insert.dxf.name)
        if a is None or b is None or handle_map.get(a.block_record_handle,a.block_record_handle)!=b.block_record_handle:return False
        if not a.block.dxf.base_point.isclose(b.block.dxf.base_point,abs_tol=1e-6):return False
        key=a.block_record_handle
        if key in trail or len(trail)>32:return False
        if key in verified:return True
        left={e.dxf.handle:e for e in a if handle_map.get(e.dxf.handle,e.dxf.handle) not in omitted};right={e.dxf.handle:e for e in b}
        if {handle_map.get(h,h) for h in left}!=right.keys():return False
        for handle,old in left.items():
            actual=right[handle_map.get(handle,handle)]
            if old.dxftype()!=actual.dxftype():return False
            if old.dxftype() not in ('LINE','ARC','CIRCLE','LWPOLYLINE','POLYLINE','DIMENSION','ELLIPSE','SPLINE','TEXT','MTEXT','SOLID','POINT','INSERT','HATCH'):return False
            try:
                if not near(copy_snapshot(old),copy_snapshot(actual),1e-6):return False
            except ValueError:return False
            if old.dxftype()=='INSERT' and not same(old,actual,trail+(key,)):return False
        verified.add(key);return True
    return same(before,after)


def reopen(run_path,key,reuse=False,native_readback=False):
    require_local()
    from backend.services import catalog_service as storage
    from backend.services.change_service import context_for
    from cad.nested_scope_export import path_entity
    from cad.geometry import snapshot,near
    import ezdxf
    run_path=Path(run_path).resolve();run=json.loads(run_path.read_text(encoding='utf8'));case=next(c for c in run['cases'] if c['key']==key)
    source=ROOT/case['output'];assert digest(source)==case['output_sha256']
    if native_readback:
        # Read the native exporter's saved/reopened DXF without starting another
        # AutoCAD process. Report this separately from an independent import.
        revision_path=storage.folder(case['document_id'])/'revisions'/case['revision_id']
        scope=case.get('export_scope','document')
        revision=json.loads((revision_path/'revision.json').read_text(encoding='utf8'))
        validation=revision['scoped_dwg_validation' if scope=='selection' else 'dwg_validation']
        assert validation['status']=='validated_roundtrip' and validation['dwg_hash']==case['output_sha256']
        folder=revision_path;status=dict(dxf=('reopen-selection' if scope=='selection' else 'reopen')+'/modified.dxf')
    elif reuse:
        uploaded=dict(id=case['reopened_document_id'])
        assert digest(storage.folder(uploaded['id'])/'original.dwg')==case['output_sha256']
    else:
        with source.open('rb') as stream:
            uploaded=api('POST','/documents',files={'file':('COMPANY-REOPEN-'+key+'.dwg',stream,'application/octet-stream')})
        case['reopened_document_id']=uploaded['id'];save_case(run_path,case)
    if not native_readback:
        status=wait_document(uploaded['id']);folder=storage.folder(uploaded['id'])
        status.update(auxiliary=True,company_regression=True,source_document_id=case['source_document_id']);storage.write_json(folder/'status.json',status)
    original_folder=storage.folder(case['document_id']);plan=json.loads((original_folder/'change-plans'/(case['plan_id']+'.json')).read_text(encoding='utf8'))
    if case.get('applied_plan_kind')=='checked_partial_preview':plan['plan']=plan['checked_preview_plan']
    revision_path=original_folder/'revisions'/case['revision_id'];revision=json.loads((revision_path/'revision.json').read_text(encoding='utf8'))
    from cad.nested_scope_export import mapped_ref
    def after_ref(ref):return mapped_ref(ref,revision['validation'].get('block_isolation',[]))
    scope=case.get('export_scope','document');validation=revision['scoped_dwg_validation' if scope=='selection' else 'dwg_validation']
    assert validation['status']=='validated_roundtrip'
    assert validation['converter']=='AutoCAD Core Console'
    doc=ezdxf.readfile(folder/status['dxf']);original=ezdxf.readfile(original_folder/case['dxf'])
    from ezdxf.math import Matrix44
    def matrix_for(drawing,ref):
        matrix=Matrix44()
        for handle in reversed(ref.split('/')[:-1]):matrix=matrix*drawing.entitydb[handle].matrix44()
        return matrix
    details={}
    if key=='mr106':
        recipes=plan['plan']['resize_recipes'];assert len(recipes)>=2
        dimensions=[];holes=[];outlines=[]
        for recipe in recipes:
            d=path_entity(doc,after_ref(recipe['dimension_ref']));old=path_entity(original,recipe['dimension_ref'])
            before=abs(old.get_measurement()*old.override().get('dimlfac',1));after=abs(d.get_measurement()*d.override().get('dimlfac',1))
            assert abs(after-15)<1e-6
            dimensions.append(dict(ref=recipe['dimension_ref'],before_mm=before,after_mm=after))
            for ref in recipe['hole_refs']:
                a=path_entity(original,ref);b=path_entity(doc,after_ref(ref))
                assert near(snapshot(a),snapshot(b),1e-6)
                old_center=matrix_for(original,ref).transform(a.dxf.center);new_center=matrix_for(doc,after_ref(ref)).transform(b.dxf.center)
                assert old_center.isclose(new_center,abs_tol=1e-6)
                holes.append(dict(ref=ref,center=list(new_center),radius=b.dxf.radius))
            for ref in recipe['outline_refs']:
                a=path_entity(original,ref);b=path_entity(doc,after_ref(ref));outlines.append(dict(ref=ref,before=snapshot(a),after=snapshot(b)))
        # Orthogonal profile extent is measured from the actual edited entities,
        # independently of displayed DIM text and source nominal BOM numbers.
        from ezdxf import bbox
        bounds=bbox.extents([path_entity(doc,after_ref(ref)).copy().transform(matrix_for(doc,after_ref(ref))) for ref in recipes[0]['outline_refs']])
        assert abs(bounds.size.x-15)<1e-6 and abs(bounds.size.y-15)<1e-6
        details=dict(dimensions=dimensions,holes=list({h['ref']:h for h in holes}.values()),physical_profile_mm=[bounds.size.x,bounds.size.y],outline_entity_count=len({o['ref'] for o in outlines}))
    elif key=='leg6949':
        # Measure four actual inner/outer arc pairs in the source-owned tube
        # detail. The oracle is radius difference, independent of the writer.
        root=next(t for t in plan['targets'] if t['id'] in plan['root_target_ids'])
        a,b,c,d=root['bbox'];arcs=[e for e in original.layouts.get(root['layout']).query('ARC') if a<=e.dxf.center.x<=c and b<=e.dxf.center.y<=d]
        pairs=[]
        for inner in arcs:
            for outer in arcs:
                if inner.dxf.center.isclose(outer.dxf.center,abs_tol=1e-6) and abs(outer.dxf.radius-inner.dxf.radius-2)<1e-6 and abs(inner.dxf.start_angle-outer.dxf.start_angle)<1e-6 and abs(inner.dxf.end_angle-outer.dxf.end_angle)<1e-6:
                    new_inner=doc.entitydb[inner.dxf.handle];new_outer=doc.entitydb[outer.dxf.handle]
                    assert near(snapshot(outer),snapshot(new_outer),1e-6)
                    assert abs(new_outer.dxf.radius-new_inner.dxf.radius-1.2)<1e-6
                    pairs.append(dict(inner_ref=inner.dxf.handle,outer_ref=outer.dxf.handle,before_wall_mm=2,after_wall_mm=new_outer.dxf.radius-new_inner.dxf.radius))
        assert len(pairs)==4,'Tube section not uniquely measured after reopen'
        dimensions=[];native_kept_measure=[]
        from cad.dimension_associations import source_binding
        for op in plan['plan']['operations']:
            if op['action']!='replace_geometry':continue
            old=original.entitydb.get(op['ref']);actual=doc.entitydb.get(op['ref'])
            if old is not None and old.dxftype()=='DIMENSION':
                assert actual is not None and actual.dxftype()=='DIMENSION'
                dimensions.append(dict(ref=op['ref'],before_mm=abs(old.get_measurement()*old.override().get('dimlfac',1)),after_mm=abs(actual.get_measurement()*actual.override().get('dimlfac',1))))
                if 'DIMASSOC' in op['reason']:
                    binding=source_binding(actual)
                    assert binding and binding['status']=='verified_source_points'
                    assert abs(actual.get_measurement()-old.get_measurement())<1e-6
                    native_kept_measure.append(dict(ref=op['ref'],measurement_mm=actual.get_measurement(),binding=binding))
        assert dimensions,'No linked dimension was independently checked'
        assert any(abs(d['before_mm']-25.6)<1e-6 and abs(d['after_mm']-27.2)<1e-6 for d in dimensions),'Missing 25.6 -> 27.2 mm companion fit'
        assert len(native_kept_measure)>=3,'Missing equal-measurement native followers'
        details=dict(section_walls=pairs,linked_dimension_changes=dimensions,equal_measurement_native_followers=native_kept_measure)
        # Check every planned detached projection against actual saved entities.
        from backend.services.revision_service import export_changes
        scope_manifest=json.loads((revision_path/'selection-source/scope.json').read_text(encoding='utf8')) if scope=='selection' else None
        changes=export_changes(revision['validation'],scope_manifest)
        projection_checks=[]
        for op in plan['plan']['operations']:
            if 'hình chiếu 2D' not in op['reason']:continue
            if op['action']=='replace_geometry':
                assert near(snapshot(path_entity(doc,after_ref(op['ref']))),json.loads(op['after']),1e-6),op['ref']
                projection_checks.append(dict(ref=op['ref'],action=op['action']))
            elif op['action']=='append_geometry':
                change=next(c for c in changes if c['ref']==op['ref'] and c['action']=='append_geometry')
                for added in change['added_entities']:
                    assert near(snapshot(doc.entitydb[added['handle']]),added['geometry'],1e-6),added['handle']
                projection_checks.append(dict(ref=op['ref'],action=op['action'],added_count=len(change['added_entities'])))
        details['projection_operation_checks']=projection_checks
    # All BOM changes are checked against native table cells, not rendered text.
    from cad.table_data import table_cells
    cells=table_cells(folder/status['dxf']);bom_checks=[]
    for op in plan['plan']['operations']:
        if op['action']=='table_cell':
            actual=next(c for c in cells[op['ref']] if c['index']==op['cell_index'])['raw_text']
            from bom.reader import plain
            assert plain(actual)==plain(op['after'])
            bom_checks.append(dict(table_ref=op['ref'],cell_index=op['cell_index'],before=plain(op['before']),after=plain(actual)))
    retained=None;export_clones=[];omitted_nested=[]
    if scope=='selection':
        selected=ezdxf.readfile(revision_path/'selection-source/modified.dxf');retained={e.dxf.handle for layout in selected.layouts for e in layout}
        assert {e.dxf.handle for layout in doc.layouts for e in layout}==retained
        scope_manifest=json.loads((revision_path/'selection-source/scope.json').read_text(encoding='utf8'))
        assert digest(revision_path/'selection-source/modified.dxf')==scope_manifest['output_hash']
        export_clones=scope_manifest.get('export_isolation',[])
        omitted_nested=scope_manifest.get('nested_selection',{}).get('removed_handles',[])
    outside=audit_outside(original,doc,plan['plan']['operations'],retained,export_clones,omitted_nested)
    outside['nested_excluded_by_export_scope']=omitted_nested
    save(run_path.parent/(key+'-outside-audit.json'),outside)
    assert outside['passed'],outside['failures'][:10]
    ole_integrity=None
    if validation.get('input_normalization'):
        from cad.empty_ole import verify as verify_ole
        ole_integrity=verify_ole(original,doc,validation['input_normalization'])
    if scope=='document':
        assert {(l.name,e.dxf.handle,e.dxftype()) for l in original.layouts for e in l}=={(l.name,e.dxf.handle,e.dxftype()) for l in doc.layouts for e in l}
    original_source=ROOT/'storage/documents'/case['source_document_id']/'original.dwg'
    assert digest(original_source)==case['source_sha256'] and digest(original_folder/'original.dwg')==case['source_sha256']
    assert digest(original_folder/case['dxf'])==case['dxf_sha256']
    found=None
    if not native_readback:
        atlas=api('POST',f'/documents/{case["reopened_document_id"]}/atlas');deadline=time.monotonic()+300
        while atlas['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(2);atlas=api('GET',f'/documents/{case["reopened_document_id"]}/atlas/{atlas["id"]}')
        assert atlas['status']=='ready',atlas
        report=api('GET',f'/documents/{case["reopened_document_id"]}/atlas/{atlas["id"]}/report')
        found=next(p for p in report['parts'] if p['part_code']==case['part_code'])
        assert not found['definition_conflict'] and found['detail_sheet_ids']
    proof=dict(status='passed',company_dwg=True,synthetic=False,source_document_id=case['source_document_id'],document_id=case['document_id'],
               reopened_document_id=case.get('reopened_document_id') if not native_readback else None,source_sha256=case['source_sha256'],output_sha256=case['output_sha256'],
               whole_file_target=case['part_code'],root_target_ids=plan['root_target_ids'],expanded_target_ids=plan['target_ids'],
               source_unchanged=True,independent_native_open=not native_readback,native_save_reopen=True,cloud_used=False,details=details,bom_checks=bom_checks,
               export_scope=scope,outside_checked_count=outside['checked_count'],outside_unread_types=outside['metadata_or_unsupported'],
               excluded_by_export_scope=outside['excluded_by_export_scope'],
               reopened_part=dict(part_code=found['part_code'],descriptions=found['descriptions'],detail_sheet_ids=found['detail_sheet_ids']) if found else None,
               applied_plan_kind=case.get('applied_plan_kind','request_plan'),full_request_executable=plan['execution_available'],
               input_normalization=validation.get('input_normalization'),ole_integrity=ole_integrity,
               drawing_sync=revision.get('drawing_sync'),complete_product_backup=revision.get('complete_product_backup',False),production_release=False,engineer_accepted=False)
    suffix='-native-readback-verification.json' if native_readback else '-verification.json'
    save(run_path.parent/(key+suffix),proof);case.update(status='native_roundtrip_verified' if native_readback else 'verified',verification=str((run_path.parent/(key+suffix)).relative_to(ROOT)))
    save_case(run_path,case);print(json.dumps(proof,ensure_ascii=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','inspect','replan','execute','reopen','download','export']);parser.add_argument('run',nargs='?');parser.add_argument('--case',choices=['mr106','leg6949']);parser.add_argument('--partial',action='store_true');parser.add_argument('--reuse-reopen',action='store_true');parser.add_argument('--native-readback',action='store_true');parser.add_argument('--scope',choices=['document','selection'],default='document');args=parser.parse_args()
    try:
        if args.action=='prepare':prepare()
        elif args.action=='replan':replan(args.run,args.case)
        elif args.action=='execute':execute(args.run,args.case,args.partial,args.scope)
        elif args.action=='download':download_existing(args.run,args.case,args.scope)
        elif args.action=='export':export_existing(args.run,args.case,args.scope)
        elif args.action=='reopen':reopen(args.run,args.case,args.reuse_reopen,args.native_readback)
        else:inspect(args.run)
    except Exception as error:
        if args.run and args.case:
            path=Path(args.run);run=json.loads(path.read_text(encoding='utf8'));case=next(c for c in run['cases'] if c['key']==args.case)
            case.setdefault('errors',[]).append(dict(action=args.action,message=str(error),at=time.time()))
            case['status']=args.action+'_failed';save_case(path,case)
        raise
