"""Live local API smoke check using a COPY of Autodesk's installed sample DWG.

Does not certify arbitrary drawings or assemblies. Requires activated local AutoCAD.
All edits use the normal selection/planning/download routes; no generated CAD code.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import requests
import ezdxf
from cad.edit_engine import digest
from backend.services import catalog_service as storage


def geometry_signature(entity):
    from ezdxf.disassemble import recursive_decompose
    rows=[]
    def point(value):return tuple(round(float(c),8) for c in value)
    for e in recursive_decompose([entity]):
        if e.dxf.get('invisible',0):continue
        kind=e.dxftype()
        if kind=='LINE':row=(kind,point(e.dxf.start),point(e.dxf.end))
        elif kind=='CIRCLE':row=(kind,point(e.dxf.center),round(e.dxf.radius,8))
        elif kind=='ARC':row=(kind,point(e.dxf.center),round(e.dxf.radius,8),round(e.dxf.start_angle,8),round(e.dxf.end_angle,8))
        elif kind=='LWPOLYLINE':row=(kind,[point(p) for p in e.get_points()],e.closed)
        elif kind=='ELLIPSE':row=(kind,point(e.dxf.center),point(e.dxf.major_axis),round(e.dxf.ratio,8))
        elif kind in ('SOLID','TRACE','3DFACE'):row=(kind,[point(e.dxf.get('vtx'+str(i))) for i in range(4)])
        else:continue
        rows.append(json.dumps(row,sort_keys=True))
    return sorted(rows)


def nested_workflow(args,session,call,wait,source):
    """Exercise shared static ancestors and distinct occurrences of one leaf.

    The installed Autodesk sample supplies an authored dynamic block. Only a
    new DXF fixture is assembled; source/customer drawings are never edited.
    """
    from uuid import uuid4
    task=ROOT/'storage/validation-fixtures'/('native-nested-'+uuid4().hex[:8]);task.mkdir()
    d=ezdxf.readfile(source);model=d.modelspace()
    # This sample's long bolt is independently checked for its authored Length
    # parameter below. Fixture identifiers are not part of production planning.
    bolt=d.entitydb.get('1B4C')
    assert bolt is not None and bolt.dxftype()=='INSERT'
    model.unlink_entity(bolt)
    inner=d.blocks.new('NESTED_INNER_'+uuid4().hex[:8]);inner.add_entity(bolt)
    outer=d.blocks.new('NESTED_OUTER_'+uuid4().hex[:8])
    branches=[outer.add_blockref(inner.name,(300*i,0)) for i in range(30 if args.many else 2)]
    first,second=branches[0],branches[-1]
    outer.add_line((0,-160),(300,-160))
    outer.add_linear_dim(base=(0,-180),p1=(0,-160),p2=(300,-160)).render()
    outer.add_mtext('Fixed source annotation',dxfattribs={'insert':(0,-200),'char_height':2})
    outer.add_ellipse((0,-240),major_axis=(10,0),ratio=.5)
    root=model.add_blockref(outer.name,(0,0),dxfattribs=dict(rotation=27,xscale=1.5,yscale=1.5,zscale=1.5))
    sibling=model.add_blockref(outer.name,(1200,0))
    authored=task/'input.dxf';d.saveas(authored);source_hash=digest(authored)
    with authored.open('rb') as stream:
        response=session.post(args.base+'/documents',files={'file':('synthetic-nested-'+task.name+'.dxf',stream,'application/octet-stream')},timeout=30)
        response.raise_for_status();did=response.json()['id']
    url='/documents/'+did;wait(url)
    # Create native DWG once, then upload that DWG as a NEW document. The
    # acceptance flow must exercise DWG input, not just a DXF-to-DWG export.
    prepared_state=storage.read_status(did)
    prepared_state.update(synthetic_test=True,auxiliary=True,source_kind='synthetic_test')
    storage.write_json(storage.folder(did)/'status.json',prepared_state)
    response=session.get(args.base+url+'/autocad/jobs/'+prepared_state['native_import_job_id']+'/files/modified.dwg',timeout=60)
    response.raise_for_status();input_dwg=task/'input.dwg';input_dwg.write_bytes(response.content)
    dwg_source_hash=digest(input_dwg)
    with input_dwg.open('rb') as stream:
        response=session.post(args.base+'/documents',files={'file':('synthetic-nested-'+task.name+'.dwg',stream,'application/octet-stream')},timeout=30)
        response.raise_for_status();did=response.json()['id']
    url='/documents/'+did;wait(url)
    if args.provider=='aps':
        imported=call(url+'/aps/import',{});did=imported['id'];url='/documents/'+did;wait(url,limit=240)
    route=args.provider
    folder=storage.folder(did);saved=storage.read_status(did)
    saved.update(synthetic_test=True,auxiliary=True,source_kind='synthetic_test');storage.write_json(folder/'status.json',saved)
    readback=folder/saved['dxf'];before=ezdxf.readfile(readback)
    refs=[f'{root.dxf.handle}/{branch.dxf.handle}/{bolt.dxf.handle}' for branch in (first,second)]
    ctx=call(url+'/'+route+'/context',dict(ids=[root.dxf.handle],parameter_offset=0))
    pages=[ctx];offset=ctx.get('next_parameter_offset')
    while offset is not None:
        page=call(url+'/'+route+'/context',dict(ids=[root.dxf.handle],parameter_offset=offset))
        assert page['inspection_id']==ctx['inspection_id'] and page['original_source_hash']==ctx['original_source_hash']
        pages.append(page);offset=page['next_parameter_offset']
    assert set(refs)<={r['ref'] for page in pages for r in page['records'] if r.get('nested_editable')}
    assert sum(len(page['records']) for page in pages)==len(branches)
    results=[]
    for goals in ([80.],[80.,70.]):
        request='; '.join(f'#{ref} Length từ 50 thành {goal:g} mm' for ref,goal in zip(refs,goals))
        planning=call(url+'/planning-jobs',dict(ids=[root.dxf.handle],request=request));planning=wait(url+'/planning-jobs/'+planning['id'])
        plan=call(url+'/change-plans/'+planning['plan_id'])
        assert plan.get('native_execution_available'),plan
        assert [op['instance_path'] for op in plan['native_edit']['operations']]==[r.split('/') for r in refs[:len(goals)]]
        job=call(url+'/'+route+'/native-edits',plan['native_edit']);job=wait(url+'/'+route+'/jobs/'+job['id'],limit=240)
        inventory=call(job['inventory_url']);effects=inventory['dynamic_effects']
        assert len(effects)==len(goals)
        after=ezdxf.readfile(folder/'aps-jobs'/job['id']/'result/roundtrip.dxf')
        for ref,goal in zip(refs,goals):
            effect=next(e for e in effects if e['source_ref']==ref)
            assert effect['handle']!=bolt.dxf.handle
            actual=next(e for e in inventory['entities'] if e['handle']==effect['handle'])
            assert next(float(p['value']) for p in actual['parameters'] if p['name']=='Length')==goal
            from ezdxf.disassemble import recursive_decompose
            edges=[e for e in recursive_decompose([after.entitydb[effect['handle']]]) if e.dxftype()=='LINE'
                and abs(e.dxf.start.y-e.dxf.end.y)<1e-8 and abs(e.dxf.start.distance(e.dxf.end)-goal)<1e-6]
            assert len(edges)==2,'Native property changed without changing shaft geometry'
            # The edited value is an authored LOCAL dynamic parameter. With a
            # scaled parent, its layout length must retain that scale; do not
            # report the property as an unscaled product/world DIM.
            branch=first if ref==refs[0] else second
            placed=after.entitydb[effect['handle']].copy()
            placed.transform(branch.matrix44());placed.transform(after.entitydb[root.dxf.handle].matrix44())
            world_edges=[e for e in recursive_decompose([placed]) if e.dxftype()=='LINE'
                and abs(e.dxf.start.distance(e.dxf.end)-goal*1.5)<1e-6]
            assert len(world_edges)==2,'Nested parent scale was lost in the placed geometry'
        for entity in before.modelspace():
            if entity.dxftype()=='INSERT' and entity.dxf.handle!=root.dxf.handle:
                assert geometry_signature(entity)==geometry_signature(after.entitydb[entity.dxf.handle]),'Unselected layout instance changed'
        before_container=before.blocks[before.entitydb[root.dxf.handle].dxf.name]
        after_container=after.blocks[after.entitydb[root.dxf.handle].dxf.name]
        bd=list(before_container.query('DIMENSION'));ad=list(after_container.query('DIMENSION'))
        assert len(bd)==len(ad)==1 and abs(bd[0].get_measurement()-300)<1e-8 and abs(ad[0].get_measurement()-300)<1e-8
        assert [e.text for e in before_container.query('MTEXT')]==[e.text for e in after_container.query('MTEXT')]
        assert geometry_signature(before.entitydb[bolt.dxf.handle])==geometry_signature(after.entitydb[bolt.dxf.handle]),'Shared original leaf changed'
        changed={first.dxf.handle} if len(goals)==1 else {first.dxf.handle,second.dxf.handle}
        b=after.blocks[after.entitydb[root.dxf.handle].dxf.name]
        for branch in branches:
            if branch.dxf.handle in changed:continue
            untouched=next(e for e in b.query('INSERT') if abs(e.dxf.insert.x-branch.dxf.insert.x)<1e-8)
            assert geometry_signature(before.entitydb[branch.dxf.handle])==geometry_signature(untouched)
        response=session.get(args.base+job['download_url'],timeout=60);response.raise_for_status()
        output=task/f'backup-{len(goals)}-branches.dwg';output.write_bytes(response.content)
        assert response.content.startswith(b'AC1032') and digest(authored)==source_hash
        assert digest(folder/'original.dwg')==dwg_source_hash
        preview=session.get(args.base+url+'/'+route+'/jobs/'+job['id']+'/preview/'+root.dxf.handle,timeout=60);preview.raise_for_status()
        (task/f'preview-{len(goals)}-branches.svg').write_bytes(preview.content)
        results.append(dict(goals_mm=goals,parameter_space='block-local',placed_shaft_lengths_mm=[goal*1.5 for goal in goals],
            plan_id=plan['id'],job_id=job['id'],effects=effects,
            download_url=args.base+job['download_url'],dwg=str(output),dwg_sha256=digest(output),source_unchanged=True,
            untouched_sibling_geometry_preserved=True))
        print(json.dumps(dict(goals_mm=goals,job_id=job['id'],status='passed')),flush=True)
    from cad.converter import DWGConverter,converter_path
    DWGConverter(converter_path()).convert_dwg_to_dxf(task,task/'independent-readback')
    for case in results:
        reopened=ezdxf.readfile(task/'independent-readback'/(Path(case['dwg']).stem+'.dxf'))
        expected_dxf=ezdxf.readfile(folder/'aps-jobs'/case['job_id']/'result/roundtrip.dxf')
        for effect in case['effects']:
            # Compare downloaded DWG geometry to its own native readback, not
            # another job's newly allocated clone handles.
            assert geometry_signature(reopened.entitydb[effect['handle']])==geometry_signature(expected_dxf.entitydb[effect['handle']])
        case['downloaded_dwg_independently_reopened']=True
    report=dict(document_id=did,provider=route,fixture='Autodesk dynamic block inside shared static ancestors',rotated_scaled_root=True,
        shared_branch_count=len(branches),parameter_pages=len(pages),
        uploaded_format='dwg',uploaded_dwg_source_hash=dwg_source_hash,
        source_path=str(authored),source_hash=source_hash,cases=results,complete_product_backup=False)
    (task/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(str(task/'report.json'),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',type=Path,required=True)
    parser.add_argument('--base',default='http://127.0.0.1:8765')
    parser.add_argument('--nested',action='store_true',help='Verify isolated nested occurrences inside repeated static containers')
    parser.add_argument('--many',action='store_true',help='Nested fixture with 30 branches; selects first and last across parameter pages')
    parser.add_argument('--provider',choices=['autocad','aps'],default='autocad',help='Nested verification only; APS explicitly uploads the synthetic fixture')
    args=parser.parse_args()
    session=requests.Session();session.trust_env=False
    def call(path,body=None):
        response=session.post(args.base+path,json=body,timeout=60) if body is not None else session.get(args.base+path,timeout=60)
        response.raise_for_status();return response.json()
    def wait(path,terminal=('ready','failed'),limit=120):
        deadline=time.monotonic()+limit
        while time.monotonic()<deadline:
            value=call(path)
            if value['status'] in terminal:
                if value['status']!='ready':raise RuntimeError(value)
                return value
            time.sleep(.5)
        raise TimeoutError(path)
    status=call('/autocad/status')
    assert status['configured'] and status['live_verified'] and status['read_backend']=='autocad'
    original_hash=digest(args.sample)
    with args.sample.open('rb') as stream:
        response=session.post(args.base+'/documents',files={'file':('synthetic-autodesk-dynamic.dwg',stream,'application/octet-stream')},timeout=30)
        response.raise_for_status();document=response.json()['id']
    root='/documents/'+document;wait(root)
    folder=storage.folder(document);saved=storage.read_status(document)
    saved['synthetic_test']=True;storage.write_json(folder/'status.json',saved)
    source=folder/saved['dxf'];before_dxf=ezdxf.readfile(source)
    if args.nested:
        nested_workflow(args,session,call,wait,source);return
    results=[]
    cases=[('2E4','Part Number từ 626 thành 627',{'Part Number':'627','Outside Diameter':'22','Width':'7','Bore':'7'}),
           ('1B4C','Tăng chiều dài lên 80 mm',{'Length':'80'}),
           ('25A','Side từ 0 thành 1',{'Side':'1'}),
           ('25A','Weld Symbol từ Backing thành Fillet',{'Weld Symbol':'Fillet'}),
           ('103','Size từ M10 thành M12',{'Size':'M12'})]
    for target,request,expected in cases:
        started=time.monotonic()
        planning=call(root+'/planning-jobs',dict(ids=[target],request=request))
        planning=wait(root+'/planning-jobs/'+planning['id'])
        plan=call(root+'/change-plans/'+planning['plan_id'])
        assert plan.get('native_execution_available'),plan
        assert plan['model']=='native-parameter-compiler' and not plan['complete_product_backup']
        job=call(root+'/autocad/native-edits',plan['native_edit'])
        job=wait(root+'/autocad/jobs/'+job['id'])
        assert not job['complete_product_backup'] and job['download_url']
        inventory=call(job['inventory_url'])
        entity=next(e for e in inventory['entities'] if e['handle']==target)
        actual={p['name']:p['value'] for p in entity['parameters'] if p['name'] in expected}
        assert actual==expected,(actual,expected)
        preview=session.get(args.base+root+'/autocad/jobs/'+job['id']+'/preview/'+target,timeout=60)
        preview.raise_for_status();assert '<svg' in preview.text
        download=session.get(args.base+job['download_url'],timeout=60);download.raise_for_status()
        assert download.content.startswith(b'AC1032') and 'attachment' in download.headers['content-disposition']
        work=ROOT/'storage/validation-fixtures'/('native-dynamic-'+job['id']);work.mkdir(exist_ok=True)
        (work/'modified.dwg').write_bytes(download.content);(work/'preview.svg').write_bytes(preview.content)
        # Measure actual geometry in DXF exported from the reopened native DWG.
        result_dxf=folder/'aps-jobs'/job['id']/'result/roundtrip.dxf'
        readback=ezdxf.readfile(result_dxf)
        from ezdxf import bbox
        old=bbox.extents([before_dxf.entitydb[target]])
        new=bbox.extents([readback.entitydb[target]])
        if target=='2E4':assert abs(old.size.y-19)<1e-6 and abs(new.size.y-22)<1e-6
        if target=='1B4C':
            # The authored centerline extends beyond the original bolt and is
            # not a stretch member. Measure the two shaft edges, not total bbox.
            from ezdxf.disassemble import recursive_decompose
            for drawing,length in ((before_dxf,50),(readback,80)):
                edges=[e for e in recursive_decompose([drawing.entitydb[target]]) if e.dxftype()=='LINE'
                       and abs(e.dxf.start.y-e.dxf.end.y)<1e-8 and abs(e.dxf.start.distance(e.dxf.end)-length)<1e-6]
                assert len(edges)==2,(length,len(edges))
        assert geometry_signature(before_dxf.entitydb[target])!=geometry_signature(readback.entitydb[target]),'Parameter changed without visible geometry change'
        for other in before_dxf.modelspace().query('INSERT'):
            if other.dxf.handle!=target:
                assert geometry_signature(other)==geometry_signature(readback.entitydb[other.dxf.handle]),'Unselected block geometry changed'
        effects=job['native_summary']['dynamic_effects']
        assert len(effects)==1 and effects[0]['handle']==target
        assert digest(args.sample)==original_hash==digest(folder/'original.dwg')
        results.append(dict(target=target,request=request,expected=expected,actual=actual,job_id=job['id'],plan_id=plan['id'],
                            seconds=round(time.monotonic()-started,2),bbox_before=list(old.size),bbox_after=list(new.size),
                            download_url=args.base+job['download_url'],download_hash=digest(work/'modified.dwg'),
                            preview_url=args.base+root+'/autocad/jobs/'+job['id']+'/preview/'+target))
        print(json.dumps(results[-1],ensure_ascii=True),flush=True)
    report=dict(document_id=document,source_hash=original_hash,cases=results,complete_product_backup=False,
                checks=['real DWG upload','source-bound natural request','authored dynamic lookup/stretch/flip/visibility',
                        'native DWG reopen','dependent parameters','geometry measurement','unselected dynamic parameter/bbox/geometry check',
                        'SVG preview HTTP 200','DWG download HTTP 200','original unchanged'])
    output=ROOT/'storage/validation-fixtures/autocad-dynamic-native-2026-10-16.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(str(output))


if __name__=='__main__':main()
