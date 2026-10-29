"""Audit the bounded outside-object differences against source DXF and no-op control."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    import ezdxf
    from cad.dimensions import serialize
    from cad.compound_streams import inventory
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source_dxf',type=Path);parser.add_argument('control_evidence',type=Path);args=parser.parse_args()
    source=ezdxf.readfile(args.source_dxf);control=ezdxf.readfile(args.control_evidence/'relationship-repair.dxf')
    differences=json.loads((args.control_evidence/'relationship-repair-outside-diff.json').read_text());rows=[]
    assert not differences['added'] and not differences['removed']
    def split(tags):
        other=[];pieces=[]
        for i in range(0,len(tags),2):
            code=int(tags[i]);value=tags[i+1].decode().strip()
            if code==310:pieces.append(value)
            else:other.append((code,value))
        return other,bytes.fromhex(''.join(pieces))
    for change in differences['changed']:
        h=change['handle'];a=serialize(source.entitydb[h]);b=serialize(control.entitydb[h]);kind=source.entitydb[h].dxftype()
        row=dict(handle=h,type=kind,raw_source_tags_equal=a==b)
        if a!=b:
            assert kind=='OLE2FRAME'
            meta_a,blob_a=split(a);meta_b,blob_b=split(b)
            assert [(c,v) for c,v in meta_a if c!=90]==[(c,v) for c,v in meta_b if c!=90]
            assert [int(v) for c,v in meta_a if c==90]==[len(blob_a)] and [int(v) for c,v in meta_b if c==90]==[len(blob_b)]
            x,y=inventory(blob_a),inventory(blob_b)
            assert x['streams']==y['streams'] and x['root_clsid']==y['root_clsid'] and x['root_state']==y['root_state']
            prefix_a=blob_a.find(bytes.fromhex('d0cf11e0a1b11ae1'));prefix_b=blob_b.find(bytes.fromhex('d0cf11e0a1b11ae1'))
            assert prefix_a==prefix_b
            row.update(export_metadata_equal_except_payload_length=True,compound_streams_equal=True,source_compound=x,control_compound=y,
                       wrapper_differing_byte_offsets=[i for i in range(prefix_a) if blob_a[i]!=blob_b[i]],
                       appearance_verified=False,limitation='Compound allocation/wrapper changed under no-op save. Streams are identical; pixel appearance and OLE host activation are not tested.')
        rows.append(row)
    report=dict(status='audited_noop_outside_objects',object_count=len(rows),objects=rows,
                conclusion='No-op reproduces the outside bbox changes. Source content streams retained; no claim of pixel-identical rendering.')
    (args.control_evidence/'outside-source-control-audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(status=report['status'],object_count=len(rows),raw_source_tags_equal=sum(r['raw_source_tags_equal'] for r in rows),compound_streams_equal=sum(r.get('compound_streams_equal',False) for r in rows))))


if __name__=='__main__':main()
