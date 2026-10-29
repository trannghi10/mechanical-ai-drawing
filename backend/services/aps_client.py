"""Server-only APS transport. Credentials and signed URLs never reach the UI."""
import base64
import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import httpx

API = 'https://developer.api.autodesk.com'
SMOKE_CHECK_FILE=Path(__file__).resolve().parents[2]/'storage/aps-cloud-check.json'
PLUGIN_PACKAGE=Path(__file__).resolve().parents[2]/'autodesk/MechanicalCad.zip'


class APSError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    enabled: bool
    client_id: str
    client_secret: str
    bucket: str
    activity: str
    region: str

    @classmethod
    def load(cls):
        return cls(os.getenv('APS_CLOUD_ENABLED', '0') == '1',
                   (os.getenv('APS_CLIENT_ID') or '').strip('\'" '),
                   (os.getenv('APS_CLIENT_SECRET') or '').strip('\'" '),
                   (os.getenv('APS_BUCKET_KEY') or '').strip('\'" '),
                   (os.getenv('APS_ACTIVITY_ID') or '').strip('\'" '),
                   (os.getenv('APS_REGION') or 'us-east').strip('\'" '))

    def missing(self):
        return [key for key, value in (
            ('APS_CLIENT_ID', self.client_id), ('APS_CLIENT_SECRET', self.client_secret),
            ('APS_BUCKET_KEY', self.bucket), ('APS_ACTIVITY_ID', self.activity)) if not value]

    def check(self):
        if not self.enabled:
            raise APSError('Chưa bật APS_CLOUD_ENABLED=1; CAD vẫn ở máy.')
        if self.missing():
            raise APSError('Thiếu cấu hình: ' + ', '.join(self.missing()))
        if not re.fullmatch(r'[a-z0-9._-]{3,128}', self.bucket):
            raise APSError('APS_BUCKET_KEY không hợp lệ.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\+[A-Za-z0-9_-]+', self.activity):
            raise APSError('APS_ACTIVITY_ID phải có dạng nickname.activity+alias.')
        if self.region not in ('us-east', 'us-west', 'eu-west'):
            raise APSError('APS_REGION không được hỗ trợ.')


def _verified_smoke(cfg):
    """Last successful synthetic run, bound to config, bundle and local files.

    This is historical readback evidence, not a fresh Autodesk health probe or
    authorization to edit an unverified customer design.
    """
    try:
        if SMOKE_CHECK_FILE.stat().st_size>32768:return None
        proof=json.loads(SMOKE_CHECK_FILE.read_text(encoding='utf8'))
        if (proof.get('status')!='passed' or proof.get('provider')!='aps' or proof.get('customer_cad_uploaded') is not False
                or proof.get('source_unchanged') is not True or proof.get('activity')!=cfg.activity or proof.get('bucket')!=cfg.bucket
                or proof.get('engine')!=os.getenv('APS_ENGINE','Autodesk.AutoCAD+25_0')
                or proof.get('client_id_sha256')!=hashlib.sha256(cfg.client_id.encode()).hexdigest()):return None
        if proof.get('bundle_sha256')!=hashlib.sha256(PLUGIN_PACKAGE.read_bytes()).hexdigest():return None
        paths=proof.get('source_hashes',{})
        if not isinstance(paths,dict) or not 1<=len(paths)<=2:return None
        paths=dict(paths);paths[proof['dwg']]=proof['dwg_sha256']
        root=(SMOKE_CHECK_FILE.parent/'documents').resolve()
        for filename,expected in paths.items():
            path=Path(filename).resolve()
            if not path.is_relative_to(root) or path.stat().st_size>2*1024*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:return None
        return proof
    except (OSError,ValueError,TypeError,KeyError):return None


def status():
    cfg = Settings.load()
    try:
        cfg.check()
        ready, message = True, 'Đã cấu hình APS; chưa kiểm tra kết nối hoặc plugin.'
    except APSError as error:
        ready, message = False, str(error)
    proof=_verified_smoke(cfg) if ready else None
    if proof:message='APS đã kiểm chứng đọc, sửa bản sao và xuất/mở lại DWG tổng hợp; chưa chứng nhận mọi bản vẽ.'
    return dict(provider='aps', configured=ready, enabled=cfg.enabled, missing=cfg.missing(),
                backend=os.getenv('CAD_DWG_BACKEND', 'oda'), read_backend=read_backend(), message=message,
                cloud_disclosure='DWG/DXF và dữ liệu lệnh sẽ được gửi tới Autodesk khi chạy APS.',
                live_verified=bool(proof),verified_at=proof.get('checked_at') if proof else None)


