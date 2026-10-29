"""Prepare/check a local AutoCAD adapter; preserves original CAD and APS config."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime,timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv,set_key
from backend.services import autocad_host
from cad.edit_engine import digest


def dotnet(host):
    major='10' if host['framework'].startswith('net10') else '8'
    portable=ROOT/'storage/tools'/('dotnet'+major)/'dotnet.exe'
    path=str(portable) if portable.is_file() else shutil.which('dotnet')
    if not path:raise ValueError('Cần .NET SDK '+major+' để build plugin phù hợp AutoCAD.')
    result=subprocess.run([path,'--list-sdks'],capture_output=True,text=True,timeout=20,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if not any(line.startswith(major+'.') for line in result.stdout.splitlines()):raise ValueError('Chưa có .NET SDK '+major+'; runtime đơn thuần không đủ để build.')
    return path


def build():
    host=autocad_host.discover();sdk=dotnet(host)
    blank=autocad_host.bootstrap(host)
    project=ROOT/'autodesk/MechanicalCad'
    output=ROOT/'autodesk/local'/host['series'];output.mkdir(parents=True,exist_ok=True)
    log=output/'build.log'
    env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
             DOTNET_CLI_HOME=str(ROOT/'storage/tools/dotnet-home'),NUGET_PACKAGES=str(ROOT/'storage/tools/nuget-packages'))
    args=[sdk,'build',str(project/'MechanicalCad.Local.csproj'),'-c','Release',
          '-p:AutoCADManagedDir='+host['managed_dir'],'-p:AutoCADTargetFramework='+host['framework'],
          '-p:BaseIntermediateOutputPath=obj-local/','-p:MSBuildProjectExtensionsPath='+str(project/'obj-local'),
          '-p:RestoreConfigFile='+str(project/'NuGet.Config'),'-p:NuGetAudit=false','--ignore-failed-sources']
    with log.open('wb') as stream:
        result=subprocess.run(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=240,env=env,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Chưa build được plugin theo SDK AutoCAD hiện tại; xem '+str(log))
    compiled=project/'bin-local'/host['framework']/'MechanicalCad.Local.dll'
    if not compiled.is_file():raise ValueError('Build không trả DLL plugin local.')
    bundle=output/'MechanicalCad.Local.bundle';contents=bundle/'Contents';contents.mkdir(parents=True,exist_ok=True)
    for extension in ('.dll','.deps.json'):
        source=compiled.with_suffix(extension) if extension=='.dll' else compiled.with_name('MechanicalCad.Local.deps.json')
        if source.is_file():shutil.copyfile(source,contents/source.name)
    root=ET.Element('ApplicationPackage',SchemaVersion='1.0',AppVersion='1.0.0',Name='MechanicalCad.Local',
                    ProductCode='{E7B60C62-8CCD-4C98-BF87-25BD112E5CBA}',Author='Mechanical AI Drawing')
    ET.SubElement(root,'CompanyDetails',Name='Mechanical AI Drawing')
    components=ET.SubElement(root,'Components')
    ET.SubElement(components,'RuntimeRequirements',OS='Win64',Platform='AutoCAD*',SeriesMin=host['series'],SeriesMax=host['series'])
    entry=ET.SubElement(components,'ComponentEntry',AppName='MechanicalCad.Local',ModuleName='./Contents/MechanicalCad.Local.dll',LoadOnAutoCADStartup='True')
    commands=ET.SubElement(entry,'Commands',GroupName='MechanicalCad')
    ET.SubElement(commands,'Command',Global='MECHANICALCAD',Local='MECHANICALCAD')
    manifest=bundle/'PackageContents.xml';ET.ElementTree(root).write(manifest,encoding='utf-8',xml_declaration=True)
    receipt=dict(host,bundle=str(bundle),plugin_hash=digest(contents/'MechanicalCad.Local.dll'),manifest_hash=digest(manifest),
                 bootstrap_path=str(blank),bootstrap_hash=digest(blank),
                 built_at=datetime.now(timezone.utc).isoformat())
    autocad_host.receipt_path().write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    set_key(str(ROOT/'.env'),'AUTOCAD_CORE_CONSOLE',host['core'],quote_mode='always')
    return dict(status='built',release=host['release'],framework=host['framework'],next='python scripts/setup_autocad.py check')


def prebuild():
    """Compile against Autodesk's 2027 reference packages, without a CAD host."""
    sdk=dotnet({'framework':'net10.0-windows'});project=ROOT/'autodesk/MechanicalCad'
    output=ROOT/'autodesk/local/preflight-2027';output.mkdir(parents=True,exist_ok=True)
    config=output/'NuGet.Config'
    config.write_text('<?xml version="1.0" encoding="utf-8"?>\n<configuration><packageSources><clear />'
                      '<add key="nuget.org" value="https://api.nuget.org/v3/index.json" />'
                      '</packageSources></configuration>\n',encoding='utf8')
    env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
             DOTNET_CLI_HOME=str(ROOT/'storage/tools/dotnet-home'),NUGET_PACKAGES=str(ROOT/'storage/tools/nuget-packages'))
    log=output/'build.log'
    args=[sdk,'build',str(project/'MechanicalCad.Local.csproj'),'-c','Release',
          '-p:AutoCADReferencePackages=true','-p:AutoCADTargetFramework=net10.0-windows',
          '-p:BaseIntermediateOutputPath=obj-local/','-p:MSBuildProjectExtensionsPath='+str(project/'obj-local'),
          '-p:RestoreConfigFile='+str(config),'-p:NuGetAudit=false']
    with log.open('wb') as stream:
        result=subprocess.run(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=240,env=env,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Chưa biên dịch được với SDK tham chiếu 2027; xem '+str(log))
    compiled=project/'bin-local/net10.0-windows/MechanicalCad.Local.dll'
    if not compiled.is_file():raise ValueError('Prebuild chưa trả DLL plugin.')
    shutil.copyfile(compiled,output/compiled.name)
    # No host receipt, configuration change or live verification is made here.
    proof=dict(status='compiled',release=2027,framework='net10.0-windows',
               reference_packages=['AutoCAD.NET.Core/26.0.0','AutoCAD.NET.Model/26.0.0'],
               plugin_hash=digest(compiled),live_verified=False,complete_product_backup=False)
    (output/'receipt.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
    return proof


def check():
    """Real native open/save/edit/readback; never uses a customer drawing."""
    import ezdxf
    from backend.services import catalog_service as storage,aps_jobs
    host=autocad_host.ready();document_id=uuid.uuid4().hex;folder=storage.ROOT/document_id;folder.mkdir()
    source=folder/'original.dxf';drawing=ezdxf.new('R2018');drawing.units=4
    model=drawing.modelspace();line=model.add_line((0,0),(100,0));text=model.add_text('HOST_CHECK_BEFORE',dxfattribs={'insert':(0,10)})
    text.new_extension_dict().add_xrecord('MECHANICAL_HOST_CHECK').reset([(1,'native dictionary readback')])
    dimension=model.add_linear_dim(base=(0,20),p1=(0,0),p2=(100,0));dimension.render()
    drawing.saveas(source);before=digest(source)
    storage.write_json(folder/'status.json',dict(id=document_id,filename='synthetic-autocad-host-check.dxf',status='ready',
                       dxf='original.dxf',source_kind='synthetic_test',auxiliary=True))
    inspection=aps_jobs.start(document_id,provider='autocad');inspection=aps_jobs.wait(document_id,inspection['id'])
    inventory=json.loads(aps_jobs.artifact(document_id,inspection['id'],'inventory.json').read_text(encoding='utf-8-sig'))
    matches=[row for row in inventory['entities'] if row.get('text')=='HOST_CHECK_BEFORE' and row.get('is_layout')]
    if len(matches)!=1:raise ValueError('Native check không xác định đúng text fixture.')
    native=matches[0];native_source=aps_jobs.artifact(document_id,inspection['id'],'modified.dwg')
    if not any(record['name']=='MECHANICAL_HOST_CHECK' for record in native.get('extension_records',[])):
        raise ValueError('Native check không đọc đủ extension dictionary fixture.')
    edit=aps_jobs.start(document_id,provider='autocad',mode='edit',source=native_source,scope_handles=[native['handle']],
         operations=[dict(action='replace_text',handle=native['handle'],owner_handle=native['owner_handle'],expected_type=native['type'],
                          before='HOST_CHECK_BEFORE',after='HOST_CHECK_AFTER')])
    edit=aps_jobs.wait(document_id,edit['id'])
    reopened=ezdxf.readfile(aps_jobs.artifact(document_id,edit['id'],'roundtrip.dxf'))
    if not any(e.dxftype()=='TEXT' and e.dxf.text=='HOST_CHECK_AFTER' for e in reopened.modelspace()):raise ValueError('Native edit text không khớp sau mở lại.')
    if not any(e.dxftype()=='LINE' and abs(e.dxf.start.distance(e.dxf.end)-100)<1e-6 for e in reopened.modelspace()):raise ValueError('Native check không giữ geometry 100 mm.')
    if not any(e.dxftype()=='DIMENSION' and abs(e.get_measurement()-100)<1e-6 for e in reopened.modelspace()):raise ValueError('Native check không giữ DIM 100 mm.')
    if digest(source)!=before:raise ValueError('Nguồn fixture đã thay đổi.')
    proof=dict(status='passed',runtime_key=host['runtime_key'],document_id=document_id,inspection_id=inspection['id'],edit_id=edit['id'],
               checks=['native load','extension dictionary','DWG save/readback','bounded text edit','geometry 100 mm','DIM 100 mm','source unchanged'],
               checked_at=datetime.now(timezone.utc).isoformat(),complete_product_backup=False)
    (ROOT/'storage/autocad-host-check.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    return proof


def activate():
    result=autocad_host.status()
    if not result['configured'] or not result['live_verified']:raise ValueError('Cần build và chạy check thành công trên đúng AutoCAD/plugin trước khi activate.')
    for name,value in (('CAD_DWG_BACKEND','autocad'),('CAD_READ_BACKEND','autocad')):
        set_key(str(ROOT/'.env'),name,value,quote_mode='always')
    return dict(status='activated',message='Khởi động lại backend. AutoCAD local được dùng để đọc/xuất; AI provider và cấu hình APS giữ nguyên.')


def main():
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['status','prebuild','build','check','activate'])
    parser.add_argument('--core',type=Path);args=parser.parse_args()
    if args.core:os.environ['AUTOCAD_CORE_CONSOLE']=str(args.core.resolve())
    actions={'status':autocad_host.status,'prebuild':prebuild,'build':build,'check':check,'activate':activate}
    print(json.dumps(actions[args.action](),ensure_ascii=False,indent=2))


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    try:main()
    except Exception as error:
        print(str(error) if isinstance(error,ValueError) else 'Chuẩn bị AutoCAD chưa hoàn tất; xem log build/tác vụ và cấu hình.',file=sys.stderr)
        sys.exit(1)
