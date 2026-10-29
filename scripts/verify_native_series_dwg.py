"""Regression via real upload/approve/download/ODA reopen on unseen series DWGs."""
import argparse,json,sys,time,uuid,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import ezdxf,httpx
from ezdxf import bbox
from test_native_contacts import native_series_fits_fixture as fixture,one_wall_series_fixture
from cad.converter import DWGConverter,converter_path
from cad.edit_engine import digest
from cad.sheets import discover_sheets
from cad.part_identity import record_identity
from cad.frame_geometry import world
from backend.services.change_service import context_for


def main(one_wall=False):
    client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=150,trust_env=False)
    def api(method,path,**kwargs):
        response=client.request(method,path,**kwargs)
        if response.is_error:raise RuntimeError(f'{path}: {response.status_code} {response.text[:2000]}')
        return response.json()
    batch=Path('storage/validation-fixtures')/('native-series-dwg-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());receipts=[]
    cases=[('two-growing',2,110,False,False,False,0,False),('three-shrinking-classic',3,141,True,False,True,0,False),
           ('nested-notched-clearance',3,111,False,True,True,2,False),('different-parts-blocked',2,110,False,False,False,0,True)]
    if one_wall:cases=[('one-wall-two-growing',2,100,False,False,False,0,False),
        ('one-wall-four-shrinking-classic',4,100,True,False,True,0,False),
        ('one-wall-upper-clearance',2,100,False,False,True,2,False),
        ('one-wall-nested-upper-clearance',2,100,False,True,True,2,False),
        ('one-wall-gauge',2,100,False,False,False,0,False)]
    for name,count,new_upper,classic,nested,notched,gap,mixed in cases:
        started=time.perf_counter();folder=batch/name;folder.mkdir();authored=folder/'authored';authored.mkdir()
        side='UPPER' if 'upper' in name else 'LOWER';new_size=120 if 'shrinking' in name else 80;gauge=name=='one-wall-gauge'
        if one_wall:
            source,c,_,_,_,_,_,request=one_wall_series_fixture(authored,count,side,new_size,classic,nested,notched,gap,gauge=gauge)
        else:source,c,_,_,_,_,_,request=fixture(authored,count,new_upper,classic,nested,notched,gap,bool(gap),mixed=mixed)
        doc=ezdxf.readfile(source);m=doc.modelspace()
        if nested:
            root=next(e for e in m.query('INSERT') if e.dxf.name=='SERIES-ASSEMBLY');extent=bbox.extents([root])
            a,b=extent.extmin.x-50,extent.extmin.y-50;x=extent.extmax.x+50
            frames=[dict(bbox=[a,b,x,b+max((x-a)/1.414,extent.size.y+100)])]
        else:frames=c['targets']
        for i,f in enumerate(frames):
            a,b,x,y=f['bbox'];m.add_lwpolyline([(a,b),(x,b),(x,y),(a,y)],close=True)
            m.add_text('BẢN VẼ KIỂM THỬ '+str(i),dxfattribs=dict(insert=(a+5,b+5),height=3))
        space=doc.blocks['SERIES-ASSEMBLY'] if nested else m
        for e in space.query('MTEXT'):
            e.dxf.char_height=3
            if one_wall and e.text.startswith('Bas '):e.text+=' (Cắt laser)'
        doc.saveas(source);converter.convert_dxf_to_dwg(authored,folder/'initial-dwg');dwg=folder/'initial-dwg/series-fit.dwg';input_hash=digest(dwg)
        with dwg.open('rb') as f:uploaded=api('POST','/documents',files={'file':('unseen-series-'+uuid.uuid4().hex+'.dwg',f,'application/octet-stream')})
        document_id=uploaded['id'];url='/documents/'+document_id;deadline=time.monotonic()+100
        while True:
            status=api('GET',url)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.3)
        from backend.services import catalog_service as storage
        upload_folder=storage.folder(document_id);assert digest(upload_folder/'original.dwg')==input_hash
        upload_status=storage.read_status(document_id);upload_status['synthetic_test']=True
        storage.write_json(upload_folder/'status.json',upload_status)
        catalog=api('GET',url+'/catalog');sheets=api('GET',url+'/sheets')['items']
        if nested:target=next(t for t in catalog['items'] if t.get('name')=='SERIES-ASSEMBLY' and t['kind']=='block')
        else:target=next(s for s in sheets if s['bbox'][0]<1250<s['bbox'][2] and s['bbox'][1]<880<s['bbox'][3])
        original=Path('storage/documents')/document_id/status['dxf'];source_hash=digest(original)
        proposal=api('POST',url+'/change-plans',json=dict(ids=[target['id']],request=request))
        # The nested fixture intentionally has standalone drawings inside the
        # same native wrapper as the process assembly. No source frame proves
        # their role, so they must not inherit the fixed-support certificate.
        unbound_process=one_wall and nested
        if mixed or unbound_process:
            assert not proposal['execution_available'] and not proposal['plan']['operations'] and proposal['plan']['questions']
            rejected=client.post(url+f'/change-plans/{proposal["id"]}/apply',json=dict(preview_only=True))
            assert rejected.status_code==422,'An unresolved plan must not create an approved/applicable revision'
            assert digest(original)==source_hash and digest(dwg)==input_hash
            receipt=dict(kind=name,synthetic=True,document_id=document_id,plan_id=proposal['id'],approved_backup=False,
                unsupported_split_rejected=mixed,unbound_process_view_rejected=unbound_process,
                questions=proposal['plan']['questions'],source_unchanged=True,customer_file_modified=False,apply_status=rejected.status_code)
        else:
            assert proposal['execution_available'],proposal['plan']['questions']
            bindings=proposal['plan']['native_span_fits'];assert len(bindings)==1 and len(bindings[0]['peer_refs'])==count-1
            if one_wall:
                binding=bindings[0];assert binding['outside_dimension_ref'] and len(binding['fixed_support_refs'])==1
                assert not any(o['ref'] in binding['fixed_support_refs'] or o['ref']==binding['outside_dimension_ref'] for o in proposal['plan']['operations'])
                fixed='UPPER' if side=='LOWER' else 'LOWER'
                assert {r['part_code']:r['status'] for r in proposal['plan']['process_assessments']}=={side:'changed',fixed:'unaffected','MIDDLE':'changed'}
            assert 'MIDDLE' in proposal['impact_graph']['derived_codes']
            if not nested:
                detail=next(s for s in sheets if 'MIDDLE' in s['texts']);assert detail['id'] in proposal['target_ids']
            revision=api('POST',url+f'/change-plans/{proposal["id"]}/apply',json=dict(preview_only=True));revurl=url+'/revisions/'+revision['id']
            for t in revision['targets']:
                suffix=f'/sheets/{t["id"]}/preview' if t['kind']=='sheet' else f'/items/{t["id"]}/preview'
                response=client.get(revurl+suffix);response.raise_for_status()
                if t['id']==target['id']:(folder/'after.svg').write_bytes(response.content)
            api('POST',revurl+'/approve',json=dict(confirmed_dependencies=revision['pending_dependencies']))
            job=api('POST',revurl+'/exports',json=dict(format='dwg',scope='selection',preview=False));deadline=time.monotonic()+150
            while job['status']!='ready':
                if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
                time.sleep(.3);job=api('GET',revurl+'/exports/'+job['id'])
            response=client.get(job['download_url']);response.raise_for_status();download=folder/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
            converter.convert_dwg_to_dxf(download,folder/'reopen');reopened=folder/'reopen/backup.dxf';after=context_for(reopened,discover_sheets(reopened))
            expected=100+((.8 if gauge else 100-new_size) if one_wall else 120-new_upper)/count
            groups={e['ref']:[child for child in after['entities'] if child['ref'].startswith(e['ref']+'/')] for e in after['entities'] if record_identity(e,{'MIDDLE'})=='MIDDLE'}
            assert len(groups)==count+1,groups.keys()
            positions=[]
            for ref,group in groups.items():
                values=[e['scaled_measurement'] for e in group if e['type']=='DIMENSION'];assert len(values)==2
                assert any(math.isclose(v,expected,abs_tol=1e-5) for v in values)
                holes=[e for e in group if e['type']=='CIRCLE'];assert len(holes)==1 and holes[0]['geometry']['radius']==2
                outline=next(e for e in group if e['type'] in ('LWPOLYLINE','POLYLINE'));p=outline['geometry']['points']
                assert math.isclose(max(q[1] for q in p)-min(q[1] for q in p),expected,abs_tol=1e-5)
                if notched:assert len(p)==8 and {round(q[0],6) for q in p}=={0,4,20}
                placed=world(outline)['geometry']['points'];positions.append([min(p[0] for p in placed),min(p[1] for p in placed)])
            offset=[250,700] if nested else [0,0]
            actual=sorted(p[1]-offset[1] for p in positions if abs(p[0]-800-offset[0])<1e-5)
            base=(1.2 if gauge else new_size if side=='LOWER' else 100) if one_wall else 80
            assert len(actual)==count and all(math.isclose(a,base+i*(expected+gap),abs_tol=1e-5) for i,a in enumerate(actual)),positions
            rows={r['part_code']:r for e in after['entities'] for r in e.get('bom',{}).get('rows',[])}
            suffix=' (Cắt laser)' if one_wall else ''
            assert rows['MIDDLE']['description']==f'Bas 2x20x{expected:g}'+suffix and rows['MIDDLE']['quantity_text']==str(count)
            expected_lower=('Bas 1.2x20x100' if gauge else f'Bas 2x20x{new_size if side=="LOWER" else 100}') if one_wall else 'Bas 2x20x80'
            expected_upper=f'Bas 2x20x{new_size if side=="UPPER" else 100}' if one_wall else f'Bas 2x20x{new_upper}'
            assert rows['LOWER']['description']==expected_lower+suffix and rows['UPPER']['description']==expected_upper+suffix
            total=(count+2)*100+(count-1)*gap-(98 if gauge else 0)
            assert any(e['type']=='DIMENSION' and math.isclose(e['scaled_measurement'],total,abs_tol=1e-5) for e in after['entities'])
            if gap:assert len([e for e in after['entities'] if e['type']=='DIMENSION' and math.isclose(e.get('scaled_measurement',0),gap,abs_tol=1e-5)])==count-1
            assert digest(original)==source_hash and digest(dwg)==input_hash
            receipt=dict(kind=name,synthetic=True,document_id=document_id,plan_id=proposal['id'],revision_id=revision['id'],approved_backup=True,download_status=response.status_code,
                source_unchanged=True,series_part_count=count,part_length_mm=expected,outer_length_mm=total,clearance_mm=gap,
                native_span_fits=bindings,solid_validation=revision['solid_validation'],dwg_sha256=digest(backup),elapsed_seconds=round(time.perf_counter()-started,3),
                engine_mapping_supplied=False,parameter_links_supplied=False,customer_file_modified=False,single_changed_support=one_wall,
                process_review_checked=one_wall,process_assessments=proposal['plan']['process_assessments'],request=request,backup_path=str(backup.resolve()))
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');receipts.append(receipt)
        print(name,'approved/downloaded/reopened' if receipt['approved_backup'] else 'insufficient-source-evidence-blocked',flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8');print('Receipts:',batch/'receipts.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--one-wall',action='store_true')
    main(parser.parse_args().one_wall)
