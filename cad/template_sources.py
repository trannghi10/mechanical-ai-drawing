"""Reuse checked bindings only across proven reads of the identical DWG."""
import json
import re
from pathlib import Path
from cad.edit_engine import digest


def register(template_path,source_dxf,derived_dxf,source_dwg,derived_dwg):
    from cad.catalog import load_document
    from cad.nested_scope_export import path_entity,copy_snapshot
    from cad.geometry import near
    template_path=Path(template_path);template=json.loads(template_path.read_text(encoding='utf8'))
    if digest(source_dxf)!=template['source_hash']:raise ValueError('Template canonical DXF hash mismatch')
    if digest(source_dwg)!=digest(derived_dwg):raise ValueError('Binding variants require the identical source DWG')
    if not re.fullmatch(rb'AC10[0-9]{2}',Path(source_dwg).read_bytes()[:6]):raise ValueError('Binding source must have a DWG signature')
    refs=set()
    def visit(value):
        if isinstance(value,dict):
            for key,child in value.items():visit(key);visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
        elif isinstance(value,str) and re.fullmatch(r'[0-9A-F]{4,16}(?:/[0-9A-F]{4,16})*',value):refs.add(value)
    visit(template)
    if not refs:raise ValueError('No source references to prove')
    before=load_document(str(source_dxf));after=load_document(str(derived_dxf));records=[]
    if before.units!=after.units or before.dxfversion!=after.dxfversion:raise ValueError('Template units/version mismatch')
    for ref in sorted(refs):
        a=path_entity(before,ref);b=path_entity(after,ref)
        if a.dxftype() not in ('INSERT','LINE','LWPOLYLINE','POLYLINE','ARC','CIRCLE','ELLIPSE','SPLINE','DIMENSION','TEXT','MTEXT'):
            raise ValueError('Unsupported template witness: '+ref)
        left=copy_snapshot(a);right=copy_snapshot(b)
        if a.dxf.owner!=b.dxf.owner or not near(left,right,1e-6):raise ValueError('Template source geometry/owner mismatch: '+ref)
        if a.dxftype()=='INSERT' and before.blocks[a.dxf.name].block_record_handle!=after.blocks[b.dxf.name].block_record_handle:
            raise ValueError('Template instance definition mismatch: '+ref)
        records.append(dict(ref=ref,owner=a.dxf.owner,snapshot=left))
    proof=dict(status='verified_same_dwg_bindings',template_hash=digest(template_path),canonical_source_hash=digest(source_dxf),
               source_hash=digest(derived_dxf),source_dwg_hash=digest(source_dwg),reference_count=len(records),records=records,
               new_relationships_inferred=False,complete_product_backup=False)
    registry=template_path.with_suffix('.sources.json')
    existing=json.loads(registry.read_text(encoding='utf8')) if registry.is_file() else dict(version=1,sources=[])
    existing['sources']=[p for p in existing['sources'] if p['source_hash']!=proof['source_hash']]+[proof]
    registry.write_text(json.dumps(existing,ensure_ascii=False,indent=2),encoding='utf8')
    return proof


def resolve(template_path,source_hash):
    template_path=Path(template_path);template=json.loads(template_path.read_text(encoding='utf8'))
    if source_hash==template['source_hash']:return template
    registry=template_path.with_suffix('.sources.json')
    if not registry.is_file():return None
    for proof in json.loads(registry.read_text(encoding='utf8')).get('sources',[]):
        if proof['source_hash']!=source_hash:continue
        if (proof.get('status')!='verified_same_dwg_bindings' or proof.get('template_hash')!=digest(template_path)
                or proof.get('canonical_source_hash')!=template['source_hash'] or not proof.get('source_dwg_hash')
                or proof.get('reference_count',0)!=len(proof.get('records',[])) or not proof.get('records')):
            raise ValueError('Template source-equivalence proof is stale or incomplete')
        return template
    return None
