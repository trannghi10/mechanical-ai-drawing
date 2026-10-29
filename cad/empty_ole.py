"""Normalize only empty OLE placeholders to a native-read canonical header.

Nonempty OLE payloads and every other source byte remain unchanged. This is
an import compatibility operation, never permission to alter drawing geometry.
"""
from pathlib import Path
from cad.edit_engine import chunks, digest, separate_output

POLICY_VERSION=3
# Empty 128-byte AcDbOle2Frame wrapper verified by local AutoCAD save/reopen.
# It contains no embedded CFB/document. Nonempty payloads are never touched.
EMPTY_PAYLOAD=bytes.fromhex('8055'+'00'*100+'0100000000010000010000000100000000000400000000000000')


def normalize(source, destination):
    source,destination=map(Path,(source,destination))
    separate_output(source,destination)
    source_hash=digest(source)
    raw=source.read_bytes().splitlines(keepends=True)
    def pairs(lines):return [(int(lines[i]),lines[i+1].strip()) for i in range(0,len(lines),2)]
    changes={};report=[]
    for handle,start,end in chunks(raw):
        if raw[start+1].strip()!=b'OLE2FRAME':continue
        before=pairs(raw[start:end])
        # These placeholders have no size, embedded data or OLE type at all.
        if any(code in (73,90,310) for code,value in before):continue
        if [(c,v) for c,v in before if c==70]!=[(70,b'2')]:continue
        if [(c,v) for c,v in before if c==100][-1:]!=[(100,b'AcDbOle2Frame')]:continue
        if [(c,v) for c,v in before if c==1]!=[(1,b'OLE')]:continue
        assert len(EMPTY_PAYLOAD)==128
        insertion=next(i for i in range(start,end,2) if int(raw[i])==1)
        newline=b'\r\n' if raw[start].endswith(b'\r\n') else b'\n'
        added=[b' 73',b'1',b' 90',b'128']
        for offset in range(0,len(EMPTY_PAYLOAD),32):added.extend([b'310',EMPTY_PAYLOAD[offset:offset+32].hex().upper().encode('ascii')])
        replacement=raw[start:insertion]+[line+newline for line in added]+raw[insertion:end]
        if [(c,v) for c,v in pairs(replacement) if c not in (73,90,310)]!=before:raise ValueError('Empty OLE metadata changed')
        changes[start]=(end,replacement);report.append(dict(ref=handle,before_payload_bytes=0,after_payload_bytes=128,metadata_equal=True))
    if not report:return None
    output=[];cursor=0
    for start,(end,replacement) in sorted(changes.items()):
        output.extend(raw[cursor:start]);output.extend(replacement);cursor=end
    output.extend(raw[cursor:]);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(b''.join(output))
    if digest(source)!=source_hash:raise ValueError('OLE normalization source changed')
    return dict(policy_version=POLICY_VERSION,source_hash=source_hash,output_hash=digest(destination),
                empty_ole=report,other_source_bytes_preserved=True,appearance_verified=False)


def verify(before,after,normalization):
    """Recheck every opaque OLE payload, metadata and XDATA after native save."""
    from cad.geometry import near
    allowed={row['ref'] for row in normalization['empty_ole']};found=set();rows=[]
    old={e.dxf.handle:e for e in before.entitydb.values() if e.dxftype()=='OLE2FRAME'}
    new={e.dxf.handle:e for e in after.entitydb.values() if e.dxftype()=='OLE2FRAME'}
    if old.keys()!=new.keys():raise ValueError('OLE inventory changed after native save')
    for ref,entity in old.items():
        actual=new[ref];a=entity.binary_data();b=actual.binary_data();empty=ref in allowed
        if empty:
            if a or b!=EMPTY_PAYLOAD:raise ValueError('Empty OLE normalization mismatch: '+ref)
            found.add(ref)
        elif a!=b:raise ValueError('Opaque OLE payload changed: '+ref)
        def metadata(e):
            return [(c,v) for c,v in (e.acdb_ole2frame or []) if c!=310 and not (empty and c in (73,90))]
        if not near(metadata(entity),metadata(actual),1e-6) or not near(entity.dxfattribs(),actual.dxfattribs(),1e-6):
            raise ValueError('OLE metadata changed after native save: '+ref)
        def xdata(e):return {app:[(tag.code,tag.value) for tag in tags] for app,tags in (e.xdata.data.items() if e.xdata else [])}
        if not near(xdata(entity),xdata(actual),1e-9):
            raise ValueError('OLE XDATA changed after native save: '+ref)
        rows.append(dict(ref=ref,empty_normalized=empty,payload_bytes_before=len(a),payload_bytes_after=len(b),
                         payload_equal=a==b,metadata_equal=True,xdata_equal=True))
    if found!=allowed:raise ValueError('Normalized OLE missing from source')
    return dict(status='passed',objects=rows,appearance_verified=False)
