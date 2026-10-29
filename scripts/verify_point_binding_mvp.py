"""Native export -> explicit binding -> solver -> native vertex write -> reopen."""
import argparse,json,os,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def fixture(path):
    import ezdxf
    from ezdxf.entities import DXFTagStorage
    doc=ezdxf.new('R2018');doc.units=4;m=doc.modelspace()
    doc.styles.get('Standard').dxf.font='txt.shx'
    doc.dimstyles.get('Standard').dxf.dimtxsty='Standard'
    poly=m.add_lwpolyline([(0,0),(100,0),(100,50),(0,50)],close=True)
    wrapper=m.add_linear_dim(base=(0,-15),p1=(0,0),p2=(100,0));wrapper.render();dim=wrapper.dimension
    ext=dim.new_extension_dict();handle=doc.entitydb.next_handle()
    tags=['0','DIMASSOC','5',handle,'330',ext.dictionary.dxf.handle,'100','AcDbDimAssoc','330',dim.dxf.handle,'90','3','70','0','71','0']
    for i in (0,1):
        tags+=['1','AcDbOsnapPointRef','72','13','331',poly.dxf.handle,'73','2','91',str(i+1),'40','0','10',str(i*100),'20','0','30','0','75','0']
    assoc=DXFTagStorage.from_text('\n'.join(tags)+'\n',doc);doc.entitydb.add(assoc);doc.objects.add_object(assoc)
    ext['ACAD_DIMASSOC']=assoc;assoc.set_reactors([ext.dictionary.dxf.handle]);dim.set_reactors([handle]);poly.set_reactors([handle]);doc.header['$DIMASSOC']=2
    control=m.add_line((250,250),(300,275));doc.saveas(path)
    return poly.dxf.handle,dim.dxf.handle,control.dxf.handle


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    import ezdxf
    from backend.services import autocad_host,catalog_service as storage
    from cad.edit_engine import digest
    from cad.dimension_associations import source_binding
    from cad.geometry import near,snapshot
    from scripts.point_binding_mvp import solve_binding
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--target',type=float,default=120)
    parser.add_argument('--negative',choices=['source-hash','fixed-edge','shared-visual'])
    args=parser.parse_args();output=Path(args.output).resolve()
    if output.exists():raise ValueError('Choose a new evidence directory')
    output.mkdir(parents=True);run=ROOT/'storage/acwork'/('point-mvp-'+uuid.uuid4().hex[:8]);run.mkdir()
    host=autocad_host.ready();shutil.copyfile(host['bootstrap_path'],run/'bootstrap.dwg');shutil.copytree(host['bundle'],run/'MechanicalCad.Local.bundle')
    poly,dim,control=fixture(run/'fixture.dxf');storage.write_json(run/'point-request.json',dict(polyline_handle=poly,dimension_handle=dim))
    if args.negative=='shared-visual':
        drawing=ezdxf.readfile(run/'fixture.dxf')
        drawing.modelspace().add_blockref(drawing.entitydb[dim].dxf.geometry,(300,0))
        drawing.saveas(run/'fixture.dxf')
    plugin=run/'MechanicalCad.Local.bundle/Contents/MechanicalCad.Local.dll'
    env={k:v for k,v in os.environ.items() if k not in ('DATABASE_URL','PG_ADMIN_PASSWORD','PGPASSWORD','APS_CLIENT_SECRET','GEMINI_API_KEY','OPENAI_API_KEY')}
    if host.get('dotnet_root'):env.update(DOTNET_ROOT=host['dotnet_root'],DOTNET_ROOT_X64=host['dotnet_root'])
    def execute(commands,phase,expected_error=None):
        script=run/(phase+'.scr');script.write_text('_.SETVAR\nTRUSTEDPATHS\n'+plugin.parent.as_posix()+'\n_.SETVAR\nSECURELOAD\n2\n_.NETLOAD\n'+plugin.as_posix()+'\n'+'\n'.join(commands)+'\n_.QUIT\n_Y\n',encoding='utf8')
        with autocad_host._engine_lock:
            with (output/(phase+'.log')).open('wb') as log:
                completed=subprocess.run([host['core'],'/i',str(run/'bootstrap.dwg'),'/s',str(script),'/isolate','MechanicalPointMvp',str(run/'profile'),'/language','en-US'],cwd=run,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=env)
        if (run/'aicad-error.json').exists():
            detail=json.loads((run/'aicad-error.json').read_text())
            shutil.copyfile(run/'aicad-error.json',output/(phase+'-error.json'))
            if expected_error and completed.returncode==0 and detail['message']==expected_error and not (run/'point-result.dwg').exists() and not (run/'point-receipt.json').exists():return detail
            raise RuntimeError(str(detail))
        if completed.returncode:raise RuntimeError('Core Console failed: '+str(completed.returncode))
        if expected_error:raise AssertionError('Native preflight accepted invalid evidence')
    execute(['AICAD_BUILD_FIXTURE','AICAD_EXPORT_POINTS'],'export')
    binding=json.loads((run/'point-binding.json').read_text());original_hash=digest(run/'input.cad')
    before=ezdxf.readfile(run/'source-readback.dxf');b=source_binding(before.entitydb[dim])
    assert before.units==4 and abs(before.entitydb[dim].get_measurement()-100)<1e-7
    assert binding['source_sha256']==original_hash and abs(binding['dimension']['measurement_mm']-100)<1e-7
    assert b['status']=='verified_source_points' and b['source_refs']==[poly],b
    assert [p['vertex_index'] for p in b['points']]==[0,1]
    solved=solve_binding(binding,args.target)
    storage.write_json(run/'solver-result.json',solved)
    solution=dict(source_sha256=original_hash,binding_sha256=digest(run/'point-binding.json'),polyline_handle=poly,dimension_handle=dim,target_width_mm=args.target,points=solved['points'])
    if args.negative=='source-hash':solution['source_sha256']='0'*64
    if args.negative=='fixed-edge':
        for point in solution['points']:point[0]+=1
    storage.write_json(run/'point-solution.json',solution)
    expected={'source-hash':'Point solution source/binding hash mismatch','fixed-edge':'Point solution changed fixed edge or height','shared-visual':'Rectangle DIM visual block has another user'}
    rejected=execute(['AICAD_APPLY_POINTS'],'apply',expected.get(args.negative))
    if args.negative:
        assert digest(run/'input.cad')==original_hash and not (run/'point-result.dxf').exists()
        storage.write_json(output/'receipt.json',dict(status='validated_point_binding_rejection',negative_case=args.negative,error=rejected,source_unchanged=True,output_dwg_created=False,customer_revision_created=False))
        print(json.dumps(dict(status='validated_point_binding_rejection',negative_case=args.negative,output=str(output))));return
    receipt=json.loads((run/'point-receipt.json').read_text());after=ezdxf.readfile(run/'point-result.dxf')
    assert after.units==4 and abs(after.entitydb[dim].get_measurement()-args.target)<1e-7
    actual=source_binding(after.entitydb[dim]);assert actual['status']=='verified_source_points' and actual['association_ref']==b['association_ref'] and [p['vertex_index'] for p in actual['points']]==[0,1],actual
    assert near(snapshot(after.entitydb[control]),snapshot(before.entitydb[control]),1e-7)
    for i,p in enumerate(after.entitydb[poly].get_points('xy')):assert near(list(p),solved['points'][i][:2],1e-7)
    block=after.blocks[after.entitydb[dim].dxf.geometry]
    labels=[e.plain_text() if e.dxftype()=='MTEXT' else e.dxf.text for e in block if e.dxftype() in ('TEXT','MTEXT')]
    assert any(abs(float(label)-args.target)<1e-7 for label in labels),labels
    assert digest(run/'input.cad')==original_hash and digest(run/'point-result.dwg')==receipt['output_sha256']
    receipt.update(status='validated_solver_to_native_rectangle_stretch',runtime_release=host['release'],source_width_mm=before.entitydb[dim].get_measurement(),result_height_mm=after.entitydb[poly].get_points('xy')[3][1]-after.entitydb[poly].get_points('xy')[0][1],independent_dxf_readback=True,source_binding=actual,rendered_labels=labels,source_unchanged=True,aps_automation_verified=False,work_directory=str(run))
    for name in ('fixture.dxf','input.cad','source-readback.dxf','point-binding.json','point-solution.json','solver-result.json','point-result.dwg','point-result.dxf','point-dim-diagnostics.json'):
        shutil.copyfile(run/name,output/('source.dwg' if name=='input.cad' else name))
    storage.write_json(output/'receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=True))


if __name__=='__main__':main()
