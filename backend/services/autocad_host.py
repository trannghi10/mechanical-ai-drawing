"""Headless local AutoCAD adapter. Does not launch TrueView or arbitrary scripts."""
import ctypes
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from functools import lru_cache
from pathlib import Path

from cad.edit_engine import digest

ROOT=Path(__file__).resolve().parents[2]
_engine_lock=threading.Lock()


def file_version(path):
    if os.name!='nt':raise ValueError('Adapter AutoCAD local cần Windows.')
    library=ctypes.WinDLL('version',use_last_error=True)
    library.GetFileVersionInfoSizeW.argtypes=[ctypes.c_wchar_p,ctypes.c_void_p]
    library.GetFileVersionInfoSizeW.restype=ctypes.c_uint
    library.GetFileVersionInfoW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p]
    library.VerQueryValueW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_uint)]
    size=library.GetFileVersionInfoSizeW(str(path),None)
    if not size:raise ValueError('Không đọc được phiên bản thư viện AutoCAD.')
    buffer=ctypes.create_string_buffer(size)
    if not library.GetFileVersionInfoW(str(path),0,size,buffer):raise ValueError('Không đọc được thông tin AutoCAD.')
    pointer=ctypes.c_void_p();length=ctypes.c_uint()
    if not library.VerQueryValueW(buffer,'\\',ctypes.byref(pointer),ctypes.byref(length)):
        raise ValueError('Thiếu thông tin phiên bản AutoCAD.')
    fields=ctypes.cast(pointer,ctypes.POINTER(ctypes.c_uint32))
    return fields[2]>>16,fields[2]&0xffff


@lru_cache(maxsize=16)
def _framework(path,size,mtime):
    markers=set(re.findall(rb'\.NETCoreApp,Version=v(\d+\.\d+)',Path(path).read_bytes()))
    if len(markers)!=1:raise ValueError('Không xác định duy nhất .NET target của SDK AutoCAD.')
    version=next(iter(markers)).decode()
    if version not in ('8.0','10.0'):raise ValueError('Plugin hiện chuẩn bị cho AutoCAD .NET 8 hoặc .NET 10.')
    return 'net'+version+'-windows'


def framework(path):
    stat=Path(path).stat()
    return _framework(str(path),stat.st_size,stat.st_mtime_ns)


def managed_runtime(target):
    configured=os.getenv('AUTOCAD_DOTNET_ROOT','').strip()
    root=Path(configured).resolve() if configured else ROOT/'storage/tools/dotnet10'
    if not target.startswith('net10') or not root.is_dir():
        if configured:raise ValueError('AUTOCAD_DOTNET_ROOT chưa có runtime .NET phù hợp.')
        return dict(dotnet_root=None,runtime_version=None,runtime_hashes={})
    versions=[]
    for folder in (root/'shared/Microsoft.NETCore.App').glob('10.0.*'):
        if not re.fullmatch(r'10\.0\.\d+',folder.name):continue
        if all((root/'shared'/name/folder.name).is_dir() for name in ('Microsoft.NETCore.App','Microsoft.WindowsDesktop.App','Microsoft.AspNetCore.App')):
            versions.append(folder.name)
    if not versions:raise ValueError('Runtime AutoCAD cần đủ .NETCore, WindowsDesktop và AspNetCore .NET 10.')
    version=max(versions,key=lambda value:tuple(map(int,value.split('.'))))
    files={'coreclr':root/'shared/Microsoft.NETCore.App'/version/'coreclr.dll',
           'hostfxr':root/'host/fxr'/version/'hostfxr.dll'}
    if not all(path.is_file() for path in files.values()):raise ValueError('Runtime AutoCAD portable thiếu coreclr/hostfxr.')
    return dict(dotnet_root=str(root.resolve()),runtime_version=version,runtime_hashes={name:digest(path) for name,path in files.items()})


