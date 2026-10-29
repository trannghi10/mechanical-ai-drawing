"""Export a synthetic nested-perpendicular DIMASSOC edit through native AutoCAD."""
import argparse,json,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    import ezdxf
    from backend.services import catalog_service as storage,aps_jobs
    from cad.edit_engine import apply_patch,digest
    from cad.dimension_associations import source_binding,verify
    from scripts.dimassoc_perpendicular_fixture import make_fixture,width_operations
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--anchor-dy',type=float,default=0);args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    if (output/'started.json').exists():raise ValueError('Inspect the saved native jobs before reusing this directory.')
    doc,profile,dim,assoc=make_fixture();fixture=output/'source.dxf';doc.saveas(fixture)
    with fixture.open('rb') as stream:state=storage.create_document('synthetic-dimassoc-perpendicular-'+uuid.uuid4().hex[:8]+'.dxf',stream,read_backend_override='autocad')
    document_id=state['id'];storage.write_json(output/'started.json',state);deadline=time.monotonic()+300
    while state['status'] not in ('ready','failed'):
        if time.monotonic()>deadline:raise RuntimeError('Import remains active: '+document_id)
        time.sleep(1);state=storage.read_status(document_id)
    assert state['status']=='ready',state
    folder=storage.folder(document_id);source=folder/state['dxf'];before=ezdxf.readfile(source)
    assert before.units==4,'Native fixture must remain in millimeters'
    old_hash=digest(source);original_hash=digest(folder/'original.dxf')
    native_profile=before.entitydb[profile.dxf.handle];native_dim=before.entitydb[dim.dxf.handle]
    baseline=source_binding(native_dim);assert baseline['status']=='verified_source_points',baseline
    assert baseline['points'][1]['osnap_type']==8 and baseline['points'][1].get('last_point_ref')
    edited=folder/'perpendicular-edited.dxf';ops=width_operations(native_profile,native_dim,anchor_dy=args.anchor_dy)
    patch=apply_patch(source,edited,ops,{profile.dxf.handle,dim.dxf.handle},old_hash);storage.write_json(output/'patch.json',patch)
    job=aps_jobs.start(document_id,provider='autocad',mode='convert',source=edited,expected_source_hash=digest(edited))
    storage.write_json(output/'export-started.json',job);aps_jobs.wait(document_id,job['id'],timeout=300)
    readback=aps_jobs.artifact(document_id,job['id'],'roundtrip.dxf');dwg=aps_jobs.artifact(document_id,job['id'],'modified.dwg')
    after=ezdxf.readfile(readback);actual=after.entitydb[dim.dxf.handle]
    assert after.units==4,'Native DWG readback changed fixture units'
    assert abs(actual.get_measurement()-95)<1e-6
    verify(after,patch['native_associations'])
    binding=source_binding(actual)
    assert binding['status']=='verified_source_points' and binding['points'][1]['osnap_type']==8 and binding['points'][1].get('last_point_ref')
    assert digest(source)==old_hash and digest(folder/'original.dxf')==original_hash
    report=dict(status='validated_nested_perpendicular_dimassoc',document_id=document_id,import_job_id=state['native_import_job_id'],export_job_id=job['id'],
        source_hash=old_hash,original_hash=original_hash,output_hash=digest(dwg),output=str(dwg),profile_handle=profile.dxf.handle,dimension_handle=dim.dxf.handle,
        dimension_mm=actual.get_measurement(),anchor_delta_y=args.anchor_dy,drawing_units='Millimeters',binding=binding,source_unchanged=True,customer_revision_created=False,complete_product_backup=False)
    storage.write_json(output/'receipt.json',report);print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()
