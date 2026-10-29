"""Experimental CenterMark translation on an isolated validation copy only."""
import argparse,json,os,re,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from backend.services import autocad_host,catalog_service as storage
from cad.edit_engine import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('document_id');parser.add_argument('circle_handle');parser.add_argument('--dx',type=float,default=3);parser.add_argument('--dy',type=float,default=-2);parser.add_argument('--expect-rejected',action='store_true');args=parser.parse_args()
    if not re.fullmatch('[0-9A-F]{1,16}',args.circle_handle):raise ValueError('Invalid circle handle')
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig');host=autocad_host.ready()
    source=storage.folder(args.document_id)/'original.dwg';before=digest(source)
    token=uuid.uuid4().hex[:8];run=ROOT/'storage/acwork'/('center-'+token);run.mkdir(parents=True)
    output=ROOT/'storage/validation-fixtures'/('native-center-probe-'+token);output.mkdir(parents=True)
    shutil.copyfile(source,run/'input.cad');shutil.copyfile(host['bootstrap_path'],run/'bootstrap.dwg')
    shutil.copytree(host['bundle'],run/'MechanicalCad.Local.bundle');plugin=run/'MechanicalCad.Local.bundle/Contents/MechanicalCad.Local.dll'
    (run/'center-probe.json').write_text(json.dumps(dict(source_sha256=before,circle_handle=args.circle_handle,delta=[args.dx,args.dy,0])),encoding='utf8')
    script=run/'probe.scr';script.write_text('_.SETVAR\nTRUSTEDPATHS\n'+plugin.parent.as_posix()+'\n_.SETVAR\nSECURELOAD\n2\n_.NETLOAD\n'+plugin.as_posix()+'\nMECHANICALCENTERPROBE\n_.QUIT\n_Y\n',encoding='utf8')
    environment={k:v for k,v in os.environ.items() if k not in ('DATABASE_URL','PG_ADMIN_PASSWORD','PGPASSWORD','APS_CLIENT_SECRET','GEMINI_API_KEY','OPENAI_API_KEY')}
    if host.get('dotnet_root'):environment.update(DOTNET_ROOT=host['dotnet_root'],DOTNET_ROOT_X64=host['dotnet_root'])
    with autocad_host._engine_lock:
        with (output/'console.log').open('wb') as log:
            completed=subprocess.run([host['core'],'/i',str(run/'bootstrap.dwg'),'/s',str(script),'/isolate','MechanicalCenterProbe',str(run/'profile'),'/language','en-US'],cwd=run,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=environment)
    assert digest(source)==before
    for name in ('center-probe-error.json','center-probe-receipt.json','center-probe-differences.json','center-probe.json'):
        if (run/name).exists():shutil.copyfile(run/name,output/name)
    error=run/'center-probe-error.json';receipt=run/'center-probe-receipt.json'
    if completed.returncode or error.exists() or not receipt.exists():
        detail=json.loads(error.read_text(encoding='utf8')) if error.exists() else dict(returncode=completed.returncode)
        expected=args.expect_rejected and detail.get('message') in ('Probe requires one circle dependency','Probe target must be CIRCLE')
        summary=dict(status='validated_native_rejection_probe' if expected else 'failed_validation_probe',output=str(output),source_unchanged=True,error=detail)
        storage.write_json(output/'probe-summary.json',summary);print(json.dumps(summary,ensure_ascii=True));return 0 if expected else 2
    if args.expect_rejected:raise AssertionError('Probe unexpectedly accepted a rejected case')
    evidence=json.loads(receipt.read_text(encoding='utf8'));assert evidence['source_sha256']==before and evidence['output_sha256']==digest(run/'center-probe.dwg')
    assert evidence.get('persisted_state_verified_before_evaluation') is True
    assert evidence.get('reopened_evaluation_stable') is True
    for name in ('center-probe.dwg','center-probe.dxf'):shutil.copyfile(run/name,output/name)
    import ezdxf
    from cad.geometry import near
    reopened=ezdxf.readfile(output/'center-probe.dxf');circle=reopened.entitydb[evidence['circle_handle']];mark=reopened.entitydb[evidence['mark_handle']]
    assert near(list(circle.dxf.center),evidence['circle_center'],1e-6) and near(list(mark.dxf.insert),evidence['mark_position'],1e-6)
    assert abs(circle.dxf.radius-evidence['radius'])<1e-8 and circle.get_reactors() and mark.get_reactors()
    assert near(evidence['circle_center'],[a+b for a,b in zip(evidence['source_circle_center'],evidence['delta'])],1e-6)
    evidence['independent_dxf_readback']=True;storage.write_json(output/'center-probe-receipt.json',evidence)
    print(json.dumps(dict(status=evidence['status'],output=str(output),circle=evidence['circle_handle'],mark=evidence['mark_handle'],unselected_inventory_entries_verified=evidence['unselected_inventory_entries_verified'],source_unchanged=True,customer_revision_created=False),ensure_ascii=True))


if __name__=='__main__':raise SystemExit(main() or 0)