def probe(core):
    core=Path(core).resolve()
    if core.name.lower()!='accoreconsole.exe' or any(ord(c)<32 or c=='"' for c in str(core)):
        raise ValueError('AUTOCAD_CORE_CONSOLE phải trỏ đúng accoreconsole.exe.')
    directory=core.parent
    files=[core,directory/'acad.exe',directory/'AcDbMgd.dll',directory/'AcCoreMgd.dll']
    if not all(file.is_file() for file in files):
        raise ValueError('Cần AutoCAD đầy đủ cùng acad.exe/AcDbMgd/AcCoreMgd; TrueView và LT không thay thế được.')
    major,minor=file_version(directory/'AcDbMgd.dll')
    if (major,minor) not in ((25,0),(25,1),(26,0)):
        raise ValueError('Cần chuẩn bị SDK adapter riêng cho phiên bản AutoCAD này.')
    target=framework(directory/'AcDbMgd.dll')
    if framework(directory/'AcCoreMgd.dll')!=target:raise ValueError('Hai thư viện SDK AutoCAD không cùng phiên bản .NET.')
    if major==26 and target!='net10.0-windows':raise ValueError('AutoCAD 2027 cần bộ SDK .NET 10 phù hợp.')
    return dict(core=str(core),managed_dir=str(directory),series=f'R{major}.{minor}',
                core_hash=digest(core),
                release=2027 if major==26 else 2025+minor,framework=target,
                managed_hashes={name:digest(directory/name) for name in ('AcDbMgd.dll','AcCoreMgd.dll')},**managed_runtime(target))


def registry_installs():
    """Read Autodesk installation locations, including custom drives."""
    if os.name!='nt':return []
    import winreg
    found=[]
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Autodesk\AutoCAD',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as base:
            for index in range(winreg.QueryInfoKey(base)[0]):
                release=winreg.EnumKey(base,index)
                if not re.fullmatch(r'R\d+\.\d+',release):continue
                with winreg.OpenKey(base,release) as version:
                    for product_index in range(winreg.QueryInfoKey(version)[0]):
                        product=winreg.EnumKey(version,product_index)
                        try:
                            with winreg.OpenKey(version,product) as key:
                                location,_=winreg.QueryValueEx(key,'AcadLocation')
                                if isinstance(location,str) and location:found.append(Path(location)/'accoreconsole.exe')
                        except OSError:continue
    except OSError:pass
    return found


def discover():
    configured=os.getenv('AUTOCAD_CORE_CONSOLE','').strip()
    if configured:return probe(configured)
    base=Path(os.getenv('ProgramFiles','C:/Program Files'))/'Autodesk'
    candidates=[]
    for path in sorted(set(base.glob('AutoCAD */accoreconsole.exe'))|set(registry_installs()),reverse=True):
        try:candidates.append(probe(path))
        except ValueError:continue
    if not candidates:raise ValueError('Chưa có AutoCAD đầy đủ trên máy. Cài/kích hoạt AutoCAD 2027 rồi chạy setup_autocad.py build.')
    return max(candidates,key=lambda item:(item['release'],item['framework']))


def receipt_path():
    return ROOT/'autodesk/local/host.json'


def bootstrap(host):
    prepared=ROOT/'autodesk/local/bootstrap.dwg'
    candidates=[prepared]
    directory=Path(host['managed_dir'])
    for pattern in ('UserDataCache/*/Template/acad*.dwt','UserDataCache/Template/acad*.dwt','Template/acad*.dwt'):
        candidates.extend(sorted(directory.glob(pattern)))
    local=Path(os.getenv('LOCALAPPDATA','C:/Users/Default/AppData/Local'))/'Autodesk'/('AutoCAD '+str(host['release']))/host['series']
    candidates.extend(sorted(local.glob('*/Template/acad*.dwt')))
    for candidate in candidates:
        if candidate.is_file():
            with candidate.open('rb') as stream:
                if stream.read(6).startswith(b'AC10'):return candidate.resolve()
    raise ValueError('Chưa có bản DWG/DWT trống để khởi tạo Core Console. Mở AutoCAD một lần để tạo template mặc định.')


def ready():
    host=discover();receipt=receipt_path()
    if not receipt.is_file():raise ValueError('Đã tìm thấy AutoCAD; chưa build plugin local đúng SDK. Chạy python scripts/setup_autocad.py build.')
    data=json.loads(receipt.read_text(encoding='utf8'))
    for key in ('core','core_hash','framework','series','managed_hashes','dotnet_root','runtime_version','runtime_hashes'):
        if data.get(key)!=host[key]:raise ValueError('AutoCAD/SDK đã thay đổi; cần build lại plugin local trước khi chạy.')
    blank=bootstrap(host)
    if str(blank)!=data.get('bootstrap_path') or digest(blank)!=data.get('bootstrap_hash'):
        raise ValueError('Bản khởi tạo DWG đã đổi; cần build lại receipt local.')
    bundle=Path(data['bundle']).resolve();dll=bundle/'Contents/MechanicalCad.Local.dll'
    if not bundle.is_relative_to((ROOT/'autodesk/local').resolve()):raise ValueError('Bundle local nằm ngoài thư mục build được quản lý.')
    if not dll.is_file() or digest(dll)!=data.get('plugin_hash'):raise ValueError('Plugin local thiếu hoặc sai hash; cần build lại.')
    manifest=bundle/'PackageContents.xml'
    if not manifest.is_file() or digest(manifest)!=data.get('manifest_hash'):raise ValueError('Manifest plugin local đã đổi; cần build lại.')
    return dict(host,bundle=str(bundle),bootstrap_path=str(blank),runtime_key=digest(receipt))