def activity_contract(engine, qualified_bundle):
    return dict(id='MechanicalCad', engine=engine, appbundles=[qualified_bundle],
        # APS placeholder indices use the bundle's short ID. The qualified
        # nickname/id+alias belongs only in the appbundles dependency list.
        commandLine=['"$(engine.path)\\accoreconsole.exe" /al "$(appbundles[MechanicalCad].path)" /s "$(settings[script].path)"'],
        parameters={
            'inputFile': {'verb': 'get', 'required': True, 'localName': 'input.cad'},
            'commands': {'verb': 'get', 'required': True, 'localName': 'commands.json'},
            'result': {'verb': 'put', 'required': True, 'localName': 'result.zip'}},
        settings={'script': {'value': 'MECHANICALCAD\n'}})


def check_connection(client):
    """Read-only account/activity check; does not upload CAD or run a workitem."""
    client.token()
    actual=client.request('GET',client.da+'/activities/'+quote(client.cfg.activity,safe='')).json()
    expected={'inputFile','commands','result'}
    if not expected<=set(actual.get('parameters',{})):
        raise ValueError('Activity không dùng hợp đồng MechanicalCad: thiếu inputFile/commands/result.')
    if actual.get('engine')!=os.getenv('APS_ENGINE','Autodesk.AutoCAD+25_0'):
        raise ValueError('Engine Activity không khớp SDK/plugin đã cấu hình.')
    expected_activity=activity_contract(actual['engine'],client.cfg.activity)
    if any(actual.get(key)!=expected_activity[key] for key in ('commandLine','appbundles','parameters','settings')):
        raise ValueError('Activity không khớp plugin/script đã kiểm tra; cần đăng ký lại bằng setup_aps.py register.')
    client.request('GET','/oss/v2/buckets/'+quote(client.cfg.bucket,safe='')+'/details')
    return {'authentication':'ok','activity':'ok','bucket':'ok','cad_uploaded':False,
            'note':'Kết nối đạt; vẫn phải chạy DWG smoke test để kiểm chứng engine/plugin.'}


def read_backend():
    value = (os.getenv('CAD_READ_BACKEND') or os.getenv('CAD_DWG_BACKEND', 'oda')).strip('\'" ')
    if value not in ('oda','aps','autocad'):
        raise APSError('CAD_READ_BACKEND phải là oda, aps hoặc autocad.')
    return value


def safe_storage_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    s3 = bool(re.fullmatch(r'(?:[a-z0-9.-]+\.)?s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com(?:\.cn)?', host))
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or not s3):
        raise APSError('APS trả về địa chỉ lưu trữ ngoài miền được phép.')
    return url


