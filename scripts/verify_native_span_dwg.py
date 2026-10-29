"""Public API regression of source-derived receiver resizing on unseen DWGs."""
import argparse,json,sys,time,uuid,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import ezdxf,httpx
from ezdxf import bbox
from test_native_contacts import native_span_fits_fixture as fixture,one_wall_gauge_fixture
from cad.converter import DWGConverter,converter_path
from cad.edit_engine import digest
from cad.sheets import discover_sheets
from backend.services.change_service import context_for


def main(rotated=False,one_wall=False,process=False):
    client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=150,trust_env=False)
    def api(method,path,**kwargs):
        r=client.request(method,path,**kwargs)
        if r.is_error:raise RuntimeError(f'{path}: {r.status_code} {r.text[:2400]}')
        return r.json()
    batch=Path('storage/validation-fixtures')/('native-span-dwg-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());receipts=[]
    cases=[('grow',110,False,False,0,0),('shrink-classic',130,True,False,0,0),('nested-clearance',110,False,True,2,0)]
    if rotated:cases=[('rotated-30',110,False,True,0,30),('rotated-classic-minus35',130,True,True,0,-35),('rotated-clearance-73',110,False,True,2,73)]
    if process:one_wall=True
    if one_wall:cases=[('one-wall',100,False,False,0,0),('one-wall-classic-minus35',100,True,True,2,-35),('one-wall-clearance-73',100,False,True,2,73),('one-wall-gauge',100,False,False,0,0),('one-wall-opposite',80,False,True,2,37)]
    if process:cases=[('one-wall',100,False,False,0,0),('one-wall-gauge',100,False,False,0,0),('one-wall-opposite',80,False,False,0,0)]
    for name,new_c,classic,nested,gap,angle in cases:
        started=time.perf_counter();folder=batch/name;folder.mkdir();authored=folder/'authored';authored.mkdir()
        gauge_case=name=='one-wall-gauge'
        opposite_case=name=='one-wall-opposite'
        if gauge_case:source,c,_,_,_,_,request=one_wall_gauge_fixture(authored)
        else:
            source,c,_,_,_,_,request=fixture(authored,new_c=110 if one_wall else new_c,classic=classic,nested=nested,rotation=angle,gap=gap,measured_gap=bool(gap),notched=bool(angle))
            if one_wall:request=f'Mã {"UPPER" if opposite_case else "LOWER"} chiều cao từ 100 thành 80 mm, giữ {"trên" if opposite_case else "dưới"}; giữ kích thước ngoài cụm'
        if angle:request=request.replace('chiều cao','chiều dài')
        doc=ezdxf.readfile(source);m=doc.modelspace();space=doc.blocks['WRAPPER'] if nested else m
        if process:
            for e in space.query('MTEXT'):
                if e.text.startswith('Bas '):e.text+=' (Cắt laser)'
        for e in space:
            if e.dxftype()=='MTEXT' or e.dxftype()=='LINE' and min(e.dxf.start.y,e.dxf.end.y)>=360-1e-5:e.translate(50,0,0)
        if nested:
            root=next(e for e in m.query('INSERT') if e.dxf.name=='WRAPPER');extent=bbox.extents([root]);a,b=extent.extmin.x-50,extent.extmin.y-50;x=extent.extmax.x+50
            frames=[dict(bbox=[a,b,x,b+max((x-a)/1.414,extent.size.y+100)])]
        else:
            frames=[dict(t) for t in c['targets']];frames[-1]['bbox']=[590,-30,1100,460]
        for i,f in enumerate(frames):
            a,b,x,y=f['bbox'];m.add_lwpolyline([(a,b),(x,b),(x,y),(a,y)],close=True);m.add_text('BẢN VẼ TEST '+str(i),dxfattribs=dict(insert=(a+5,b+5),height=3))
        for e in space.query('MTEXT'):e.dxf.char_height=3
        doc.saveas(source);converter.convert_dxf_to_dwg(authored,folder/'initial-dwg');dwg=folder/'initial-dwg/span-fit.dwg';input_hash=digest(dwg)
        with dwg.open('rb') as f:uploaded=api('POST','/documents',files={'file':('unseen-span-'+uuid.uuid4().hex+'.dwg',f,'application/octet-stream')})
        id=uploaded['id'];root_url='/documents/'+id;deadline=time.monotonic()+100
        while True:
            status=api('GET',root_url)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.3)
        # Hide only our exact uploaded bytes, before planning can fail. Failed
        # regressions must not leave sample DWGs in the customer's file list.
        from backend.services import catalog_service as storage
        upload_folder=storage.folder(id)
        assert digest(upload_folder/'original.dwg')==input_hash
        upload_status=storage.read_status(id);upload_status['synthetic_test']=True
        storage.write_json(upload_folder/'status.json',upload_status)
        catalog=api('GET',root_url+'/catalog');sheets=api('GET',root_url+'/sheets')['items']
        if nested:target=next(t for t in catalog['items'] if t.get('name')=='WRAPPER' and t['kind']=='block')
        else:target=next(s for s in sheets if s['bbox'][0]<650<s['bbox'][2] and s['bbox'][1]<420<s['bbox'][3])
        original=Path('storage/documents')/id/status['dxf'];original_hash=digest(original)
        proposal=api('POST',root_url+'/change-plans',json=dict(ids=[target['id']],request=request))
        assert proposal['execution_available'],proposal['plan']['questions']
        assert len(proposal['plan']['native_span_fits'])==1
        if process:
            fixed='LOWER' if opposite_case else 'UPPER';driver='UPPER' if opposite_case else 'LOWER'
            assert {r['part_code']:r['status'] for r in proposal['plan']['process_assessments']}=={driver:'changed',fixed:'unaffected','MIDDLE':'changed'}
        if one_wall:
            fit=proposal['plan']['native_span_fits'][0]
            assert fit['outside_dimension_ref'] and len(fit['fixed_support_refs'])==1
            assert not any(o['ref'] in fit['fixed_support_refs'] or o['ref']==fit['outside_dimension_ref'] for o in proposal['plan']['operations'])
        if angle:assert math.isclose(proposal['plan']['native_span_fits'][0]['analysis_angle'],math.radians(angle)% (math.pi/2),abs_tol=1e-7)
        if not nested:
            middle=next(s for s in sheets if 'MIDDLE' in s['texts'])
            assert middle['id'] in proposal['target_ids'],'Derived manufacturing detail was not expanded'
        assert 'MIDDLE' in proposal['impact_graph']['derived_codes']
        revision=api('POST',root_url+f'/change-plans/{proposal["id"]}/apply',json=dict(preview_only=True));revroot=root_url+'/revisions/'+revision['id']
        for t in revision['targets']:
            r=client.get(revroot+(f'/sheets/{t["id"]}/preview' if t['kind']=='sheet' else f'/items/{t["id"]}/preview'));r.raise_for_status()
        approved=api('POST',revroot+'/approve',json=dict(confirmed_dependencies=revision['pending_dependencies']))
        job=api('POST',revroot+'/exports',json=dict(format='dwg',scope='selection',preview=False));deadline=time.monotonic()+150
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.3);job=api('GET',revroot+'/exports/'+job['id'])
        response=client.get(job['download_url']);response.raise_for_status();download=folder/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
        converter.convert_dwg_to_dxf(download,folder/'reopen');reopened=folder/'reopen/backup.dxf';after=context_for(reopened,discover_sheets(reopened));expected=100.8 if gauge_case else 120 if opposite_case else 220-new_c
        receiver_dims=[e for e in after['entities'] if e['type']=='DIMENSION' and abs(e.get('scaled_measurement',0)-expected)<1e-5]
        assert len(receiver_dims)>=2,'Receiver assembly/detail DIM mismatch'
        outer_span=202 if gauge_case else 300+gap
        assert any(e['type']=='DIMENSION' and abs(e.get('scaled_measurement',0)-outer_span)<1e-5 for e in after['entities'])
        rows={r['part_code']:r['description'] for e in after['entities'] for r in e.get('bom',{}).get('rows',[])}
        expected_rows=dict(LOWER='Bas 1.2x20x100' if gauge_case else 'Bas 2x20x100' if opposite_case else 'Bas 2x20x80',MIDDLE=f'Bas 2x20x{expected:g}',UPPER=f'Bas 2x20x{new_c}')
        if process:expected_rows={k:v+' (Cắt laser)' for k,v in expected_rows.items()}
        assert rows==expected_rows,rows
        from cad.part_identity import record_identity
        receiver_roots={e['ref'] for e in after['entities'] if e['type']=='INSERT' and record_identity(e,{'MIDDLE'})=='MIDDLE'}
        assert len(receiver_roots)>=2
        if one_wall:
            receiving=[e for e in after['entities'] if e['ref'] in receiver_roots and abs(e['position'][0]-600)<1e-5]
            assert len(receiving)==1 and abs(receiving[0]['position'][1]-(1.2 if gauge_case else 100 if opposite_case else 80))<1e-5
        for ref in receiver_roots:
            shape=next(e for e in after['entities'] if e['ref'].startswith(ref+'/') and e['type'] in ('LWPOLYLINE','POLYLINE'))
            points=shape['geometry']['points']
            assert math.isclose(max(p[1] for p in points)-min(p[1] for p in points),expected,abs_tol=1e-5)
            assert math.isclose(max(p[0] for p in points)-min(p[0] for p in points),20,abs_tol=1e-5)
            assert len(points)==(8 if angle else 4)
        if nested:
            from cad.block_provenance import source_name
            actual=ezdxf.readfile(reopened);wrapper=next(e for e in actual.modelspace().query('INSERT')
                if e.dxf.name=='WRAPPER' or source_name(actual,e.dxf.name)=='WRAPPER')
            members=list(actual.blocks[wrapper.dxf.name].query('INSERT'))
            # Instance names may have been cloned during isolation; use native
            # child profile DIMs to locate the assembly receiver instead.
            candidates=[e for e in members if abs(e.dxf.insert.x-600)<1e-5 and abs(e.dxf.insert.y-(100 if opposite_case else 80))<1e-5]
            assert len(candidates)==1,'Derived receiver position was not updated'
        if gap:
            gapdim=next(e for e in after['entities'] if e['type']=='DIMENSION' and abs(e.get('scaled_measurement',0)-gap)<1e-5)
            assert gapdim['geometry']['text'] in ('','<>')
        assert digest(original)==original_hash and digest(dwg)==input_hash
        receipt=dict(kind=name,synthetic=True,document_id=id,plan_id=proposal['id'],revision_id=revision['id'],planner=proposal['planner'],
            approved_backup=True,download_status=response.status_code,source_unchanged=True,receiver_length_mm=expected,outer_span_mm=outer_span,clearance_mm=gap,
            receiver_representations_checked=len(receiver_dims),derived_codes=proposal['impact_graph']['derived_codes'],target_count=len(proposal['target_ids']),
            native_span_fits=proposal['plan']['native_span_fits'],solid_validation=revision['solid_validation'],dwg_sha256=digest(backup),
            elapsed_seconds=round(time.perf_counter()-started,3),engine_mapping_supplied=False,parameter_links_supplied=False,customer_file_modified=False,
            rotation_degrees=angle,receiver_geometry_checked=len(receiver_roots),backup_path=str(backup.resolve()),single_changed_support=one_wall,
            changed_support_before_mm=2 if gauge_case else 100,changed_support_after_mm=1.2 if gauge_case else 80,request=request,
            process_review_checked=process,process_assessments=proposal['plan']['process_assessments'])
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');receipts.append(receipt)
        print(name,'approved/downloaded/reopened',expected,'mm',receipt['elapsed_seconds'],'seconds',flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8');print('Receipts:',batch/'receipts.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--rotated',action='store_true');mode.add_argument('--one-wall',action='store_true');mode.add_argument('--process',action='store_true')
    args=parser.parse_args();main(args.rotated,args.one_wall,args.process)
