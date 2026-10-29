"""Read native HATCH adapter coverage without modifying the customer file."""
import argparse,json,sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import ezdxf
from cad.edit_engine import digest
from cad.hatch_translation import snapshot,validate_preserved
from backend.services import catalog_service as storage


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document_id');parser.add_argument('--output',required=True)
    args=parser.parse_args();folder=storage.folder(args.document_id);status=storage.read_status(args.document_id)
    if status['status']!='ready':raise ValueError('Document is not ready')
    source=folder/status['dxf'];before=digest(source);doc=ezdxf.readfile(source);items=[];groups=[]
    placements=Counter(e.dxf.name if e.dxftype()=='INSERT' else e.dxf.get('geometry','') for e in doc.entitydb.values()
        if e.is_alive and e.dxftype() in ('INSERT','ACAD_TABLE'))
    for block in doc.blocks:
        from cad.hatch_association import graph as association_graph
        try:association_proof=association_graph(doc,block);association_status='supported_unchanged_internal_group'
        except ValueError as exc:association_proof={};association_status=str(exc)
        if association_proof.get('hatches'):
            groups.append(dict(block=block.name,hatch_refs=sorted(association_proof['hatches']),
                dimension_refs=sorted(association_proof['extensions']),owned_object_refs=sorted(association_proof['objects']),
                direct_container_references=placements[block.name],layout_root=block.name.startswith('*Model_Space') or block.name.startswith('*Paper_Space'),
                policy='Preserve the complete unchanged group; other block dependencies still need validation.'))
        for hatch in block.query('HATCH'):
            item=dict(handle=hatch.dxf.handle,block=block.name,extrusion=list(hatch.dxf.extrusion),
                      path_types=['polyline' if hasattr(p,'vertices') else '+'.join(sorted({e.EDGE_TYPE for e in p.edges})) for p in hatch.paths],
                      associative=bool(hatch.dxf.associative),reactors=list(hatch.get_reactors()),
                      has_extension_dictionary=bool(hatch.has_extension_dict),
                      source_boundary_handles=[list(p.source_boundary_objects) for p in hatch.paths])
            dependencies=[]
            for handle in sorted({h for p in hatch.paths for h in p.source_boundary_objects}):
                boundary=doc.entitydb.get(handle)
                dependencies.append(dict(handle=handle,exists=boundary is not None,
                    type=boundary.dxftype() if boundary is not None else None,
                    same_owner=boundary is not None and boundary.dxf.owner==hatch.dxf.owner,
                    reciprocal_reactor=boundary is not None and hatch.dxf.handle in boundary.get_reactors()))
            item['boundary_dependencies']=dependencies
            if hatch.dxf.associative:item['unchanged_association_adapter']=association_status
            try:snapshot(hatch);item['edit_adapter']='supported'
            except ValueError as exc:item['edit_adapter']=str(exc)
            try:validate_preserved(hatch);item['raw_copy_adapter']='supported'
            except ValueError as exc:item['raw_copy_adapter']=str(exc)
            items.append(item)
    after=digest(source);assert before==after
    result=dict(document_id=args.document_id,source_hash=before,source_unchanged=True,hatch_count=len(items),
                raw_copy_counts=dict(Counter(i['raw_copy_adapter'] for i in items)),
                edit_counts=dict(Counter(i['edit_adapter'] for i in items)),items=items,
                unchanged_association_counts=dict(Counter(i['unchanged_association_adapter'] for i in items if i['associative'])),
                unchanged_association_groups=groups,
                policy='Entity adapter coverage only; not proof of block isolation, identity, design dependencies or complete-product editing.')
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);storage.write_json(output,result)
    print(json.dumps({k:v for k,v in result.items() if k!='items'},ensure_ascii=True))


if __name__=='__main__':main()
