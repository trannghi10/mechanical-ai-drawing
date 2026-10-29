"""Inspect configuration, check live engines, or register a compiled APS bundle.

No CAD upload here. `register` changes APS app/activity versions explicitly.
"""
import argparse
import hashlib
import json
import os
import sys
import uuid
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from backend.services.aps_client import APSClient, Settings, safe_storage_url, status, activity_contract as activity, check_connection


def _publish_alias(client, resource, alias, version):
    response = client.request('POST', client.da + resource + '/aliases', allowed=(409,),
                              json={'id': alias, 'version': version})
    if response.status_code == 409:
        client.request('PATCH', client.da + resource + '/aliases/' + quote(alias, safe=''), json={'version': version})


def register(client, package, engine, alias):
    # This source/project is deliberately pinned to the verified .NET 8 SDK ABI.
    if engine != 'Autodesk.AutoCAD+25_0':
        raise ValueError('Plugin hiện nhắm AutoCAD 2025/.NET 8; cần build/kiểm tra lại khi đổi engine.')
    engines = []
    page = None
    while True:
        result = client.request('GET', client.da + '/engines', params={'page': page} if page else {}).json()
        engines.extend(result['data'])
        page = result.get('paginationToken')
        if not page:
            break
    if engine not in engines:
        raise ValueError('Engine không còn khả dụng; không đăng ký Activity sai phiên bản.')
    with zipfile.ZipFile(package) as archive:
        if not {'MechanicalCad.bundle/PackageContents.xml', 'MechanicalCad.bundle/Contents/MechanicalCad.dll'} <= set(archive.namelist()):
            raise ValueError('Bundle thiếu DLL/PackageContents.xml; chạy build-aps.ps1 trước.')
    # /forgeapps/me is the APS nickname; it can differ from the client ID.
    nickname = client.request('GET', client.da + '/forgeapps/me').json()
    if not isinstance(nickname, str):
        raise ValueError('APS không trả về nickname hợp lệ.')
    response = client.request('POST', client.da + '/appbundles', allowed=(409,),
                              json={'id': 'MechanicalCad', 'engine': engine})
    if response.status_code == 409:
        response = client.request('POST', client.da + '/appbundles/MechanicalCad/versions', json={'engine': engine})
    bundle = response.json()
    upload = bundle['uploadParameters']
    with Path(package).open('rb') as stream:
        response = client.http.post(safe_storage_url(upload['endpointURL']),
            data=upload['formData'], files={'file': (Path(package).name, stream, 'application/zip')})
    client.check_response(response)
    _publish_alias(client, '/appbundles/MechanicalCad', alias, bundle['version'])
    qualified = nickname + '.MechanicalCad+' + alias
    spec = activity(engine, qualified)
    response = client.request('POST', client.da + '/activities', allowed=(409,), json=spec)
    if response.status_code == 409:
        spec.pop('id')
        response = client.request('POST', client.da + '/activities/MechanicalCad/versions', json=spec)
    _publish_alias(client, '/activities/MechanicalCad', alias, response.json()['version'])
    client.bucket()
    return dict(APS_ACTIVITY_ID=qualified, APS_ENGINE=engine, message='Đã đăng ký; cần chạy smoke test trên một DWG trước khi dùng thật.')


