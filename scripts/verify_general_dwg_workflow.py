"""Exercise real upload -> checked resize -> download -> DWG reopen locally.

Creates an independent synthetic CAD document. It does not demonstrate that
unproven customer assemblies or every DWG entity are editable.
"""
import hashlib
import json
import sys
import time
import uuid
import argparse
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import ezdxf
import requests
from cad.converter import DWGConverter,converter_path
from backend.services.change_service import context_for


def association_workflow(mode,approve=False):
    """Roundtrip real native DIMASSOC, including its body pointers/snaps."""
    sys.path.insert(0,str(ROOT/'tests'))
    from test_geometry import midpoint_profile_fixture
    from test_bom import grid
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    token=uuid.uuid4().hex[:8];task=ROOT/'storage/validation-fixtures'/('native-snap-'+token)
    inputs=task/'input';inputs.mkdir(parents=True)
    source,_,_,_,_=midpoint_profile_fixture(inputs,center=mode=='center')
    doc=ezdxf.readfile(source);m=doc.modelspace();code='UNSEEN-'+token
    grid(m,rows=[['1',code,'Bas 2x80x100','Sắt','1','']],x=180,y=280)
    m.add_text(code,dxfattribs=dict(insert=(0,-20),height=3))
    m.add_text('PART NAME',dxfattribs=dict(insert=(0,-30),height=3))
    m.add_text('PART LIST',dxfattribs=dict(insert=(180,150),height=3))
    m.add_lwpolyline([(-60,-40),(140,-40),(140,110),(-60,110)],close=True)
    m.add_lwpolyline([(160,140),(650,140),(650,440),(160,440)],close=True)
    doc.saveas(source);converter=DWGConverter(converter_path())
    converter.convert_dxf_to_dwg(inputs,task/'dwg');dwg=task/'dwg/native-association.dwg';original=digest(dwg)
    session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765'
    def call(path,data=None):
        r=session.post(base+path,json=data,timeout=150) if data is not None else session.get(base+path,timeout=150)
        if r.status_code>=400:raise RuntimeError(f'{path}: {r.status_code} {r.text[:2000]}')
        return r.json()
    with dwg.open('rb') as stream:
        r=session.post(base+'/documents',files={'file':('synthetic-native-snap-'+token+'.dwg',stream,'application/octet-stream')},timeout=30)
        r.raise_for_status();did=r.json()['id']
    root='/documents/'+did;deadline=time.monotonic()+120
    while True:
        state=call(root)
        if state['status']=='ready':break
        if state['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(state)
        time.sleep(.3)
    folder=storage.folder(did);assert digest(folder/'original.dwg')==original
    status=storage.read_status(did);status['synthetic_test']=True;storage.write_json(folder/'status.json',status)
    target=next(t for t in call(root+'/sheets')['items'] if code in t['texts'] and t['bbox'][0]<0)
    from backend.services.part_graph_service import document_graph
    assert target['id'] in next(n for n in document_graph(did)['nodes'] if n['code']==code)['detail_sheets']
    plan=call(root+'/change-plans',dict(ids=[target['id']],request=f'Mã {code} chiều cao từ 100 thành 80 mm, giữ dưới'))
    assert plan['execution_available'],plan['plan']['questions']
    revision=call(root+f'/change-plans/{plan["id"]}/apply',dict(preview_only=True));rid=revision['id'];rev=root+'/revisions/'+rid
    picture=session.get(base+rev+f'/sheets/{target["id"]}/preview',timeout=30);picture.raise_for_status()
    (task/'preview.svg').write_text(picture.text,encoding='utf8')
    for related in revision['targets']:
        if related['id']==target['id']:continue
        route=f'/sheets/{related["id"]}/preview' if related['kind']=='sheet' else f'/items/{related["id"]}/preview'
        checked=session.get(base+rev+route,timeout=30);checked.raise_for_status()
    if approve:assert call(rev+'/approve',dict(confirmed_dependencies=revision['pending_dependencies']))['status']=='approved'
    job=call(rev+'/exports',dict(format='dwg',scope='selection',preview=not approve));deadline=time.monotonic()+150
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(.3);job=call(rev+'/exports/'+job['id'])
    response=session.get(base+job['download_url'],timeout=30);response.raise_for_status()
    download=task/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
    converter.convert_dwg_to_dxf(download,task/'reopen');reopened=task/'reopen/backup.dxf'
    from cad.sheets import discover_sheets
    after=context_for(reopened,discover_sheets(reopened));expected=70 if mode=='center' else 40
    dims=[e for e in after['entities'] if e['type']=='DIMENSION']
    assert sorted(e['scaled_measurement'] for e in dims)==[expected,80]
    native=next(e for e in dims if e.get('dimension_association'))
    assert native['dimension_association']['status']=='verified_source_points'
    from cad.dimension_associations import verify
    verify(ezdxf.readfile(reopened),revision['validation']['native_associations'])
    assert [r['description'] for e in after['entities'] for r in e.get('bom',{}).get('rows',[])]==['Bas 2x80x80']
    assert digest(dwg)==original
    report=dict(mode=mode,synthetic=True,document_id=did,plan_id=plan['id'],revision_id=rid,
        approved=approve,source_unchanged=True,profile_height_mm=80,dependent_dimension_mm=expected,
        native_association_preserved=True,association_sources=revision['validation']['association_sources'],
        solid_validation=revision['solid_validation']['status'],backup=str(backup.resolve()),dwg_sha256=digest(backup),
        download_url=base+job['download_url'],customer_file_modified=False)
    (task/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


def container_scope_workflow():
    """Source-frame membership and isolated edits inside a shared container."""
    import httpx,math
    sys.path.insert(0,str(ROOT/'tests'))
    from test_context import multi_drawing_container
    from cad.edit_engine import digest
    from cad.catalog import load_document
    from cad.sheets import discover_sheets
    from backend.services import catalog_service as storage
    client=httpx.Client(base_url='http://127.0.0.1:8765',trust_env=False,timeout=150)
    def api(method,path,**kwargs):
        r=client.request(method,path,**kwargs)
        if r.is_error:raise RuntimeError(f'{path}: {r.status_code} {r.text[:1800]}')
        return r.json()
    batch=ROOT/'storage/validation-fixtures'/('source-scopes-dwg-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());receipts=[]
    for name,angle,scale,mirror in [('nested-frames',0,1,False),('rotated-scaled-frames',90,2,False),('mirrored-frames',180,1,True)]:
        started=time.perf_counter();folder=batch/name;authored=folder/'authored';authored.mkdir(parents=True)
        _,source,_,_,_,_,_=multi_drawing_container(authored,angle,scale,mirror)
        if angle==90:
            source_doc=ezdxf.readfile(source);container=source_doc.blocks['DRAWINGS']
            container.set_redraw_order([(e.dxf.handle,str(i+100)) for i,e in enumerate(container)])
            source_doc.saveas(source)
        converter.convert_dxf_to_dwg(authored,folder/'input');dwg=folder/'input/container.dwg';original_hash=digest(dwg)
        with dwg.open('rb') as stream:uploaded=api('POST','/documents',files={'file':('unseen-frames-'+uuid.uuid4().hex+'.dwg',stream,'application/octet-stream')})
        did=uploaded['id'];url='/documents/'+did;deadline=time.monotonic()+100
        while True:
            status=api('GET',url)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.3)
        path=storage.folder(did);assert digest(path/'original.dwg')==original_hash
        saved=storage.read_status(did);saved['synthetic_test']=True;storage.write_json(path/'status.json',saved)
        sheets=api('GET',url+'/sheets')['items'];assert len(sheets)==2,sheets
        target=next(s for s in sheets if 'BẢN VẼ PART-A' in s['texts']);other=next(s for s in sheets if s['id']!=target['id'])
        c=context_for(path/status['dxf'],sheets);by={e['ref']:e for e in c['entities']}
        roots={e['name']:e['ref'] for e in c['entities'] if e['type']=='INSERT' and e.get('name') in ('PART-A','PART-B')}
        assert by[roots['PART-A']]['source_sheet_ids']==[target['id']]
        assert by[roots['PART-B']]['source_sheet_ids']==[other['id']]
        input_dxf_hash=digest(path/status['dxf'])
        from cad.frame_geometry import world
        dimension=next(e for e in c['entities'] if e['type']=='DIMENSION' and e['ref'].startswith(roots['PART-A']+'/'))
        g=world(dimension)['geometry'];p,q=g['defpoint2'],g['defpoint3']
        axis=max((0,1),key=lambda k:abs(p[k]-q[k]))
        side=(('trái','phải') if axis==0 else ('dưới','trên'))[p[axis]>q[axis]]
        request=f'Mã PART-A chiều dài từ 100 thành 80 mm, giữ {side}'
        anchor_reply=None
        if angle==90:
            started_question=time.perf_counter()
            question=api('POST',url+'/change-plans',json=dict(ids=[target['id']],request='Mã PART-A chiều dài từ 100 thành 80 mm, giữ dưới'))
            assert not question['execution_available'] and not question['plan']['operations'] and len(question['plan']['questions'])==1
            assert question['planner']=='checked_measured_profile_resize'
            assert 'đo theo hướng ngang' in question['plan']['questions'][0]
            question_seconds=time.perf_counter()-started_question;started_refine=time.perf_counter()
            plan=api('POST',url+f'/change-plans/{question["id"]}/refine',json=dict(answers=['Giữ '+side]))
            anchor_reply=dict(question_plan_id=question['id'],question=question['plan']['questions'][0],answer='Giữ '+side,
                question_seconds=round(question_seconds,3),refinement_seconds=round(time.perf_counter()-started_refine,3),model_used=False)
        else:plan=api('POST',url+'/change-plans',json=dict(ids=[target['id']],request=request))
        assert plan['execution_available'],plan['plan']['questions']
        assert plan['target_ids']==[target['id']],plan['target_ids']
        assert not any(o['ref'].startswith(roots['PART-B']) for o in plan['plan']['operations'])
        revision=api('POST',url+f'/change-plans/{plan["id"]}/apply',json=dict(preview_only=True));revurl=url+'/revisions/'+revision['id']
        working=context_for(path/'revisions'/revision['id']/'modified.dxf',sheets)
        assert sorted(e['scaled_measurement'] for e in working['entities'] if e['type']=='DIMENSION')==[80,100]
        all_working=context_for(path/'revisions'/revision['id']/'modified.dxf',[dict(id=e.dxf.handle,kind='block',layout='Model') for e in load_document(str(path/'revisions'/revision['id']/'modified.dxf')).modelspace().query('INSERT')])
        assert sorted(e['scaled_measurement'] for e in all_working['entities'] if e['type']=='DIMENSION')==[80,100,100]
        preview=client.get(revurl+f'/sheets/{target["id"]}/preview');preview.raise_for_status()
        (folder/'after.svg').write_bytes(preview.content)
        api('POST',revurl+'/approve',json=dict(confirmed_dependencies=revision['pending_dependencies']))
        job=api('POST',revurl+'/exports',json=dict(format='dwg',scope='selection',preview=False));deadline=time.monotonic()+150
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.3);job=api('GET',revurl+'/exports/'+job['id'])
        response=client.get(job['download_url']);response.raise_for_status();download=folder/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
        converter.convert_dwg_to_dxf(download,folder/'reopened');reopened=folder/'reopened/backup.dxf';after=context_for(reopened,sheets)
        dims={s['id']:[e['scaled_measurement'] for e in after['entities'] if e['type']=='DIMENSION' and s['id'] in e.get('source_sheet_ids',[])] for s in sheets}
        assert len(dims[target['id']])==1 and math.isclose(dims[target['id']][0],80,abs_tol=1e-5),dims
        assert dims[other['id']]==[],dims
        tables={e['bom']['rows'][0]['part_code']:e for e in after['entities'] if e.get('bom')}
        assert tables['PART-A']['bom']['rows'][0]['description']=='Bas 2x20x80'
        assert set(tables)=={'PART-A'}
        assert tables['PART-A']['source_sheet_ids']==[target['id']]
        # The working revision keeps every other view unchanged. Selection
        # exports prune their placements while preserving reusable definitions.
        full=context_for(reopened,[dict(id=e.dxf.handle,kind='block',layout='Model') for e in load_document(str(reopened)).modelspace().query('INSERT')])
        a=[e['scaled_measurement'] for e in full['entities'] if e['type']=='DIMENSION' and any(r.get('name')=='PART-A' or r.get('source_block_name')=='PART-A' for r in full['entities'] if r['type']=='INSERT' and e['ref'].startswith(r['ref']+'/'))]
        assert a==[80],a
        assert len(discover_sheets(reopened))==1
        assert digest(path/status['dxf'])==input_dxf_hash and digest(dwg)==original_hash
        receipt=dict(kind=name,synthetic=True,document_id=did,plan_id=plan['id'],revision_id=revision['id'],approved_backup=True,download_status=response.status_code,
            selected_dimension_mm=80,working_neighbor_dimension_mm=100,working_unselected_same_code_mm=100,selected_bom='Bas 2x20x80',
            exported_neighbor_present=False,exported_unselected_same_code_present=False,exported_sheet_count=1,
            source_unchanged=True,detector_modified=False,engine_mapping_supplied=False,scope_ids=plan['target_ids'],solid_validation=revision['solid_validation'],
            rotation_degrees=angle,scale=scale,mirrored=mirror,dwg_sha256=digest(backup),backup_path=str(backup),elapsed_seconds=round(time.perf_counter()-started,3),
            nested_scope_trimmed=True,retained_source_resources=True,request=request,source_anchor_reply=anchor_reply)
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');receipts.append(receipt)
        print(name,'approved/downloaded/reopened; selected=80, other placements absent; working revision unchanged',flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8');print('Receipts:',batch/'receipts.json',flush=True)


def shared_export_masks_workflow():
    """Independent real-DWG exporter regression; not a planner/assembly claim."""
    sys.path.insert(0,str(ROOT/'tests'))
    from test_context import multi_drawing_container
    from cad.edit_engine import digest
    from cad.catalog import load_document
    from cad.sheets import discover_sheets
    from cad.scoped_export import select_entities
    from cad.nested_scope_export import verify,verify_copies,path_entity,mapped_ref
    converter=DWGConverter(converter_path())
    batch=ROOT/'storage/validation-fixtures'/('shared-export-masks-'+uuid.uuid4().hex[:8]);receipts=[]
    for name,angle,scale,mirror in [('nested',0,1,False),('rotated-scaled',90,2,False),('mirrored',180,1,True),('native-dxf',0,1,False)]:
        folder=batch/name;authored=folder/'authored';authored.mkdir(parents=True)
        doc,source,_,_,_,_,_=multi_drawing_container(authored,angle,scale,mirror)
        doc.modelspace().add_blockref('OUTER',(6000,1000),dxfattribs=dict(rotation=angle,xscale=-scale if mirror else scale,yscale=scale))
        container=doc.blocks['DRAWINGS'];container.set_redraw_order([(e.dxf.handle,str(i+100)) for i,e in enumerate(container)])
        doc.saveas(source);input_file=source;input_hash=digest(source)
        if name!='native-dxf':
            converter.convert_dxf_to_dwg(authored,folder/'input')
            input_file=folder/'input/container.dwg';input_hash=digest(input_file)
            converter.convert_dwg_to_dxf(folder/'input',folder/'parsed');source=folder/'parsed/container.dxf'
        source_hash=digest(source)
        sheets=discover_sheets(source);assert len(sheets)==4,sheets
        a=min((s for s in sheets if 'BẢN VẼ PART-A' in s['texts']),key=lambda s:s['bbox'][0])
        b=max((s for s in sheets if 'BẢN VẼ PART-B' in s['texts']),key=lambda s:s['bbox'][0])
        c=context_for(source,[a,b]);refs={e['ref'] for e in c['entities'] if e['type']!='GRAPHIC_TABLE'}
        keep={ref for ref in refs if '/' not in ref};assert len(keep)==2
        selected=folder/'selected/modified.dxf';started=time.perf_counter()
        manifest=select_entities(source,selected,keep,keep_refs=refs)
        assert manifest['export_isolation']
        converter.convert_dxf_to_dwg(selected.parent,folder/'output');backup=folder/'output/modified.dwg'
        converter.convert_dwg_to_dxf(folder/'output',folder/'reopened');reopened=folder/'reopened/modified.dxf'
        actual=load_document(str(reopened));verify(actual,manifest,converter_normalized=True)
        verify_copies(load_document(str(source)),actual,manifest['export_isolation'],manifest['nested_selection']['removed_handles'])
        for ref in refs:path_entity(actual,mapped_ref(ref,manifest['export_isolation']))
        visible=context_for(reopened,[dict(id=e.dxf.handle,kind='block',layout='Model') for e in actual.modelspace()])
        assert sorted(e['scaled_measurement'] for e in visible['entities'] if e['type']=='DIMENSION')==[100,100]
        assert sorted(r['part_code'] for e in visible['entities'] for r in e.get('bom',{}).get('rows',[]))==['PART-A','PART-B']
        assert len(discover_sheets(reopened))==2
        assert digest(source)==source_hash and digest(input_file)==input_hash
        receipt=dict(kind=name,synthetic=True,scope='exporter roundtrip only',planner_test=False,source_unchanged=True,
            input_format=input_file.suffix,source_sheets=4,selected_sheets=2,reopened_sheets=2,export_isolated_definitions=len(manifest['export_isolation']),
            selected_codes=['PART-A','PART-B'],dimensions_mm=[100,100],sortents_preserved=True,detector_modified=False,
            backup=str(backup.resolve()),dwg_sha256=digest(backup),elapsed_seconds=round(time.perf_counter()-started,3))
        (folder/'scope.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        receipts.append(receipt);print(name,'shared masks exported/reopened with only the two selected drawings',flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
    print('Receipts:',batch/'receipts.json',flush=True)


def tube_specifications_workflow(approve=False):
    """New DWGs, random codes/STT: resolve by material size, then measure output.

    These independent synthetic sources test general selection and CAD
    execution. They do not certify an arbitrary production assembly.
    """
    sys.path.insert(0,str(ROOT/'tests'))
    from test_bom import grid
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    batch=ROOT/'storage/validation-fixtures'/('tube-specifications-'+uuid.uuid4().hex[:8])
    batch.mkdir(parents=True);receipts=[]
    session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765'
    def api(route,data=None):
        response=session.post(base+route,json=data,timeout=120) if data is not None else session.get(base+route,timeout=120)
        if response.status_code>=400:raise RuntimeError((route,response.status_code,response.text[:1800]))
        return response.json()
    for width,height,length,number,new,separator in [(60,30,571.5,11,1.2,'x'),(80,40,853.2,27,1,' × '),(50,25,320.3,'A',1.6,'x')]:
        folder=batch/f'{width}-{height}';inputs=folder/'input';inputs.mkdir(parents=True)
        doc=ezdxf.new('R2018');doc.units=4;doc.layers.new('Hidden');m=doc.modelspace()
        code='NEW-'+uuid.uuid4().hex[:10]
        for center,start,end in [((5,5),180,270),((width-5,5),270,0),((width-5,height-5),0,90),((5,height-5),90,180)]:
            for radius in (3,5):m.add_arc(center,radius,start,end)
        for inset in (0,2):
            for p,q in [((inset,5),(inset,height-5)),((width-inset,5),(width-inset,height-5)),((5,inset),(width-5,inset)),((5,height-inset),(width-5,height-inset))]:m.add_line(p,q)
        for x,sign in [(150,1),(150+width,-1),(300,1),(300+height,-1)]:
            m.add_line((x,0),(x,length));m.add_line((x+2*sign,0),(x+2*sign,length),dxfattribs=dict(layer='Hidden'))
        def dim(p,q,base,angle=0):m.add_linear_dim(base=base,p1=p,p2=q,angle=angle).render()
        dim((150,length),(152,length),(145,length+10))
        dim((150,0),(150,length),(130,0),90)
        dim((0,0),(width,0),(0,-10));dim((0,0),(0,height),(-10,0),90)
        m.add_text(code,dxfattribs=dict(insert=(10,-25),height=3))
        m.add_lwpolyline([(-30,-40),(400,-40),(400,length+40),(-30,length+40)],close=True)
        description='Sắt hộp '+separator.join(('2',str(height),str(width),f'{length:g}'))+'mm'
        grid(m,rows=[[str(number),code,description,'Sắt','1',''],['3','BOLT-'+uuid.uuid4().hex[:5],'Bu lông M6','Sắt','4','']],x=550,y=400)
        m.add_text('BẢNG KÊ VẬT TƯ',dxfattribs=dict(insert=(560,420),height=3))
        m.add_lwpolyline([(530,100),(1050,100),(1050,450),(530,450)],close=True)
        source=inputs/'new-tube.dxf';doc.saveas(source)
        converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(inputs,folder/'dwg')
        dwg=folder/'dwg/new-tube.dwg';original=digest(dwg)
        with dwg.open('rb') as stream:
            response=session.post(base+'/documents',files={'file':('synthetic-new-tube-'+uuid.uuid4().hex[:8]+'.dwg',stream,'application/octet-stream')},timeout=30)
        response.raise_for_status();did=response.json()['id'];route='/documents/'+did;deadline=time.monotonic()+150
        while True:
            status=api(route)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.3)
        status['synthetic_test']=True;storage.write_json(storage.folder(did)/'status.json',status)
        sheets=api(route+'/sheets')['items'];target=next(s for s in sheets if 'BẢNG KÊ VẬT TƯ' in s['texts'])
        request=(f'STT {number} ' if isinstance(number,str) else '')+f'Hộp {height}{separator}{width} dày 2 mm thành {new:g} mm'
        started=time.monotonic();plan=api(route+'/change-plans',dict(ids=[target['id']],request=request))
        assert plan['planner']=='checked_tube_wall' and plan['execution_available'],plan
        assert plan['impact_graph']['seed_codes']==[code]
        planning_seconds=time.monotonic()-started
        revision=api(route+f'/change-plans/{plan["id"]}/apply',dict(preview_only=True));rid=revision['id'];rev=route+'/revisions/'+rid
        for selected in revision['targets']:
            response=session.get(base+rev+f'/sheets/{selected["id"]}/preview',timeout=30);response.raise_for_status()
        if approve:assert api(rev+'/approve',dict(confirmed_dependencies=revision['pending_dependencies']))['status']=='approved'
        job=api(rev+'/exports',dict(format='dwg',scope='selection',preview=not approve));deadline=time.monotonic()+150
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.3);job=api(rev+'/exports/'+job['id'])
        response=session.get(base+job['download_url'],timeout=30);response.raise_for_status()
        download=folder/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
        converter.convert_dwg_to_dxf(download,folder/'reopen');reopened=ezdxf.readfile(folder/'reopen/backup.dxf')
        entities=list(reopened.modelspace());dimensions=[round(float(e.get_measurement()),6) for e in entities if e.dxftype()=='DIMENSION']
        assert all(v in dimensions for v in (new,width,height,length)),dimensions
        radii=sorted(round(e.dxf.radius,6) for e in entities if e.dxftype()=='ARC')
        assert radii==sorted([5]*4+[5-new]*4),radii
        after_description=description.replace('Sắt hộp 2',f'Sắt hộp {new:g}',1)
        from bom.reader import plain
        assert any(e.dxftype() in ('TEXT','MTEXT') and plain(e.dxf.text if e.dxftype()=='TEXT' else e.text)==after_description for e in entities)
        assert digest(storage.folder(did)/'original.dwg')==original
        receipt=dict(synthetic=True,document_id=did,plan_id=plan['id'],revision_id=rid,request=request,random_source_code=code,source_stt=number,
                     read_backend=status.get('read_backend'),export_backend=job.get('backend'),preview=job['preview'],
                     planner=plan['planner'],planning_seconds=planning_seconds,approved=approve,source_unchanged=True,download=str(backup.resolve()),download_url=base+job['download_url'],
                     reopened_dimensions_mm=dimensions,reopened_radii_mm=radii,bom=after_description,sha256=digest(backup))
        receipts.append(receipt)
        (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(receipt,ensure_ascii=True),flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
    print('Receipts:',batch/'receipts.json',flush=True)


def bom_view_sync_workflow(exploded=False,select_by_image=False,duplicate_dims=False):
    """New uncoded blocks: source STT/BOM -> measured assembly/detail -> DWG."""
    sys.path.insert(0,str(ROOT/'tests'))
    from test_bom import grid
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    from ezdxf.enums import TextEntityAlignment
    token=uuid.uuid4().hex[:8];code='UNSEEN-'+token;task=ROOT/'storage/validation-fixtures'/(('exploded-view-sync-' if exploded else 'bom-view-sync-')+token)
    inputs=task/'input';inputs.mkdir(parents=True);source=inputs/'source.dxf'
    d=ezdxf.new('R2018');d.units=4;m=d.modelspace();block=d.blocks.new('Uncoded-'+token)
    block.add_lwpolyline([(0,0),(100,0),(100,20),(0,20)],close=True)
    if exploded:block.add_circle((20,10),3)
    body=m.add_blockref(block.name,(100,100));detail=None;detail_edges=[]
    if exploded:
        points=[(900,100),(900,300),(860,300),(860,100)]
        detail_edges=[m.add_line(a,b) for a,b in zip(points,points[1:]+points[:1])]
        detail_hole=m.add_circle((880,140),6)
    else:detail=m.add_blockref(block.name,(900,100),dxfattribs=dict(rotation=90,xscale=2,yscale=2))
    outside=m.add_blockref(block.name,(1600,100))
    for x in (0,750):
        m.add_lwpolyline([(x,0),(x+600,0),(x+600,500),(x,500)],close=True)
        m.add_text('PART NAME',dxfattribs=dict(insert=(x+10,20),height=4))
    m.add_text(code,dxfattribs=dict(insert=(950,30),height=4))
    grid(m,rows=[['1',code,'Bas 2x20x100','Sắt','1',''],['2','OTHER-'+token,'Bas 2x30x100','Sắt','1','']],x=20,y=450)
    # A detail frame has its own raw material table, separate from assembly STT.
    grid(m,rows=[['1','STOCK-'+token,'Sắt tấm 2x1220x2500','Sắt','1','']],x=800,y=450)
    m.add_text('BẢNG KÊ NGUYÊN LIỆU',dxfattribs=dict(insert=(800,470),height=4))
    for label,center,radius in [('C1',(-30,250),8),('1',(80,110),5)]:
        m.add_circle(center,radius)
        m.add_text(label,dxfattribs=dict(height=3)).set_placement(center,align=TextEntityAlignment.MIDDLE_CENTER)
    arrow=m.add_leader([(190,110),(85,110)])
    a=m.add_linear_dim(base=(100,80),p1=(100,100),p2=(200,100));a.render()
    b=m.add_linear_dim(base=(920,100),p1=(900,100),p2=(900,300),angle=90,override={'dimlfac':.5});b.render()
    redundant=[]
    if duplicate_dims:
        c=m.add_linear_dim(base=(100,60),p1=(200,100),p2=(100,100));c.render()
        e=m.add_linear_dim(base=(940,100),p1=(900,300),p2=(900,100),angle=90,override={'dimlfac':.5});e.render()
        redundant=[(c.dimension.dxf.handle,1),(e.dimension.dxf.handle,.5)]
    d.saveas(source);converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(inputs,task/'dwg')
    dwg=task/'dwg/source.dwg';original=digest(dwg);client=requests.Session();client.trust_env=False;base='http://127.0.0.1:8765'
    def call(path,data=None):
        response=client.post(base+path,json=data,timeout=150) if data is not None else client.get(base+path,timeout=150)
        if response.status_code>=400:raise RuntimeError(f'{path}: {response.status_code} {response.text[:3000]}')
        return response.json()
    with dwg.open('rb') as stream:
        response=client.post(base+'/documents',files={'file':(('synthetic-exploded-view-sync-' if exploded else 'synthetic-bom-view-sync-')+token+'.dwg',stream,'application/octet-stream')},timeout=30)
        response.raise_for_status();did=response.json()['id']
    root='/documents/'+did;deadline=time.monotonic()+150
    while True:
        state=call(root)
        if state['status']=='ready':break
        if state['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(state)
        time.sleep(.3)
    folder=storage.folder(did);status=storage.read_status(did);status.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',status)
    sheets=call(root+'/sheets')['items'];target=next(t for t in sheets if t['bbox'][0]<1 and t['bbox'][2]>500)
    graph=call(root+'/part-graph');assert any(g['label']=='C1' and g['status']=='source_row_group' for g in graph['drawing_rows']['groups'])
    print(json.dumps(dict(stage='upload_read',document_id=did,frames=len(sheets),source_row='C1')),flush=True)
    selection=None
    if select_by_image:
        mapped=call(root+'/part-map',dict(ids=[target['id']],include_related=True))
        view=next(v for v in mapped['views'] if v['identity_status']=='verified_source_identity' and v['part_codes']==[code] and target['id'] in v['sheet_ids'])
        selection=dict(map_id=mapped['id'],view_id=view['id'],source_hash=mapped['source_hash'],part_code=code)
    request='Chiều dài từ 100 thành 76 mm, giữ đầu trái' if select_by_image else 'Chi tiết số 1 chiều dài từ 100 thành 76 mm, giữ đầu trái'
    started=time.monotonic();plan=call(root+'/change-plans',dict(ids=[target['id']],request=request,**({'part_selection':selection} if selection else {})))
    if selection:
        assert plan['part_selection']['part_code']==code and plan['user_request']==request
        conflict=client.post(base+root+'/change-plans',json=dict(ids=[target['id']],request='Chi tiết số 2 chiều dài từ 100 thành 76 mm, giữ trái',part_selection=selection),timeout=90)
        assert conflict.status_code==422,conflict.text
    assert len(plan['plan']['resize_recipes'])==2,plan
    assert plan['execution_available'],plan['plan']['questions']
    assert plan['material_input_review'][0]['status']=='verified_single_blank_envelope',plan['material_input_review']
    print(json.dumps(dict(stage='plan',id=plan['id'],seconds=round(time.monotonic()-started,2),recipes=2)),flush=True)
    if plan['execution_available']:revision=call(root+f'/change-plans/{plan["id"]}/apply',dict(preview_only=True))
    else:revision=call(root+f'/change-plans/{plan["id"]}/apply-checked-preview',{})
    rid=revision['id'];rev=root+'/revisions/'+rid
    if selection:assert revision['part_selection']['part_code']==code
    assert revision['source_preservation']['status']=='verified_unchanged'
    assert revision.get('complete_product_backup') is False,revision
    for t in revision['targets']:
        if t['kind']!='sheet':continue
        picture=client.get(base+rev+f'/sheets/{t["id"]}/preview',timeout=60);picture.raise_for_status()
        (task/('preview-'+t['id']+'.svg')).write_bytes(picture.content)
    job=call(rev+'/exports',dict(format='dwg',scope='document',preview=True));deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(.5);job=call(rev+'/exports/'+job['id'])
    response=client.get(base+job['download_url'],timeout=30);response.raise_for_status()
    download=task/'download';download.mkdir();backup=download/'checked-preview.dwg';backup.write_bytes(response.content)
    converter.convert_dwg_to_dxf(download,task/'reopen');actual=ezdxf.readfile(task/'reopen/checked-preview.dxf')
    for instance,width in [(body,76),*([] if exploded else [(detail,76)]),(outside,100)]:
        shape=next(iter(actual.blocks[actual.entitydb[instance.dxf.handle].dxf.name].query('LWPOLYLINE')))
        assert abs(max(p[0] for p in shape.get_points())-width)<1e-6
    if exploded:
        vertices=[list(getattr(actual.entitydb[e.dxf.handle].dxf,key)) for e in detail_edges for key in ('start','end')]
        assert abs(max(p[1] for p in vertices)-252)<1e-6 and abs(min(p[1] for p in vertices)-100)<1e-6
        assert list(actual.entitydb[detail_hole.dxf.handle].dxf.center)==[880.,140.,0.]
    assert abs(actual.entitydb[a.dimension.dxf.handle].get_measurement()-76)<1e-6
    assert abs(actual.entitydb[b.dimension.dxf.handle].get_measurement()/2-76)<1e-6
    for ref,factor in redundant:assert abs(actual.entitydb[ref].get_measurement()*factor-76)<1e-6
    assert list(actual.entitydb[arrow.dxf.handle].vertices[0])==[166.,110.,0.]
    assert digest(dwg)==original and digest(folder/'original.dwg')==original
    after=context_for(task/'reopen/checked-preview.dxf',sheets)
    descriptions={r['part_code']:r['description'] for e in after['entities'] for r in e.get('bom',{}).get('rows',[])}
    assert descriptions[code]=='Bas 2x20x76' and descriptions['OTHER-'+token]=='Bas 2x30x100'
    receipt=dict(document_id=did,plan_id=plan['id'],revision_id=rid,source_row_read_from_cad=True,assembly_and_detail_mm=[76,76],exploded_detail=exploded,
        selected_by_image=select_by_image,part_selection=selection,user_request=request,
        redundant_dimensions=duplicate_dims,reopened_redundant_dimensions_mm=[round(actual.entitydb[ref].get_measurement()*factor,6) for ref,factor in redundant],
        outside_instance_mm=100,arrow_tip=[166,110,0],bom_updated=True,source_unchanged=True,download_http_status=200,
        complete_product_backup=revision['complete_product_backup'],synthetic=True,backup=str(backup.resolve()),dwg_sha256=digest(backup),
        raw_material_review=revision['material_input_review'],assembly_review=revision['drawing_sync'],source_preservation=revision['source_preservation'],
        explorer_url=base+f'/explorer?doc={did}&target={target["id"]}&revision={rid}',download_url=base+job['download_url'])
    (task/'report.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(receipt,ensure_ascii=True),flush=True)


def plate_intent_workflow(detail_scope=False,multiple_views=False):
    """Unseen uploads: nominal/actual policy, axis selection and decision reuse.

    These independent random-code DWGs verify the website path, not a claim
    about arbitrary proxy/dynamic objects or production assembly coverage.
    """
    sys.path.insert(0,str(ROOT/'tests'))
    from test_parametric import two_axis_plate_fixture,repeated_plate_views_fixture
    from test_bom import grid
    from cad.edit_engine import digest
    from backend.services import catalog_service as storage
    batch=ROOT/'storage/validation-fixtures'/('plate-intent-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765';receipts=[]
    def call(route,data=None):
        r=session.get(base+route,timeout=150) if data is None else session.post(base+route,json=data,timeout=150)
        if r.status_code>=400:raise RuntimeError((route,r.status_code,r.text[:1800]))
        return r.json()
    for name,width,height,number,target in [('square',27.2,27.2,23,18),('rectangle',40.2,30.2,29,32)]:
        folder=batch/name;inputs=folder/'input';inputs.mkdir(parents=True)
        receiving=[]
        if multiple_views:
            source,_,body,_,outside,dimensions,receiving=repeated_plate_views_fixture(inputs,width,height,position=(1100,100))
        else:source,_,body,outside,_,_,dimensions,_=two_axis_plate_fixture(inputs,width,height)
        d=ezdxf.readfile(source);m=d.modelspace();code='NEW-PLATE-'+uuid.uuid4().hex[:8]
        # Separate actual detail and BOM frames; let ordinary upload discovery
        # and graph building bind them, without injecting a prepared graph.
        for e in list(m):
            if e.dxftype() in ('LINE','MTEXT'):
                points=[e.dxf.start,e.dxf.end] if e.dxftype()=='LINE' else [e.dxf.insert]
                if all(p.x>=200 for p in points):m.delete_entity(e)
        description=f'Bas - Sắt tấm 3x{height-.2:g}x{width-.2:g}mm (Lã rung đá)'
        grid(m,rows=[[str(number),code,description,'Sắt','10',''],['2','OTHER-'+uuid.uuid4().hex[:8],'Bu lông M6','Sắt','4','']],x=250,y=450)
        m.add_text('BẢNG KÊ VẬT TƯ',dxfattribs=dict(insert=(250,470),height=3))
        m.add_text('PART LIST',dxfattribs=dict(insert=(250,480),height=3))
        m.add_lwpolyline([(230,100),(730,100),(730,500),(230,500)],close=True)
        m.add_lwpolyline([(60,45),(195,45),(195,185),(60,185)],close=True)
        m.add_text(code,dxfattribs=dict(insert=(100,60),height=2));d.saveas(source)
        m.add_text('PART NAME',dxfattribs=dict(insert=(100,54),height=2));d.saveas(source)
        if multiple_views:
            # Keep the control instance outside both drawing frames. The
            # original fixture location would lie inside this added frame.
            d.entitydb[outside.dxf.handle].dxf.insert=(1700,100,0)
            m.add_lwpolyline([(990,45),(1300,45),(1300,350),(990,350)],close=True)
            m.add_text(code,dxfattribs=dict(insert=(1050,60),height=2))
            m.add_text('PART NAME',dxfattribs=dict(insert=(1050,54),height=2))
            m.add_mtext(description,dxfattribs=dict(insert=(1050,70),char_height=2));d.saveas(source)
        converter.convert_dxf_to_dwg(inputs,folder/'dwg');dwg=folder/'dwg/plate.dwg';original=digest(dwg)
        with dwg.open('rb') as stream:r=session.post(base+'/documents',files={'file':('synthetic-plate-intent-'+uuid.uuid4().hex[:8]+'.dwg',stream,'application/octet-stream')},timeout=30)
        r.raise_for_status();did=r.json()['id'];root='/documents/'+did;deadline=time.monotonic()+150
        while True:
            state=call(root)
            if state['status']=='ready':break
            if state['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(state)
            time.sleep(.3)
        state.update(synthetic_test=True,auxiliary=True);storage.write_json(storage.folder(did)/'status.json',state)
        sheets=call(root+'/sheets')['items'];selected=next(t for t in sheets if 'BẢNG KÊ VẬT TƯ' in t['texts'])
        graph=call(root+'/part-graph');node=next(n for n in graph['nodes'] if n['code']==code);assert node['detail_sheets'],node
        if detail_scope:
            details=[t for t in sheets if t['id'] in node['detail_sheets']]
            assert len(details)==(2 if multiple_views else 1),details
            selected=min(details,key=lambda t:t['bbox'][0])
        request=f'Giảm chiều dài chi tiết số {number} thành {target:g}'
        if name=='square':
            first=call(root+'/change-plans',dict(ids=[selected['id']],request=request))
            assert not first['execution_available'] and first['plan']['questions']
            confirmed=call(root+f'/change-plans/{first["id"]}/refine',dict(answers=[f'DIM thực tế phải còn đúng {target:g} mm. Cả hai DIM → {target:g} mm, giữ tâm lỗ.']))
            assert confirmed['execution_available'],confirmed['plan']['questions']
            started=time.monotonic();plan=call(root+'/change-plans',dict(ids=[selected['id']],request=request))
            assert plan['request_interpretation'].get('reused_decision'),plan
            expected=[target,target];bom=f'3x{target:g}x{target:g}mm'
        else:
            request+= ' mm, giữ tâm lỗ, DIM thực tế'
            started=time.monotonic();plan=call(root+'/change-plans',dict(ids=[selected['id']],request=request))
            assert not plan['request_interpretation'].get('reused_decision')
            expected=[target,height];bom=f'3x{height-.2:g}x{target:g}mm'
        assert plan['execution_available'] and not plan['plan']['questions'],plan
        planning_seconds=round(time.monotonic()-started,3)
        revision=call(root+f'/change-plans/{plan["id"]}/apply',dict(preview_only=True));rid=revision['id'];rev=root+'/revisions/'+rid
        assert revision['solid_validation']['status']=='passed'
        job=call(rev+'/exports',dict(format='dwg',scope='document',preview=True));deadline=time.monotonic()+180
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.5);job=call(rev+'/exports/'+job['id'])
        r=session.get(base+job['download_url'],timeout=30);r.raise_for_status();download=folder/'download';download.mkdir();backup=download/'preview.dwg';backup.write_bytes(r.content)
        converter.convert_dwg_to_dxf(download,folder/'reopen');actual=ezdxf.readfile(folder/'reopen/preview.dxf')
        measured=[actual.entitydb[e.dxf.handle].get_measurement() for e in dimensions]
        assert all(abs(a-b)<1e-6 for a,b in zip(measured,expected)),measured
        measured_receiving=[actual.entitydb[e.dxf.handle].get_measurement()/2 for e in receiving]
        if multiple_views:
            assert len(plan['plan']['resize_recipes'])==(4 if name=='square' else 2)
            assert all(abs(a-b)<1e-6 for a,b in zip(measured_receiving,expected)),measured_receiving
        checked=context_for(folder/'reopen/preview.dxf',sheets);descriptions={r['part_code']:r['description'] for e in checked['entities'] for r in e.get('bom',{}).get('rows',[])}
        assert bom in descriptions[code],descriptions
        outside_shape=next(iter(actual.blocks[actual.entitydb[outside.dxf.handle].dxf.name].query('LWPOLYLINE')))
        assert abs(max(p[0] for p in outside_shape.get_points())-width)<1e-6
        assert digest(dwg)==original and digest(storage.folder(did)/'original.dwg')==original
        receipt=dict(synthetic=True,kind=name,document_id=did,part_code=code,part_number=number,request=request,
            selection_scope='detail_without_bom' if detail_scope else 'assembly_bom',selected_target_id=selected['id'],
            bom_scope=plan['request_interpretation'].get('bom_scope'),
            source_view_count=2 if multiple_views else 1,receiving_dimensions_mm=measured_receiving,
            plan_id=plan['id'],revision_id=rid,actual_dimensions_mm=measured,expected_dimensions_mm=expected,
            decision_reused=name=='square',planning_seconds=planning_seconds,bom=descriptions[code],
            source_unchanged=True,outside_instance_unchanged=True,download_http_status=r.status_code,
            solid_validation=revision['solid_validation']['status'],backup=str(backup.resolve()),download_url=base+job['download_url'],
            complete_product_backup=revision.get('complete_product_backup'),limitations='Synthetic geometry validation; not arbitrary DWG or production assembly certification')
        receipts.append(receipt);(folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(receipt,ensure_ascii=True),flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')


def projected_face_workflow(balloon=False,multiface=False,split_lines=False,holes=0,joined=False,approve=False):
    """Upload a new independent oblique-face DWG, edit, download and measure."""
    sys.path.insert(0,str(ROOT/'tests'))
    from test_assembly import projected_face_fixture,projected_multiface_fixture,split_projected_fixture
    from cad.edit_engine import digest
    from backend.services import catalog_service as storage
    from cad.geometry import near
    import numpy as np
    token=uuid.uuid4().hex[:8];task=ROOT/'storage/validation-fixtures'/('projected-face-'+token)
    inputs=task/'input';inputs.mkdir(parents=True)
    if joined:multiface=True
    if split_lines:
        source,_,_,source_root,target_root,outside,matrix,origin=split_projected_fixture(inputs,'both',holes,asymmetric=holes==0)
        transforms=[(matrix,origin)]
    elif multiface:
        source,_,_,source_root,target_root,outside,transforms=projected_multiface_fixture(inputs,transformed=True)
        matrix,origin=transforms[0]
    else:
        source,_,_,source_root,target_root,outside,matrix,origin=projected_face_fixture(inputs,mutation='no_identity' if balloon else None,transformed=True,dimensions=True)
        transforms=[(matrix,origin)]
    d=ezdxf.readfile(source);code='UNSEEN-'+token
    if joined:
        block=d.blocks['OBLIQUE-FACE'];seen=set()
        for poly in list(block.query('LWPOLYLINE')):
            ps=[list(p[:2]) for p in poly.get_points()]
            for a,b in zip(ps,ps[1:]+ps[:1]):
                edge=tuple(sorted(tuple(round(v,5) for v in p) for p in (a,b)))
                if edge not in seen:block.add_line(a,b);seen.add(edge)
            block.delete_entity(poly)
    d.blocks.rename_block('UNSEEN-FACE',code)
    for layout in d.layouts:
        for e in layout.query('INSERT'):
            if e.dxf.name=='UNSEEN-FACE':e.dxf.name=code
            for a in e.attribs:
                if a.dxf.text=='UNSEEN-FACE':a.dxf.text=code
        for e in layout.query('TEXT MTEXT'):
            if e.dxftype()=='TEXT':e.dxf.text=e.dxf.text.replace('UNSEEN-FACE',code)
            else:e.text=e.text.replace('UNSEEN-FACE',code)
    m=d.modelspace();m.add_lwpolyline([(-30,-40),(800,-40),(800,320),(-30,320)],close=True)
    m.add_text('PART NAME',dxfattribs={'insert':(-20,-30),'height':3})
    if balloon:
        from ezdxf.enums import TextEntityAlignment
        from ezdxf.math import Vec3
        point=matrix@np.array([40,30])+origin
        point=d.entitydb[target_root].matrix44().transform(Vec3(*point,0))
        m.add_circle((600,120),8)
        m.add_text('01',dxfattribs={'height':3}).set_placement((600,120),align=TextEntityAlignment.MIDDLE_CENTER)
        m.add_leader([point,(592,120)])
    d.saveas(source);converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(inputs,task/'dwg')
    dwg=task/'dwg/projected-product.dwg';original=digest(dwg)
    session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765'
    def api(path,data=None):
        r=session.post(base+path,json=data,timeout=180) if data is not None else session.get(base+path,timeout=180)
        r.raise_for_status();return r.json()
    with dwg.open('rb') as stream:
        response=session.post(base+'/documents',files={'file':('synthetic-projected-'+token+'.dwg',stream,'application/octet-stream')},timeout=30)
        response.raise_for_status();did=response.json()['id']
    route='/documents/'+did;deadline=time.monotonic()+150
    while True:
        state=api(route)
        if state['status']=='ready':break
        if state['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(state)
        time.sleep(.4)
    folder=storage.folder(did);state=storage.read_status(did);state.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',state)
    target=next(t for t in api(route+'/sheets')['items'] if t['bbox'][0]<0 and t['bbox'][2]>700)
    request=f'Mã {code} chiều dài từ 100 thành 85 mm, giữ trái'
    plan=api(route+'/change-plans',dict(ids=[target['id']],request=request))
    assert plan['execution_available'] or plan.get('preview_execution_available'),plan['plan']['questions']
    action='apply' if plan['execution_available'] else 'apply-checked-preview'
    revision=api(route+f'/change-plans/{plan["id"]}/{action}',dict(preview_only=True));rid=revision['id'];rev=route+'/revisions/'+rid
    if approve:
        for target in revision['targets']:
            kind='sheets' if target['kind']=='sheet' else 'items'
            r=session.get(base+rev+f'/{kind}/{target["id"]}/preview',timeout=60);r.raise_for_status()
        assert api(rev+'/approve',dict(confirmed_dependencies=revision['pending_dependencies']))['status']=='approved'
    job=api(rev+'/exports',dict(format='dwg',scope='selection',preview=not approve));deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(.5);job=api(rev+'/exports/'+job['id'])
    r=session.get(base+job['download_url'],timeout=30);r.raise_for_status()
    download=task/'download';download.mkdir();backup=download/('projected-backup.dwg' if approve else 'projected-preview.dwg');backup.write_bytes(r.content)
    converter.convert_dwg_to_dxf(download,task/'reopened');after=ezdxf.readfile(task/'reopened'/backup.with_suffix('.dxf').name)
    blocks=[after.blocks[after.entitydb[root].dxf.name] for root in (source_root,target_root)]
    if split_lines or joined:
        from graph.projected_profiles import straight_faces
        from cad.geometry import snapshot
        rings=[]
        for block in blocks:
            rings.append(straight_faces([dict(ref=e.dxf.handle,type=e.dxftype(),geometry=snapshot(e)) for e in block.query('LINE LWPOLYLINE')]))
        assert len(rings[0])==1 and len(rings[1])==len(transforms)
        points=rings[0][0]['points'];assert max(p[0] for p in points)==85
        from shapely.geometry import Polygon
        used=set()
        for matrix,origin in transforms:
            projected=[(matrix@np.array(p[:2])+origin).tolist() for p in points]
            matches=[i for i,f in enumerate(rings[1]) if Polygon(projected).hausdorff_distance(Polygon(f['points']))<1e-5]
            assert len(matches)==1 and matches[0] not in used;used.add(matches[0])
        if joined:assert len(list(blocks[1].query('LINE')))==7
        faces=rings[1]
    else:
        plate=list(blocks[0].query('LWPOLYLINE'))[0];faces=list(blocks[1].query('LWPOLYLINE'))
        assert max(p[0] for p in plate.get_points())==85
        assert len(faces)==len(transforms)
    circles=list(blocks[0].query('CIRCLE'));ellipses=list(blocks[1].query('ELLIPSE'))
    for i,(face,(matrix,origin)) in enumerate(zip(faces,transforms)):
        if not (split_lines or joined):assert near([list(p[:2]) for p in face.get_points()],[(matrix@np.array(p[:2])+origin).tolist() for p in plate.get_points()],1e-5)
        for circle,ellipse in zip(circles,ellipses[2*i:2*i+2]):
            assert near(list(ellipse.dxf.center)[:2],(matrix@np.array(list(circle.dxf.center)[:2])+origin).tolist(),1e-5)
    dims=list(blocks[1].query('DIMENSION'));assert len(dims)==len(transforms)
    assert all(abs(dim.get_measurement()*abs(dim.override().get('dimlfac',1))-85)<1e-5 for dim in dims)
    assert digest(folder/'original.dwg')==original
    receipt=dict(synthetic=True,customer_file=False,document_id=did,revision_id=rid,plan_id=plan['id'],request=request,
        download=str(backup.resolve()),download_url=base+job['download_url'],download_http=r.status_code,sha256=digest(backup),
        source_unchanged=True,export_backend=job.get('backend'),identity_from_local_balloon=balloon,split_line_outlines=split_lines or joined,shared_native_seam=joined,
        projected_faces=len(faces),projected_holes=len(ellipses),source_length_mm=85,projected_dimension_mm=85,
        drawing_sync=revision['drawing_sync'],roundtrip='validated_roundtrip',approved=approve)
    (task/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=True),flush=True)


def source_gap_workflow():
    """Real upload/AutoCAD readback with a requested, unannotated source gap."""
    sys.path.insert(0,str(ROOT/'tests'))
    from test_native_contacts import native_span_fits_fixture
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    token=uuid.uuid4().hex[:8];task=ROOT/'storage/validation-fixtures'/('mount-gap-'+token)
    inputs=task/'input';inputs.mkdir(parents=True)
    source,_,_,members,total,_,request=native_span_fits_fixture(inputs,gap=2,notched=True)
    d=ezdxf.readfile(source);m=d.modelspace()
    m.add_lwpolyline([(-30,-40),(1000,-40),(1000,450),(-30,450)],close=True)
    m.add_text('PART NAME',dxfattribs={'insert':(-20,-30),'height':3});d.saveas(source)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(inputs,task/'dwg')
    dwg=task/'dwg/span-fit.dwg';original=digest(dwg)
    session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765'
    def api(path,data=None):
        r=session.post(base+path,json=data,timeout=180) if data is not None else session.get(base+path,timeout=180)
        r.raise_for_status();return r.json()
    with dwg.open('rb') as stream:
        r=session.post(base+'/documents',files={'file':('synthetic-mount-gap-'+token+'.dwg',stream,'application/octet-stream')},timeout=30)
        r.raise_for_status();did=r.json()['id']
    route='/documents/'+did;deadline=time.monotonic()+150
    while True:
        state=api(route)
        if state['status']=='ready':break
        if state['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(state)
        time.sleep(.4)
    folder=storage.folder(did);state=storage.read_status(did);state.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',state)
    target=next(t for t in api(route+'/sheets')['items'] if t['bbox'][0]<0 and t['bbox'][2]>900)
    request+='; giữ khe hở nguồn'
    plan=api(route+'/change-plans',dict(ids=[target['id']],request=request))
    assert plan['execution_available'] or plan.get('preview_execution_available'),plan['plan']['questions']
    raw=plan.get('checked_preview_plan') or plan['plan']
    assert any(b['clearance_policy']=='source_faces_on_explicit_keep_gap_request' and b['clearances']==[0,2] for b in raw['native_span_fits'])
    action='apply' if plan['execution_available'] else 'apply-checked-preview'
    revision=api(route+f'/change-plans/{plan["id"]}/{action}',dict(preview_only=True));rid=revision['id'];rev=route+'/revisions/'+rid
    job=api(rev+'/exports',dict(format='dwg',scope='selection',preview=True));deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(.5);job=api(rev+'/exports/'+job['id'])
    r=session.get(base+job['download_url'],timeout=30);r.raise_for_status()
    download=task/'download';download.mkdir();backup=download/'mount-gap-preview.dwg';backup.write_bytes(r.content)
    converter.convert_dwg_to_dxf(download,task/'reopened');after=ezdxf.readfile(task/'reopened/mount-gap-preview.dxf')
    lower,middle,upper=[after.entitydb[e.dxf.handle] for e in members]
    heights=[max(d.get_measurement() for d in after.blocks[e.dxf.name].query('DIMENSION')) for e in (lower,middle,upper)]
    assert all(abs(a-b)<1e-5 for a,b in zip(heights,[80,110,110]))
    # A top-anchored resize may change the block's local minimum while its
    # insertion point stays put. Measure the actual placed faces, not INSERT.
    def height_planes(insert):
        ys=[p[1] for e in insert.virtual_entities() if e.dxftype()=='LWPOLYLINE' for p in e.get_points()]
        return min(ys),max(ys)
    lower_planes,middle_planes,upper_planes=map(height_planes,(lower,middle,upper))
    gap=upper_planes[0]-middle_planes[1]
    assert abs(lower_planes[0])<1e-5 and abs(upper_planes[1]-302)<1e-5
    assert abs(gap-2)<1e-5 and abs(after.entitydb[total.dxf.handle].get_measurement()-302)<1e-5
    assert digest(folder/'original.dwg')==original
    receipt=dict(synthetic=True,customer_file=False,document_id=did,plan_id=plan['id'],revision_id=rid,request=request,
        download=str(backup.resolve()),download_url=base+job['download_url'],download_http=r.status_code,sha256=digest(backup),
        source_unchanged=True,export_backend=job.get('backend'),source_gap_mm=2,after_gap_mm=gap,
        after_heights_mm=heights,overall_height_mm=302,roundtrip='validated_roundtrip',approved=False)
    (task/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(receipt,ensure_ascii=True),flush=True)


def anonymous_mount_workflow():
    """New anonymous DWG: local BOM arrows own bodies, including a DIM-less receiver."""
    import math
    sys.path.insert(0,str(ROOT/'tests'))
    from test_native_contacts import anonymous_bom_contact_fixture
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    token=uuid.uuid4().hex[:8];task=ROOT/'storage/validation-fixtures'/('leader-mount-'+token)
    inputs=task/'input';inputs.mkdir(parents=True)
    source,context,a,b,total,outside,transform=anonymous_bom_contact_fixture(inputs,23,'receiver_no_dim')
    d=ezdxf.readfile(source);m=d.modelspace()
    for target in context['targets']:
        x0,y0,x1,y1=target['bbox'];m.add_lwpolyline([(x0,y0),(x1,y0),(x1,y1),(x0,y1)],close=True)
        m.add_text('PART NAME',dxfattribs={'insert':(x0+3,y0+3),'height':2})
    d.saveas(source)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(inputs,task/'dwg')
    dwg=task/'dwg/contacts.dwg';original=digest(dwg)
    session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765'
    def api(path,data=None):
        r=session.post(base+path,json=data,timeout=180) if data is not None else session.get(base+path,timeout=180)
        if not r.ok:raise RuntimeError(f'{path}: {r.status_code} {r.text[:2000]}')
        return r.json()
    with dwg.open('rb') as stream:
        r=session.post(base+'/documents',files={'file':('synthetic-leader-mount-'+token+'.dwg',stream,'application/octet-stream')},timeout=30)
        r.raise_for_status();did=r.json()['id']
    route='/documents/'+did;deadline=time.monotonic()+150
    while True:
        state=api(route)
        if state['status']=='ready':break
        if state['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(state)
        time.sleep(.4)
    folder=storage.folder(did);state=storage.read_status(did);state.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',state)
    sheets=api(route+'/sheets')['items']
    target=next(t for t in sheets if t['bbox'][0]<0 and t['bbox'][2]<150)
    request='Chi tiết số 1 chiều cao từ 100 thành 80 mm, giữ đầu dưới'
    plan=api(route+'/change-plans',dict(ids=[target['id']],request=request))
    assert plan['execution_available'],plan['plan']['questions']
    revision=api(route+f'/change-plans/{plan["id"]}/apply',dict(preview_only=True));rid=revision['id'];rev=route+'/revisions/'+rid
    assert revision.get('complete_product_backup') is not False,revision.get('preview_only_reason')
    for related in revision['targets']:
        kind='sheets' if related['kind']=='sheet' else 'items'
        picture=session.get(base+rev+f'/{kind}/{related["id"]}/preview',timeout=60);picture.raise_for_status()
        if related['id']==target['id']:(task/'after.svg').write_text(picture.text,encoding='utf8')
    approved=api(rev+'/approve',dict(confirmed_dependencies=revision['pending_dependencies']))
    assert approved['status']=='approved'
    job=api(rev+'/exports',dict(format='dwg',scope='selection',preview=False));deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(.5);job=api(rev+'/exports/'+job['id'])
    r=session.get(base+job['download_url'],timeout=30);r.raise_for_status()
    download=task/'download';download.mkdir();backup=download/'leader-mount-backup.dwg';backup.write_bytes(r.content)
    converter.convert_dwg_to_dxf(download,task/'reopened');after=ezdxf.readfile(task/'reopened/leader-mount-backup.dxf')
    from ezdxf.math import Vec3
    receiver=after.entitydb[b.dxf.handle];expected=list(transform.transform(Vec3(600,80,0)))
    assert all(abs(x-y)<1e-5 for x,y in zip(receiver.dxf.insert,expected))
    assert not list(after.blocks[receiver.dxf.name].query('DIMENSION'))
    def local_height(insert):
        outline=list(after.blocks[insert.dxf.name].query('LWPOLYLINE'))
        assert len(outline)==1
        ys=[p[1] for p in outline[0].get_points()]
        return max(ys)-min(ys)
    assert abs(local_height(after.entitydb[a.dxf.handle])-80)<1e-5
    assert abs(local_height(receiver)-100)<1e-5
    assert abs(after.entitydb[total.dxf.handle].get_measurement()-180)<1e-5
    from cad.sheets import discover_sheets
    reopened_context=context_for(task/'reopened/leader-mount-backup.dxf',discover_sheets(task/'reopened/leader-mount-backup.dxf'))
    rows=[row for e in reopened_context['entities'] for row in e.get('bom',{}).get('rows',[])]
    assert next(row['description'] for row in rows if row['part_code']=='PART-A')=='Bas 2x20x80'
    assert next(row['description'] for row in rows if row['part_code']=='PART-B')=='Bas 2x20x100'
    assert digest(folder/'original.dwg')==original
    receipt=dict(synthetic=True,customer_file=False,document_id=did,plan_id=plan['id'],revision_id=rid,
        request=request,approved=True,source_unchanged=True,receiver_has_no_dimension=True,
        receiver_position=list(receiver.dxf.insert),overall_height_mm=180,source_part_height_mm=80,receiver_height_mm=100,bom_verified=True,
        assembly_rotation_degrees=23,roundtrip='validated_roundtrip',drawing_sync=approved.get('drawing_sync'),
        download_url=base+job['download_url'],download_http=r.status_code,sha256=digest(backup),backup=str(backup.resolve()))
    (task/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=True),flush=True)


def curved_projection_workflow(approve=False,circular=False,mirror=False):
    """Independent curved-face DWG through the public editing/export routes."""
    sys.path.insert(0,str(ROOT/'tests'))
    from test_geometry import curved_projection_fixture
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    from cad.geometry import near
    from graph.curved_projected_profiles import inventory,matches
    from cad.sheets import discover_sheets
    token=uuid.uuid4().hex[:8];task=ROOT/'storage/validation-fixtures'/('curved-projection-'+token)
    inputs=task/'input';inputs.mkdir(parents=True)
    source,_,_,ids=curved_projection_fixture(inputs,mirror=mirror,circular=circular)
    d=ezdxf.readfile(source);code='UNSEEN-CURVE-'+token
    d.blocks['PROJECTED-FACE'].add_text('Tấm cung 8x50x100mm',dxfattribs=dict(insert=(0,-15),height=3))
    d.blocks.rename_block('CURVED-PART',code)
    for layout in d.layouts:
        for e in layout.query('INSERT'):
            if e.dxf.name=='CURVED-PART':e.dxf.name=code
            for a in e.attribs:a.dxf.text=a.dxf.text.replace('CURVED-PART',code)
        for e in layout.query('TEXT MTEXT'):
            if e.dxftype()=='TEXT':e.dxf.text=e.dxf.text.replace('CURVED-PART',code)
            else:e.text=e.text.replace('CURVED-PART',code)
    m=d.modelspace();m.add_lwpolyline([(-100,-200),(1200,-200),(1200,400),(-100,400)],close=True)
    m.add_text('PART NAME',dxfattribs=dict(insert=(-90,-90),height=3));d.saveas(source)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(inputs,task/'dwg')
    dwg=task/'dwg'/source.with_suffix('.dwg').name;original=digest(dwg)
    session=requests.Session();session.trust_env=False;base='http://127.0.0.1:8765'
    def api(path,data=None):
        r=session.post(base+path,json=data,timeout=180) if data is not None else session.get(base+path,timeout=180)
        if not r.ok:raise RuntimeError(f'{path}: {r.status_code} {r.text[:2000]}')
        return r.json()
    with dwg.open('rb') as stream:
        r=session.post(base+'/documents',files={'file':('synthetic-curved-projection-'+token+'.dwg',stream,'application/octet-stream')},timeout=30)
        r.raise_for_status();did=r.json()['id']
    route='/documents/'+did;deadline=time.monotonic()+150
    while True:
        state=api(route)
        if state['status']=='ready':break
        if state['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(state)
        time.sleep(.4)
    folder=storage.folder(did);state=storage.read_status(did);state.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',state)
    target=next(t for t in api(route+'/sheets')['items'] if t['bbox'][0]<0 and t['bbox'][2]>1100)
    request=f'Mã {code} độ dày từ 8 thành 6 mm, giữ biên ngoài'
    plan=api(route+'/change-plans',dict(ids=[target['id']],request=request))
    (task/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
    assert plan['execution_available'] or plan.get('preview_execution_available'),plan['plan']['questions']
    action='apply' if plan['execution_available'] else 'apply-checked-preview'
    revision=api(route+f'/change-plans/{plan["id"]}/{action}',dict(preview_only=True));rid=revision['id'];rev=route+'/revisions/'+rid
    for related in revision['targets']:
        kind='sheets' if related['kind']=='sheet' else 'items'
        picture=session.get(base+rev+f'/{kind}/{related["id"]}/preview',timeout=60);picture.raise_for_status()
        if related['id']==target['id']:(task/'after.svg').write_text(picture.text,encoding='utf8')
    if approve:assert api(rev+'/approve',dict(confirmed_dependencies=revision['pending_dependencies']))['status']=='approved'
    job=api(rev+'/exports',dict(format='dwg',scope='selection',preview=not approve));deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(.5);job=api(rev+'/exports/'+job['id'])
    r=session.get(base+job['download_url'],timeout=30);r.raise_for_status()
    download=task/'download';download.mkdir();backup=download/'curved-face-backup.dwg';backup.write_bytes(r.content)
    converter.convert_dwg_to_dxf(download,task/'reopened');reopened=task/'reopened/curved-face-backup.dxf';after=ezdxf.readfile(reopened)
    blocks=[after.blocks[after.entitydb[ids[k]].dxf.name] for k in ('source_root','target_root')]
    assert sorted(e.dxf.radius for e in blocks[0].query('ARC'))==[44,50]
    assert sorted(e.dxf.radius for e in blocks[0].query('CIRCLE'))==[1,1.3]
    if circular:
        assert near(sorted(e.dxf.radius for e in blocks[1].query('ARC')),[74.8,85],1e-6)
        assert near(sorted(e.dxf.radius for e in blocks[1].query('CIRCLE')),[1.7,2.21],1e-6)
        assert not list(blocks[1].query('ELLIPSE'))
    else:assert len(list(blocks[1].query('ELLIPSE')))==4
    assert [e.dxf.text for e in blocks[1].query('TEXT')]==['Tấm cung 6x50x100mm']
    context=context_for(reopened,discover_sheets(reopened));_,views=inventory(context)
    a=next(v for v in views if v['root']==ids['source_root']);b=next(v for v in views if v['root']==ids['target_root'])
    assert len(matches(a,b))==1
    rows=[row for e in context['entities'] for row in e.get('bom',{}).get('rows',[])]
    assert next(row['description'] for row in rows if row['part_code']==code)=='Tấm cung 6x50x100mm'
    assert digest(folder/'original.dwg')==original
    receipt=dict(synthetic=True,customer_file=False,document_id=did,revision_id=rid,plan_id=plan['id'],request=request,
        download=str(backup.resolve()),download_url=base+job['download_url'],download_http=r.status_code,sha256=digest(backup),
        source_unchanged=True,export_backend=job.get('backend'),outer_radius_mm=50,inner_radius_mm=44,wall_mm=6,
        projected_analytic_ellipses=0 if circular else 4,projected_native_arcs=2 if circular else 0,mirrored=mirror,
        complete_face_correspondence=True,bom_verified=True,projected_description_verified=True,
        drawing_sync=revision['drawing_sync'],roundtrip='validated_roundtrip',approved=approve)
    (task/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(receipt,ensure_ascii=True),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    curves=parser.add_mutually_exclusive_group()
    curves.add_argument('--legacy',action='store_true',help='Use a classic 2D POLYLINE with semicircular bulges')
    curves.add_argument('--spline',action='store_true',help='Use native rational quadratic SPLINE end caps')
    curves.add_argument('--nurbs',action='store_true',help='Use noncircular rational cubic SPLINE end caps')
    curves.add_argument('--ellipse',action='store_true',help='Use native noncircular ELLIPSE end caps')
    curves.add_argument('--association',choices=['midpoint','center'],help='Use a layout part with native DIMASSOC midpoint/center snaps')
    curves.add_argument('--container-scopes',action='store_true',help='Check framed drawings inside a shared nested container')
    curves.add_argument('--shared-export-masks',action='store_true',help='Roundtrip different source-selected subsets of shared nested instances')
    curves.add_argument('--tube-specifications',action='store_true',help='New DWGs selected by BOM tube specification without a known code or STT')
    curves.add_argument('--plate-intent',action='store_true',help='New DWGs: actual versus nominal size, explicit single/two axes, saved human decision, export/reopen')
    curves.add_argument('--plate-linked-views',action='store_true',help='New DWGs: select one detail, synchronize a cloned rotated/scaled view and remote BOM, export and reopen')
    curves.add_argument('--projected-face',action='store_true',help='New DWG: match a flat detail to a rotated/scaled oblique face using all outline vertices and two circular/elliptic bores')
    curves.add_argument('--projected-face-balloon',action='store_true',help='New DWG: identify an uncoded oblique face through its real local BOM/balloon/leader before editing')
    curves.add_argument('--projected-multiface',action='store_true',help='New DWG: two registered perforated faces in one rotated/scaled INSERT; preserve their shared seam and both physical DIMs')
    curves.add_argument('--projected-lines',action='store_true',help='New DWG: oblique face assembled from LINE entities, zero/one bores, full unique correspondence and DWG reopen')
    curves.add_argument('--projected-shared-seam',action='store_true',help='New DWG: two projected faces made of seven LINEs with one shared native seam, four bores, two true DIMs')
    curves.add_argument('--curved-projection',action='store_true',help='New DWG: native circular-edge face and its independently coded elliptical projection, edit/BOM/approve/export/reopen')
    curves.add_argument('--circular-projection',action='store_true',help='New DWG: rotated, scaled and reflected native ARC/CIRCLE face, edit/BOM/approve/export/reopen')
    parser.add_argument('--projected-line-holes',type=int,choices=[0,1],default=0)
    curves.add_argument('--source-mount-gap',action='store_true',help='New DWG: preserve an explicitly requested source gap between measured native faces without inventing a fixed datum')
    curves.add_argument('--anonymous-mount',action='store_true',help='New DWG: anonymous BOM/leader-owned bodies, rotated face contact, receiver without DIM, approval/download/reopen')
    curves.add_argument('--bom-view-sync',action='store_true',help='New uncoded blocks identified through local STT/BOM and complete view correspondence')
    curves.add_argument('--exploded-view-sync',action='store_true',help='New DWG with a block and a rotated/scaled exploded LINE view; preserve source and reopen the new DWG')
    curves.add_argument('--selected-part-sync',action='store_true',help='Choose a source Part Map image then resize without typing its STT/code; verify identity and new DWG')
    curves.add_argument('--redundant-dim-sync',action='store_true',help='New DWG with duplicate/reversed source and exploded-view dimensions; resize once, synchronize all DIMs and BOM, reopen output')
    parser.add_argument('--depth',type=int,default=8)
    parser.add_argument('--approve',action='store_true',help='Exercise approval/final backup for this synthetic fixture only')
    parser.add_argument('--background',action='store_true',help='Exercise resumable planning jobs used by the browser')
    parser.add_argument('--detail-scope',action='store_true',help='With --plate-intent, select the detail frame whose BOM is in another frame')
    args=parser.parse_args()
    if args.detail_scope and not args.plate_intent:parser.error('--detail-scope requires --plate-intent')
    if args.plate_intent:return plate_intent_workflow(args.detail_scope)
    if args.plate_linked_views:return plate_intent_workflow(detail_scope=True,multiple_views=True)
    if args.projected_face:return projected_face_workflow(approve=args.approve)
    if args.projected_face_balloon:return projected_face_workflow(balloon=True,approve=args.approve)
    if args.projected_multiface:return projected_face_workflow(multiface=True,approve=args.approve)
    if args.projected_lines:return projected_face_workflow(split_lines=True,holes=args.projected_line_holes,approve=args.approve)
    if args.projected_shared_seam:return projected_face_workflow(joined=True,approve=args.approve)
    if args.curved_projection:return curved_projection_workflow(approve=args.approve)
    if args.circular_projection:return curved_projection_workflow(approve=args.approve,circular=True,mirror=True)
    if args.source_mount_gap:return source_gap_workflow()
    if args.anonymous_mount:return anonymous_mount_workflow()
    if args.bom_view_sync:return bom_view_sync_workflow()
    if args.exploded_view_sync:return bom_view_sync_workflow(exploded=True)
    if args.selected_part_sync:return bom_view_sync_workflow(exploded=True,select_by_image=True)
    if args.redundant_dim_sync:
        bom_view_sync_workflow(select_by_image=True,duplicate_dims=True)
        return bom_view_sync_workflow(exploded=True,select_by_image=True,duplicate_dims=True)
    if args.container_scopes:return container_scope_workflow()
    if args.shared_export_masks:return shared_export_masks_workflow()
    if args.tube_specifications:return tube_specifications_workflow(args.approve)
    if args.association:return association_workflow(args.association,args.approve)
    if not 0<=args.depth<=20:parser.error('depth must be between 0 and 20')
    base='http://127.0.0.1:8765'
    token=uuid.uuid4().hex[:8]
    task=ROOT/'storage'/'validation-fixtures'/('general-workflow-'+token)
    inputs=task/'input';inputs.mkdir(parents=True)
    d=ezdxf.new('R2018');d.units=4
    part=d.blocks.new('UNSEEN-'+token)
    if args.legacy:
        part.add_polyline2d([(15,0,0),(125,0,1),(125,30,0),(15,30,1)],format='xyb',close=True,dxfattribs={'flags':129})
    elif args.nurbs:
        part.add_line((15,0),(125,0));part.add_line((125,30),(15,30))
        q=[(15,30,0),(6,30,0),(0,25.5,0),(0,15,0),(0,4.5,0),(6,0,0),(15,0,0)]
        for poles in (q,[(140-x,y,z) for x,y,z in q[::-1]]):
            s=part.add_spline();s.dxf.degree=3;s.control_points=poles
            s.knots=[0]*4+[.5]*3+[1]*4;s.weights=[1,.8,1.1,1,1.1,.8,1];s.dxf.flags=4
    elif args.ellipse:
        part.add_line((20,0),(120,0));part.add_line((120,30),(20,30))
        from math import pi
        part.add_ellipse((20,15),major_axis=(20,0),ratio=.75,start_param=pi/2,end_param=3*pi/2)
        part.add_ellipse((120,15),major_axis=(20,0),ratio=.75,start_param=3*pi/2,end_param=5*pi/2)
    elif args.spline:
        from ezdxf.math import BSpline,ConstructionArc
        part.add_line((15,0),(125,0));part.add_line((125,30),(15,30))
        for center,first,last in [((15,15),90,270),((125,15),270,90)]:
            part.add_spline().apply_construction_tool(BSpline.from_arc(ConstructionArc(center,15,first,last)))
    else:part.add_lwpolyline([(0,0),(140,0),(140,30),(80,30),(80,25),(60,25),(60,30),(0,30)],close=True)
    part.add_circle((15,15),2);part.add_circle((125,15),2)
    dim_y=15 if args.legacy or args.spline or args.nurbs or args.ellipse else 0
    dim=part.add_aligned_dim(p1=(0,dim_y),p2=(140,dim_y),distance=10);dim.render()
    dim.dimension.dxf.dimtype=(dim.dimension.dxf.dimtype & ~15)|1
    dim.dimension.dxf.angle=0
    name=part.name
    for i in range(args.depth):
        wrapper=d.blocks.new(f'WRAP-{token}-{i}')
        wrapper.add_blockref(name,(3,4),dxfattribs={'rotation':9})
        name=wrapper.name
    d.modelspace().add_blockref(name,(400,300),dxfattribs={'rotation':23,'xscale':2,'yscale':2,'zscale':2})
    d.saveas(inputs/'synthetic-general.dxf')
    converter=DWGConverter(converter_path())
    converter.convert_dxf_to_dwg(str(inputs),str(task/'dwg'))
    source=task/'dwg'/'synthetic-general.dwg'
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open('rb') as file:
        response=requests.post(base+'/documents',files={'file':('synthetic-general-'+token+'.dwg',file,'application/octet-stream')},timeout=20)
    response.raise_for_status();did=response.json()['id']
    deadline=time.monotonic()+180
    while True:
        state=requests.get(base+'/documents/'+did,timeout=10);state.raise_for_status();status=state.json()
        if status['status']=='ready':break
        if status['status']=='error' or time.monotonic()>deadline:raise RuntimeError(status)
        time.sleep(1)
    catalog=requests.get(base+f'/documents/{did}/catalog',timeout=30);catalog.raise_for_status()
    target=next(e for e in catalog.json()['items'] if e.get('name')==name)
    # A fixture must contain a genuinely measured contour. Do not fall through
    # to a slow model call if its DIM endpoints were constructed incorrectly.
    from backend.services.measured_profile_planner import compile_plan
    local=context_for(ROOT/'storage'/'documents'/did/status['dxf'],[dict(target,kind='block')])
    local.update(root_target_ids=[target['id']],part_graph={})
    assert compile_plan(local,'Chiều dài từ 140 thành 123 mm, giữ tâm') is not None
    plan_started=time.monotonic();planning_job=None
    response=requests.post(base+f'/documents/{did}/'+('planning-jobs' if args.background else 'change-plans'),json={'ids':[target['id']],'request':'Chiều dài từ 140 thành 123 mm, giữ tâm'},timeout=60)
    response.raise_for_status();plan=response.json()
    if args.background:
        planning_job=plan;deadline=time.monotonic()+150
        while planning_job['status'] not in ('ready','failed','cancelled'):
            assert time.monotonic()<deadline,planning_job
            time.sleep(.2)
            response=requests.get(base+f"/documents/{did}/planning-jobs/{planning_job['id']}",timeout=10)
            response.raise_for_status();planning_job=response.json()
        assert planning_job['status']=='ready',planning_job
        response=requests.get(base+f"/documents/{did}/change-plans/{planning_job['plan_id']}",timeout=20)
        response.raise_for_status();plan=response.json()
    planning_seconds=time.monotonic()-plan_started
    assert plan['execution_available'],plan['plan']['questions']
    assert plan['planner']=='checked_measured_profile_resize',plan['planner']
    response=requests.post(base+f"/documents/{did}/change-plans/{plan['id']}/apply",json={'preview_only':True},timeout=60)
    response.raise_for_status();revision=response.json();rid=revision['id']
    assert revision['solid_validation']['status']=='passed',revision.get('solid_validation')
    assert revision['solid_validation']['checks'][0]['mode']=='planar'
    response=requests.get(base+f'/documents/{did}/revisions/{rid}/items/{target["id"]}/preview',timeout=30)
    response.raise_for_status();assert '<svg' in response.text
    if args.approve:
        response=requests.post(base+f'/documents/{did}/revisions/{rid}/approve',json={'confirmed_dependencies':[]},timeout=30)
        response.raise_for_status();assert response.json()['status']=='approved'
    response=requests.post(base+f'/documents/{did}/revisions/{rid}/exports',json={'format':'dwg','scope':'selection','preview':not args.approve},timeout=20)
    response.raise_for_status();job=response.json();deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(1)
        response=requests.get(base+f"/documents/{did}/revisions/{rid}/exports/{job['id']}",timeout=10)
        response.raise_for_status();job=response.json()
    response=requests.get(base+job['download_url'],timeout=30);response.raise_for_status()
    download=task/'download';download.mkdir();file=download/'checked-preview.dwg';file.write_bytes(response.content)
    assert file.read_bytes()[:6]==b'AC1032'
    converter.convert_dwg_to_dxf(str(download),str(task/'reopened'))
    checked=context_for(task/'reopened'/'checked-preview.dxf',[dict(target,kind='block')])
    measured=[e['scaled_measurement'] for e in checked['entities'] if e['type']=='DIMENSION']
    assert len(measured)==1 and abs(measured[0]-123)<1e-6,measured
    holes=[e['geometry'] for e in checked['entities'] if e['type']=='CIRCLE']
    assert len(holes)==2 and all(abs(e['radius']-2)<1e-6 for e in holes)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    assert max(e['ref'].count('/') for e in checked['entities'])==args.depth+1
    if args.legacy:
        profiles=[e for e in checked['entities'] if e['type']=='POLYLINE']
        assert len(profiles)==1 and [p[4] for p in profiles[0]['geometry']['points']]==[0,1,0,1],profiles
    if args.spline or args.nurbs:
        from cad.geometry import near
        from cad.spline_arcs import primitives
        originals=[e['geometry'] for e in local['entities'] if e['type']=='SPLINE']
        splines=[e for e in checked['entities'] if e['type']=='SPLINE']
        assert len(splines)==len(originals)==2 and not any(e['type']=='ARC' for e in checked['entities'])
        for before,e in zip(originals,splines):
            for key in ('degree','flags','knots','weights','fit_points'):assert near(before[key],e['geometry'][key])
            if args.spline:assert all(abs(edge['radius']-15)<1e-6 for edge in primitives(e))
            else:assert e['geometry']['degree']==3 and not primitives(e)
    if args.ellipse:
        from cad.geometry import near
        originals=[e['geometry'] for e in local['entities'] if e['type']=='ELLIPSE']
        ellipses=[e['geometry'] for e in checked['entities'] if e['type']=='ELLIPSE']
        assert len(ellipses)==len(originals)==2
        for before,after in zip(originals,ellipses):
            for key in ('major_axis','ratio','start_param','end_param','extrusion'):assert near(before[key],after[key])
    report=dict(document_id=did,plan_id=plan['id'],revision_id=rid,export_job_id=job['id'],
        explorer_url=base+f'/explorer?doc={did}&revision={rid}',download_url=base+job['download_url'],
        fixture='independent synthetic nested block, no BOM, native aligned DIM'+('; classic bulged POLYLINE' if args.legacy else '; rational quadratic circular SPLINE' if args.spline else '; noncircular rational cubic SPLINE' if args.nurbs else '; noncircular native ELLIPSE' if args.ellipse else ''),
        nested_depth=args.depth,original_mm=140,modified_mm=123,hole_radii_mm=[e['radius'] for e in holes],
        solid_validation=revision['solid_validation'],
        approved_synthetic_fixture=args.approve,
        background_planning_job=planning_job,planning_seconds=planning_seconds,
        source_hash=source_hash,download_hash=hashlib.sha256(response.content).hexdigest(),
        backup=str(file),checks=['real DWG upload','deterministic source-bound planner','SVG preview HTTP 200',
            'persistent download HTTP 200','downloaded DWG reopened through ODA','aligned DIM measures 123 mm','hole diameters preserved','source unchanged'])
    (task/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
