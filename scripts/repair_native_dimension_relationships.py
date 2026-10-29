"""Native DIMREASSOCIATE on a private DWG copy, then verify source bindings."""
import argparse,json,os,shutil,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    import ezdxf
    from backend.services import autocad_host,catalog_service as storage
    from cad.edit_engine import digest
    from cad.geometry import snapshot,near
    from cad.dimension_associations import source_binding
    from cad.dimension_visuals import verify_translation
    from cad.relationship_repairs import legacy_endpoint_proposals
    from scripts.probe_native_polyline_dimensions import inspection_group
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('document_id');parser.add_argument('polyline_handle');parser.add_argument('--inspection-job',required=True)
    parser.add_argument('--control-only',action='store_true');parser.add_argument('--control-evidence',type=Path)
    parser.add_argument('--native-heads',action='store_true');parser.add_argument('--subentity-evidence',type=Path)
    parser.add_argument('--migrate-native-to-dimassoc',action='store_true',help='Explicit private-copy migration: replace old native association storage with two-point DIMASSOC.')
    parser.add_argument('--restore-native-b',action='store_true',help='Experimental: restore existing native B objects after adding legacy A association.')
    args=parser.parse_args();source=storage.folder(args.document_id)/'original.dwg';source_hash=digest(source)
    if args.native_heads or args.migrate_native_to_dimassoc or args.restore_native_b:
        parser.error('Native head repair is disabled: current managed API cannot preserve both endpoint bindings after save/reopen. Use read-only native-head inspection; original and existing revisions remain unchanged.')
    baseline,group=inspection_group(args.document_id,args.inspection_job,args.polyline_handle,source_hash)
    plan=legacy_endpoint_proposals(baseline,group);plan['source_sha256']=source_hash
    if args.migrate_native_to_dimassoc and (not args.native_heads or args.control_only):parser.error('Migration requires --native-heads and cannot be a control')
    if args.restore_native_b and not args.migrate_native_to_dimassoc:parser.error('Native B restoration requires explicit migration experiment')
    if args.native_heads:
        if not args.subentity_evidence:parser.error('--native-heads requires --subentity-evidence')
        from cad.native_head_repairs import propose
        group['source_sha256']=source_hash
        plan=propose(baseline,group,json.loads(args.subentity_evidence.read_text(encoding='utf-8-sig')));plan['source_sha256']=source_hash
        if args.migrate_native_to_dimassoc:plan['migrate_native_to_dimassoc']=True
        if args.restore_native_b:
            report=json.loads(args.subentity_evidence.read_text(encoding='utf-8-sig'))
            handles=[]
            for action in group['native_actions']:
                handles.extend([action['action_handle'],action['body_handle'],action['geometry_dependency'],action['dimension_dependency']])
            handles.extend(row['handle'] for tree in report['action_parameters'] for row in tree['rows'])
            plan.update(restore_native_b=True,native_restore_handles=list(dict.fromkeys(handles)))
    if args.control_only and args.control_evidence:parser.error('Control cannot consume another control')
    if args.control_only:plan['control_only']=True
    if args.control_evidence:
        control=json.loads((args.control_evidence/'repair-receipt.json').read_text())
        assert control['source_sha256']==source_hash and control['control_only'] is True
        assert control['output_sha256']==digest(args.control_evidence/'relationship-repair.dwg')
        plan['control_outside_diff']=json.loads((args.control_evidence/'relationship-repair-outside-diff.json').read_text())
    token=uuid.uuid4().hex[:8];run=ROOT/'storage/acwork'/('relationship-repair-'+token);output=ROOT/'storage/validation-fixtures'/('relationship-repair-'+token)
    run.mkdir();output.mkdir();host=autocad_host.ready()
    shutil.copyfile(source,run/'input.dwg');shutil.copytree(host['bundle'],run/'MechanicalCad.Local.bundle')
    storage.write_json(run/'relationship-repair.json',plan);storage.write_json(output/'relationship-repair.json',plan)
    plugin=run/'MechanicalCad.Local.bundle/Contents/MechanicalCad.Local.dll'
    script=run/'repair.scr';script.write_text('_.SETVAR\nTRUSTEDPATHS\n'+plugin.parent.as_posix()+'\n_.SETVAR\nSECURELOAD\n2\n_.NETLOAD\n'+plugin.as_posix()+'\nMECHANICALREPAIRRELATIONSHIPS\n_.QUIT\n_N\n',encoding='utf8')
    environment={k:v for k,v in os.environ.items() if k not in ('DATABASE_URL','PG_ADMIN_PASSWORD','PGPASSWORD','APS_CLIENT_SECRET','GEMINI_API_KEY','OPENAI_API_KEY')}
    if host.get('dotnet_root'):environment.update(DOTNET_ROOT=host['dotnet_root'],DOTNET_ROOT_X64=host['dotnet_root'])
    with autocad_host._engine_lock:
        with (output/'console.log').open('wb') as log:
            completed=subprocess.run([host['core'],'/i',str(run/'input.dwg'),'/s',str(script),'/isolate','MechanicalRelationshipRepair',str(run/'profile'),'/language','en-US'],cwd=run,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=environment)
    assert digest(source)==source_hash
    for name in ('relationship-repair-error.json','relationship-repair-stage.json','relationship-repair-native.json','relationship-repair-outside-diff.json','relationship-repair-dim-properties.json','relationship-native-head-state.json','poly-dim-current.json'):
        if (run/name).exists():shutil.copyfile(run/name,output/name)
    native=output/'relationship-repair-native.json';error=output/'relationship-repair-error.json'
    if completed.returncode or error.exists() or not native.exists():
        summary=dict(status='failed_relationship_repair_probe',source_unchanged=True,customer_revision_created=False,output=str(output),
            error=json.loads(error.read_text()) if error.exists() else dict(returncode=completed.returncode),candidate_dwg_created=(run/'relationship-repair.dwg').exists())
        storage.write_json(output/'repair-summary.json',summary);print(json.dumps(summary));return 2
    receipt=json.loads(native.read_text());assert receipt['source_sha256']==source_hash and receipt['output_sha256']==digest(run/'relationship-repair.dwg')
    after=ezdxf.readfile(run/'relationship-repair.dxf');checks=[]
    assert near(snapshot(baseline.entitydb[args.polyline_handle]),snapshot(after.entitydb[args.polyline_handle]),1e-6)
    repaired={r['dimension_handle']:r for r in plan['repairs']}
    for handle in group['dimension_handles']:
        before=baseline.entitydb[handle];actual=after.entitydb[handle]
        visual=verify_translation(before,actual,[0,0,0]);binding=source_binding(actual)
        if handle in repaired and not args.control_only:
            proposal=repaired[handle]
            if args.native_heads and (not args.migrate_native_to_dimassoc or args.restore_native_b):
                from cad.native_head_repairs import hybrid_binding
                binding=hybrid_binding(actual,proposal['dimension_dependency'])
            assert binding and binding['status']=='verified_source_points' and binding['source_refs']==[args.polyline_handle],binding
            expected={'defpoint2':proposal['a_vertex']} if args.native_heads and (not args.migrate_native_to_dimassoc or args.restore_native_b) else {'defpoint2':proposal['a_vertex'],'defpoint3':proposal['b_vertex']}
            assert {p['dimension_field']:p['vertex_index'] for p in binding['points']}==expected,binding
        else:assert binding==source_binding(before)
        checks.append(dict(dimension_handle=handle,binding=binding,visual_verification=visual))
    # Compare exact exported tags, including OLE binary payload, against the
    # independently regenerated no-op control for every outside changed entity.
    if args.control_evidence:
        from cad.ole_control import compare_exported_entity
        control_doc=ezdxf.readfile(args.control_evidence/'relationship-repair.dxf')
        raw_checks=[]
        for change in plan['control_outside_diff']['changed']:
            handle=change['handle']
            comparison=compare_exported_entity(control_doc.entitydb[handle],after.entitydb[handle])
            raw_checks.append(dict(handle=handle,type=after.entitydb[handle].dxftype(),**comparison))
        receipt['outside_raw_control_checks']=raw_checks
    for name in ('relationship-repair.dwg','relationship-repair.dxf'):shutil.copyfile(run/name,output/name)
    receipt.update(status='validated_noop_control' if args.control_only else 'validated_relationship_repair_proposal',dimension_checks=checks,independent_dxf_readback=True,
        repaired_endpoint_count=0 if args.control_only else 2,design_intent_confirmed=False,proposal_only=True,source_unchanged=True)
    receipt['native_heads_repaired']=bool(args.native_heads and not args.control_only)
    storage.write_json(output/'repair-receipt.json',receipt)
    print(json.dumps(dict(status=receipt['status'],output=str(output),repaired_endpoint_count=receipt['repaired_endpoint_count'],source_unchanged=True,customer_revision_created=False)));return 0


if __name__=='__main__':raise SystemExit(main())
