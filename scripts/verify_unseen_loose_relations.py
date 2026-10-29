"""Cold DWG uploads with random part codes; whole-file request and native reopen.

Synthetic holdouts prove the generic adapter boundary, not company acceptance
or unrestricted mechanical understanding. All CAD runs on local AutoCAD.
"""
import json
from pathlib import Path
import sys
import time
import uuid
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from scripts.verify_company_whole_file import api,require_local,wait_document,save
from cad.edit_engine import digest
from backend.services import catalog_service as storage

BASE='http://127.0.0.1:8765'


def upload(path,name):
    with path.open('rb') as stream:return api('POST','/documents',files={'file':(name,stream,'application/octet-stream')})['id']


def wait_job(url):
    deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        value=api('GET',url)
        if value['status'] not in ('queued','running'):return value
        time.sleep(1)
    raise ValueError('Job still running; receipt retained')


def verify(case,source,after):
    import ezdxf
    from ezdxf.math import Vec3
    from cad.geometry import snapshot,near
    a=ezdxf.readfile(source);b=ezdxf.readfile(after);ids=case['ids'];shift=Vec3(case['expected_shift'])
    axis=shift.normalize();cross=Vec3(-axis.y,axis.x,0)
    def profile_points(doc,refs):
        result=[]
        for ref in refs:
            e=doc.entitydb[ref]
            if e.dxftype()=='LINE':result.extend([e.dxf.start,e.dxf.end])
            else:result.extend(Vec3(p[0],p[1],e.dxf.elevation) for p in e.get_points())
        return result
    original=profile_points(a,ids['bodies'][0]);modified=profile_points(b,ids['bodies'][0])
    before_span=[min(p.dot(axis) for p in original),max(p.dot(axis) for p in original)]
    after_span=[min(p.dot(axis) for p in modified),max(p.dot(axis) for p in modified)]
    centered=case.get('hold')=='center'
    assert near(after_span,[before_span[0]-(11.5 if centered else 0),before_span[1]+(11.5 if centered else 23)],1e-6)
    assert near([min(p.dot(cross) for p in original),max(p.dot(cross) for p in original)],
                [min(p.dot(cross) for p in modified),max(p.dot(cross) for p in modified)],1e-6)
    ref=ids['holes'][0];old_hole=a.entitydb[ref];new_hole=b.entitydb[ref]
    assert abs(new_hole.dxf.radius-old_hole.dxf.radius)<1e-8
    expected_hole=old_hole.dxf.center+axis*(11.5 if centered else 23)
    assert new_hole.dxf.center.isclose(expected_hole,abs_tol=1e-6)
    ref=ids['arrows'][0]
    assert Vec3(b.entitydb[ref].vertices[0]).isclose(Vec3(a.entitydb[ref].vertices[0])-axis*(11.5 if centered else 0),abs_tol=1e-6)
    for ref in ids['bubbles'][0]:
        if a.entitydb[ref].dxftype()=='CIRCLE':assert near(snapshot(b.entitydb[ref]),snapshot(a.entitydb[ref]),1e-6)
        else:assert b.entitydb[ref].dxf.insert.isclose(a.entitydb[ref].dxf.insert,abs_tol=1e-6)
    for i in (1,2):
        for ref in ids['bodies'][i]:
            before=a.entitydb[ref];actual=b.entitydb[ref]
            if before.dxftype()=='LINE':
                assert actual.dxf.start.isclose(before.dxf.start+shift,abs_tol=1e-6) and actual.dxf.end.isclose(before.dxf.end+shift,abs_tol=1e-6)
            else:
                for p,q in zip(before.get_points(),actual.get_points()):assert near([q[0]-p[0],q[1]-p[1]],list(shift)[:2],1e-6)
        ref=ids['holes'][i];assert b.entitydb[ref].dxf.center.isclose(a.entitydb[ref].dxf.center+shift,abs_tol=1e-6)
        ref=ids['dims'][i];assert abs(b.entitydb[ref].get_measurement()-case['heights'][i])<1e-6
        ref=ids['arrows'][i];assert Vec3(b.entitydb[ref].vertices[0]).isclose(Vec3(a.entitydb[ref].vertices[0])+shift,abs_tol=1e-6)
        for ref in ids['bubbles'][i]:assert near(snapshot(b.entitydb[ref]),snapshot(a.entitydb[ref]),1e-6) if a.entitydb[ref].dxftype()=='CIRCLE' else b.entitydb[ref].dxf.insert.isclose(a.entitydb[ref].dxf.insert)
    assert abs(b.entitydb[ids['dims'][0]].get_measurement()-(case['heights'][0]+23))<1e-6
    total=sum(case['heights'])+23+case.get('source_clearance_total_mm',0)
    assert abs(b.entitydb[ids['total']].get_measurement()-total)<1e-6
    for ref in ids.get('gap_dims',[]):
        assert abs(b.entitydb[ref].get_measurement()-case['source_clearance_total_mm'])<1e-6
        for field in ('defpoint2','defpoint3'):
            assert Vec3(getattr(b.entitydb[ref].dxf,field)).isclose(Vec3(getattr(a.entitydb[ref].dxf,field))+shift,abs_tol=1e-6)
    detail=case.get('detail')
    if detail:
        assert abs(b.entitydb[detail['dimension']].get_measurement()-(case['heights'][0]+23))<1e-6
        from ezdxf.math import Matrix44
        inverse=Matrix44(detail['placement']);inverse.inverse()
        points=[inverse.transform(getattr(b.entitydb[ref].dxf,field)) for ref in detail['refs'] for field in ('start','end')]
        assert abs(max(p.y for p in points)-min(p.y for p in points)-(case['heights'][0]+23))<1e-6
        assert abs((max(p.y for p in points)+min(p.y for p in points))/2-case['heights'][0]/2)<1e-6
        ref=detail['hole'];old=inverse.transform(a.entitydb[ref].dxf.center);new=inverse.transform(b.entitydb[ref].dxf.center)
        assert near(list(new),list(old+Vec3(0,11.5,0)),1e-6)
        ref=detail['arrow'];old=inverse.transform(Vec3(a.entitydb[ref].vertices[0]));new=inverse.transform(Vec3(b.entitydb[ref].vertices[0]))
        assert near(list(new),list(old-Vec3(0,11.5,0)),1e-6)
        for ref in (detail['bubble'],detail['label']):
            if a.entitydb[ref].dxftype()=='CIRCLE':assert near(snapshot(a.entitydb[ref]),snapshot(b.entitydb[ref]),1e-6)
            else:assert a.entitydb[ref].dxf.insert.isclose(b.entitydb[ref].dxf.insert,abs_tol=1e-6)
    assert near(snapshot(a.entitydb[ids['outside']]),snapshot(b.entitydb[ids['outside']]),1e-6)
    from cad.table_data import table_cells
    from cad.catalog import text_of
    changed_rows=0
    for layout in a.layouts:
        for entity in layout:
            raw=text_of(entity) or ''
            if not raw.startswith('Bas 2x'):continue
            expected=raw
            if raw.endswith('x'+f'{case["heights"][0]:g}'):
                expected=raw.rsplit('x',1)[0]+'x'+f'{case["heights"][0]+23:g}';changed_rows+=1
            assert text_of(b.entitydb[entity.dxf.handle])==expected
    assert changed_rows==(2 if detail else 1)
    text=' '.join(text_of(e) or '' for e in b.modelspace())+' '+json.dumps(table_cells(after),ensure_ascii=False)
    assert f'{case["heights"][0]+23:g}' in text
    return dict(status='passed',primary_geometry_and_hole_verified=True,receiver_bodies=2,receiver_holes=2,total_mm=total,
                clearance_dims=len(ids.get('gap_dims',[])),detail_sheet_verified=bool(detail),bom_changed_rows=changed_rows,
                arrows_followed_bubbles_fixed=True,outside_unchanged=True)


