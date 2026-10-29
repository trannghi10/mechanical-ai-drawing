"""Read-only tube rule audit on existing company DXFs; no native execution.

Source DWGs, ownership reports and conversion provenance are retained. A plan
for one measured detail never certifies other assembly views or file release.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def records_for(source,frame):
    from backend.services.change_service import context_for
    # The same production traversal as planning: block children keep their
    # exact instance path, placement and native dimension precision.
    return [e for e in context_for(source,[frame])['entities']
            if e['type'] in ('LINE','ARC','LWPOLYLINE','DIMENSION') and e.get('geometry')
            and (e['type']!='DIMENSION' or e.get('dimension_type',0) in (0,1))]


def main():
    from cad.catalog import load_document
    from cad.edit_engine import digest
    from cad.tube_stock import parse
    from backend.services.tube_planner import wall_operations
    from cad.frame_geometry import transform,world
    from cad.geometry import near
    from ezdxf.math import Matrix44
    import math
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    sources=[('51ec94944c4443b19fb8d5bd7930a6dd','c756444e398e47c8a0085c205a56b730'),
             ('1c7d831296ff402bb1a838479063a99d','93f393d98f124ae1ae9d6a71e9572ce2'),
             ('baf461e9c2764a5ba9000a48772f846c','0c1da0c6a58940868336f5a3f57a63f1')]
    report=dict(status='read_and_plan_only',cloud_used=False,native_save_reopen=False,production_release=False,
                sources=[],cases=[])
    for did,aid in sources:
        folder=ROOT/'storage/documents'/did;status=json.loads((folder/'status.json').read_text(encoding='utf8'))
        atlas=json.loads((folder/'document-atlas'/aid/'report.json').read_text(encoding='utf8'))
        dxf=folder/status['dxf'];before=digest(dxf);dwg_hash=digest(folder/'original.dwg')
        if before!=atlas['source_hash']:raise ValueError('Corpus atlas source changed: '+did)
        frames={f['id']:f for f in atlas['frames']}
        source=dict(document_id=did,filename=status['filename'],source_sha256=dwg_hash,dxf_sha256=before,read_backend=status.get('read_backend','legacy_oda'))
        report['sources'].append(source)
        for part in atlas['parts']:
            if part.get('definition_conflict'):continue
            for description in part.get('descriptions',[]):
                values=re.findall(r'\d+(?:[.,]\d+)?',description)
                stocks={s.raw:s for value in values for s in [parse(description,float(value.replace(',','.')))] if s}
                if len(stocks)!=1:continue
                stock=next(iter(stocks.values()));new=round(stock.wall*.8,6)
                for sid in part.get('detail_sheet_ids',[]):
                    if sid not in frames:continue
                    row=dict(document_id=did,part_code=part['part_code'],sheet_id=sid,source_spec=stock.raw,
                             source_wall_mm=stock.wall,probe_target_wall_mm=new,engineering_intent_confirmed=False)
                    try:
                        records=records_for(dxf,frames[sid]);operations=wall_operations(records,stock.wall,new)
                        canonical=[world(e) for e in records]
                        baseline=wall_operations(canonical,stock.wall,new)
                        by_ref={e['ref']:e for e in records};baseline_by_ref={o.ref:o for o in baseline}
                        if {o.ref for o in operations}!=baseline_by_ref.keys() or any(
                            not near(world(dict(by_ref[o.ref],geometry=json.loads(o.after)))['geometry'],json.loads(baseline_by_ref[o.ref].after),1e-6)
                            for o in operations):raise ValueError('Local and layout operation coordinates mismatch')
                        # Check equivariance of real source geometry. These are
                        # transformed derivatives, never extra company files.
                        rotations=[]
                        for degrees in (0,37,90):
                            matrix=Matrix44.z_rotate(math.radians(degrees)) @ Matrix44.translate(1234,-5678,0)
                            turned=[dict(e,geometry=transform(e['type'],e['geometry'],matrix)) for e in canonical]
                            actual=wall_operations(turned,stock.wall,new)
                            expected={o.ref:transform(by_ref[o.ref]['type'],json.loads(o.after),matrix) for o in baseline}
                            if {o.ref for o in actual}!=expected.keys() or any(not near(json.loads(o.after),expected[o.ref],1e-6) for o in actual):
                                raise ValueError('Rotated source geometry mismatch')
                            rotations.append(dict(angle_degrees=degrees,passed=True,transformed_derivative=True))
                        row.update(status='measured_detail_plan_verified',operation_count=len(operations),operations=[o.model_dump() for o in operations],rotation_checks=rotations)
                    except ValueError as error:row.update(status='unsupported_detail',reason=str(error))
                    report['cases'].append(row)
        source['original_unchanged']=digest(folder/'original.dwg')==dwg_hash and digest(dxf)==before
        print(json.dumps(dict(document_id=did,filename=status['filename'],cases=sum(r['document_id']==did for r in report['cases']))),flush=True)
    report['planned_detail_count']=sum(r['status']=='measured_detail_plan_verified' for r in report['cases'])
    report['unsupported_detail_count']=sum(r['status']=='unsupported_detail' for r in report['cases'])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:report[k] for k in ('status','planned_detail_count','unsupported_detail_count')}),flush=True)


if __name__=='__main__':main()
