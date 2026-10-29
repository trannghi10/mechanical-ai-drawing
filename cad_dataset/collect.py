"""Bounded downloads from explicit public sources; no execution of source code."""
import io
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit,urljoin
import requests
from cad_dataset import store
from cad_dataset.models import Asset,Evidence,Record,Rights,Label

ALLOWED={'raw.githubusercontent.com','api.github.com','huggingface.co','service.tib.eu','damassets.autodesk.net','download.autodesk.com'}
MAX_BYTES=50*1024*1024


def allowed(url):
    parsed=urlsplit(url);host=parsed.hostname or ''
    return parsed.scheme=='https' and not parsed.username and not parsed.password and (host in ALLOWED or host.endswith(('.huggingface.co','.xethub.hf.co','.hf.co')))


def download(url,path):
    receipt=path.with_name(path.name+'.download.json')
    if path.exists():
        if not receipt.exists():raise ValueError('File tải có sẵn nhưng thiếu bằng chứng URL/hash; không tự nhận là file đúng nguồn.')
        cached=json.loads(receipt.read_text(encoding='utf8'))
        if cached.get('url')!=url or cached.get('sha256')!=store.sha256(path):raise ValueError('File tải có sẵn thuộc nguồn/hash khác; không ghi đè.')
        return path
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.part')
    try:
        with requests.Session() as session:
            current=url
            for _ in range(8):
                if not allowed(current):raise ValueError('Đích tải không thuộc nguồn HTTPS đã cho phép.')
                response=session.get(current,stream=True,timeout=(15,45),allow_redirects=False,headers={'User-Agent':'MechanicalDWGDatasetV1/1.0'})
                if response.is_redirect:
                    current=urljoin(current,response.headers['Location']);response.close();continue
                with response:
                    if not response.ok:raise ValueError(f'Nguồn tải trả HTTP {response.status_code}')
                    if int(response.headers.get('Content-Length','0'))>MAX_BYTES:raise ValueError('File vượt giới hạn tải 50 MB.')
                    size=0
                    with temp.open('wb') as stream:
                        for chunk in response.iter_content(1024*128):
                            size+=len(chunk)
                            if size>MAX_BYTES:raise ValueError('File vượt giới hạn tải 50 MB.')
                            stream.write(chunk)
                    if not size:raise ValueError('File tải rỗng.')
                    temp.replace(path);store.write_json(receipt,dict(url=url,sha256=store.sha256(path),bytes=size));return path
            raise ValueError('Chuỗi chuyển hướng tải quá dài.')
    finally:temp.unlink(missing_ok=True)


def check_signature(path,format):
    data=path.read_bytes()
    if data.startswith(b'version https://git-lfs.github.com/spec'):raise ValueError('Chỉ tải được Git LFS pointer, chưa có CAD gốc.')
    if format=='DWG' and not (data[:4]==b'AC10' and data[4:6].isdigit() and len(data)>64):raise ValueError('File không có chữ ký DWG hợp lệ.')
    if format=='STEP' and not (data.lstrip().startswith(b'ISO-10303-21;') and b'END-ISO-10303-21;' in data and b'DATA;' in data):raise ValueError('File không có cấu trúc STEP Part 21.')
    if format=='DXF':
        import ezdxf
        ezdxf.readfile(path)
    if format=='JSON':json.loads(data.decode('utf8'))
    if format=='PNG':
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:image.verify()
    return 'parsed' if format in ('DXF','JSON','PNG') else 'signature_checked'


def asset(root,path,id,format,role,url=None,validation=None):
    return Asset(id=id,path=path.relative_to(root).as_posix(),sha256=store.sha256(path),bytes=path.stat().st_size,
                 format=format,role=role,download_url=url,validation=validation or check_signature(path,format))


def source_asset(root,name,id,role='license'):
    return asset(root,root/'source-evidence'/name,id,'TEXT',role,validation='downloaded')


