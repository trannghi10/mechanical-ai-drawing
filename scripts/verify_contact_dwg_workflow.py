"""Real local HTTP workflow for an independent notched native 2D assembly.

Approval applies to this generated test document only, never customer CAD.
"""
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import ezdxf
import requests
from cad.converter import DWGConverter,converter_path
from backend.services.change_service import context_for


def wait_ready(url):
    deadline=time.monotonic()+180
    while True:
        response=requests.get(url,timeout=20);response.raise_for_status();data=response.json()
        if data['status']=='ready':return data
        if data['status'] in ('error','failed') or time.monotonic()>deadline:raise RuntimeError(data)
        time.sleep(1)


def main():
    base='http://127.0.0.1:8765';token=uuid.uuid4().hex[:8]
    task=ROOT/'storage'/'validation-fixtures'/('contact-workflow-'+token)
    inputs=task/'input';inputs.mkdir(parents=True)
    doc=ezdxf.new('R2018');doc.units=4
    for code in ('PART-A','PART-B'):
        block=doc.blocks.new(code)
        points=[(0,0),(20,0),(20,100),(12,100),(12,85),(8,85),(8,100),(0,100)] if code=='PART-A' else [(0,0),(20,0),(20,100),(0,100)]
        block.add_lwpolyline(points,close=True)
        dim=block.add_linear_dim(base=(-10,0),p1=(0,0),p2=(0,100),angle=90);dim.render()
    group=doc.blocks.new('ASSEMBLY-'+token)
    group.add_blockref('PART-A',(0,0))
    b=group.add_blockref('PART-B',(0,100));b.add_attrib('CODE','PART-B',(2,103))
    total=group.add_linear_dim(base=(-25,0),p1=(0,0),p2=(0,200),angle=90);total.render()
    headers=['STT','Mã hàng','Vật tư','Vật liệu','SL','Ghi chú']
    rows=[headers,['1','PART-A','Bas 2x20x100','Sắt','1',''],['2','PART-B','Bas 2x20x100','Sắt','1','']]
    xs=[80+i*70 for i in range(7)];ys=[260-i*12 for i in range(4)]
    for y in ys:group.add_line((xs[0],y),(xs[-1],y))
    for x in xs:group.add_line((x,ys[-1]),(x,ys[0]))
    for j,row in enumerate(rows):
        for i,text in enumerate(row):
            if text:group.add_mtext(text,dxfattribs={'insert':(xs[i]+2,ys[j]-3),'char_height':2})
    doc.modelspace().add_blockref(group.name,(400,300))
    doc.saveas(inputs/'contact-assembly.dxf')
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(inputs),str(task/'dwg'))
    source=task/'dwg'/'contact-assembly.dwg';original=hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open('rb') as file:
        response=requests.post(base+'/documents',files={'file':('synthetic-general-'+token+'.dwg',file,'application/octet-stream')},timeout=20)
    response.raise_for_status();did=response.json()['id'];state=wait_ready(base+'/documents/'+did)
    from backend.services import catalog_service as storage
    state.update(synthetic_test=True,auxiliary=True);storage.write_json(storage.folder(did)/'status.json',state)
    response=requests.get(base+f'/documents/{did}/catalog',timeout=30);response.raise_for_status()
    target=next(e for e in response.json()['items'] if e.get('name')==group.name)
    response=requests.post(base+f'/documents/{did}/change-plans',json={'ids':[target['id']],'request':'Chi tiết số 1 chiều cao từ 100 thành 80 mm, giữ đầu dưới'},timeout=60)
    response.raise_for_status();proposal=response.json()
    assert proposal['execution_available'],proposal['plan']['questions']
    assert len(proposal['plan']['dependencies'])==1
    assert any(o['action']=='move_insert' for o in proposal['plan']['operations'])
    response=requests.post(base+f"/documents/{did}/change-plans/{proposal['id']}/apply",json={'preview_only':True},timeout=60)
    response.raise_for_status();revision=response.json();rid=revision['id']
    assert revision['solid_validation']['status']=='passed'
    for t in revision['targets']:
        kind='sheets' if t['kind']=='sheet' else 'items'
        response=requests.get(base+f'/documents/{did}/revisions/{rid}/{kind}/{t["id"]}/preview',timeout=30)
        response.raise_for_status();assert '<svg' in response.text
        if t['id']==target['id']:(task/'after.svg').write_text(response.text,encoding='utf8')
    pending=revision.get('pending_dependencies',[])
    response=requests.post(base+f'/documents/{did}/revisions/{rid}/approve',json={'confirmed_dependencies':pending},timeout=30)
    response.raise_for_status();assert response.json()['status']=='approved'
    response=requests.post(base+f'/documents/{did}/revisions/{rid}/exports',json={'format':'dwg','scope':'selection','preview':False},timeout=20)
    response.raise_for_status();job=wait_ready(base+f"/documents/{did}/revisions/{rid}/exports/{response.json()['id']}")
    response=requests.get(base+job['download_url'],timeout=30);response.raise_for_status()
    downloads=task/'download';downloads.mkdir();backup=downloads/'checked-assembly-backup.dwg';backup.write_bytes(response.content)
    assert response.content[:6]==b'AC1032'
    converter.convert_dwg_to_dxf(str(downloads),str(task/'reopened'))
    reopened=task/'reopened'/'checked-assembly-backup.dxf';context=context_for(reopened,[dict(target,kind='block')])
    dimensions=sorted(e['scaled_measurement'] for e in context['entities'] if e['type']=='DIMENSION')
    assert len(dimensions)==3 and all(abs(a-b)<1e-6 for a,b in zip(dimensions,[80,100,180])),dimensions
    moved=next(e for e in context['entities'] if e['type']=='INSERT' and e.get('name')=='PART-B')
    assert abs(moved['position'][1]-80)<1e-6
    attr=next(e for e in context['entities'] if e['type']=='ATTRIB' and e.get('text')=='PART-B')
    assert abs(attr['text_placement']['anchor'][1]-83)<1e-6
    rows=[r for e in context['entities'] for r in e.get('bom',{}).get('rows',[])]
    assert next(r for r in rows if r['part_code']=='PART-A')['description']=='Bas 2x20x80'
    assert next(r for r in rows if r['part_code']=='PART-B')['description']=='Bas 2x20x100'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    report=dict(fixture='independent synthetic notched 2D native assembly, selected as one block; not Dauphine',document_id=did,plan_id=proposal['id'],revision_id=rid,
        backup=str(backup),download_url=base+job['download_url'],explorer_url=base+f'/explorer?doc={did}&revision={rid}',
        dimensions_mm=dimensions,receiving_insert_y_mm=moved['position'][1],attribute_y_mm=attr['text_placement']['anchor'][1],
        source_hash=original,backup_hash=hashlib.sha256(backup.read_bytes()).hexdigest(),solid_validation=revision['solid_validation'],
        approved_synthetic_fixture=True,checks=['actual boundary contact','BOM preserved and updated','attribute followed moved INSERT','native DIM assembly updated','HTTP preview, approval and download succeeded','downloaded DWG reopened and measured','source unchanged'])
    (task/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
