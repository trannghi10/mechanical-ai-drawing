"""Experimental native translation of an explicitly closed polyline/DIM group."""
import argparse,json,os,re,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def inspection_group(document_id, job_id, handle, source_hash):
    """Accept only hash-checked inspection artifacts for the current source DWG."""
    from backend.services import aps_jobs
    from cad.edit_engine import digest
    from cad.native_polyline_dimensions import discover
    import ezdxf
    job=aps_jobs.read(document_id,job_id)
    if job['mode']!='inspect' or job['source_hash']!=source_hash:
        raise ValueError('Inspection does not match the source DWG')
    inventory_path=aps_jobs.artifact(document_id,job_id,'inventory.json')
    dxf_path=aps_jobs.artifact(document_id,job_id,'roundtrip.dxf')
    baseline=ezdxf.readfile(dxf_path)
    group=discover(json.loads(inventory_path.read_text(encoding='utf-8-sig')),baseline,handle)
    group.update(inspection_job_id=job_id,source_sha256=source_hash,
                 input_sha256=dict(inventory=digest(inventory_path),dxf=digest(dxf_path)))
    return baseline,group


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    from backend.services import autocad_host,catalog_service as storage
    from cad.edit_engine import digest
    from cad.dimension_associations import source_binding
    from cad.dimensions import dimension_snapshot
    from cad.dimension_visuals import verify_translation,verify_horizontal_stretch
    from cad.geometry import near,snapshot
    import ezdxf
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('document_id');parser.add_argument('polyline_handle')
    parser.add_argument('--dx',type=float,default=5);parser.add_argument('--dy',type=float,default=-3)
    parser.add_argument('--inspection-job',help='Discover the complete probe group from a hash-checked inspection of this source DWG.')
    parser.add_argument('--stretch-width',type=float,help='Experimental left-fixed octagon width target in mm.')
    parser.add_argument('--inspect-subentities',action='store_true',help='Read native persistent/transient subentity evidence only; no geometry writes or output DWG.')
    parser.add_argument('--subentity-evidence',type=Path,help='Source-hash checked native subentity report to refine endpoint evidence in a stretch plan.')
    parser.add_argument('--native-auto-endpoints',action='store_true',help='Experimental: let native actions update proven endpoints instead of assigning them; may reject before save.')
    parser.add_argument('--allow-unbound-test-assumptions',action='store_true',help='Explicitly permit exact-vertex assumptions for partially associated DIMs on a private test copy.')
    parser.add_argument('--negative',choices=['missing-association','wrong-dimension','discovered-dimensions','discovered-actions'],help='Deliberately invalidate evidence to verify native preflight rejection.')
    args=parser.parse_args()
    if args.inspect_subentities and (not args.inspection_job or args.stretch_width is not None or args.negative):
        parser.error('Subentity inspection requires --inspection-job and cannot be combined with stretch/negative modes')
    if args.subentity_evidence and args.stretch_width is None:parser.error('--subentity-evidence requires --stretch-width')
    if args.native_auto_endpoints and not args.subentity_evidence:parser.error('--native-auto-endpoints requires --subentity-evidence')
    if args.stretch_width is not None and not args.inspection_job:parser.error('Stretch probe requires --inspection-job')
    if args.negative in ('discovered-dimensions','discovered-actions') and not args.inspection_job:
        parser.error('Discovery rejection checks require --inspection-job')
    if not re.fullmatch('[0-9A-F]{1,16}',args.polyline_handle):raise ValueError('Invalid polyline handle')
    host=autocad_host.ready();folder=storage.folder(args.document_id);source=folder/'original.dwg';source_hash=digest(source)
    group=None
    if args.inspection_job:
        baseline,group=inspection_group(args.document_id,args.inspection_job,args.polyline_handle,source_hash)
    else:
        baseline=ezdxf.readfile(folder/storage.read_status(args.document_id)['dxf'])
    poly=baseline.entitydb[args.polyline_handle]
    stretch=None
    if args.stretch_width is not None:
        from cad.octagon_width import plan
        subentity_evidence=json.loads(args.subentity_evidence.read_text(encoding='utf-8-sig')) if args.subentity_evidence else None
        stretch=plan(baseline,group,args.stretch_width,allow_unbound_test_assumptions=args.allow_unbound_test_assumptions,subentity_evidence=subentity_evidence)
    legacy=[]
    for layout in baseline.layouts:
        for dim in layout:
            if dim.dxftype()!='DIMENSION' or not dim.has_extension_dict or 'ACAD_DIMASSOC' not in dim.get_extension_dict():continue
            association=dim.get_extension_dict()['ACAD_DIMASSOC']
            if association.dxf.handle not in poly.get_reactors():continue
            binding=source_binding(dim)
            assert binding['status']=='verified_source_points' and binding['source_refs']==[args.polyline_handle],binding
            legacy.append(dict(association_ref=association.dxf.handle,dimension_handle=dim.dxf.handle,binding=binding))
    assert len(legacy)==4
    if group and legacy!=group['legacy_associations']:
        # Layout iteration order need not equal native reactor order.
        assert {r['association_ref']:r for r in legacy}=={r['association_ref']:r for r in group['legacy_associations']}
    if args.negative=='missing-association':legacy.pop()
    if args.negative=='wrong-dimension':legacy[0]=dict(legacy[0],dimension_handle=legacy[1]['dimension_handle'])
    token=uuid.uuid4().hex[:8];run=ROOT/'storage/acwork'/('poly-dim-'+token);run.mkdir(parents=True)
    output=ROOT/'storage/validation-fixtures'/('native-poly-dim-probe-'+token);output.mkdir(parents=True)
    shutil.copyfile(source,run/'input.cad');shutil.copyfile(host['bootstrap_path'],run/'bootstrap.dwg');shutil.copytree(host['bundle'],run/'MechanicalCad.Local.bundle')
    plugin=run/'MechanicalCad.Local.bundle/Contents/MechanicalCad.Local.dll'
    config=dict(source_sha256=source_hash,polyline_handle=args.polyline_handle,delta=[args.dx,args.dy,0],legacy_associations=legacy)
    if args.inspect_subentities:config['inspect_subentities_only']=True
    if args.native_auto_endpoints:config['native_auto_endpoints']=True
    if stretch:
        storage.write_json(output/'stretch-plan.json',stretch)
        config.update(delta=[0,0,0],stretch_before_points=[[p[0],p[1],stretch['before']['elevation']] for p in stretch['before']['points']],
                      stretch_points=[[p[0],p[1],stretch['after']['elevation']] for p in stretch['after']['points']],stretch_dimensions=stretch['dimensions'])
        if args.subentity_evidence:
            config['native_vertex_bindings']=[dict(dimension_handle=r['dimension_handle'],**r['evidence']) for r in stretch['binding_review']['endpoints'] if r['status']=='source_bound_native_vertex']
    if group:
        storage.write_json(output/'discovery.json',group)
        config['expected_dimension_handles']=group['dimension_handles']
        config['expected_action_handles']=[r['action_handle'] for r in group['native_actions']]
        if args.negative=='discovered-dimensions':config['expected_dimension_handles']=group['dimension_handles'][:-1]
        if args.negative=='discovered-actions':config['expected_action_handles']=config['expected_action_handles'][:-1]
    storage.write_json(run/'poly-dim-probe.json',config)
    script=run/'probe.scr';script.write_text('_.SETVAR\nTRUSTEDPATHS\n'+plugin.parent.as_posix()+'\n_.SETVAR\nSECURELOAD\n2\n_.NETLOAD\n'+plugin.as_posix()+'\nMECHANICALPOLYDIMPROBE\n_.QUIT\n_Y\n',encoding='utf8')
    environment={k:v for k,v in os.environ.items() if k not in ('DATABASE_URL','PG_ADMIN_PASSWORD','PGPASSWORD','APS_CLIENT_SECRET','GEMINI_API_KEY','OPENAI_API_KEY')}
    if host.get('dotnet_root'):environment.update(DOTNET_ROOT=host['dotnet_root'],DOTNET_ROOT_X64=host['dotnet_root'])
    with autocad_host._engine_lock:
        with (output/'console.log').open('wb') as log:
            completed=subprocess.run([host['core'],'/i',str(run/'bootstrap.dwg'),'/s',str(script),'/isolate','MechanicalPolyDimProbe',str(run/'profile'),'/language','en-US'],cwd=run,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=environment)
    assert digest(source)==source_hash
    for name in ('poly-dim-probe.json','poly-dim-current.json','poly-dim-native-evaluation.json','poly-dim-source-text.json','poly-dim-subentities.json','poly-dim-error.json','poly-dim-receipt.json'):
        if (run/name).exists():shutil.copyfile(run/name,output/name)
    error=run/'poly-dim-error.json';receipt=run/'poly-dim-receipt.json'
    if args.inspect_subentities:
        report=output/'poly-dim-subentities.json'
        if completed.returncode or error.exists() or not report.exists():
            raise RuntimeError('Native subentity inspection failed; see '+str(output))
        evidence=json.loads(report.read_text(encoding='utf8'))
        assert evidence['source_sha256']==source_hash and not (run/'poly-dim-probe.dwg').exists() and not (run/'poly-dim-probe.dxf').exists()
        assert {r['dimension_handle'] for r in evidence['dependencies']}=={r['dimension_handle'] for r in group['native_actions']}
        print(json.dumps(dict(status=evidence['status'],output=str(output),source_unchanged=True,output_dwg_created=False,customer_revision_created=False)))
        return 0
    if completed.returncode or error.exists() or not receipt.exists():
        detail=json.loads(error.read_text(encoding='utf8')) if error.exists() else dict(returncode=completed.returncode)
        expected_errors={'missing-association':'Polyline probe requires four independently bound legacy DIMASSOC records',
                         'wrong-dimension':'Legacy DIMASSOC DIM ownership mismatch',
                         'discovered-dimensions':'Discovered DIM group does not match native source',
                         'discovered-actions':'Discovered action group does not match native source'}
        rejected=(args.negative is not None and completed.returncode==0 and detail.get('message')==expected_errors[args.negative]
                  and not receipt.exists() and not (run/'poly-dim-probe.dwg').exists() and not (run/'poly-dim-probe.dxf').exists())
        summary=dict(status='validated_polyline_dimension_rejection' if rejected else 'failed_polyline_dimension_probe',output=str(output),negative_case=args.negative,source_unchanged=True,error=detail,
                     output_dwg_created=(run/'poly-dim-probe.dwg').exists(),customer_revision_created=False)
        storage.write_json(output/'probe-summary.json',summary);print(json.dumps(summary));return 0 if rejected else 2
    if args.negative:raise AssertionError('Native probe unexpectedly accepted deliberately invalid evidence')
    evidence=json.loads(receipt.read_text(encoding='utf8'))
    assert evidence['source_sha256']==source_hash and evidence['output_sha256']==digest(run/'poly-dim-probe.dwg')
    if group:
        assert set(evidence['dimension_handles'])==set(group['dimension_handles'])
        assert set(evidence['action_handles'])=={r['action_handle'] for r in group['native_actions']}
        evidence['discovery_verified']=True
        evidence['inspection_job_id']=args.inspection_job
    for name in ('poly-dim-probe.dwg','poly-dim-probe.dxf'):shutil.copyfile(run/name,output/name)
    after=ezdxf.readfile(output/'poly-dim-probe.dxf');delta=evidence['delta'];checks=[]
    if stretch and args.subentity_evidence:
        from cad.native_subentity_bindings import vertex_bindings
        before_bindings,before_report_hash=vertex_bindings(baseline,group,evidence['native_subentities_before'])
        assert before_report_hash==stretch['binding_review']['native_subentity_report_sha256'], 'Native source subentity evidence changed'
        after_bindings,after_report_hash=vertex_bindings(after,dict(group,source_sha256=evidence['output_sha256']),evidence['native_subentities_after'])
        assert set(before_bindings)==set(after_bindings)
        for key in before_bindings:
            assert all(before_bindings[key][field]==after_bindings[key][field] for field in ('vertex_index','geometry_dependency','action_handle','transient_subentity_index'))
        evidence['native_endpoint_bindings_verified_after_reopen']=dict(count=len(after_bindings),before_report_sha256=before_report_hash,after_report_sha256=after_report_hash)
    expected=stretch['after'] if stretch else json.loads(json.dumps(snapshot(poly)))
    if not stretch:
        for point in expected['points']:point[0]+=delta[0];point[1]+=delta[1]
    assert near(snapshot(after.entitydb[args.polyline_handle]),expected,1e-6)
    for handle in evidence['dimension_handles']:
        original=baseline.entitydb[handle];actual=after.entitydb[handle];a=dimension_snapshot(original);b=dimension_snapshot(actual)
        expectation=next((r for r in stretch['dimensions'] if r['handle']==handle),None) if stretch else None
        if stretch:
            assert near(b['defpoint2'],expectation['a'],1e-6) and near(b['defpoint3'],expectation['b'],1e-6)
            assert abs(actual.get_measurement()-expectation['measurement'])<1e-6
        else:
            assert all(near(b[key],[v+d for v,d in zip(a[key],delta)],1e-6) for key in ('defpoint','defpoint2','defpoint3'))
            assert abs(actual.get_measurement()-original.get_measurement())<1e-6
        def label(doc,dim):return ' '.join(e.plain_text() if e.dxftype()=='MTEXT' else e.dxf.text for e in doc.blocks[dim.dxf.geometry] if e.dxftype() in ('TEXT','MTEXT'))
        if stretch:assert abs(float(label(after,actual))-round(expectation['measurement']))<1e-6
        else:assert label(after,actual)==label(baseline,original)
        legacy_row=next((row for row in legacy if row['dimension_handle']==handle),None)
        if legacy_row:
            binding=source_binding(actual)
            assert binding['status']=='verified_source_points' and binding['association_ref']==legacy_row['association_ref'] and binding['source_refs']==[args.polyline_handle]
        if stretch and abs(actual.get_measurement()-original.get_measurement())>1e-6:
            metrics=evidence['native_text_heights'][handle]
            visual=verify_horizontal_stretch(original,actual,before_text_height=metrics['before'],after_text_height=metrics['after'])
        elif stretch:
            shift=[y-x for x,y in zip(a['defpoint2'],b['defpoint2'])]
            visual=verify_translation(original,actual,shift)
        else:visual=verify_translation(original,actual,delta)
        checks.append(dict(handle=handle,measurement=actual.get_measurement(),rendered_text=label(after,actual),visual_verification=visual))
    evidence.update(independent_dxf_readback=True,dimension_checks=checks)
    if stretch:evidence.update(source_width_mm=stretch['source_width_mm'],target_width_mm=stretch['target_width_mm'],test_assumptions=stretch['test_assumptions'],mechanical_group_complete=False,binding_review=stretch['binding_review'])
    storage.write_json(output/'poly-dim-receipt.json',evidence)
    print(json.dumps(dict(status=evidence['status'],output=str(output),dimension_count=len(checks),output_hash=evidence['output_sha256'],source_unchanged=True,customer_revision_created=False)))
    return 0


if __name__=='__main__':raise SystemExit(main())
