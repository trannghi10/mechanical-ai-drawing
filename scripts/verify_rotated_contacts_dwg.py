"""Exercise new rotated native assemblies through upload/edit/approve/DWG roundtrip."""
import json,sys,time,uuid,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import ezdxf,httpx
from test_native_contacts import rotated_native_contacts_fixture as fixture
from cad.converter import DWGConverter,converter_path
from cad.edit_engine import digest
from cad.part_identity import record_identity
from cad.frame_geometry import world
from backend.services.change_service import context_for
from cad.sheets import discover_sheets


def main():
    client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=150,trust_env=False)
    def api(method,path,**kwargs):
        r=client.request(method,path,**kwargs)
        if r.is_error:raise RuntimeError(f'{path}: {r.status_code} {r.text[:1600]}')
        return r.json()
    batch=Path('storage/validation-fixtures')/('rotated-contact-dwg-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());receipts=[]
    for name,angle,classic,notched,nested in [('rotated-30',30,False,False,False),('notched-classic-minus35',-35,True,True,False),('nested-73',73,False,False,True)]:
        started=time.perf_counter();folder=batch/name;folder.mkdir();authored=folder/'authored';authored.mkdir()
        source,c,_,_,_,_,_,_=fixture(authored,angle,classic=classic,notched=notched,nested=nested)
        doc=ezdxf.readfile(source);m=doc.modelspace()
        if not nested:
            for t in c['targets']:
                a,b,x,y=t['bbox'];m.add_lwpolyline([(a,b),(x,b),(x,y),(a,y)],close=True)
                m.add_text('BẢN VẼ KIỂM THỬ',dxfattribs={'insert':(a+5,b+5),'height':3})
        else:
            from ezdxf import bbox
            inserted=next(e for e in m.query('INSERT') if e.dxf.name=='ROTATED-ASSEMBLY')
            extent=bbox.extents([inserted]);a,b=extent.extmin.x-50,extent.extmin.y-50;x,y=extent.extmax.x+50,extent.extmax.y+50
            m.add_lwpolyline([(a,b),(x,b),(x,y),(a,y)],close=True)
            m.add_text('BẢN VẼ KIỂM THỬ',dxfattribs={'insert':(a+5,b+5),'height':3})
        space=doc.blocks['ROTATED-ASSEMBLY'] if nested else m
        for e in space.query('MTEXT'):e.dxf.char_height=3
        doc.saveas(source);converter.convert_dxf_to_dwg(authored,folder/'input-dwg');dwg=folder/'input-dwg/contacts.dwg';input_hash=digest(dwg)
        with dwg.open('rb') as f:uploaded=api('POST','/documents',files={'file':('unseen-rotated-'+uuid.uuid4().hex+'.dwg',f,'application/octet-stream')})
        did=uploaded['id'];url='/documents/'+did;deadline=time.monotonic()+100
        while True:
            status=api('GET',url)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.3)
        sheets=api('GET',url+'/sheets')['items'];catalog=api('GET',url+'/catalog')['items']
        if nested:target=next(t for t in catalog if t.get('name')=='ROTATED-ASSEMBLY' and t['kind']=='block')
        else:target=next(t for t in sheets if t['bbox'][0]<0<t['bbox'][2] and 'PART-A' in t.get('texts',[]))
        original=Path('storage/documents')/did/status['dxf'];original_hash=digest(original)
        proposal=api('POST',url+'/change-plans',json={'ids':[target['id']],'request':'Mã PART-A chiều dài từ 100 thành 80 mm, giữ tâm'})
        assert proposal['execution_available'],proposal['plan']['questions']
        assert any(d.get('coordinate_rule') for d in proposal['plan']['dependencies'])
        revision=api('POST',url+f'/change-plans/{proposal["id"]}/apply',json={'preview_only':True});revurl=url+'/revisions/'+revision['id']
        for t in revision['targets']:
            endpoint=f'/sheets/{t["id"]}/preview' if t['kind']=='sheet' else f'/items/{t["id"]}/preview'
            response=client.get(revurl+endpoint);response.raise_for_status()
        api('POST',revurl+'/approve',json={'confirmed_dependencies':revision['pending_dependencies']})
        job=api('POST',revurl+'/exports',json={'format':'dwg','scope':'selection','preview':False});deadline=time.monotonic()+150
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.3);job=api('GET',revurl+'/exports/'+job['id'])
        response=client.get(job['download_url']);response.raise_for_status();download=folder/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
        converter.convert_dwg_to_dxf(download,folder/'reopen');reopened=folder/'reopen/backup.dxf';after=context_for(reopened,discover_sheets(reopened))
        dims=[e['scaled_measurement'] for e in after['entities'] if e['type']=='DIMENSION']
        assert sum(math.isclose(d,80,abs_tol=1e-5) for d in dims)>=2,dims
        assert any(math.isclose(d,180,abs_tol=1e-5) for d in dims),dims
        rows={r['part_code']:r['description'] for e in after['entities'] for r in e.get('bom',{}).get('rows',[])}
        assert rows=={'PART-A':'Bas 2x20x80','PART-B':'Bas 2x20x100'},rows
        from ezdxf.math import Vec3
        expected=Vec3(600-90*math.sin(math.radians(angle)),90*math.cos(math.radians(angle)),0)
        if nested:expected=inserted.matrix44().transform(expected)
        receiving=[world(e)['position'] for e in after['entities'] if e['type']=='INSERT' and record_identity(e,{'PART-A','PART-B'})=='PART-B']
        assert any(math.dist(p,list(expected))<1e-5 for p in receiving),(receiving,list(expected))
        assert digest(original)==original_hash and digest(dwg)==input_hash
        for review in revision.get('drawing_sync',[]):assert review['status']!='unverified_projection_mapping',review
        receipt=dict(case=name,synthetic=True,customer_file_modified=False,document_id=did,plan_id=proposal['id'],revision_id=revision['id'],
            approved_backup=True,download_status=response.status_code,source_unchanged=True,driver_length_mm=80,assembly_dimension_mm=180,
            assembly_rotation_degrees=angle,nested=nested,classic=classic,notched=notched,solid_validation=revision['solid_validation'],
            receiver_world_position_checked=list(expected),
            dwg_sha256=digest(backup),backup_path=str(backup.resolve()),elapsed_seconds=round(time.perf_counter()-started,3),engine_mapping_supplied=False)
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');receipts.append(receipt)
        print(name,'approved/downloaded/reopened',receipt['elapsed_seconds'],'seconds',flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8');print('Receipts:',batch/'receipts.json',flush=True)


if __name__=='__main__':main()
