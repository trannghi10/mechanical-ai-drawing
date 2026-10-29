"""Source-bound native facts enrich planning without expanding the whole DWG prompt."""
import json
from pathlib import Path

from backend.services import catalog_service as storage
from backend.services import aps_jobs, aps_repository
from cad.edit_engine import digest


def attach(context,source,*,parameter_offset=None,record_refs=None):
    context.pop('aps_native',None)
    source=Path(source).resolve()
    try:
        relative=source.relative_to(storage.ROOT.resolve())
    except ValueError:return context
    if len(relative.parts)<2:return context
    document_id=relative.parts[0]
    status_path=storage.ROOT/document_id/'status.json'
    if not status_path.is_file():return context
    status=json.loads(status_path.read_text(encoding='utf8'))
    job_id=status.get('native_import_job_id')
    if not job_id or status.get('status')!='ready':return context
    try:
        job=aps_repository.read(document_id,job_id)
        if job['mode']!='inspect' or job['status']!='ready':return context
        readback=aps_jobs.artifact(document_id,job_id,'roundtrip.dxf')
        if digest(source)!=digest(readback):return context
        inventory=json.loads(aps_jobs.artifact(document_id,job_id,'inventory.json').read_text(encoding='utf-8-sig'))
    except (ValueError,FileNotFoundError):return context
    native={row['handle']:row for row in inventory['entities']}
    blocks={b['handle']:b for b in inventory.get('blocks',[])}
    records=[];matched=0
    for entity in context.get('entities',[]):
        path=entity['ref'].split('/')
        rows=[native.get(handle) for handle in path]
        if any(row is None for row in rows) or not rows[0].get('is_layout'):continue
        if any(child.get('owner_handle')!=parent.get('block_handle') for parent,child in zip(rows,rows[1:])):continue
        row=rows[-1]
        if row['type']!=entity['type']:continue
        matched+=1
        if row.get('parameters') or row.get('extension_records') or row.get('persistent_reactor_handles') or row.get('measurement') is not None:
            facts={key:row[key] for key in ('handle','type','owner_handle','native_class','measurement','parameters','extension_records','persistent_reactor_handles','extension_dictionary_handle') if key in row}
            facts['ref']=entity['ref']
            if len(path)>1:
                facts['nested_editable']=len(path)<=8 and all(not parent.get('dynamic') and not parent.get('attributes') and
                    parent.get('block_handle') in blocks and not blocks[parent['block_handle']].get('is_xref',False) for parent in rows[:-1])
            records.append(facts)
    records.sort(key=lambda row:not bool(row.get('parameters')))
    total_parameters=sum(bool(r.get('parameters')) for r in records)
    if record_refs is not None:
        requested=set(record_refs)
        selected=[r for r in records if r['ref'] in requested]
        next_offset=None
    elif parameter_offset is not None:
        parameters=[r for r in records if r.get('parameters')]
        selected=parameters[parameter_offset:parameter_offset+25]
        next_offset=parameter_offset+25 if parameter_offset+25<len(parameters) else None
    else:selected=records[:25];next_offset=None
    context['aps_native']={
        'provider':job.get('provider','aps'),
        'inspection_id':job_id,'original_source_hash':job['source_hash'],
        'readback_hash':digest(readback),'matched_scope_entities':matched,
        'drawing_units':inventory.get('summary',{}).get('drawing_units'),
        'native_topology_available':bool(native) and all('persistent_reactor_handles' in row and 'extension_dictionary_handle' in row for row in native.values()),
        'records':selected,'deferred_record_count':len(records)-len(selected),
        'deferred_parameter_record_count':total_parameters-sum(bool(r.get('parameters')) for r in selected),
        'parameter_record_count':total_parameters,'next_parameter_offset':next_offset,
        'inventory_url':f'/documents/{document_id}/{"autocad" if job.get("provider")=="autocad" else "aps"}/jobs/{job_id}/files/inventory.json',
        'policy':'Native handles/owner paths verified against this exact readback. Native facts and reactor handles do not authorize inferred mechanical dependencies or arbitrary CAD code. Missing topology metadata is not evidence of an unlinked entity.'}
    return context
