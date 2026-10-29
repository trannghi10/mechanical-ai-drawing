"""Author unseen DWGs, upload, confirm measured rules, edit and reopen downloads.

Synthetic regression evidence only; this does not certify a customer's product.
"""
import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import ezdxf,httpx
from test_dependencies import parameter_links_fixture as fixture
from cad.converter import DWGConverter,converter_path
from cad.edit_engine import digest
from cad.sheets import discover_sheets
from backend.services.change_service import context_for


def main():
    client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=120,trust_env=False)
    def api(method,path,**kwargs):
        response=client.request(method,path,**kwargs)
        if response.is_error:raise RuntimeError(f'{path}: {response.status_code} {response.text[:1800]}')
        return response.json()
    batch=Path('storage/validation-fixtures')/('parameter-links-dwg-'+uuid.uuid4().hex[:8]);batch.mkdir(parents=True)
    converter=DWGConverter(converter_path());receipts=[]
    for kind,widths,target,expected in [('chain',(100,60,40),76,[76,36,16]),('fit',(2,25.6,30),1.2,[1.2,27.2,30])]:
        started=time.perf_counter();folder=batch/kind;folder.mkdir();source,_,_,_,_=fixture(folder/'input',widths=widths)
        doc=ezdxf.readfile(source);m=doc.modelspace();m.add_lwpolyline([(-50,-50),(500,-50),(500,260),(-50,260)],close=True)
        for text in m.query('MTEXT'):text.dxf.char_height=3.2
        m.add_text('CÔNG TY TEST',dxfattribs={'insert':(-30,-30),'height':3});doc.saveas(source)
        converter.convert_dxf_to_dwg(source.parent,folder/'initial-dwg')
        with (folder/'initial-dwg/original.dwg').open('rb') as stream:
            uploaded=api('POST','/documents',files={'file':('synthetic-general-'+uuid.uuid4().hex[:8]+'.dwg',stream,'application/octet-stream')})
        id=uploaded['id'];root='/documents/'+id;print(kind,'uploaded',id,flush=True)
        deadline=time.monotonic()+90
        while True:
            status=api('GET',root)
            if status['status']=='ready':break
            if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
            time.sleep(.25)
        api('GET',root+'/catalog');sheets=api('GET',root+'/sheets')['items'];sheet=next(s for s in sheets if s['category']!='reference')
        model=api('POST',root+'/design-model',json={'ids':[sheet['id']]})
        parameters={r['part_id']:r['parameters'][0]['dimension_ref'] for r in model['representations'] if r['part_id']}
        assert set(parameters)=={'PART-A','PART-B','PART-C'},parameters
        rules=[dict(kind='equal_delta',driver_ref=parameters[a],receiver_ref=parameters[b],outside_ref=None,wall_count=2,driver_anchor='first',receiver_anchor='first')
               for a,b in [('PART-A','PART-B'),('PART-B','PART-C')]] if kind=='chain' else [dict(kind='wall_clearance',driver_ref=parameters['PART-A'],receiver_ref=parameters['PART-B'],outside_ref=parameters['PART-C'],wall_count=2,driver_anchor='first',receiver_anchor='first')]
        for rule in rules:api('POST',root+'/parameter-links',json=dict(ids=[sheet['id']],source_hash=model['source_hash'],rule=rule,confirmed=True))
        request=f'Chi tiết PART-A {"chiều dài" if kind=="chain" else "độ dày"} từ {widths[0]} thành {target} mm'
        plan=api('POST',root+'/change-plans',json=dict(ids=[sheet['id']],request=request))
        assert plan['execution_available'],dict(planner=plan.get('planner'),questions=plan['plan']['questions'])
        print(kind,'compiled',plan['planner'],'operations',len(plan['plan']['operations']),flush=True)
        revision=api('POST',root+f'/change-plans/{plan["id"]}/apply',json=dict(preview_only=True))
        revroot=root+f'/revisions/{revision["id"]}'
        preview=client.get(revroot+f'/sheets/{sheet["id"]}/preview');preview.raise_for_status();(folder/'after.svg').write_bytes(preview.content)
        approved=api('POST',revroot+'/approve',json=dict(confirmed_dependencies=revision['pending_dependencies']))
        assert approved['approved_hash']==revision['validation']['output_hash']
        job=api('POST',revroot+'/exports',json=dict(format='dwg',scope='selection',preview=False));deadline=time.monotonic()+120
        while job['status']!='ready':
            if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
            time.sleep(.3);job=api('GET',revroot+f'/exports/{job["id"]}')
        download=client.get(job['download_url']);download.raise_for_status();(folder/'download').mkdir();dwg=folder/'download/backup.dwg';dwg.write_bytes(download.content)
        converter.convert_dwg_to_dxf(dwg.parent,folder/'reopen');reopened=folder/'reopen/backup.dxf';checked=ezdxf.readfile(reopened)
        actual=[next(e for e in checked.blocks[r.dxf.name] if e.dxftype()=='DIMENSION').get_measurement() for r in sorted(checked.modelspace().query('INSERT'),key=lambda e:e.dxf.insert.x)]
        assert all(abs(a-b)<1e-6 for a,b in zip(actual,expected)) and len(actual)==3,(actual,expected)
        frames=discover_sheets(reopened);c=context_for(reopened,frames);rows=[r for e in c['entities'] for r in e.get('bom',{}).get('rows',[])]
        assert {r['part_code']:r['description'] for r in rows}=={code:f'Plate 1x23x{value:g}' for code,value in zip(['PART-A','PART-B','PART-C'],expected)}
        original=Path('storage/documents')/id/status['dxf'];assert digest(original)==model['source_hash']
        receipt=dict(synthetic=True,kind=kind,document_id=id,plan_id=plan['id'],revision_id=revision['id'],job_id=job['id'],planner=plan['planner'],request=request,
            registered_source=status['dxf'],
            source_hash=model['source_hash'],source_unchanged=True,operation_count=len(plan['plan']['operations']),actual_dimensions_mm=actual,
            download_status=download.status_code,download_url=job['download_url'],dwg_sha256=digest(dwg),dwg_file=str(dwg.resolve()),
            approved_backup=True,preview_export=False,approval_hash=approved['approved_hash'],
            preview_file=str((folder/'after.svg').resolve()),solid_validation=revision['solid_validation'],elapsed_seconds=round(time.perf_counter()-started,3))
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');receipts.append(receipt)
        print(kind,'DWG reopened dimensions',actual,'download',download.status_code,flush=True)
    (batch/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8');print('Receipts:',batch/'receipts.json',flush=True)


if __name__=='__main__':main()