def collect_autodesk(root=store.ROOT):
    """Only links observed on the official article; quarantine pending rights."""
    root=Path(root);index=root/'source-evidence/autodesk-mechanical-browser-links.json'
    if not index.exists():return []
    discovery=json.loads(index.read_text(encoding='utf8'));results=[]
    for entry in discovery['links']:
        url=entry['url']
        if urlsplit(url).hostname!='download.autodesk.com' or not url.lower().endswith('.dwg'):raise ValueError('Liên kết mẫu Autodesk không hợp lệ.')
        stem=Path(urlsplit(url).path).stem.lower();rid='autodesk-'+stem
        if (root/'records'/(rid+'.json')).exists():continue
        path=download(url,root/'assets'/rid/Path(urlsplit(url).path).name)
        original=asset(root,path,'original','DWG','original',url)
        source=asset(root,index,'official-download-links','JSON','source_metadata')
        group=('shafts_gears' if stem=='drive_shaft' else 'machine_assemblies' if stem in ('gear_pump_subassy','robot_handling_cell') else
               'fixtures' if stem.startswith('gripper') else 'plates' if stem=='bottom_plate' else 'unclassified')
        record=Record(id=rid,title=entry['title'],source_id='autodesk_mechanical',source_url=discovery['source_url'],source_revision='sha256:'+original.sha256,
            lineage_id='autodesk-sample:'+stem,leakage_group='autodesk-sample:'+('gear-pump-family' if stem in ('gear_pump_subassy','pump_cover','pump_wheel') else
                'gripper-family' if stem.startswith('gripper') else 'trolley-family' if stem in ('trolley_structure','wheel_casing') else stem),
            origin='external_cad',group=group,assets=[original,source],
            evidence=[Evidence(id='official-source',asset_id=source.id,kind='source_metadata')],
            rights=Rights(status='pending',note='Mẫu tải công khai từ Autodesk; chưa xác minh điều khoản cho benchmark AI, huấn luyện hoặc phân phối. Giữ cách ly, chỉ kiểm tải/chữ ký.'),
            notes=['File tải từ liên kết được quan sát trên trang Autodesk chính thức. URL thư mục ghi 2020 dù tiêu đề trang ghi 2023; giữ hash bytes làm phiên bản thực.','Nhóm là đề xuất theo tên nguồn, chưa có nhãn/quan hệ/đáp án kỹ sư.'])
        store.write(record,root);results.append(rid)
    return results


def collect_cadquarry(root=store.ROOT):
    root=Path(root);evidence=root/'source-evidence'
    tree=json.loads((evidence/'cadquarry-tree.txt').read_text(encoding='utf8'))
    revision=json.loads((evidence/'cadquarry-commit.txt').read_text(encoding='utf8'))['sha']
    paths={entry['path'] for entry in tree['tree']};results=[]
    families={'plate':'plates','revolved':'shafts_gears','bracket':'fixtures','flanged':'piping','gear':'shafts_gears','threaded':'fasteners',
              'ribbed':'unclassified','compound':'unclassified','enclosure':'unclassified','profiled':'unclassified'}
    for family,group in families.items():
        original=next(path for path in sorted(paths) if path.startswith('sample/demo-1k/geometry/'+family+'_') and path.endswith('.step'))
        stem=Path(original).stem;rid='cadquarry-'+stem
        if (root/'records'/(rid+'.json')).exists():continue
        selections=[(original,'original','STEP'),(f'sample/demo-1k/params/{stem}.params.json','parameters','JSON'),
                    (f'sample/demo-1k/meta/{stem}.meta.json','source_metadata','JSON')]
        assets=[]
        for source,role,format in selections:
            url=f'https://raw.githubusercontent.com/jacobjennings/CadQuarry/{revision}/{source}'
            path=download(url,root/'assets'/rid/Path(source).name)
            assets.append(asset(root,path,role,format,role,url))
        license=source_asset(root,'cadquarry-data-license.txt','data-license');assets.append(license)
        meta=Evidence(id='source-meta',asset_id='source_metadata',kind='source_metadata')
        permission=Evidence(id='license-evidence',asset_id=license.id,kind='license',note='CadQuarry DATA_LICENSE applies to generated STEP, params, meta and rendered data.')
        record=Record(id=rid,title=stem,source_id='cadquarry',source_url='https://github.com/jacobjennings/CadQuarry',source_revision=revision,
                      lineage_id='cadquarry:'+stem,leakage_group='cadquarry:'+stem,origin='generated',group=group,
                      assets=assets,evidence=[meta,permission],rights=Rights(status='publisher_declared',license_id='CC0-1.0',evidence_ids=[permission.id],evaluation=True,training=True,redistribution=True),
                      notes=['Nhóm sản phẩm chỉ là đề xuất theo family của bộ sinh, chưa được kỹ sư xác nhận.','STEP chưa được kiểm B-rep hoặc chuyển thành DWG; chưa có cặp sửa/đáp án kỹ sư.'])
        store.write(record,root);results.append(rid)
    return results


def collect_engineering(root=store.ROOT):
    root=Path(root);evidence=root/'source-evidence'
    tree=json.loads((evidence/'engineering-tree.txt').read_text(encoding='utf8'))
    revision=json.loads((evidence/'engineering-commit.txt').read_text(encoding='utf8'))['sha']
    readme=download(f'https://raw.githubusercontent.com/david1203d/EngineeringCADDrawings/{revision}/README.md',evidence/'engineering-readme.txt')
    results=[]
    for entry in tree['tree']:
        source=entry['path']
        if not source.lower().endswith('.dwg'):continue
        rid='engineering-'+Path(source).stem.lower()
        if (root/'records'/(rid+'.json')).exists():continue
        url=f'https://raw.githubusercontent.com/david1203d/EngineeringCADDrawings/{revision}/{source}'
        path=download(url,root/'assets'/rid/Path(source).name)
        original=asset(root,path,'original','DWG','original',url);permission=asset(root,readme,'source-readme','TEXT','license',validation='downloaded')
        record=Record(id=rid,title=source,source_id='engineering_cad_drawings',source_url='https://github.com/david1203d/EngineeringCADDrawings',source_revision=revision,
            lineage_id='engineering:'+original.sha256,leakage_group='engineering:'+original.sha256,origin='external_cad',assets=[original,permission],
            evidence=[Evidence(id='readme-permission',asset_id=permission.id,kind='license',note='README cho dùng/sửa. Repository chưa có LICENSE chuẩn; giữ chờ quyền huấn luyện/phân phối.')],
            rights=Rights(status='publisher_declared',license_id='LicenseRef-README-use-modify',evidence_ids=['readme-permission'],evaluation=True,training=False,redistribution=False),
            notes=['Chỉ đánh giá cục bộ theo README. Không đưa file vào ZIP phân phối hoặc tập huấn luyện.','Chưa phân loại nội dung, gắn nhãn hoặc nghiệm thu cơ khí.'])
        store.write(record,root);results.append(rid)
    return results