def smoke_test(document_id=None):
    """Run native read/edit/save and geometric DWG readback on synthetic CAD.

    This deliberately does not approve a design or exercise unknown customer
    assemblies. It uses up to three Automation workitems (normal APS usage).
    """
    import ezdxf
    from backend.services import catalog_service as storage,aps_jobs
    from cad.edit_engine import digest
    cfg=Settings.load();cfg.check()
    if document_id:
        from backend.services.revision_service import safe_id
        document_id=safe_id(document_id);state=storage.read_status(document_id)
        if state.get('source_kind')!='synthetic_test' or not state.get('filename','').startswith('synthetic-aps-'):
            raise ValueError('Smoke test chỉ được dùng tài liệu tổng hợp do APS setup tạo; không gửi file khách.')
    else:
        document_id=uuid.uuid4().hex;folder=storage.ROOT/document_id;folder.mkdir(parents=True)
        drawing=ezdxf.new('R2018');drawing.units=4;m=drawing.modelspace()
        m.add_line((0,0),(100,0));text=m.add_text('APS_CHECK_BEFORE',dxfattribs={'insert':(0,10)})
        text.new_extension_dict().add_xrecord('APS_CHECK').reset([(1,'native readback')])
        m.add_linear_dim(base=(0,20),p1=(0,0),p2=(100,0)).render();drawing.saveas(folder/'original.dxf')
        storage.write_json(folder/'status.json',dict(id=document_id,filename='synthetic-aps-cloud-smoke.dxf',
            status='ready',dxf='original.dxf',source_kind='synthetic_test',synthetic_test=True,auxiliary=True))
    folder=storage.folder(document_id)
    originals={str(p):digest(p) for p in (folder/'original.dwg',folder/'original.dxf') if p.is_file()}
    inspection=aps_jobs.start(document_id,provider='aps')
    print(json.dumps(dict(stage='inspect',document_id=document_id,job_id=inspection['id'])),flush=True)
    inspection=aps_jobs.wait(document_id,inspection['id'],timeout=240)
    inv=json.loads(aps_jobs.artifact(document_id,inspection['id'],'inventory.json').read_text(encoding='utf-8-sig'))
    matches=[e for e in inv['entities'] if e.get('text')=='APS_CHECK_BEFORE' and e.get('is_layout')]
    if len(matches)!=1:raise ValueError('APS không đọc đúng TEXT nguồn của smoke test.')
    native=matches[0]
    if not any(e.get('name')=='APS_CHECK' for e in native.get('extension_records',[])):
        raise ValueError('APS chưa giữ extension dictionary nguồn.')
    native_source=aps_jobs.artifact(document_id,inspection['id'],'modified.dwg')
    edit=aps_jobs.start(document_id,provider='aps',mode='edit',source=native_source,
        expected_source_hash=digest(native_source),scope_handles=[native['handle']],operations=[dict(action='replace_text',
        handle=native['handle'],owner_handle=native['owner_handle'],expected_type=native['type'],
        before='APS_CHECK_BEFORE',after='APS_CHECK_AFTER')])
    print(json.dumps(dict(stage='native_edit',job_id=edit['id'])),flush=True)
    edit=aps_jobs.wait(document_id,edit['id'],timeout=240)
    drawing=ezdxf.readfile(aps_jobs.artifact(document_id,edit['id'],'roundtrip.dxf'));m=drawing.modelspace()
    lines=list(m.query('LINE'));dims=list(m.query('DIMENSION'))
    if len(lines)!=1 or len(dims)!=1 or abs(lines[0].dxf.start.distance(lines[0].dxf.end)-100)>1e-6 or abs(dims[0].get_measurement()-100)>1e-6:
        raise ValueError('Sửa TEXT trên APS làm đổi hình/DIM 100 mm.')
    if not any(e.dxf.text=='APS_CHECK_AFTER' for e in m.query('TEXT')):raise ValueError('APS chưa sửa đúng TEXT.')
    # A new synthetic source explicitly exercises the geometric save bridge.
    # Source drawings remain immutable; no customer design rule is inferred.
    lines[0].dxf.end=(80,0,0);dims[0].dxf.defpoint3=(80,0,0);dims[0].dxf.actual_measurement=80
    dims[0].override().render();working=folder/'aps-smoke';working.mkdir(exist_ok=True)
    resized=working/'geometry-80.dxf';drawing.saveas(resized);resized_hash=digest(resized)
    converted=aps_jobs.start(document_id,provider='aps',mode='convert',source=resized,expected_source_hash=resized_hash)
    print(json.dumps(dict(stage='geometry_save',job_id=converted['id'])),flush=True)
    converted=aps_jobs.wait(document_id,converted['id'],timeout=240)
    reopened=ezdxf.readfile(aps_jobs.artifact(document_id,converted['id'],'roundtrip.dxf'))
    line=next(iter(reopened.modelspace().query('LINE')));dim=next(iter(reopened.modelspace().query('DIMENSION')))
    if abs(line.dxf.start.distance(line.dxf.end)-80)>1e-6 or abs(dim.get_measurement()-80)>1e-6:
        raise ValueError('DWG mở lại từ APS chưa giữ hình/DIM 80 mm.')
    if digest(resized)!=resized_hash or any(digest(Path(p))!=h for p,h in originals.items()):raise ValueError('Nguồn smoke test đã đổi.')
    output=aps_jobs.artifact(document_id,converted['id'],'modified.dwg')
    proof=dict(status='passed',provider='aps',document_id=document_id,inspection_id=inspection['id'],edit_id=edit['id'],
        geometry_job_id=converted['id'],checked_at=datetime.now(timezone.utc).isoformat(),
        source_hashes=originals,source_unchanged=True,customer_cad_uploaded=False,complete_product_backup=False,
        engine=os.getenv('APS_ENGINE','Autodesk.AutoCAD+25_0'),activity=cfg.activity,bucket=cfg.bucket,
        client_id_sha256=hashlib.sha256(cfg.client_id.encode()).hexdigest(),
        bundle_sha256=digest(ROOT/'autodesk/MechanicalCad.zip'),geometry_mm=80,dimension_mm=80,
        checks=['native inventory','extension dictionary','scoped TEXT edit','geometry/DIM 100 retained',
                'new geometry/DIM 80 saved','DWG readback','source unchanged'],
        dwg=str(output.resolve()),dwg_sha256=digest(output),
        download_url=f'/documents/{document_id}/aps/jobs/{converted["id"]}/files/modified.dwg')
    storage.write_json(ROOT/'storage/aps-cloud-check.json',proof)
    return proof


