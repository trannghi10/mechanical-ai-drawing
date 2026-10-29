"""Attach four independently verified native-B-only challenges to a repair report."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import ezdxf
    from cad.native_head_repairs import hybrid_binding
    from cad.edit_engine import digest
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path);parser.add_argument('report',type=Path)
    parser.add_argument('--first-challenge',type=Path,required=True)
    args=parser.parse_args();report=json.loads(args.report.read_text());paths=[args.first_challenge]
    for row in json.loads((args.run/'native-b-isolation-batch.json').read_text()):
        if row['returncode']:raise ValueError('Native B isolation failed')
        paths.append(Path(json.loads(row['output'])['output']))
    targets={t['dimension_handle']:t for t in report['scope']['repairs']}
    rows=[];coverage=set()
    for path in paths:
        r=json.loads((path/'challenge-receipt.json').read_text())
        if r['source_sha256']!=report['output_sha256'] or r['status']!='validated_repaired_dim_auto_follow' or not r.get('native_b_isolated_from_legacy_b') or r['dim_endpoint_writer_assigned'] or not r['save_reopen_verified']:
            raise ValueError('Native B isolation receipt invalid')
        if digest(path/'relationship-challenge.dwg')!=r['output_sha256']:raise ValueError('Isolation DWG hash mismatch')
        handle=r['dimension_handle'];dep=targets[handle]['dimension_dependency']
        dxf=ezdxf.readfile(path/'relationship-challenge.dxf');binding=hybrid_binding(dxf.entitydb[handle],dep)
        if not binding or binding['status']!='verified_source_points' or len(binding['points'])!=1 or binding['points'][0]['dimension_field']!='defpoint2':
            raise ValueError('Redundant legacy B reference not removed')
        difference=r['after_measurement']-r['before_measurement']
        if abs(abs(difference)-10)>1e-6:raise ValueError('Unexpected native B movement')
        key=(handle,1 if difference>0 else -1)
        if key in coverage:raise ValueError('Duplicate B isolation case')
        coverage.add(key);rows.append(dict(dimension=handle,step=key[1]*10,evidence=str(path.resolve()),
            measurement=r['after_measurement'],receipt_sha256=digest(path/'challenge-receipt.json'),legacy_binding=binding))
    if coverage!={(h,s) for h in targets for s in [-1,1]}:raise ValueError('Four isolated native B challenges required')
    proof=dict(status='verified_original_native_b_independently_of_new_legacy_b',challenges=rows,
        challenge_bridge_sha256=digest(ROOT/'autodesk/NativePointReference/build/MechanicalPointReference.dll'),final_dwg_modified=False)
    target=args.report.parent/'native-b-isolation.json';target.write_text(json.dumps(proof,indent=2),encoding='utf8')
    report['native_b_isolation']=dict(status=proof['status'],challenge_count=4,evidence_sha256=digest(target))
    args.report.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(status=proof['status'],challenges=4,report=str(target),output=str(target.parent.resolve()))))


if __name__=='__main__':main()
