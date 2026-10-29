"""Verify general multi-axis/notched fits through the actual upload/export API."""
import json,sys,time,uuid,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import ezdxf,httpx
from ezdxf import bbox
from test_native_contacts import native_multi_span_fixture as fixture
from cad.converter import DWGConverter,converter_path
from cad.edit_engine import digest
from cad.sheets import discover_sheets
from backend.services.change_service import context_for
from cad.frame_geometry import world
from cad.part_identity import record_identity


def main():
    client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=150,trust_env=False)
    def api(method,path,**kwargs):
        r=client.request(method,path,**kwargs)
        if r.is_error:raise RuntimeError(f'{path}: {r.status_code} {r.text[:2400]}')
        return r.json()
    batch=Path('storage/validation-fixtures')/('native-multi-span-dwg-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());receipts=[]
    cases=[('grow',False,False,False,75,115,False),('shrink-notched-classic',True,False,True,55,95,False),('nested-notched',False,True,True,75,115,False),('cross-source-values',False,False,False,100,60,False),('unmeasured-body-blocked',False,False,False,75,115,True)]
    for name,classic,nested,notched,w,h,unmeasured in cases:
        started=time.perf_counter();folder=batch/name;folder.mkdir();authored=folder/'authored';authored.mkdir()
        source,c,_,_,_,_,_,request=fixture(authored,classic,nested,notched,w,h,unmeasured)
        doc=ezdxf.readfile(source);m=doc.modelspace()
        if nested:
            root=next(e for e in m.query('INSERT') if e.dxf.name=='MULTI-FIT-ASSEMBLY');extent=bbox.extents([root])
            a,b=extent.extmin.x-50,extent.extmin.y-50;x=extent.extmax.x+50
            frames=[dict(bbox=[a,b,x,b+max((x-a)/1.414,extent.size.y+100)])]
        else:frames=c['targets']
        for i,f in enumerate(frames):
            a,b,x,y=f['bbox'];m.add_lwpolyline([(a,b),(x,b),(x,y),(a,y)],close=True)
            m.add_text('BẢN VẼ KIỂM THỬ '+str(i),dxfattribs=dict(insert=(a+5,b+5),height=3))
        space=doc.blocks['MULTI-FIT-ASSEMBLY'] if nested else m
        for e in space.query('MTEXT'):e.dxf.char_height=3
        doc.saveas(source);converter.convert_dxf_to_dwg(authored,folder/'initial-dwg');dwg=folder/'initial-dwg/multi-fit.dwg';input_hash=digest(dwg)
        with dwg.open('rb') as f:uploaded=api('POST','/documents',files={'file':('unseen-multi-fit-'+uuid.uuid4().hex+'.dwg',f,'application/octet-stream')})
        id=uploaded['id'];url='/documents/'+id;deadline=time.monotonic()+100
        while True:
            status=api('GET',url)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.3)
        catalog=api('GET',url+'/catalog');sheets=api('GET',url+'/sheets')['items']
        if nested:target=next(t for t in catalog['items'] if t.get('name')=='MULTI-FIT-ASSEMBLY' and t['kind']=='block')
        else:target=next(s for s in sheets if s['bbox'][0]<1500<s['bbox'][2] and s['bbox'][1]<620<s['bbox'][3])
        original=Path('storage/documents')/id/status['dxf'];original_hash=digest(original)
        proposal=api('POST',url+'/change-plans',json=dict(ids=[target['id']],request=request))
        assert proposal['execution_available'],proposal['plan']['questions']
        assert len(proposal['plan']['native_span_fits'])==2
        assert {f['axis'] for f in proposal['plan']['native_span_fits']}=={0,1}
        assert 'INFILL' in proposal['impact_graph']['derived_codes']
        if not nested:
            detail=next(s for s in sheets if 'INFILL' in s['texts'])
            assert detail['id'] in proposal['target_ids'],'Receiver manufacturing view missing'
        revision=api('POST',url+f'/change-plans/{proposal["id"]}/apply',json=dict(preview_only=True));revurl=url+'/revisions/'+revision['id']
        for t in revision['targets']:
            endpoint=f'/sheets/{t["id"]}/preview' if t['kind']=='sheet' else f'/items/{t["id"]}/preview'
            response=client.get(revurl+endpoint);response.raise_for_status()
            if t['id']==target['id']:(folder/'after.svg').write_bytes(response.content)
        if unmeasured:
            rejected=client.post(revurl+'/approve',json=dict(confirmed_dependencies=revision['pending_dependencies']))
            assert rejected.status_code==422 and 'UNMEASURED' in rejected.json()['detail'],rejected.text
        else:api('POST',revurl+'/approve',json=dict(confirmed_dependencies=revision['pending_dependencies']))
        job=api('POST',revurl+'/exports',json=dict(format='dwg',scope='selection',preview=unmeasured));deadline=time.monotonic()+150
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.3);job=api('GET',revurl+'/exports/'+job['id'])
        response=client.get(job['download_url']);response.raise_for_status();download=folder/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
        converter.convert_dwg_to_dxf(download,folder/'reopen');reopened=folder/'reopen/backup.dxf';after=context_for(reopened,discover_sheets(reopened))
        doc=ezdxf.readfile(reopened)
        names={e['ref'] for e in after['entities'] if record_identity(e,{'INFILL'})=='INFILL'}
        groups={ref:[e for e in after['entities'] if e['ref'].startswith(ref+'/')] for ref in names}
        assert len(groups)>=2
        for group in groups.values():
            measurements=[e['scaled_measurement'] for e in group if e['type']=='DIMENSION']
            assert len(measurements)==2 and all(math.isclose(a,b,abs_tol=1e-5) for a,b in zip(sorted(measurements),sorted([w,h]))),measurements
            holes=[e for e in group if e['type']=='CIRCLE'];assert len(holes)==2 and all(e['geometry']['radius']==2 for e in holes)
            shape=next(e for e in group if e['type'] in ('LWPOLYLINE','POLYLINE'))
            p=shape['geometry']['points'];assert abs(max(q[0] for q in p)-min(q[0] for q in p)-w)<1e-5 and abs(max(q[1] for q in p)-min(q[1] for q in p)-h)<1e-5
            if notched:assert len(p)==8 and {round(q[0],6) for q in p}=={0,4,w}
        rows={r['part_code']:r['description'] for e in after['entities'] for r in e.get('bom',{}).get('rows',[])}
        expected=dict(WEST='Bas 2x30x60',EAST=f'Bas 2x{110-w}x60',BASE='Bas 2x60x20',TOP=f'Bas 2x60x{140-h}',INFILL=f'Bas 2x{w}x{h}')
        if unmeasured:expected['UNMEASURED']='Bas 2x20x10'
        assert rows==expected,rows
        assert {round(e['scaled_measurement'],5) for e in after['entities'] if e['type']=='DIMENSION'}>={140,160}
        assert digest(original)==original_hash and digest(dwg)==input_hash
        receipt=dict(kind=name,synthetic=True,document_id=id,plan_id=proposal['id'],revision_id=revision['id'],approved_backup=not unmeasured,
            incomplete_approval_rejected=unmeasured,preview_only=unmeasured,
            download_status=response.status_code,source_unchanged=True,receiver_size_mm=[w,h],receiver_representations_checked=len(groups),
            target_count=len(proposal['target_ids']),native_span_fits=proposal['plan']['native_span_fits'],solid_validation=revision['solid_validation'],
            dwg_sha256=digest(backup),elapsed_seconds=round(time.perf_counter()-started,3),engine_mapping_supplied=False,parameter_links_supplied=False,customer_file_modified=False)
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');receipts.append(receipt)
        print(name,'approval-blocked/preview-downloaded/reopened' if unmeasured else 'approved/downloaded/reopened',[w,h],'mm',receipt['elapsed_seconds'],'seconds',flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8');print('Receipts:',batch/'receipts.json',flush=True)


if __name__=='__main__':main()
