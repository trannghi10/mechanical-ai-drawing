"""Check a two-edit inverse translation against the original native readback."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import ezdxf
    from cad.edit_engine import digest
    from cad.geometry import near,snapshot
    from cad.dimensions import dimension_snapshot
    from cad.dimension_associations import source_binding
    from cad.dimension_visuals import verify_translation
    from backend.services import catalog_service as storage
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_document_id');parser.add_argument('first_probe');parser.add_argument('second_probe');parser.add_argument('--output',required=True)
    args=parser.parse_args();first=Path(args.first_probe);second=Path(args.second_probe)
    a=json.loads((first/'poly-dim-receipt.json').read_text(encoding='utf8'));b=json.loads((second/'poly-dim-receipt.json').read_text(encoding='utf8'))
    assert a['status']==b['status']=='validated_polyline_dimension_translation_probe'
    assert a['independent_dxf_readback'] and b['independent_dxf_readback']
    assert digest(first/'poly-dim-probe.dwg')==a['output_sha256']==b['source_sha256']
    assert digest(second/'poly-dim-probe.dwg')==b['output_sha256']
    assert near([x+y for x,y in zip(a['delta'],b['delta'])],[0,0,0],1e-10)
    assert a['dimension_handles']==b['dimension_handles'] and a['action_handles']==b['action_handles']
    original=storage.folder(args.original_document_id);status=storage.read_status(args.original_document_id)
    assert digest(original/'original.dwg')==a['source_sha256']
    before=ezdxf.readfile(original/status['dxf']);after=ezdxf.readfile(second/'poly-dim-probe.dxf')
    root=a['polyline_handle'];assert root==b['polyline_handle'] and near(snapshot(before.entitydb[root]),snapshot(after.entitydb[root]),1e-6)
    rows=[]
    for handle in a['dimension_handles']:
        dim0,dim1=before.entitydb[handle],after.entitydb[handle]
        assert near(dimension_snapshot(dim0),dimension_snapshot(dim1),1e-6)
        assert abs(dim0.get_measurement()-dim1.get_measurement())<1e-6
        assert set(dim0.get_reactors())==set(dim1.get_reactors())
        binding0,binding1=source_binding(dim0),source_binding(dim1)
        if binding0:
            assert binding0['status']==binding1['status']=='verified_source_points'
            assert binding0['source_refs']==binding1['source_refs'] and binding0['association_ref']==binding1['association_ref']
        rows.append(dict(handle=handle,**verify_translation(dim0,dim1,[0,0,0])))
    report=dict(status='verified_two_edit_return_to_source',original_document_id=args.original_document_id,
                first_output_hash=a['output_sha256'],second_output_hash=b['output_sha256'],dimension_count=len(rows),
                visual_primitive_count=sum(r['primitive_count'] for r in rows),items=rows,
                customer_revision_created=False,edit_authorization=False,complete_product_backup=False)
    storage.write_json(Path(args.output),report);print(json.dumps(report))


if __name__=='__main__':main()