class APSClient:
    def __init__(self, settings=None, transport=None):
        self.cfg = settings or Settings.load()
        self.cfg.check()
        self.http = httpx.Client(timeout=httpx.Timeout(120, connect=20), transport=transport,
                                 follow_redirects=False)
        self._token = None
        self._expires = 0
        self._lock = threading.Lock()

    def close(self):
        self.http.close()

    def token(self):
        with self._lock:
            if not self._token or time.monotonic() >= self._expires:
                response = self.http.post(API + '/authentication/v2/token',
                    auth=(self.cfg.client_id, self.cfg.client_secret),
                    data={'grant_type': 'client_credentials',
                          'scope': 'data:read data:write data:create bucket:create bucket:read code:all'})
                self.check_response(response)
                result = response.json()
                self._token = result['access_token']
                self._expires = time.monotonic() + max(1, result['expires_in'] - 60)
            return self._token

    @staticmethod
    def check_response(response, allowed=()):
        if response.is_success or response.status_code in allowed:
            return
        # Exception URLs/bodies may contain bearer credentials or signed URLs.
        raise APSError(f'Autodesk HTTP {response.status_code}; kiểm tra tài khoản, quyền và Activity trên APS.')

    def request(self, method, endpoint, allowed=(), **kwargs):
        if not endpoint.startswith('/') or endpoint.startswith('//'):
            raise APSError('Đường dẫn APS không hợp lệ.')
        response = self.http.request(method, API + endpoint,
            headers={'Authorization': 'Bearer ' + self.token()}, **kwargs)
        self.check_response(response, allowed)
        return response

    @property
    def da(self):
        return '/da/' + self.cfg.region + '/v3'

    def bucket(self):
        response = self.request('POST', '/oss/v2/buckets', allowed=(409,),
            json={'bucketKey': self.cfg.bucket, 'policyKey': 'persistent'})
        if response.status_code == 409:
            self.request('GET', '/oss/v2/buckets/' + quote(self.cfg.bucket, safe='') + '/details')

    def object_path(self, key):
        return '/oss/v2/buckets/' + quote(self.cfg.bucket, safe='') + '/objects/' + quote(key, safe='')

    def object_id(self, key):
        return 'urn:adsk.objects:os.object:' + quote(self.cfg.bucket, safe='') + '/' + quote(key, safe='')

    def upload(self, key, path):
        path = Path(path)
        if not 0 < path.stat().st_size <= 200 * 1024 * 1024:
            raise APSError('APS nhận file từ 1 byte đến 200 MB.')
        session = self.request('GET', self.object_path(key) + '/signeds3upload',
                               params={'parts': 1, 'minutesExpiration': 15}).json()
        if len(session.get('urls', [])) != 1:
            raise APSError('Phiên tải lên APS không hợp lệ.')
        with path.open('rb') as stream:
            response = self.http.put(safe_storage_url(session['urls'][0]),
                content=iter(lambda: stream.read(1024 * 1024), b''),
                headers={'Content-Length': str(path.stat().st_size)})
        self.check_response(response)
        result = self.request('POST', self.object_path(key) + '/signeds3upload',
                              json={'uploadKey': session['uploadKey']}).json()
        if unquote(result.get('objectId', '')) != unquote(self.object_id(key)):
            raise APSError('OSS trả về object không khớp file tải lên.')
        return result['objectId']

    def download(self, key, destination, limit=400 * 1024 * 1024):
        result = self.request('GET', self.object_path(key) + '/signeds3download').json()
        if result.get('status') != 'complete' or not result.get('url'):
            raise APSError('Kết quả OSS chưa sẵn sàng; thử kiểm tra lại tác vụ.')
        destination = Path(destination)
        temporary = destination.with_suffix(destination.suffix + '.part')
        try:
            with self.http.stream('GET', safe_storage_url(result['url'])) as response:
                self.check_response(response)
                total = 0
                with temporary.open('wb') as stream:
                    for chunk in response.iter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > limit:
                            raise APSError('File APS vượt giới hạn tải về.')
                        stream.write(chunk)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def submit(self, input_key, command_key, output_key):
        auth = {'Authorization': 'Bearer ' + self.token()}
        return self.request('POST', self.da + '/workitems', json={
            'activityId': self.cfg.activity,
            'arguments': {
                'inputFile': {'verb': 'get', 'url': self.object_id(input_key), 'headers': auth},
                'commands': {'verb': 'get', 'url': self.object_id(command_key), 'headers': auth},
                'result': {'verb': 'put', 'url': self.object_id(output_key), 'headers': auth}
            }}).json()['id']

    def workitem(self, workitem_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', workitem_id):
            raise APSError('Workitem không hợp lệ.')
        return self.request('GET', self.da + '/workitems/' + workitem_id).json()

    @staticmethod
    def urn(object_id):
        return base64.urlsafe_b64encode(object_id.encode()).decode().rstrip('=')

    def translate(self, object_id):
        urn = self.urn(object_id)
        self.request('POST', '/modelderivative/v2/designdata/job', json={
            'input': {'urn': urn}, 'output': {'formats': [{'type': 'svf2', 'views': ['2d', '3d']}]}})
        return urn

    def manifest(self, urn):
        return self.request('GET', '/modelderivative/v2/designdata/' + quote(urn, safe='') + '/manifest',
                            allowed=(404,))

    def metadata(self, urn):
        return self.request('GET', '/modelderivative/v2/designdata/' + quote(urn, safe='') + '/metadata',
                            allowed=(202,404))