def main():
    require_local()
    output=ROOT/'storage/validation-fixtures/unseen-loose-relations-2026-10-23';output.mkdir(exist_ok=True)
    manifest=output/'run.json'
    run=json.loads(manifest.read_text(encoding='utf8')) if manifest.exists() else dict(status='running',synthetic=True,cloud_used=False,production_release=False,cases=[])
    if not {934,2147,9411}<={c['seed'] for c in run['cases']}:
        from test_flat_contacts import unseen_drawing
        for seed,angle,lines in [(934,0,False),(2147,27,True),(9411,0,False)]:
            if any(c['seed']==seed for c in run['cases']):continue
            directory=output/str(seed);directory.mkdir(exist_ok=True)
            source,context,_,ids=unseen_drawing(directory,seed,angle,lines)
            run['cases'].append(dict(seed=seed,angle=angle,lines=lines,input=str(source.relative_to(ROOT)),input_sha256=digest(source),
                request=ids['request'],codes=ids['codes'],heights=ids['heights'],expected_shift=list(ids['transform'].transform_direction((0,23,0))),
                ids={key:ids[key] for key in ('bodies','dims','holes','arrows','bubbles','total','outside')}))
        save(manifest,run)
    run_cases(run,manifest,output)


def run_cases(run,manifest,output):
    """Shared resumable cold-upload/native export/readback verification."""
    for case in run['cases']:
        directory=output/str(case['seed']);source=ROOT/case['input']
        assert digest(source)==case['input_sha256']
        if not case.get('fixture_document_id'):
            case['fixture_document_id']=upload(source,'synthetic-validation.dxf');save(manifest,run)
        initial=wait_document(case['fixture_document_id'])
        if not case.get('source_dwg'):
            response=requests.get(BASE+f'/documents/{initial["id"]}/autocad/jobs/{initial["native_import_job_id"]}/files/modified.dwg',timeout=60);response.raise_for_status()
            dwg=directory/'unseen-input.dwg';dwg.write_bytes(response.content)
            case.update(source_dwg=str(dwg.relative_to(ROOT)),source_dwg_sha256=digest(dwg));save(manifest,run)
        if not case.get('document_id'):
            case['document_id']=upload(ROOT/case['source_dwg'],'synthetic-general-'+uuid.uuid4().hex[:8]+'.dwg');save(manifest,run)
        status=wait_document(case['document_id']);did=status['id']
        if not case.get('planning_job_id'):
            job=api('POST',f'/documents/{did}/planning-jobs',json=dict(ids=[],whole_document=True,request=case['request']))
            case['planning_job_id']=job['id'];save(manifest,run)
        job=wait_job(f'/documents/{did}/planning-jobs/{case["planning_job_id"]}')
        if job['status']!='ready':raise ValueError('Whole-file planning failed: '+str(job))
        plan=api('GET',f'/documents/{did}/change-plans/{job["plan_id"]}')
        case.update(plan_id=plan['id'],planner=plan['planner'],remaining_questions=plan['plan']['questions']);save(manifest,run)
        if not plan['execution_available'] and not plan.get('preview_execution_available'):raise ValueError('No executable source-checked plan')
        if not case.get('revision_id'):
            route='apply' if plan['execution_available'] else 'apply-checked-preview'
            revision=api('POST',f'/documents/{did}/change-plans/{plan["id"]}/{route}',json=dict(preview_only=True))
            case['revision_id']=revision['id'];save(manifest,run)
        rid=case['revision_id'];route=f'/documents/{did}/revisions/{rid}'
        if not case.get('export_job_id'):
            case['export_job_id']=api('POST',route+'/exports',json=dict(format='dwg',scope='document',preview=True))['id'];save(manifest,run)
        export=wait_job(route+'/exports/'+case['export_job_id'])
        if export['status']!='ready':raise ValueError('Native export failed: '+str(export))
        dwg=directory/'after.dwg';response=requests.get(BASE+export['download_url'],timeout=60);response.raise_for_status();dwg.write_bytes(response.content)
        case['output_sha256']=digest(dwg)
        case['native_roundtrip']=verify(case,storage.folder(did)/status['dxf'],storage.folder(did)/'revisions'/rid/'reopen/modified.dxf');save(manifest,run)
        if not case.get('independent_document_id'):
            case['independent_document_id']=upload(dwg,'synthetic-general-'+uuid.uuid4().hex[:8]+'.dwg');save(manifest,run)
        reopened=wait_document(case['independent_document_id'])
        case['independent_native_open']=verify(case,storage.folder(did)/status['dxf'],storage.folder(reopened['id'])/reopened['dxf'])
        assert digest(storage.folder(did)/'original.dwg')==case['source_dwg_sha256']
        case.update(status='passed',source_unchanged=True);save(manifest,run)
        print(json.dumps(dict(seed=case['seed'],status='passed',whole_file_request=True,independent_native_open=True)),flush=True)
    run['status']='passed';save(manifest,run)
    print(json.dumps(dict(status='passed',cases=len(run['cases']),manifest=str(manifest.relative_to(ROOT)))),flush=True)


if __name__=='__main__':main()