def collect_cadsy(root=store.ROOT,limit=3):
    root=Path(root);evidence=root/'source-evidence'
    metadata=json.loads((evidence/'cadsy-metadata.txt').read_text(encoding='utf8'));revision=metadata['sha']
    base=f'https://huggingface.co/datasets/cadsy/cad-technical-drawings/resolve/{revision}/'
    index=download(base+'metadata.jsonl',evidence/'cadsy-index.jsonl')
    rows=[json.loads(line) for line in index.read_text(encoding='utf8').splitlines() if line.strip()];results=[]
    for row in rows[:limit]:
        rid='cadsy-'+row['part_id']
        if (root/'records'/(rid+'.json')).exists():continue
        assets=[];observations=[];labels=[];facts=[]
        for key,role,format in [('model_step','original','STEP'),('iso_image','image','PNG'),('asme_image','image','PNG'),('iso_labels','source_labels','JSON'),('asme_labels','source_labels','JSON')]:
            source=row[key]
            if not source.startswith('samples/') or '..' in Path(source).parts:raise ValueError('Cadsy metadata có đường dẫn không hợp lệ.')
            path=download(base+source,root/'assets'/rid/Path(source).name)
            assets.append(asset(root,path,key,format,role,base+source))
        source_row=root/'assets'/rid/'source-row.json';store.write_json(source_row,row)
        assets.append(asset(root,source_row,'source-row','JSON','source_metadata'))
        assets.extend([source_asset(root,'cadsy-license.txt','license'),source_asset(root,'cadsy-upstream.txt','upstream-license'),source_asset(root,'cadsy-card.txt','dataset-card','source_metadata')])
        facts=[Evidence(id='license-evidence',asset_id='license',kind='license'),Evidence(id='upstream-evidence',asset_id='upstream-license',kind='license'),Evidence(id='row-evidence',asset_id='source-row',kind='source_metadata'),Evidence(id='card-evidence',asset_id='dataset-card',kind='source_metadata')]
        for profile in ('iso','asme'):
            data=json.loads((root/'assets'/rid/(profile+'_labels.json')).read_text(encoding='utf8'))
            for i,item in enumerate(data.get('annotations',[])):
                box=item.get('box');view=item.get('view','sheet');eid=f'{profile}-{i}'
                # Preserve every raw source annotation file. Import only valid,
                # grounded boxes as proposals; never relabel source truth as
                # an engineering approval or a native CAD handle binding.
                if not isinstance(box,list) or len(box)!=4 or not all(isinstance(v,(int,float)) for v in box) or not (0<=box[0]<box[2]<=1 and 0<=box[1]<box[3]<=1):continue
                facts.append(Evidence(id=eid,asset_id=profile+'_image',kind='image_box',box=box,note='Source profile '+profile+'; view '+view))
                labels.append(Label(id=eid,kind='dimension' if item.get('type')=='dimension' else 'datum' if item.get('type')=='datum_definition' else 'annotation',value=str(item.get('text','')) or str(item.get('type','annotation')),evidence_ids=[eid]))
        record=Record(id=rid,title=row['part_id'],source_id='cadsy',source_url='https://huggingface.co/datasets/cadsy/cad-technical-drawings',source_revision=revision,
            upstream_ids=['ADSKAILab/Zero-To-CAD-100k:'+str(row.get('uuid'))],lineage_id='zero-to-cad:'+row['uuid'],leakage_group='zero-to-cad:'+row['uuid'],origin='generated',
            assets=assets,evidence=facts,labels=labels,rights=Rights(status='publisher_declared',license_id='Apache-2.0',evidence_ids=['license-evidence','upstream-evidence'],evaluation=True,training=True,redistribution=True),
            notes=['ISO/ASME là hai biểu diễn tổng hợp của cùng một STEP; chỉ tính một hồ sơ, dùng cùng split.','Nhãn ảnh là đề xuất từ nguồn, chưa có liên kết DIM native hoặc kỹ sư nghiệm thu.'])
        store.write(record,root);results.append(rid)
    return results
