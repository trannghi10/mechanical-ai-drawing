"""Prove the new generic hole operation through upload, preview and DWG reopen."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ezdxf
import requests
from cad.converter import DWGConverter,converter_path
from backend.services.change_service import context_for


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--depth',type=int,default=8);a=parser.parse_args()
    if not 0<=a.depth<=20:parser.error('depth must be 0..20')
    token=uuid.uuid4().hex[:8];folder=Path('storage/validation-fixtures/hole-dwg-'+token);inputs=folder/'input';inputs.mkdir(parents=True)
    d=ezdxf.new('R2018');d.units=4;b=d.blocks.new('UNSEEN-HOLE-'+token)
    b.add_lwpolyline([(0,0),(140,0),(140,30),(0,30)],close=True)
    b.add_circle((15,15),2);b.add_circle((125,15),2)
    b.add_linear_dim(base=(0,-10),p1=(0,0),p2=(140,0),override={'dimlfac':1}).render()
    b.add_radius_dim(center=(15,15),radius=2,angle=90,override={'dimlfac':1}).render()
    b.add_diameter_dim(center=(15,15),radius=2,angle=30,override={'dimlfac':1}).render()
    name=b.name
    for i in range(a.depth):
        wrapper=d.blocks.new('WRAP-'+token+'-'+str(i));wrapper.add_blockref(name,(3,4));name=wrapper.name
    d.modelspace().add_blockref(name,(400,300),dxfattribs={'xscale':2,'yscale':2,'zscale':2})
    d.saveas(inputs/'source.dxf');converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(inputs),str(folder/'dwg'))
    source=folder/'dwg/source.dwg';original=hashlib.sha256(source.read_bytes()).hexdigest();base='http://127.0.0.1:8765'
    def call(path,data=None,timeout=120):
        r=requests.post(base+path,json=data,timeout=timeout) if data is not None else requests.get(base+path,timeout=timeout)
        r.raise_for_status();return r.json()
    with source.open('rb') as f:
        r=requests.post(base+'/documents',files={'file':('NEW-hole-'+token+'.dwg',f,'application/octet-stream')},timeout=30);r.raise_for_status();doc=r.json()['id']
    deadline=time.monotonic()+180
    while True:
        status=call('/documents/'+doc)
        if status['status']=='ready':break
        if status['status']=='error' or time.monotonic()>deadline:raise ValueError(status)
        time.sleep(1)
    target=next(e for e in call('/documents/'+doc+'/catalog')['items'] if e.get('name')==name)
    p=call('/documents/'+doc+'/change-plans',dict(ids=[target['id']],request='Đổi đường kính lỗ bên trái từ 4 thành 6 mm, giữ nguyên tâm lỗ'))
    assert p['execution_available'] and p['planner']=='checked_hole_resize',p['plan']['questions']
    revision=call(f'/documents/{doc}/change-plans/{p["id"]}/apply',dict(preview_only=True));rid=revision['id']
    assert revision['solid_validation']['status']=='passed'
    picture=requests.get(base+f'/documents/{doc}/revisions/{rid}/items/{target["id"]}/preview',timeout=30);picture.raise_for_status()
    (folder/'preview.svg').write_text(picture.text,encoding='utf8')
    call(f'/documents/{doc}/revisions/{rid}/approve',dict(confirmed_dependencies=[]))
    job=call(f'/documents/{doc}/revisions/{rid}/exports',dict(format='dwg',scope='selection',preview=False))
    deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise ValueError(job)
        time.sleep(1);job=call(f'/documents/{doc}/revisions/{rid}/exports/{job["id"]}')
    downloaded=requests.get(base+job['download_url'],timeout=30);downloaded.raise_for_status();download=folder/'download';download.mkdir();file=download/'hole-backup.dwg';file.write_bytes(downloaded.content)
    converter.convert_dwg_to_dxf(str(download),str(folder/'reopen'))
    reopened=context_for(folder/'reopen/hole-backup.dxf',[dict(target,kind='block')])
    holes=[e['geometry'] for e in reopened['entities'] if e['type']=='CIRCLE']
    assert sorted(g['radius'] for g in holes)==[2,3]
    assert sorted(g['center'] for g in holes)==[[15,15,0],[125,15,0]]
    dims={e['dimension_type']:e['scaled_measurement'] for e in reopened['entities'] if e['type']=='DIMENSION'}
    assert abs(dims[0]-140)<1e-6 and abs(dims[4]-3)<1e-6 and abs(dims[3]-6)<1e-6
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    proof=dict(document_id=doc,plan_id=p['id'],revision_id=rid,depth=a.depth,dimensions_mm=dims,hole_radii=[2,3],
        source_unchanged=True,dwg=str(file.resolve()),download_url=base+job['download_url'],
        dwg_hash=hashlib.sha256(downloaded.content).hexdigest(),independent_kernel=revision['solid_validation'],approved_independent_fixture=True)
    (folder/'receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(proof,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
