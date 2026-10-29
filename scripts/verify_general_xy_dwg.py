"""Exercise the public upload/edit/approve/download API on unseen DWGs.

Synthetic regression fixtures only. No existing customer drawing is modified,
no source handle mapping is supplied to the engine, and no model is required.
"""
import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import ezdxf,httpx
from test_native_contacts import native_xy_contacts_fixture as fixture
from cad.converter import DWGConverter,converter_path
from cad.edit_engine import digest
from cad.sheets import discover_sheets
from cad.frame_geometry import world
from cad.part_identity import record_identity
from backend.services.change_service import context_for


def main():
    client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=150,trust_env=False)
    def api(method,path,**kwargs):
        r=client.request(method,path,**kwargs)
        if r.is_error:raise RuntimeError(f'{path}: {r.status_code} {r.text[:2000]}')
        return r.json()
    batch=Path('storage/validation-fixtures')/('general-xy-dwg-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());receipts=[]
    for classic,nested,scale in [(False,False,1),(True,False,2),(False,True,.5)]:
        started=time.perf_counter();folder=batch/('nested' if nested else 'classic' if classic else 'polyline');folder.mkdir()
        authored=folder/'authored';authored.mkdir();source,c,_,_,_,_,_,request=fixture(authored,classic,nested,scale)
        doc=ezdxf.readfile(source);space=doc.blocks['NESTED-ASSEMBLY'] if nested else doc.modelspace()
        # Author nonoverlapping frames. The grid helper uses a fixed 70-unit
        # column width, independently of the mechanical part sizes.
        for e in space:
            if e.dxftype()=='MTEXT' or e.dxftype()=='LINE' and min(e.dxf.start.y,e.dxf.end.y)>=420*scale-60-1e-5:
                e.translate(50*scale,0,0)
        right=max(1100*scale,600*scale+450)
        frames=[dict(t) for t in c['targets']] if not nested else [dict(bbox=[-50*scale,-50*scale,right,-50*scale+(right+50*scale)/1.414])]
        if not nested:frames[-1]['bbox']=[590*scale,60*scale,right,460*scale]
        border_space=doc.modelspace() if nested else space
        for i,target in enumerate(frames):
            box=target['bbox']
            a,b,x,y=box;border_space.add_lwpolyline([(a,b),(x,b),(x,y),(a,y)],close=True)
            border_space.add_text('BẢN VẼ TEST '+str(i),dxfattribs=dict(insert=(a+5*scale,b+5*scale),height=3*scale))
        for text in space.query('MTEXT'):text.dxf.char_height=3*scale
        doc.saveas(source);converter.convert_dxf_to_dwg(authored,folder/'initial-dwg')
        dwg=folder/'initial-dwg/independent-xy.dwg';input_hash=digest(dwg)
        with dwg.open('rb') as f:uploaded=api('POST','/documents',files={'file':('unseen-'+uuid.uuid4().hex+'.dwg',f,'application/octet-stream')})
        id=uploaded['id'];root='/documents/'+id;deadline=time.monotonic()+100
        while True:
            status=api('GET',root)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.3)
        catalog=api('GET',root+'/catalog');sheets=api('GET',root+'/sheets')['items']
        if nested:
            target=next(item for item in catalog['items'] if item.get('name')=='NESTED-ASSEMBLY' and item['kind']=='block')
        else:
            candidates=[s for s in sheets if s['bbox'][0]<=650*scale<=s['bbox'][2] and s['bbox'][1]<=420*scale<=s['bbox'][3]]
            target=min(candidates,key=lambda s:(s['bbox'][2]-s['bbox'][0])*(s['bbox'][3]-s['bbox'][1]))
        original=Path('storage/documents')/id/status['dxf'];original_hash=digest(original)
        print(folder.name,'uploaded',id,'selected',target['kind'],target['id'],flush=True)
        proposal=api('POST',root+'/change-plans',json=dict(ids=[target['id']],request=request))
        assert proposal['execution_available'],proposal['plan']['questions']
        rules=[d['coordinate_rule'] for d in proposal['plan']['dependencies'] if d.get('coordinate_rule')]
        assert sum(r.get('composition')=='orthogonal' for r in rules)>=2
        revision=api('POST',root+f'/change-plans/{proposal["id"]}/apply',json=dict(preview_only=True))
        revroot=root+'/revisions/'+revision['id']
        for t in revision['targets']:
            preview=client.get(revroot+(f'/sheets/{t["id"]}/preview' if t['kind']=='sheet' else f'/items/{t["id"]}/preview'));preview.raise_for_status()
        approved=api('POST',revroot+'/approve',json=dict(confirmed_dependencies=revision['pending_dependencies']))
        job=api('POST',revroot+'/exports',json=dict(format='dwg',scope='selection',preview=False));deadline=time.monotonic()+150
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.3);job=api('GET',revroot+'/exports/'+job['id'])
        response=client.get(job['download_url']);response.raise_for_status();download=folder/'download';download.mkdir();backup=download/'backup.dwg';backup.write_bytes(response.content)
        converter.convert_dwg_to_dxf(download,folder/'reopen');reopened=folder/'reopen/backup.dxf';after=context_for(reopened,discover_sheets(reopened))
        placed=[world(e) for e in after['entities'] if e['type']=='INSERT' and record_identity(e,{'RAIL-X','RAIL-Y','JOINT'})=='JOINT']
        assert any(abs(e['position'][0]-630*scale)<1e-5 and abs(e['position'][1]-130*scale)<1e-5 for e in placed),[(e['ref'],e.get('position')) for e in placed]
        measured={round(e['scaled_measurement'],5) for e in after['entities'] if e['type']=='DIMENSION' and e.get('scaled_measurement')}
        assert round(90*scale,5) in measured
        rows=[r for e in after['entities'] for r in e.get('bom',{}).get('rows',[])]
        actual={r['part_code']:r['description'] for r in rows}
        assert actual=={'RAIL-X':f'Bas {2*scale:g}x{30*scale:g}x{150*scale:g}','RAIL-Y':f'Bas {2*scale:g}x{150*scale:g}x{30*scale:g}','JOINT':f'Bas {2*scale:g}x{60*scale:g}x{60*scale:g}'},actual
        assert digest(original)==original_hash and digest(dwg)==input_hash
        receipt=dict(kind=folder.name,synthetic=True,document_id=id,selected_kind=target['kind'],source_unchanged=True,planner=proposal['planner'],request=request,
            coordinate_rules=rules,receiver_position_mm=[630*scale,130*scale,0],assembly_dimension_mm=90*scale,bom=actual,approved_backup=True,
            approval_hash=approved['approved_hash'],download_status=response.status_code,dwg_sha256=digest(backup),solid_validation=revision['solid_validation'],
            elapsed_seconds=round(time.perf_counter()-started,3),engine_mapping_supplied=False,parameter_links_supplied=False,customer_file_modified=False)
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');receipts.append(receipt)
        print(folder.name,'approved/downloaded/reopened',receipt['elapsed_seconds'],'seconds',flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8');print('Receipts:',batch/'receipts.json',flush=True)


if __name__=='__main__':main()
