"""Run synthetic smoke or a proposal-scoped ObjectARX repair on a private copy."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--customer-copy',action='store_true',help='Bounded private probe of the hash-checked two native DIMs; never a revision.')
    parser.add_argument('--proposal-id',help='Hash-checked native proposal defining the executable scope.')
    parser.add_argument('--base-ready-revision',action='store_true',help='Use the existing hash-checked ready legacy repair as base.')
    parser.add_argument('--document-id',default='51ec94944c4443b19fb8d5bd7930a6dd')
    parser.add_argument('--base-revision-id',default='fc3037b7d2bc4588ad3c0df9b15e2494')
    args=parser.parse_args()
    if args.base_ready_revision and not args.customer_copy:parser.error('Ready revision requires customer-copy mode')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=True, encoding='utf-8-sig')
    from backend.services import autocad_host,catalog_service
    from cad.dimension_associations import source_binding
    from cad.edit_engine import digest
    import ezdxf
    bridge = ROOT / 'autodesk/NativePointReference/build/MechanicalPointReference.dll'
    if not bridge.is_file():
        raise RuntimeError('Build the ObjectARX bridge with scripts/build_native_point_reference.ps1 first')
    host = autocad_host.ready()
    run = ROOT / 'storage/acwork' / ('point-reference-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    shutil.copyfile(host['bootstrap_path'], run / 'bootstrap.dwg')
    shutil.copytree(host['bundle'], run / 'MechanicalCad.Local.bundle')
    shutil.copyfile(bridge, run / bridge.name)
    source=None
    if args.customer_copy:
        if not args.proposal_id:parser.error('Customer copy requires --proposal-id')
        from backend.services.relationship_repair_service import read,_native_base
        proposal,_=read(args.document_id,args.proposal_id)
        if proposal.get('schema_version')!=3 or proposal.get('adapter')!='native_pointrefs':raise ValueError('Evidence-derived native proposal required')
        revision,base=_native_base(args.document_id,proposal['base']['revision_id'],proposal['source_sha256'])
        source=revision/'modified.dwg';base_dxf=revision/'modified.dxf';source_hash=digest(source)
        scope=proposal['plan']['execution_scope']
        shutil.copyfile(source,run/'input.cad')
        (run/'native-point-reference.json').write_text(json.dumps(dict(source_sha256=source_hash,scope=scope)),encoding='utf8')
        (run/'base-evidence.json').write_text(json.dumps(dict(dwg=str(source),dxf=str(base_dxf),dwg_sha256=source_hash,dxf_sha256=digest(base_dxf),base_ready_revision=True,scope=scope,document_id=args.document_id,proposal_id=args.proposal_id)),encoding='utf8')
    plugin = run / 'MechanicalCad.Local.bundle/Contents/MechanicalCad.Local.dll'
    script = run / 'smoke.scr'
    script.write_text('_.SETVAR\nTRUSTEDPATHS\n' + plugin.parent.as_posix() + ';' + run.as_posix()
                      + '\n_.SETVAR\nSECURELOAD\n2\n_.NETLOAD\n' + plugin.as_posix()
                      + ('\nMECHANICALPOINTREFCUSTOMERPROBE' if args.customer_copy else '\nMECHANICALPOINTREFSMOKE')
                      + '\n_.QUIT\n_Y\n', encoding='utf8')
    environment = {k:v for k,v in os.environ.items() if k not in
                   ('DATABASE_URL','PG_ADMIN_PASSWORD','PGPASSWORD','APS_CLIENT_SECRET','GEMINI_API_KEY','OPENAI_API_KEY')}
    if host.get('dotnet_root'):
        environment.update(DOTNET_ROOT=host['dotnet_root'], DOTNET_ROOT_X64=host['dotnet_root'])
    with autocad_host._engine_lock, (run / 'console.log').open('wb') as log:
        result = subprocess.run([host['core'], '/i', str(run / 'bootstrap.dwg'), '/s', str(script),
                                 '/isolate', 'MechanicalPointReference', str(run / 'profile'), '/language', 'en-US'],
                                cwd=run, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                env=environment, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    error = run / 'native-point-reference-error.json'
    if source is not None and digest(source)!=source_hash:raise RuntimeError('Source changed during private probe')
    receipt_path = run / ('native-point-reference-customer.json' if args.customer_copy else 'native-point-reference-smoke.json')
    if result.returncode or error.exists() or not receipt_path.is_file():
        raise RuntimeError('Point-reference smoke failed; inspect ' + str(run))
    receipt = json.loads(receipt_path.read_text(encoding='utf8'))
    if args.customer_copy:
        from cad.native_head_repairs import hybrid_binding
        from cad.native_point_reference_validation import validate_inventory
        from cad.dimension_visuals import verify_translation
        from cad.ole_control import compare_exported_entity
        dxf=ezdxf.readfile(run/'native-point-reference-repair.dxf');bindings={}
        from cad.native_point_reference_scope import result_bindings,outside_content_handles
        bindings=result_bindings(dxf,scope)
        before_inventory=json.loads((run/'native-point-reference-before.json').read_text())
        inventory_audit=validate_inventory(before_inventory,json.loads((run/'native-point-reference-after.json').read_text()),scope['polyline_handle'],[t['dimension_handle'] for t in scope['repairs']])
        original=ezdxf.readfile(base_dxf)
        for h in scope['legacy_handles']:
            if source_binding(original.entitydb[h])!=source_binding(dxf.entitydb[h]):raise RuntimeError('Existing legacy binding changed')
        visuals={h:verify_translation(original.entitydb[h],dxf.entitydb[h],[0,0,0]) for h in scope['dimension_handles']}
        outside={h:compare_exported_entity(original.entitydb[h],dxf.entitydb[h]) for h in outside_content_handles(before_inventory,scope)}
        receipt.update(status='private_native_point_references_saved_reopened_verified',bindings=bindings,scope=scope,polyline_handle=scope['polyline_handle'],
                       bridge_sha256=digest(bridge),native_b_dynamic_challenges_passed=False,customer_revision_created=False,
                       inventory_audit=inventory_audit,dimension_visuals=visuals,outside_15_checks=outside)
        (run/'validation.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
        print(json.dumps(dict(status=receipt['status'],evidence=str(run),native_b_dynamic_challenges_passed=False)))
        return
    dxf = ezdxf.readfile(run / 'native-point-reference-smoke.dxf')
    binding = source_binding(dxf.entitydb[receipt['dimension_handle']])
    if binding['status'] != 'verified_source_points' or binding['source_refs'] != [receipt['polyline_handle']]:
        raise RuntimeError('Independent two-endpoint binding validation failed: ' + str(binding))
    receipt.update(status='synthetic_point_references_saved_reopened_verified', binding=binding,
                   bridge_sha256=digest(bridge), dwg_sha256=digest(run / 'native-point-reference-smoke.dwg'),
                   native_b_preservation_tested=False, customer_revision_created=False)
    (run / 'validation.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print(json.dumps(dict(status=receipt['status'], evidence=str(run), native_b_preservation_tested=False)))


if __name__ == '__main__':
    main()
