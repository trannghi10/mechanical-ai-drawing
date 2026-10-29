"""Package verified private reference repair and eight independent challenges."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from cad.edit_engine import digest
    from cad.native_point_reference_validation import validate_inventory
    from cad.native_head_repairs import hybrid_binding
    from cad.dimension_visuals import verify_translation
    from cad.ole_control import compare_exported_entity
    from cad.dimension_associations import source_binding
    from cad.native_point_reference_scope import validate_scope,result_bindings,outside_content_handles
    import ezdxf
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--first-challenge',type=Path,required=True)
    args=parser.parse_args();run=args.run.resolve()
    native=json.loads((run/'native-point-reference-customer.json').read_text())
    base=json.loads((run/'base-evidence.json').read_text())
    source=Path(base['dwg'])
    scope=validate_scope(base['scope']);targets={t['dimension_handle']:t for t in scope['repairs']}
    if digest(Path(base['dxf']))!=base['dxf_sha256']:raise ValueError('Base DXF changed')
    if digest(source)!=native['source_sha256'] or digest(run/'native-point-reference-repair.dwg')!=native['output_sha256']:
        raise ValueError('Source/output hash mismatch')
    if native['native_b_parameters_preserved'] is not True:raise ValueError('Native B evidence required')
    inventory=validate_inventory(json.loads((run/'native-point-reference-before.json').read_text()),
        json.loads((run/'native-point-reference-after.json').read_text()),scope['polyline_handle'],list(targets))
    baseline=ezdxf.readfile(base['dxf'])
    actual=ezdxf.readfile(run/'native-point-reference-repair.dxf');bindings={}
    legacy={}
    for handle in scope['legacy_handles']:
        old=source_binding(baseline.entitydb[handle]);new=source_binding(actual.entitydb[handle])
        if old!=new:raise ValueError('Existing legacy reference changed')
        if base.get('base_ready_revision') and (not new or new['status']!='verified_source_points' or len(new['points'])!=2):
            raise ValueError('Ready revision legacy two-endpoint binding not preserved')
        legacy[handle]=new
    bindings=result_bindings(actual,scope)
    visuals={h:verify_translation(baseline.entitydb[h],actual.entitydb[h],[0,0,0]) for h in scope['dimension_handles']}
    before_inventory=json.loads((run/'native-point-reference-before.json').read_text())
    outside={h:compare_exported_entity(baseline.entitydb[h],actual.entitydb[h]) for h in outside_content_handles(before_inventory,scope)}
    paths=[args.first_challenge]
    batch=json.loads((run/'challenge-batch.json').read_text())
    for row in batch:
        if row['returncode']!=0:raise ValueError('Failed dynamic challenge')
        paths.append(Path(json.loads(row['output'])['output']))
    challenges=[];coverage=set()
    for path in paths:
        receipt=json.loads((path/'challenge-receipt.json').read_text());config=json.loads((path/'relationship-challenge.json').read_text())
        if receipt['status']!='validated_repaired_dim_auto_follow' or receipt['source_sha256']!=native['output_sha256'] or receipt['dim_endpoint_writer_assigned'] or not receipt['save_reopen_verified']:
            raise ValueError('Dynamic challenge not independently validated')
        if digest(path/'relationship-challenge.dwg')!=receipt['output_sha256']:raise ValueError('Challenge DWG hash mismatch')
        if not config.get('native_point_reference_challenge'):raise ValueError('Native B challenge preservation gate missing')
        handle=receipt['dimension_handle'];vertex=config['vertex_index'];delta=config['delta']
        if handle not in bindings:raise ValueError('Unexpected challenged DIM')
        a,b=targets[handle]['a_vertex'],targets[handle]['b_vertex']
        if vertex not in [a,b] or abs(abs(receipt['after_measurement']-receipt['before_measurement'])-10)>1e-6:
            raise ValueError('Unexpected challenge movement')
        key=(handle,'A' if vertex==a else 'B',1 if receipt['after_measurement']>receipt['before_measurement'] else -1)
        if key in coverage:raise ValueError('Duplicate challenge coverage')
        coverage.add(key);challenges.append(dict(dimension=handle,endpoint=key[1],step=key[2]*10,
            measurement=receipt['after_measurement'],evidence=str(path.resolve()),dwg_sha256=receipt['output_sha256'],
            receipt_sha256=digest(path/'challenge-receipt.json')))
    expected={(h,e,s) for h in bindings for e in ['A','B'] for s in [-1,1]}
    if coverage!=expected:raise ValueError('Eight A/B positive/negative challenges required')
    output=ROOT/'storage/validation-fixtures'/('native-point-reference-validated-'+run.name.rsplit('-',1)[-1])
    output.mkdir(exist_ok=False)
    shutil.copyfile(run/'native-point-reference-repair.dwg',output/'native-dim-links-verified.dwg')
    shutil.copyfile(run/'native-point-reference-repair.dxf',output/'native-dim-links-verified.dxf')
    report=dict(native,status='verified_private_native_dim_reference_repair',adapter='ObjectARX DIMASSOC references with original native B action retained',
        bindings=bindings,scope=scope,base=base,legacy_bindings=legacy,inventory_audit=inventory,dimension_visuals=visuals,outside_15_checks=outside,challenges=challenges,
        native_b_dynamic_challenges_passed=True,source_unchanged=True,design_intent_confirmed=False,
        customer_revision_created=False,revision_integration_complete=False,original_evidence=str(run),
        artifact_sha256={p.name:digest(p) for p in output.iterdir() if p.is_file()},
        evidence_sha256={n:digest(run/n) for n in ['native-point-reference-customer.json','native-point-reference-before.json','native-point-reference-after.json']})
    (output/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(status=report['status'],challenges=len(challenges),outside_checked=inventory['unselected_entries_checked'],output=str(output))))


if __name__=='__main__':main()
