"""Compare OLE frame exports, allowing only CFB root last-modified FILETIME."""
import struct
from cad.dimensions import serialize


def _root_modified(payload):
    magic=bytes.fromhex('d0cf11e0a1b11ae1');start=payload.find(magic)
    if start<0 or payload.find(magic,start+1)>=0:raise ValueError('Unique compound file header required')
    header=payload[start:start+512]
    if len(header)!=512 or header[28:30]!=b'\xfe\xff':raise ValueError('Unsupported compound byte order')
    major,shift=struct.unpack_from('<H',header,26)[0],struct.unpack_from('<H',header,30)[0]
    if (major,shift) not in ((3,9),(4,12)):raise ValueError('Unsupported compound version/sector size')
    sector=struct.unpack_from('<I',header,48)[0];offset=start+(sector+1)*(1<<shift)
    entry=payload[offset:offset+128]
    if len(entry)!=128 or entry[66]!=5:raise ValueError('First directory entry is not compound root')
    name_len=struct.unpack_from('<H',entry,64)[0]
    if name_len<2 or name_len>64 or entry[:name_len-2].decode('utf-16le')!='Root Entry':raise ValueError('Invalid compound root entry')
    return offset+108


def compare_exported_entity(control,actual):
    a=serialize(control);b=serialize(actual)
    if a==b:return dict(raw_exported_tags_match_control=True,root_modified_time_only=False)
    if control.dxftype()!='OLE2FRAME' or actual.dxftype()!='OLE2FRAME':raise ValueError('Outside raw DXF differs from control')
    def split(tags):
        other=[];hexdata=[]
        for i in range(0,len(tags),2):
            if tags[i].strip()==b'310':hexdata.append(tags[i+1].decode().strip())
            else:other.extend(tags[i:i+2])
        return other,bytes.fromhex(''.join(hexdata))
    left,x=split(a);right,y=split(b)
    if left!=right or len(x)!=len(y):raise ValueError('OLE metadata or payload length differs from control')
    ix,iy=_root_modified(x),_root_modified(y)
    if ix!=iy or x[:ix]!=y[:iy] or x[ix+8:]!=y[iy+8:]:raise ValueError('OLE differs beyond compound root modified time')
    return dict(raw_exported_tags_match_control=False,root_modified_time_only=True,
                payload_bytes=len(x),filetime_offset=ix,control_filetime=struct.unpack_from('<Q',x,ix)[0],actual_filetime=struct.unpack_from('<Q',y,iy)[0],
                remaining_payload_and_metadata_exact=True)
