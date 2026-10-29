"""Company wall regression: HTTP preview, full DWG, independent native import.

The proposed wall value is a regression experiment, not engineer approval.
Full product coverage and publishing gates remain enforced by the application.
"""
import argparse
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.verify_company_whole_file import api,require_local,wait_document,save,audit_outside
from cad.edit_engine import digest


def verify(run,after_path):
    import ezdxf
    from cad.geometry import snapshot,near
    from cad.nested_scope_export import mapped_ref,path_entity
    from cad.table_data import table_cells
    from cad.frame_geometry import world
    from backend.services.change_service import context_for
    from backend.services import catalog_service as storage
    folder=storage.folder(run['document_id'])
    revision=json.loads((folder/'revisions'/run['revision_id']/'revision.json').read_text(encoding='utf8'))
    proposal=json.loads((folder/'change-plans'/(run['plan_id']+'.json')).read_text(encoding='utf8'))
    source=folder/storage.read_status(run['document_id'])['dxf']
    before=ezdxf.readfile(source);after=ezdxf.readfile(after_path)
    from backend.services.revision_service import verify_cloned_geometry
    modified=ezdxf.readfile(folder/'revisions'/run['revision_id']/'modified.dxf')
    verify_cloned_geometry(modified,after,revision['validation'])
    operations=proposal['checked_preview_plan']['operations'] if run['partial_preview'] else proposal['plan']['operations']
    mapping=revision['validation'].get('block_isolation',[])
    ref=lambda r:mapped_ref(r,mapping)
    geometry=[];bom=[];cells=table_cells(after_path)
    for op in operations:
        if op['action']=='replace_geometry':
            actual=path_entity(after,ref(op['ref']))
            if not near(snapshot(actual),json.loads(op['after']),1e-6):raise ValueError('Saved geometry mismatch: '+op['ref'])
            geometry.append(dict(ref=op['ref'],after_ref=ref(op['ref']),type=actual.dxftype()))
        elif op['action']=='table_cell':
            from bom.reader import plain
            actual=next(c for c in cells[op['ref']] if c['index']==op['cell_index'])['raw_text']
            if plain(actual)!=plain(op['after']):raise ValueError('Saved native BOM mismatch')
            bom.append(dict(ref=op['ref'],cell_index=op['cell_index'],value=plain(actual)))
        elif op['action']=='replace_text':
            from cad.catalog import text_of
            from bom.reader import plain
            if plain(text_of(path_entity(after,ref(op['ref']))))!=plain(op['after']):raise ValueError('Saved annotation mismatch')
        else:raise ValueError('Oracle has not been implemented for '+op['action'])
    roots=[t for t in proposal['targets'] if t['id'] in proposal['root_target_ids']]
    context=context_for(source,roots);records={e['ref']:e for e in context['entities']}
    section_ops=[o for o in operations if o['action']=='replace_geometry' and path_entity(before,o['ref']).dxftype()=='LWPOLYLINE']
    if len(section_ops)!=1:raise ValueError('A unique physical tube section is required')
    section=section_ops[0]['ref'];original=snapshot(path_entity(before,section));actual=snapshot(path_entity(after,ref(section)))
    low=[min(p[i] for p in original['points']) for i in (0,1)];high=[max(p[i] for p in original['points']) for i in (0,1)]
    outer_low=[v+(-run['old_wall_mm']) for v in low];outer_high=[v+run['old_wall_mm'] for v in high]
    if not near([min(p[i] for p in actual['points']) for i in (0,1)],[v+run['new_wall_mm'] for v in outer_low],1e-6):raise ValueError('Physical inner minimum differs from measured outer wall')
    if not near([max(p[i] for p in actual['points']) for i in (0,1)],[v-run['new_wall_mm'] for v in outer_high],1e-6):raise ValueError('Physical inner maximum differs from measured outer wall')
    outer=[]
    for e in records.values():
        if e['type']!='LWPOLYLINE' or not e.get('geometry'):continue
        g=e['geometry']
        if near([min(p[i] for p in g['points']) for i in (0,1)],outer_low,1e-6) and near([max(p[i] for p in g['points']) for i in (0,1)],outer_high,1e-6):outer.append(e)
    if len(outer)!=1 or not near(snapshot(path_entity(before,outer[0]['ref'])),snapshot(path_entity(after,ref(outer[0]['ref']))),1e-6):raise ValueError('Outer section is not uniquely preserved')
    dimension_ops=[o for o in operations if o['action']=='replace_geometry' and path_entity(before,o['ref']).dxftype()=='DIMENSION']
    if len(dimension_ops)!=1:raise ValueError('Expected one true wall DIM')
    wall_dim=path_entity(after,ref(dimension_ops[0]['ref']))
    if abs(abs(wall_dim.get_measurement())-run['new_wall_mm'])>1e-6:raise ValueError('Actual DIM did not change')
    from cad.dimensions import matches_displayed_nominal
    # Preserve exact measured length, including the source CAD residual.
    lengths=[]
    for e in records.values():
        if not matches_displayed_nominal(e,run['source_nominal_length_mm']):continue
        a=path_entity(before,e['ref']);b=path_entity(after,ref(e['ref']))
        if abs(a.get_measurement()-b.get_measurement())>1e-6:raise ValueError('Source length changed')
        lengths.append(dict(ref=e['ref'],actual_mm=abs(b.get_measurement()),nominal_mm=run['source_nominal_length_mm']))
    if not lengths:raise ValueError('No source-measured length survived')
    changed_roots={o['ref'].split('/')[0] for o in operations if '/' in o['ref']}
    changed={o['ref'] for o in operations};preserved=0
    for e in records.values():
        if e['ref'] in changed or e['ref'].split('/')[0] not in changed_roots or not e.get('geometry'):continue
        if not near(snapshot(path_entity(before,e['ref'])),snapshot(path_entity(after,ref(e['ref']))),1e-6):raise ValueError('Unedited member of changed block moved')
        preserved+=1
    inventory_before={(l.name,e.dxf.handle,e.dxftype()) for l in before.layouts for e in l}
    inventory_after={(l.name,e.dxf.handle,e.dxftype()) for l in after.layouts for e in l}
    if inventory_before!=inventory_after:raise ValueError('Full document inventory changed')
    outside=audit_outside(before,after,operations)
    if not outside['passed']:raise ValueError('Untouched source changed: '+str(outside['failures'][:5]))
    validation=revision['dwg_validation'];ole=None
    if validation.get('input_normalization'):
        from cad.empty_ole import verify as verify_ole
        ole=verify_ole(before,after,validation['input_normalization'])
    return dict(geometry=geometry,wall_dimension_mm=abs(wall_dim.get_measurement()),outer_section_unchanged=True,
                exact_source_lengths=lengths,native_bom=bom,untouched_block_members=preserved,
                full_document_layout_inventory=len(inventory_after),outside=outside,ole_integrity=ole)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('job_file',type=Path);args=parser.parse_args()
    args.job_file=args.job_file.resolve()
    require_local()
    job=json.loads(args.job_file.read_text(encoding='utf8'));did=job['document_id']
    base=args.job_file.parent/('native-'+job['id'][:12]);base.mkdir(exist_ok=True);manifest=base/'run.json'
    from backend.services import catalog_service as storage
    folder=storage.folder(did);state=storage.read_status(did)
    source=folder/state['dxf'];original=folder/'original.dwg'
    run=json.loads(manifest.read_text(encoding='utf8')) if manifest.exists() else dict(status='running',document_id=did,
        planning_job_id=job['id'],source_sha256=digest(original),dxf_sha256=digest(source),company_dwg=True,synthetic=False,
        engineering_intent_confirmed=False,old_wall_mm=1.2,new_wall_mm=1,source_nominal_length_mm=347.5,
        cloud_used=False,production_release=False,complete_product_backup=False,engineer_accepted=False)
    save(manifest,run)
    deadline=time.monotonic()+900
    while time.monotonic()<deadline:
        job=api('GET',f'/documents/{did}/planning-jobs/{job["id"]}')
        if job['status'] not in ('queued','running'):break
        time.sleep(2)
    if job['status']!='ready':raise ValueError(job)
    plan=api('GET',f'/documents/{did}/change-plans/{job["plan_id"]}')
    if plan['planner']!='checked_tube_wall':raise ValueError('Source-checked wall compiler required')
    if plan['target_resolution']['part_codes']!=['8.1.05190.002']:raise ValueError('Wrong company detail')
    partial=not plan['execution_available']
    if partial and not plan.get('preview_execution_available'):raise ValueError(plan['plan']['questions'])
    run.update(plan_id=plan['id'],partial_preview=partial,remaining_questions=plan['plan']['questions'])
    save(manifest,run)
    if not run.get('revision_id'):
        route='/apply-checked-preview' if partial else '/apply'
        revision=api('POST',f'/documents/{did}/change-plans/{plan["id"]}'+route,**({} if partial else dict(json=dict(preview_only=True))))
        run['revision_id']=revision['id'];save(manifest,run)
    rev=f'/documents/{did}/revisions/{run["revision_id"]}'
    if not run.get('export_job_id'):
        export=api('POST',rev+'/exports',json=dict(format='dwg',scope='document',preview=True))
        run['export_job_id']=export['id'];save(manifest,run)
    deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        export=api('GET',rev+'/exports/'+run['export_job_id'])
        if export['status'] in ('ready','failed'):break
        time.sleep(2)
    if export['status']!='ready':raise ValueError(export)
    import requests
    response=requests.get('http://127.0.0.1:8765'+export['download_url'],timeout=120);response.raise_for_status()
    output=base/'after.dwg';output.write_bytes(response.content)
    run.update(output=str(output.relative_to(ROOT)),output_sha256=digest(output));save(manifest,run)
    run['native_save_reopen']=verify(run,folder/'revisions'/run['revision_id']/'reopen/modified.dxf');save(manifest,run)
    if not run.get('reopened_document_id'):
        with output.open('rb') as stream:uploaded=api('POST','/documents',files={'file':('DAUPHINE-WALL-REGRESSION.dwg',stream,'application/octet-stream')})
        run['reopened_document_id']=uploaded['id'];save(manifest,run)
    again=wait_document(run['reopened_document_id']);again.update(auxiliary=True,company_regression=True);storage.write_json(storage.folder(again['id'])/'status.json',again)
    if digest(storage.folder(again['id'])/'original.dwg')!=run['output_sha256']:raise ValueError('Independent source hash mismatch')
    run['independent_native_open']=verify(run,storage.folder(again['id'])/again['dxf'])
    run['source_unchanged']=digest(source)==run['dxf_sha256'] and digest(original)==run['source_sha256']
    if not run['source_unchanged']:raise ValueError('Company source changed')
    run['status']='passed';run.pop('last_error',None);save(manifest,run)
    print(json.dumps(dict(status='passed',manifest=str(manifest.relative_to(ROOT)),revision_id=run['revision_id'],independent_native_open=True)),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        if len(sys.argv)==2:
            job_file=Path(sys.argv[1]).resolve()
            if job_file.is_file() and job_file.is_relative_to(ROOT/'storage/validation-fixtures'):
                job=json.loads(job_file.read_text(encoding='utf8'))
                manifest=job_file.parent/('native-'+job['id'][:12])/'run.json'
                if manifest.is_file():
                    run=json.loads(manifest.read_text(encoding='utf8'));run.update(status='failed',last_error=str(error));save(manifest,run)
        raise
