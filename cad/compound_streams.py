"""Read-only bounded CFB stream inventory for OLE no-op control diagnostics."""
import struct,hashlib


def inventory(payload):
    magic=bytes.fromhex('d0cf11e0a1b11ae1');offset=payload.find(magic)
    if offset<0:raise ValueError('Missing CFB header')
    data=payload[offset:];header=data[:512]
    u16=lambda b,o:struct.unpack_from('<H',b,o)[0]
    u32=lambda b,o:struct.unpack_from('<I',b,o)[0]
    u64=lambda b,o:struct.unpack_from('<Q',b,o)[0]
    if len(header)!=512 or header[28:30]!=b'\xfe\xff' or (u16(header,26),u16(header,30))!=(3,9):raise ValueError('Only bounded CFB v3 supported')
    size=512
    def sector(i):
        if i>=0xfffffffa or (i+2)*size>len(data):raise ValueError('CFB sector out of range')
        return data[(i+1)*size:(i+2)*size]
    if u32(header,72)!=0 or u32(header,44)>109:raise ValueError('Extended DIFAT not supported')
    fat=[]
    for i in range(u32(header,44)):fat.extend(struct.unpack('<128I',sector(u32(header,76+i*4))))
    def chain(start,table,read,max_count):
        seen=set();out=[]
        while start!=0xfffffffe:
            if start in seen or start>=len(table) or len(seen)>=max_count:raise ValueError('Invalid or oversized CFB chain')
            seen.add(start);out.append(read(start));start=table[start]
        return b''.join(out)
    directory=chain(u32(header,48),fat,sector,4096);entries=[]
    for pos in range(0,len(directory),128):
        e=directory[pos:pos+128];kind=e[66]
        if kind==0:continue
        n=u16(e,64)
        if n<2 or n>64:raise ValueError('Invalid CFB directory name')
        entries.append(dict(index=pos//128,name=e[:n-2].decode('utf-16le'),kind=kind,start=u32(e,116),size=u64(e,120),left=u32(e,68),right=u32(e,72),child=u32(e,76),clsid=e[80:96].hex(),state=u32(e,96)))
    by_id={e['index']:e for e in entries};root=by_id.get(0)
    if not root or root['kind']!=5:raise ValueError('Missing root')
    mini=chain(root['start'],fat,sector,100000)[:root['size']] if root['size'] else b''
    minifat_bytes=chain(u32(header,60),fat,sector,4096) if u32(header,64) else b''
    minifat=list(struct.unpack('<'+'I'*(len(minifat_bytes)//4),minifat_bytes))
    streams={};visited=set()
    def walk(index,path):
        if index==0xffffffff:return
        if index not in by_id or index in visited:raise ValueError('Invalid CFB directory tree')
        visited.add(index);e=by_id[index];walk(e['left'],path);name=path+'/'+e['name']
        if e['kind']==1:walk(e['child'],name)
        elif e['kind']==2:
            if e['size']==0:content=b''
            elif e['size']<u32(header,56):content=chain(e['start'],minifat,lambda i:mini[i*64:(i+1)*64],100000)[:e['size']]
            else:content=chain(e['start'],fat,sector,100000)[:e['size']]
            if len(content)!=e['size']:raise ValueError('Truncated stream')
            streams[name]=dict(size=len(content),sha256=hashlib.sha256(content).hexdigest(),clsid=e['clsid'],state=e['state'])
        else:raise ValueError('Unsupported directory kind')
        walk(e['right'],path)
    walk(root['child'],'')
    return dict(streams=streams,root_clsid=root['clsid'],root_state=root['state'],wrapper_sha256=hashlib.sha256(payload[:offset]).hexdigest(),payload_bytes=len(payload))
