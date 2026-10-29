"""Move only a repaired source vertex and prove DIM follows without endpoint writes."""
import argparse,json,os,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    import ezdxf
    from backend.services import autocad_host,catalog_service as storage
    from cad.edit_engine import digest
    from cad.dimension_associations import source_binding
    from cad.geometry import near
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('repair_evidence',type=Path)
    parser.add_argument('--dimension',required=True,type=str);parser.add_argument('--step',type=float,default=10)
    parser.add_argument('--observe-native-head',action='store_true')
    parser.add_argument('--check-migrated-head',action='store_true')
    parser.add_argument('--check-native-pointrefs',action='store_true',help='Private direct-reference adapter evidence; retains native B action.')
    parser.add_argument('--endpoint',choices=['A','B'],default='A')
    parser.add_argument('--native-b-only',action='store_true',help='Remove redundant new legacy B reference on the challenge copy to prove the original native B action independently.')
    parser.add_argument('--negative-unrepaired',action='store_true',help='Prove the original partial DIM does not follow the missing endpoint in the no-op control.')
    args=parser.parse_args();receipt=json.loads((args.repair_evidence/('validation.json' if args.check_native_pointrefs else 'repair-receipt.json')).read_text())
    if args.native_b_only and (not args.check_native_pointrefs or args.endpoint!='B'):parser.error('B isolation requires --check-native-pointrefs --endpoint B')
    if args.check_native_pointrefs:
        if args.observe_native_head or args.check_migrated_head or args.negative_unrepaired:parser.error('Direct-reference challenge is a separate private mode')
        assert receipt['status']=='private_native_point_references_saved_reopened_verified' and receipt['native_b_parameters_preserved'] is True
        from cad.native_point_reference_scope import challenge_target
        scope=receipt['scope']
        target,vertex,delta=challenge_target(scope,args.dimension,args.endpoint,args.step)
    if args.observe_native_head and args.check_migrated_head:parser.error('Choose observation or migrated-head validation')
    first_endpoint=args.observe_native_head or args.check_migrated_head or (args.check_native_pointrefs and args.endpoint=='A')
    if not args.check_native_pointrefs and first_endpoint!=(args.dimension in ('3DFA24','3DFA29')):parser.error('Native DIM requires observation or native-reference mode')
    if args.check_migrated_head and not receipt.get('native_heads_repaired'):parser.error('Validated native head repair evidence required')
    if args.observe_native_head and args.negative_unrepaired:parser.error('Native observation is separate from legacy negative test')
    if not args.check_native_pointrefs:assert receipt['status']==('validated_noop_control' if args.negative_unrepaired else 'validated_relationship_repair_proposal')
    prefix='native-point-reference-repair' if args.check_native_pointrefs else 'relationship-repair'
    source=args.repair_evidence/(prefix+'.dwg');source_hash=digest(source);assert source_hash==receipt['output_sha256']
    assert abs(args.step)==10
    dim=args.dimension
    if not args.check_native_pointrefs:
        if dim not in ('3DFA25','3DFA2A','3DFA24','3DFA29'):parser.error('Unsupported legacy challenge DIM')
        vertex=3 if dim=='3DFA25' else 6;delta=[0,-args.step,0] if vertex==3 else [args.step,0,0]
        if first_endpoint:
            vertex=1 if dim=='3DFA24' else 0;delta=[0,args.step,0] if vertex==1 else [-args.step,0,0]
    token=uuid.uuid4().hex[:8];run=ROOT/'storage/acwork'/('relationship-challenge-'+token);output=ROOT/'storage/validation-fixtures'/('relationship-challenge-'+token)
    run.mkdir();output.mkdir();host=autocad_host.ready();shutil.copyfile(source,run/'input.dwg');shutil.copytree(host['bundle'],run/'MechanicalCad.Local.bundle')
    config=dict(source_sha256=source_hash,polyline_handle=receipt['polyline_handle'],dimension_handle=dim,vertex_index=vertex,delta=delta)
    if args.observe_native_head:config['native_head_observation']=True
    if args.check_migrated_head:config['challenge_first_endpoint']=True
    if args.check_native_pointrefs:config.update(native_point_reference_challenge=True,challenge_first_endpoint=first_endpoint,native_target=target)
    if args.native_b_only:
        config['native_b_only']=True
        shutil.copyfile(ROOT/'autodesk/NativePointReference/build/MechanicalPointReference.dll',run/'MechanicalPointReference.dll')
    storage.write_json(run/'relationship-challenge.json',config);storage.write_json(output/'relationship-challenge.json',config)
    plugin=run/'MechanicalCad.Local.bundle/Contents/MechanicalCad.Local.dll'
    script=run/'challenge.scr';script.write_text('_.SETVAR\nTRUSTEDPATHS\n'+plugin.parent.as_posix()+'\n_.SETVAR\nSECURELOAD\n2\n_.NETLOAD\n'+plugin.as_posix()+'\nMECHANICALCHALLENGEREPAIREDDIM\n_.QUIT\n_N\n',encoding='utf8')
    env={k:v for k,v in os.environ.items() if k not in ('DATABASE_URL','PG_ADMIN_PASSWORD','PGPASSWORD','APS_CLIENT_SECRET','GEMINI_API_KEY','OPENAI_API_KEY')}
    if host.get('dotnet_root'):env.update(DOTNET_ROOT=host['dotnet_root'],DOTNET_ROOT_X64=host['dotnet_root'])
    with autocad_host._engine_lock:
        with (output/'console.log').open('wb') as log:
            done=subprocess.run([host['core'],'/i',str(run/'input.dwg'),'/s',str(script),'/isolate','MechanicalRepairedDimChallenge',str(run/'profile'),'/language','en-US'],cwd=run,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=env)
    assert digest(source)==source_hash
    for p in run.glob('relationship-challenge*.json'):shutil.copyfile(p,output/p.name)
    if args.observe_native_head:
        observation=run/'relationship-native-head.json'
        assert done.returncode==0 and observation.exists() and not (run/'relationship-challenge-error.json').exists()
        r=json.loads(observation.read_text());assert r['source_sha256']==source_hash and r['dimension_handle']==dim and r['dim_endpoint_writer_assigned'] is False
        assert not (run/'relationship-challenge.dwg').exists()
        shutil.copyfile(observation,output/observation.name)
        storage.write_json(output/'observation-receipt.json',dict(**r,source_unchanged=True,output=str(output)))
        print(json.dumps(dict(status=r['status'],dimension=dim,follows_candidate_vertex=r['follows_candidate_vertex'],original_head_unchanged=r['original_head_unchanged'],output=str(output))));return 0
    error=output/'relationship-challenge-error.json';native=output/'relationship-challenge-native.json'
    if done.returncode or error.exists() or not native.exists():
        if args.negative_unrepaired and done.returncode==0 and error.exists():
            failure=json.loads(error.read_text())
            assert failure['message']=='Repaired DIM did not follow geometry automatically' and not (run/'relationship-challenge.dwg').exists()
            summary=dict(status='validated_unrepaired_endpoint_rejection',dimension=dim,error=failure,source_unchanged=True,output_dwg_created=False,output=str(output))
            storage.write_json(output/'challenge-receipt.json',summary);print(json.dumps(summary));return 0
        print(json.dumps(dict(status='failed_repaired_dim_challenge',output=str(output),error=json.loads(error.read_text()) if error.exists() else dict(returncode=done.returncode),source_unchanged=True)));return 2
    assert not args.negative_unrepaired,'Unrepaired DIM unexpectedly followed the missing endpoint'
    result=json.loads(native.read_text());assert result['output_sha256']==digest(run/'relationship-challenge.dwg')
    baseline=ezdxf.readfile(args.repair_evidence/(prefix+'.dxf'));after=ezdxf.readfile(run/'relationship-challenge.dxf')
    old=baseline.entitydb[dim];actual=after.entitydb[dim];field='defpoint2' if first_endpoint else 'defpoint3';other='defpoint3' if first_endpoint else 'defpoint2'
    expected=[x+y for x,y in zip(getattr(old.dxf,field),delta)]
    assert near(list(getattr(actual.dxf,field)),expected,1e-6) and near(list(getattr(actual.dxf,other)),list(getattr(old.dxf,other)),1e-6)
    assert abs(actual.get_measurement()-result['after_measurement'])<1e-6 and abs(actual.get_measurement()-old.get_measurement()-args.step)<1e-6
    if args.check_native_pointrefs:
        from cad.native_head_repairs import hybrid_binding
        binding=hybrid_binding(actual,target['dimension_dependency'])
    else:binding=source_binding(actual)
    assert binding['status']=='verified_source_points' and binding['source_refs']==[receipt['polyline_handle']]
    if args.check_native_pointrefs:expected_binding={'defpoint2':target['a_vertex'],'defpoint3':target['b_vertex']}
    else:expected_binding={'defpoint2':1 if dim=='3DFA24' else 0,'defpoint3':2 if dim=='3DFA24' else 7} if first_endpoint else {'defpoint2':2 if vertex==3 else 7,'defpoint3':vertex}
    if args.native_b_only:
        expected_binding.pop('defpoint3')
        assert result['native_b_isolated_from_legacy_b'] is True
    assert {p['dimension_field']:p['vertex_index'] for p in binding['points']}==expected_binding
    labels=[e.plain_text() for e in after.blocks[actual.dxf.geometry] if e.dxftype()=='MTEXT']
    assert len(labels)==1 and abs(float(labels[0])-round(actual.get_measurement()))<1e-6
    for name in ('relationship-challenge.dwg','relationship-challenge.dxf'):shutil.copyfile(run/name,output/name)
    result.update(status='validated_repaired_dim_auto_follow',binding=binding,rendered_label=labels[0],independent_dxf_readback=True,source_unchanged=True,
                  coverage='Individual repaired endpoint perturbation only; neighboring relations are reported, not certified as a complete mechanical group.')
    storage.write_json(output/'challenge-receipt.json',result)
    print(json.dumps(dict(status=result['status'],dimension=dim,measurement=actual.get_measurement(),output=str(output),source_unchanged=True)));return 0


if __name__=='__main__':raise SystemExit(main())