def status():
    host=None
    try:
        host=discover()
        details=ready()
        proof=ROOT/'storage/autocad-host-check.json'
        checked=json.loads(proof.read_text(encoding='utf8')) if proof.is_file() else {}
        verified=checked.get('status')=='passed' and checked.get('runtime_key')==details['runtime_key']
        return dict(provider='autocad',configured=True,installed=True,release=host['release'],framework=host['framework'],
                    core=host['core'],message='AutoCAD/plugin đã qua kiểm tra native trên máy.' if verified else 'AutoCAD và plugin khớp SDK; cần chạy check để kiểm chứng license/engine.',
                    dotnet_runtime=host['runtime_version'],
                    local_only=True,live_verified=verified,runtime_key=details['runtime_key'])
    except (ValueError,FileNotFoundError) as error:
        return dict(provider='autocad',configured=False,installed=host is not None,
                    release=host.get('release') if host else None,framework=host.get('framework') if host else None,
                    message=str(error),local_only=True,live_verified=False)


def execute(folder):
    """Run only our fixed plugin command against the job's immutable snapshots."""
    host=ready();folder=Path(folder).resolve()
    if not folder.is_relative_to((ROOT/'storage/documents').resolve()):
        # Tests can override ROOT to an isolated workspace; production cannot
        # run user CAD paths or invoke an engine outside a durable document job.
        raise ValueError('Thư mục tác vụ AutoCAD không thuộc kho tài liệu dự án.')
    commands=json.loads((folder/'commands.json').read_text(encoding='utf8'))
    source=folder/commands['input_name']
    if source.parent!=folder or not source.is_file() or digest(source)!=commands['source_sha256']:
        raise ValueError('Snapshot nguồn local không khớp lệnh.')
    timeout=int(os.getenv('AUTOCAD_TIMEOUT_SECONDS','300'))
    if not 30<=timeout<=1800:raise ValueError('AUTOCAD_TIMEOUT_SECONDS cần từ 30 đến 1800 giây.')
    # Core Console and Windows CAD loaders can still enforce MAX_PATH. Keep
    # engine filenames shallow even when a durable job lives in deep storage.
    base=(ROOT/'storage/acwork').resolve();base.mkdir(parents=True,exist_ok=True)
    run=base/uuid.uuid4().hex[:16];run.mkdir()
    try:return _execute_run(host,folder,commands,source,timeout,run)
    finally:
        for name,destination in (('console.log','autocad-console.log'),('plugin-error.json','autocad-plugin-error.json'),('plugin-progress.json','autocad-plugin-progress.json'),('console-exit.json','autocad-console-exit.json'),('dxf-import.log','autocad-dxf-import.log')):
            log=run/name
            if log.is_file():shutil.copyfile(log,folder/destination)
        # Only our freshly generated private workspace may be recursively
        # removed; never the input document folder or a configured CAD path.
        if run.resolve().parent!=base or not re.fullmatch('[a-f0-9]{16}',run.name):
            raise ValueError('Thư mục tạm AutoCAD vượt phạm vi dọn dẹp được phép.')
        try:shutil.rmtree(run)
        except OSError:pass  # An Autodesk helper may briefly retain a file.


def console_startup_error(log):
    """Recognize a startup failure without exposing arbitrary console contents."""
    with Path(log).open('rb') as stream:
        stream.seek(max(0,Path(log).stat().st_size-65536))
        raw=stream.read(65536)
    text=raw.decode('utf-16-le' if b'\x00' in raw[:100] else 'utf-8',errors='replace').lower()
    if "can't open user root registry key" in text or 'failed to create registry keys or files necessary when using the /isolate switch' in text:
        return 'AutoCAD không truy cập được registry hồ sơ Windows để khởi động chế độ cách ly. Chạy backend bằng tài khoản Windows có quyền đọc/ghi hồ sơ AutoCAD; nguồn CAD chưa được xử lý.'
    return None


