"""Copy-on-write isolation of static block instances in raw ASCII DXF.

Opaque objects, XREFs and dynamic/associative definitions are refused rather than
copied with dangling external dictionaries. Original definitions remain intact.
"""
from pathlib import Path
from bisect import bisect_left
import ezdxf


def isolate(source,destination,refs,operations=()):
    from cad.edit_engine import chunks,separate_output
    source=Path(source)
    separate_output(source,destination)
    doc=ezdxf.readfile(source)
    lines=source.read_bytes().splitlines(keepends=True)
    span_records=list(chunks(lines))
    spans={h:(a,b) for h,a,b in span_records}
    span_starts=[a for h,a,b in span_records]
    newline=b'\r\n' if lines[0].endswith(b'\r\n') else b'\n'
    next_handle=max(int(h,16) for h in doc.entitydb if h)+1
    additions=[];addition_by_handle={};records=[];objects=[];replacements={};cache={};resolved={};clones=[];appid_records=[]
    # Flat geometry-only writes with exactly equal local changes may share one
    # new definition. All other writes retain per-instance isolation.
    from collections import defaultdict
    writes=defaultdict(list);ineligible=set();interned={};signatures={}
    for op in operations:
        path=op.ref.split('/')
        if len(path)>1:
            root=path[0]
            if len(path)!=2 or op.action!='replace_geometry' or op.mirror_ref:ineligible.add(root)
            else:writes[root].append((path[1],op.action,op.before,op.after,tuple(op.xyz),op.cell_index))
    for root,changes in writes.items():
        entity=doc.entitydb.get(root)
        if root in ineligible or entity is None or entity.dxftype()!='INSERT' or entity.attribs or entity.has_extension_dict or entity.get_reactors():continue
        block=doc.blocks.get(entity.dxf.name)
        if block is None or any(e.dxftype() not in ('LINE','LWPOLYLINE','ARC','CIRCLE') for e in block):continue
        signatures[root]=(entity.dxf.name,tuple(sorted(changes)))

    def allocate():
        nonlocal next_handle
        result=f'{next_handle:X}';next_handle+=1
        return result

    def replace_tag(raw,code,value,required=True):
        positions=[i for i in range(0,len(raw),2) if raw[i].strip()==str(code).encode()]
        if required and len(positions)!=1:raise ValueError('Block tag không duy nhất hoặc thiếu')
        for i in positions:raw[i+1]=str(value).encode('utf8')+newline

    def instance_raw(handle):
        if handle in replacements:return replacements[handle]
        if handle in addition_by_handle:return addition_by_handle[handle]
        if handle not in spans:raise ValueError('Instance không nằm trong dữ liệu DXF gốc')
        a,b=spans[handle];raw=list(lines[a:b]);replacements[handle]=raw
        return raw

    def clone_definition(name,parent_handle,prefix):
        if prefix in cache:return cache[prefix]
        signature=signatures.get(prefix)
        if signature in interned:
            mapping,clone=interned[signature]
            replace_tag(instance_raw(parent_handle),2,clone['new_block'])
            cache[prefix]=mapping;clone['instance_paths'].append(prefix)
            return mapping
        block=doc.blocks.get(name)
        if block is None:raise ValueError('Không tìm thấy block definition')
        if block.block.dxf.get('flags',0)&(4|8|16|32|64):raise ValueError('Chưa hỗ trợ clone XREF hoặc block phụ thuộc ngoài file')
        entities=[block.block,*list(block),block.endblk]
        supported={'BLOCK','ENDBLK','LINE','LWPOLYLINE','POLYLINE','VERTEX','SEQEND','CIRCLE','ARC','ELLIPSE',
                   'SPLINE','TEXT','MTEXT','ATTDEF','ATTRIB','INSERT','SOLID','TRACE','3DFACE','POINT','DIMENSION','HATCH'}
        # Include sequence entities (vertices and instance attributes) from raw range.
        start=spans[block.block.dxf.handle][0];end=spans[block.endblk.dxf.handle][1]
        originals=[h for h,a,b in span_records[bisect_left(span_starts,start):bisect_left(span_starts,end)]]
        from cad.hatch_association import graph as hatch_graph
        associations=hatch_graph(doc,block)
        from cad.empty_dictionary import handle as empty_dictionary_handle
        empty_extensions={handle:empty_dictionary_handle(doc.entitydb[handle]) for handle in originals if doc.entitydb.get(handle) is not None}
        empty_extensions={handle:dictionary for handle,dictionary in empty_extensions.items() if dictionary}
        for op in operations:
            if op.ref.startswith(prefix+'/') and op.ref.split('/')[-1] in associations['members']:
                raise ValueError('HATCH association chỉ hỗ trợ bảo toàn nhóm không sửa biên')
        for handle in originals:
            e=doc.entitydb.get(handle)
            if e is None or e.dxftype() not in supported:raise ValueError('Block chứa entity chưa hỗ trợ clone bảo toàn: '+(e.dxftype() if e else handle))
            if e.dxftype()=='HATCH' and handle not in associations['hatches']:
                from cad.hatch_translation import snapshot as hatch_snapshot
                try:hatch_snapshot(e)
                except ValueError:
                    from cad.hatch_translation import validate_preserved
                    validate_preserved(e)
            if e.has_extension_dict and handle not in associations['extensions'] and handle not in empty_extensions or e.get_reactors() and handle not in associations['reactors']:raise ValueError('Block có dữ liệu động/association ngoài definition; cần CAD SDK native')
        extra_objects=sorted(set(associations['objects'])|set(empty_extensions.values()))
        if block.block_record.has_extension_dict:
            extension=block.block_record.get_extension_dict()
            if set(extension.keys())!={'ACAD_SORTENTS'} or extension['ACAD_SORTENTS'].dxftype()!='SORTENTSTABLE':
                raise ValueError('Dynamic/associative block cần CAD SDK native để clone đúng')
            extra_objects.extend([extension.dictionary.dxf.handle,extension['ACAD_SORTENTS'].dxf.handle])
        record_handle=block.block_record_handle
        mapping={h:allocate() for h in [record_handle,*originals,*extra_objects]}
        new_name='AI_COPY_'+mapping[record_handle]
        # Remap internal handles, retaining layer/style/material pointers.
        def copy_raw(handle):
            a,b=spans[handle];raw=list(lines[a:b])
            handle_written=False
            for i in range(0,len(raw),2):
                code=int(raw[i]);value=raw[i+1].strip().decode('utf8')
                is_handle=code in (5,105) and not handle_written
                if code in (5,105):handle_written=True
                if (is_handle or code==1005 or 330<=code<=369 or 390<=code<=399 or code in (480,481)) and value in mapping:
                    raw[i+1]=mapping[value].encode()+newline
            return raw
        record=copy_raw(record_handle);replace_tag(record,2,new_name)
        from cad.block_provenance import APPID,MARKER,source_name
        origin=source_name(doc,name)
        if origin is None and not block.block_record.has_xdata(APPID):
            origin=name
            record.extend([b'1001'+newline,APPID.encode()+newline,b'1000'+newline,MARKER.encode()+newline,b'1000'+newline,origin.encode('utf8')+newline])
            if APPID not in doc.appids and not appid_records:
                ah=allocate();head=doc.appids.head.dxf.handle
                values=[('0','APPID'),('5',ah),('330',head),('100','AcDbSymbolTableRecord'),('100','AcDbRegAppTableRecord'),('2',APPID),('70','0')]
                appid_records.extend(v.encode('utf8')+newline for pair in values for v in pair)
        records.append(record)
        objects.extend(copy_raw(h) for h in extra_objects)
        for old in originals:
            raw=copy_raw(old)
            if old==block.block.dxf.handle:
                replace_tag(raw,2,new_name);replace_tag(raw,3,new_name,required=False)
                # The clone has a stable ordinary name, not an anonymous *U
                # name. Keeping bit 1 makes AutoCAD discard its BTR on DXFIN;
                # INSERTs then have a null BlockTableRecord and DXFOUT fails.
                # Other flags (e.g. ATTDEF ownership) still belong to the copy.
                replace_tag(raw,70,block.block.dxf.get('flags',0)&~1)
            additions.append((mapping[old],raw))
            addition_by_handle[mapping[old]]=raw
        raw=instance_raw(parent_handle)
        replace_tag(raw,2,new_name)
        parent=doc.entitydb.get(parent_handle)
        # A table geometry root also references its block record by handle.
        if parent and parent.dxftype()=='ACAD_TABLE':replace_tag(raw,343,mapping[record_handle],required=False)
        cache[prefix]=mapping
        clone={'instance_path':prefix,'instance_paths':[prefix],'original_block':name,'new_block':new_name,'handle_map':mapping}
        clones.append(clone)
        if signature is not None:interned[signature]=(mapping,clone)
        return mapping

    for reference in refs:
        path=reference.split('/')
        mapped=[path[0]]
        for index in range(len(path)-1):
            original_parent=doc.entitydb.get(path[index]);original_child=doc.entitydb.get(path[index+1])
            if original_parent is None or original_child is None:raise ValueError('Đường dẫn instance không hợp lệ')
            if original_child.dxftype()=='ATTRIB' and original_child.dxf.owner==original_parent.dxf.handle:
                parent_prefix='/'.join(path[:index])
                parent_map=cache.get(parent_prefix,{})
                mapped.append(parent_map.get(path[index+1],path[index+1]));continue
            if original_parent.dxftype()=='INSERT':name=original_parent.dxf.name
            elif original_parent.dxftype()=='ACAD_TABLE':name=original_parent.dxf.get('geometry','')
            else:raise ValueError('Parent của entity không phải INSERT hoặc bảng')
            block=doc.blocks.get(name)
            if block is None or original_child.dxf.owner!=block.block_record_handle:
                raise ValueError('Entity không thuộc block trong đường dẫn đã chọn')
            prefix='/'.join(path[:index+1])
            mapping=clone_definition(name,mapped[-1],prefix)
            mapped.append(mapping[path[index+1]])
        resolved[reference]='/'.join(mapped)
    if not clones:return None,resolved,[]

    # Locate structural insertion points without serializing any existing entity.
    block_record_end=None;blocks_end=None;objects_end=None;appid_end=None;section=None;table=None
    for i in range(0,len(lines),2):
        code=lines[i].strip();value=lines[i+1].strip()
        if code==b'0' and value==b'SECTION':section=lines[i+3].strip()
        if code==b'0' and value==b'TABLE':table=lines[i+3].strip()
        if code==b'0' and value==b'ENDTAB':
            if table==b'BLOCK_RECORD':block_record_end=i
            if table==b'APPID':appid_end=i
            table=None
        if code==b'0' and value==b'ENDSEC':
            if section==b'BLOCKS':blocks_end=i
            if section==b'OBJECTS':objects_end=i
            section=None
    if block_record_end is None or blocks_end is None:raise ValueError('Thiếu section BLOCKS/BLOCK_RECORD')
    inserts={block_record_end:[line for raw in records for line in raw],
             blocks_end:[line for _,raw in additions for line in raw]}
    if objects:
        if objects_end is None:raise ValueError('Thiếu OBJECTS để clone sort-order')
        inserts[objects_end]=[line for raw in objects for line in raw]
    if appid_records:
        if appid_end is None:raise ValueError('Thiếu bảng APPID để giữ mã nguồn block sau xuất DWG')
        inserts[appid_end]=appid_records
        appid_head=instance_raw(doc.appids.head.dxf.handle)
        replace_tag(appid_head,70,min(32767,len(doc.appids)+1))
    head=doc.tables.block_records.head.dxf.handle
    header=instance_raw(head)
    replace_tag(header,70,min(32767,len(doc.tables.block_records)+len(records)))
    edits={spans[h][0]:(spans[h][1],raw) for h,raw in replacements.items()}
    # Advance HANDSEED so subsequent CAD allocation cannot reuse cloned handles.
    for i in range(0,len(lines)-2,2):
        if lines[i].strip()==b'9' and lines[i+1].strip()==b'$HANDSEED':
            if lines[i+2].strip()!=b'5':raise ValueError('HANDSEED không hợp lệ')
            lines[i+3]=f'{next_handle:X}'.encode()+newline
    output=[];i=0
    while i<len(lines):
        if i in inserts:output.extend(inserts[i])
        if i in edits:
            end,raw=edits[i];output.extend(raw);i=end
        else:output.append(lines[i]);i+=1
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(b''.join(output))
    check=ezdxf.readfile(destination)
    for newref in resolved.values():
        if check.entitydb.get(newref.split('/')[-1]) is None:raise ValueError('Clone bị mất entity')
    from cad.hatch_association import verify_mapping
    for clone in clones:
        verify_mapping(doc,check,clone['handle_map'])
        from cad.empty_dictionary import verify_mapping as verify_empty_dictionaries
        verify_empty_dictionaries(doc,check,clone['handle_map'])
    return destination,resolved,clones