def main():
    load_dotenv(ROOT / '.env', override=True, encoding='utf-8-sig')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'engines', 'register','check','smoke'])
    parser.add_argument('--bundle', type=Path, default=ROOT / 'autodesk/MechanicalCad.zip')
    parser.add_argument('--alias', default='dev')
    parser.add_argument('--document',help='For smoke only: resume a synthetic APS setup document; customer CAD is rejected')
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return
    if args.document and args.action!='smoke':raise ValueError('--document chỉ dùng cho smoke.')
    if args.action=='smoke':
        print(json.dumps(smoke_test(args.document),ensure_ascii=False,indent=2));return
    import re
    if not re.fullmatch('[A-Za-z0-9_-]+', args.alias):
        raise ValueError('Alias không hợp lệ.')
    # Registration precedes APS_ACTIVITY_ID configuration. A syntactically valid
    # placeholder is used only for configuration validation; never for CAD jobs.
    cfg = Settings.load()
    if args.action in ('engines','register'):
        cfg = Settings(cfg.enabled, cfg.client_id, cfg.client_secret, cfg.bucket,
                       cfg.activity or 'setup.MechanicalCad+dev', cfg.region)
    client = APSClient(cfg)
    try:
        if args.action == 'engines':
            print(json.dumps(client.request('GET', client.da + '/engines').json(), indent=2))
        elif args.action=='check':
            print(json.dumps(check_connection(client),ensure_ascii=False,indent=2))
        else:
            print(json.dumps(register(client, args.bundle, os.getenv('APS_ENGINE', 'Autodesk.AutoCAD+25_0'), args.alias), ensure_ascii=True, indent=2))
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Never print HTTP request/response objects or their credential-bearing URLs.
        print(str(error) if isinstance(error, ValueError) else 'Không thực hiện được APS setup; kiểm tra mạng/SDK/cấu hình.', file=sys.stderr)
        sys.exit(1)