def _execute_run(host,folder,commands,source,timeout,run):
    shutil.copyfile(source,run/'input.cad');shutil.copyfile(folder/'commands.json',run/'commands.json')
    shutil.copyfile(host['bootstrap_path'],run/'bootstrap.dwg')
    shared_profile = (base / 'shared_profile').resolve()
    shared_profile.mkdir(parents=True, exist_ok=True)
    shared_bundle = (base / 'bundle').resolve()
    dll = shared_bundle / 'MechanicalCad.Local.bundle/Contents/MechanicalCad.Local.dll'
    if not dll.is_file():
        if shared_bundle.exists(): shutil.rmtree(shared_bundle, ignore_errors=True)
        shared_bundle.mkdir(parents=True, exist_ok=True)
        shutil.copytree(host['bundle'], shared_bundle / 'MechanicalCad.Local.bundle')
    plugin = dll
    # NETLOAD prompts consume a full line, including spaces. Literal quotes
    # become part of the filename in this Core Console version. Trust only
    # our hash-checked plugin directory inside the isolated job profile.
    script=run/'run.scr'
    # Only the disposable blank bootstrap is the active UI document. Outputs
    # are already saved/read back by the plugin. Confirm discarding bootstrap
    # changes so background Core Console does not cancel QUIT and read stdin.
    script.write_text('_.SETVAR\nTRUSTEDPATHS\n'+plugin.parent.as_posix()+'\n_.SETVAR\nSECURELOAD\n2\n_.NETLOAD\n'+plugin.as_posix()+'\nMECHANICALCAD\n_.QUIT\n_Y\n',encoding='utf8')
    log=run/'console.log'
    environment={key:value for key,value in os.environ.items() if key not in
                 ('DATABASE_URL','PG_ADMIN_PASSWORD','PGPASSWORD','APS_CLIENT_SECRET','GEMINI_API_KEY','OPENAI_API_KEY')}
    if host.get('dotnet_root'):
        environment.update(DOTNET_ROOT=host['dotnet_root'],DOTNET_ROOT_X64=host['dotnet_root'])
    with _engine_lock:
        with log.open('wb') as output:
            try:
                result=subprocess.run([host['core'],'/i',str(run/'bootstrap.dwg'),'/s',str(script),
                                       '/nologo','/isolate','MechanicalCad',str(shared_profile),'/language','en-US'],
                    cwd=run,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,timeout=timeout,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False,env=environment)
            except subprocess.TimeoutExpired:
                raise ValueError('AutoCAD quá thời gian xử lý; tiến trình tác vụ đã dừng. Kiểm tra license/plugin và log console của tác vụ.') from None
    archive=run/'result.zip'
    (run/'console-exit.json').write_text(json.dumps({'returncode':result.returncode,'archive_created':archive.is_file()}),encoding='utf8')
    if result.returncode or not archive.is_file():
        if archive.is_file():shutil.copyfile(archive,folder/'failed-result.zip')
        error=run/'plugin-error.json'
        if error.is_file():
            detail=json.loads(error.read_text(encoding='utf8'))
            if detail.get('message')=='eDwgNeedsRecovery':
                raise ValueError('DWG cần phục hồi dữ liệu (eDwgNeedsRecovery). Dùng RECOVER trong AutoCAD trên một bản sao rồi tải bản phục hồi lên; chưa sửa hoặc ghi đè nguồn.')
            message=detail.get('message','')
            if message.startswith(('AutoCAD did not accept parameter ','Parameter readback mismatch: ','Parameter outside allowed values','Unselected dynamic block changed: ')):
                raise ValueError('Chưa tạo bản sửa: ràng buộc native không chấp nhận đúng giá trị yêu cầu. '+message[:500]+'. File gốc giữ nguyên; không tải kết quả sai số.')
        progress=run/'plugin-progress.json'
        if progress.is_file():
            stage=json.loads(progress.read_text(encoding='utf8')).get('stage','unknown')
            raise ValueError('AutoCAD chưa tạo kết quả tại bước '+str(stage)[:60]+'. Xem autocad-plugin-error.json và autocad-console.log của tác vụ.')
        startup_error=console_startup_error(log)
        if startup_error:raise ValueError(startup_error)
        raise ValueError('AutoCAD chưa tạo kết quả. Mở AutoCAD để kích hoạt bản quyền, kiểm tra build/plugin và console.log của tác vụ.')
    if digest(source)!=commands['source_sha256']:raise ValueError('Snapshot nguồn đã đổi trong lúc AutoCAD chạy.')
    temporary=folder/'result.zip.part';shutil.copyfile(archive,temporary);temporary.replace(folder/'result.zip')
    return dict(runtime_key=host['runtime_key'],log='autocad-console.log')
