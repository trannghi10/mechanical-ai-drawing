"""Transactional ASCII DXF patches; preserves untouched tags including ACAD_TABLE.

Only explicitly bound operations are accepted. No unrestricted model-generated code.
"""
import hashlib
import math
from pathlib import Path
import ezdxf
from pydantic import BaseModel, ConfigDict
from typing import Literal


class Operation(BaseModel):
    model_config=ConfigDict(extra='ignore')
    ref: str
    action: Literal['replace_text','move_text','line_end','move_insert','table_cell','replace_geometry','remove_insert','append_geometry']
    before: str
    after: str
    xyz: list[float]
    reason: str
    cell_index: int = -1
    mirror_ref: str = ''


_DIGEST_CACHE = {}


def digest(path):
    p = Path(path)
    try:
        st = p.stat()
        key = (str(p.resolve()), st.st_mtime_ns, st.st_size)
        cached = _DIGEST_CACHE.get(key)
        if cached is not None:
            return cached
        val = hashlib.sha256(p.read_bytes()).hexdigest()
        if len(_DIGEST_CACHE) > 512:
            _DIGEST_CACHE.clear()
        _DIGEST_CACHE[key] = val
        return val
    except OSError:
        return hashlib.sha256(p.read_bytes()).hexdigest()


def separate_output(source,*outputs):
    """Every CAD writer must keep its input, including path/file aliases."""
    source=Path(source)
    for output in map(Path,outputs):
        if source.resolve()==output.resolve() or (source.exists() and output.exists() and source.samefile(output)):
            raise ValueError('Chỉ tạo bản mới; không được ghi đè bản vẽ nguồn hoặc đường dẫn trùng nguồn')



def chunks(lines):
    starts=[i for i in range(0,len(lines),2) if lines[i].strip()==b'0']
    starts.append(len(lines))
    for a,b in zip(starts,starts[1:]):
        handle=next((lines[j+1].strip().decode('ascii') for j in range(a,b,2) if lines[j].strip()==b'5'),None)
        if handle:yield handle,a,b


def apply_patch(source,destination,operations,allowed_refs,source_hash,*,nominal_bindings=None):
    source=Path(source);destination=Path(destination)
    separate_output(source,destination,destination.with_suffix('.isolated.dxf'),destination.with_suffix('.pending.dxf'))
    if digest(source)!=source_hash:raise ValueError('File nguồn đã thay đổi; lập kế hoạch lại')
    if not {op.ref for op in operations}<=allowed_refs:raise ValueError('Thao tác ngoài phạm vi chọn')
    from cad.capabilities import report as capabilities,validate_operations as validate_capability_operations
    validate_capability_operations(capabilities(source),operations)
    nominal_bindings=nominal_bindings or {}
    if any(ref not in allowed_refs or b.get('source_hash')!=source_hash or b.get('dimension_ref')!=ref for ref,b in nominal_bindings.items()):
        raise ValueError('Binding kích thước danh nghĩa không khớp nguồn/phạm vi')
    import json
    styles={json.loads(op.after).get('style_ref') for op in operations if op.action=='append_geometry'}
    if not styles<=allowed_refs:raise ValueError('Style cạnh mới ngoài phạm vi chọn')
    from cad.block_isolation import isolate
    prepared=destination.with_suffix('.isolated.dxf')
    candidate,mapping,clones=isolate(source,prepared,{op.ref for op in operations}|
                                    {op.mirror_ref for op in operations if op.mirror_ref},operations)
    if candidate is None:return _apply_unisolated(source,destination,operations,allowed_refs,source_hash,nominal_bindings=nominal_bindings)
    mapped=[];slots={};originals={}
    for op in operations:
        changed=op.model_copy(update={'ref':mapping.get(op.ref,op.ref),'mirror_ref':mapping.get(op.mirror_ref,op.mirror_ref)})
        slot=(changed.ref.split('/')[-1],changed.cell_index if changed.action=='table_cell' else -1)
        if slot in slots:
            first=slots[slot]
            if first.ref==changed.ref:
                prepared.unlink(missing_ok=True)
                raise ValueError('Một entity/ô có nhiều thao tác trùng lặp')
            if {k:v for k,v in first.model_dump().items() if k not in ('ref','reason')}!={k:v for k,v in changed.model_dump().items() if k not in ('ref','reason')}:
                prepared.unlink(missing_ok=True)
                raise ValueError('Block cùng bản sửa có thao tác xung đột')
            originals[slot].append(op.ref)
        else:slots[slot]=changed;mapped.append(changed);originals[slot]=[op.ref]
    shared={c['new_block']:set(c['instance_paths']) for c in clones if len(c.get('instance_paths',[]))>1}
    try:
        candidate_hash=digest(candidate)
        mapped_nominals={mapping.get(ref,ref):dict(binding,dimension_ref=mapping.get(ref,ref),source_hash=candidate_hash) for ref,binding in nominal_bindings.items()}
        report=_apply_unisolated(candidate,destination,mapped,{op.ref for op in mapped}|styles,candidate_hash,shared,nominal_bindings=mapped_nominals)
        report['prepared_hash']=report['source_hash'];report['source_hash']=source_hash
        report['block_isolation']=clones
        report['planned_operation_count']=len(operations)
        for edited in report['changes']:
            slot=(edited['ref'].split('/')[-1],edited['cell_index'] if edited['action']=='table_cell' else -1)
            edited['original_refs']=originals[slot];edited['original_ref']=originals[slot][0]
        if digest(source)!=source_hash:raise ValueError('File nguồn đã đổi trong lúc tạo bản mới; chưa chấp nhận bản sửa')
        report.update(source_unchanged=True,write_policy='new_file_only')
        return report
    finally:
        prepared.unlink(missing_ok=True)


def _apply_unisolated(source,destination,operations,allowed_refs,source_hash,shared_blocks=None,*,nominal_bindings=None):
    source=Path(source)
    separate_output(source,destination,Path(destination).with_suffix('.pending.dxf'))
    if digest(source)!=source_hash:raise ValueError('File nguồn đã thay đổi; lập kế hoạch lại')
    if not operations:raise ValueError('Kế hoạch không có thao tác thực thi')
    doc=ezdxf.readfile(source)
    if doc.dxfversion<'AC1021':raise ValueError('Engine hiện yêu cầu DXF UTF-8 R2007 trở lên')
    data=source.read_bytes()
    if data.startswith(b'AutoCAD Binary DXF'):raise ValueError('Chưa hỗ trợ DXF binary')
    lines=data.splitlines(keepends=True)
    if len(lines)%2:raise ValueError('Cấu trúc DXF không hợp lệ')
    spans={h:(a,b) for h,a,b in chunks(lines)}
    from cad.dimension_associations import validate_sources
    association_sources=validate_sources(doc,operations,{h:lines[a:b] for h,(a,b) in spans.items() if doc.entitydb.get(h) is not None and doc.entitydb[h].dxftype()=='DIMASSOC'})
    used=set();used_handles=set()
    changes={}
    audit=[]
    generated_blocks=[]
    generated_entities=[]
    added_by_ref={}
    associations=[]
    attribute_moves=[]
    native_cells=None;native_bindings={}
    reference_counts={};reference_roots={}
    # A classic polyline is one logical object with several raw entity records.
    # Never permit a second operation to overwrite one of its sequence members.
    requested_handles={op.ref.split('/')[-1] for op in operations}
    for op in operations:
        entity=doc.entitydb.get(op.ref.split('/')[-1])
        if entity is not None and entity.dxftype()=='POLYLINE' and op.action=='replace_geometry':
            members={e.dxf.handle for e in [*entity.vertices,entity.seqend]}
            if members & requested_handles:raise ValueError('POLYLINE và VERTEX/SEQEND có thao tác chồng nhau')
    for e in doc.entitydb.values():
        name=e.dxf.name if e.dxftype()=='INSERT' else e.dxf.get('geometry','') if e.dxftype()=='ACAD_TABLE' else None
        if name:
            reference_counts[name]=reference_counts.get(name,0)+1
            reference_roots.setdefault(name,set()).add(e.dxf.handle)
    for name,roots in (shared_blocks or {}).items():
        if roots!=reference_roots.get(name,set()):raise ValueError('Phạm vi block dùng chung mới không khớp toàn bộ instance đã tách')
    # Shared definition edits must not silently affect unselected instances.
    for op in operations:
        if op.ref not in allowed_refs:raise ValueError('Thao tác ngoài phạm vi chọn')
        handle=op.ref.split('/')[-1]
        slot=op.cell_index if op.action=='table_cell' else -1
        if (handle,slot) in used or (handle,-1) in used or (slot==-1 and handle in used_handles):
            raise ValueError('Một entity/ô có nhiều thao tác xung đột; gộp kế hoạch trước')
        used.add((handle,slot));used_handles.add(handle)
        entity=doc.entitydb.get(handle)
        if entity is None or handle not in spans:raise ValueError('Entity không tồn tại trong file gốc')
        if '/' in op.ref:
            owner=doc.entitydb.get(entity.dxf.owner)
            name=owner.dxf.get('name','') if owner else ''
            instance_attribute=entity.dxftype()=='ATTRIB' and owner is not None and owner.dxftype()=='INSERT' and any(a.dxf.handle==handle for a in owner.attribs)
            if not instance_attribute and reference_counts.get(name,0)>1 and name not in (shared_blocks or {}):raise ValueError('Block definition dùng chung: cần clone instance trước khi sửa')
        a,b=spans[handle];replacement=list(changes[a][1] if a in changes else lines[a:b]);kind=entity.dxftype()
        if kind=='POLYLINE' and op.action=='replace_geometry':
            from cad.legacy_polyline import sequence_span
            a,b=sequence_span(entity,spans,lines);replacement=list(lines[a:b])
        def set_value(code,value):
            positions=[j for j in range(0,len(replacement),2) if replacement[j].strip()==str(code).encode()]
            if len(positions)!=1:raise ValueError('Group code thiếu hoặc không duy nhất')
            newline=b'\r\n' if replacement[positions[0]+1].endswith(b'\r\n') else b'\n'
            replacement[positions[0]+1]=str(value).encode('utf8')+newline
        if op.action=='append_geometry':
            from cad.native_additions import add_lines
            additions=add_lines(doc,entity,op.before,op.after,allowed_refs)
            generated_entities.extend(additions)
            added_by_ref[op.ref]=[{k:v for k,v in item.items() if k!='raw'} for item in additions]
        elif op.action=='remove_insert':
            import json
            actual={'name':entity.dxf.get('name'),'position':list(entity.dxf.get('insert')),
                    'scale':[entity.dxf.xscale,entity.dxf.yscale,entity.dxf.zscale],'rotation':entity.dxf.rotation}
            if kind!='INSERT' or '/' in op.ref or entity.attribs or entity.has_extension_dict or entity.get_reactors():
                raise ValueError('Chỉ bỏ instance tĩnh trong layout, không có attribute/association')
            owner=doc.entitydb.get(entity.dxf.owner)
            if owner is None or not owner.dxf.get('layout') or json.loads(op.before)!=actual or op.after or op.xyz:
                raise ValueError('Instance bỏ khỏi bản cắt không khớp nguồn/layout')
            replacement=[]
        elif op.action=='move_text':
            from cad.text_motion import patch as move_text
            replacement,text_after=move_text(entity,replacement,op)
        elif op.action=='replace_geometry':
            import json
            if kind=='DIMENSION':
                from cad.dimensions import regenerate
                from cad.dimension_associations import update
                raw_objects={}
                if entity.has_extension_dict:
                    extension=entity.get_extension_dict()
                    if 'ACAD_DIMASSOC' in extension:
                        association_handle=extension['ACAD_DIMASSOC'].dxf.handle
                        oa,ob=spans[association_handle];raw_objects[association_handle]=lines[oa:ob]
                try:object_updates=update(entity,json.loads(op.before),json.loads(op.after),operations,raw_objects)
                except ValueError as error:raise ValueError(f'DIM #{entity.dxf.handle}: {error}') from error
                for h,raw,association in object_updates:
                    oa,ob=spans[h]
                    if oa in changes:raise ValueError('DIMASSOC có thao tác trùng')
                    changes[oa]=(ob,raw);associations.append(association)
                from cad.broken_tube import valid_binding
                nominal_binding=(nominal_bindings or {}).get(op.ref)
                nominal_checked=valid_binding(nominal_binding,op.ref,json.loads(op.before),json.loads(op.after),source_hash)
                if nominal_binding and not nominal_checked:raise ValueError('Binding DIM danh nghĩa không khớp phép sửa đã kiểm chứng')
                replacement,blocks=regenerate(entity,json.loads(op.before),json.loads(op.after),association_checked=bool(object_updates),nominal_checked=nominal_checked)
                generated_blocks.extend(blocks)
            else:
                from cad.geometry import patch_geometry
                replacement=patch_geometry(entity,replacement,json.loads(op.before),json.loads(op.after))
        elif op.action=='table_cell':
            if kind!='ACAD_TABLE':raise ValueError('table_cell cần ACAD_TABLE')
            starts=[j for j in range(0,len(replacement),2) if replacement[j].strip()==b'301' and replacement[j+1].strip()==b'CELL_VALUE']
            if op.cell_index<0 or op.cell_index>=len(starts):raise ValueError('Cell index không hợp lệ')
            start=starts[op.cell_index];end=starts[op.cell_index+1] if op.cell_index+1<len(starts) else len(replacement)
            from cad.table_data import cell_value
            value,positions,value_type=cell_value(replacement,start,end)
            if not positions or value!=op.before:raise ValueError('Cell encoding/before không khớp; cần adapter native')
            if value_type=='1':
                try:
                    if str(int(op.after))!=op.after:raise ValueError()
                except ValueError:raise ValueError('Ô số nguyên native chỉ nhận số nguyên chuẩn')
            mirror=next((o for o in operations if o.ref==op.mirror_ref and o.action=='replace_text' and o.before==op.before and o.after==op.after),None)
            if mirror is None or not op.mirror_ref.startswith(op.ref+'/'):raise ValueError('Bảng cần thao tác đồng bộ text hiển thị trong geometry của bảng')
            from cad.table_data import table_cells
            from cad.table_bindings import bind_cells
            if native_cells is None:native_cells=table_cells(source)
            if handle not in native_bindings:native_bindings[handle]={b['cell_index']:b for b in bind_cells(entity,native_cells.get(handle,[]),doc)}
            binding=native_bindings[handle].get(op.cell_index)
            if binding is None or binding['mirror_handle']!=op.mirror_ref.split('/')[-1]:
                raise ValueError('Không chứng minh được liên kết ô với geometry mirror; cần binding native trước sửa')
            if '\n' in op.after or '\r' in op.after:raise ValueError('Cell không nhận newline raw')
            for j in positions:
                newline=b'\r\n' if replacement[j+1].endswith(b'\r\n') else b'\n'
                replacement[j+1]=op.after.encode('utf8')+newline
        elif op.action=='replace_text':
            if kind not in ('TEXT','MTEXT','ATTRIB','DIMENSION'):raise ValueError('Thay text chỉ hỗ trợ TEXT/MTEXT/ATTRIB/DIMENSION; chưa sửa ô bảng native')
            raw=entity.text if kind=='MTEXT' else entity.dxf.text
            if not op.before or raw!=op.before:raise ValueError('Text trước sửa không khớp nguyên văn')
            if '\n' in op.after or '\r' in op.after:raise ValueError('Dùng mã MTEXT \\P thay newline')
            if kind=='MTEXT':
                from cad.mtext_content import patch as patch_mtext
                replacement=patch_mtext(replacement,op.after)
            elif kind=='DIMENSION':
                positions=[j for j in range(0,len(replacement),2) if replacement[j].strip()==b'1']
                if len(positions)!=1 or len(op.after)>255:raise ValueError('DIMENSION text cần đúng 1 group code 1')
                set_value(1,op.after)
            else:
                positions=[j for j in range(0,len(replacement),2) if replacement[j].strip() in (b'1',b'3')]
                if len(positions)!=1 or len(op.after)>255:raise ValueError('TEXT/ATTRIB dài cần adapter riêng')
                set_value(1,op.after)
        else:
            if len(op.xyz)!=3 or not all(math.isfinite(v) for v in op.xyz):raise ValueError('Tọa độ phải có ba giá trị hữu hạn')
            if op.action=='line_end' and kind=='LINE':
                old=list(entity.dxf.end);codes=(11,21,31)
                if sum((a-b)**2 for a,b in zip(entity.dxf.start,op.xyz))<1e-12:raise ValueError('Không tạo LINE có chiều dài bằng 0')
            elif op.action=='move_insert' and kind=='INSERT':
                old=list(entity.dxf.insert);codes=(10,20,30)
                from cad.insert_motion import attribute_updates
                updates=attribute_updates(entity,[b-a for a,b in zip(old,op.xyz)],spans,lines,changes)
                for item in updates:changes[item['start']]=(item['end'],item['raw'])
                attribute_moves.extend(updates)
            else:raise ValueError('Thao tác hình học không phù hợp loại entity')
            import json
            if json.loads(op.before)!=old:raise ValueError('Tọa độ trước sửa không khớp')
            for code,value in zip(codes,op.xyz):set_value(code,value)
        changes[a]=(b,replacement)
        entry=op.model_dump()
        if op.action=='move_text':entry['text_motion_after']=text_after
        if op.action=='append_geometry':entry['added_entities']=added_by_ref[op.ref]
        audit.append(entry)
    from cad.dimensions import new_block_insertions
    inserts=new_block_insertions(lines,generated_blocks,doc)
    from cad.native_additions import insertions
    inserts=insertions(lines,generated_entities,doc,inserts)
    output=[];i=0
    while i<len(lines):
        if i in inserts:output.extend(inserts[i])
        if i in changes:
            end,replacement=changes[i];output.extend(replacement);i=end
        else:output.append(lines[i]);i+=1
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.pending.dxf')
    temporary.write_bytes(b''.join(output))
    reread=ezdxf.readfile(temporary)
    try:
        from cad.insert_motion import verify as verify_attributes
        verify_attributes(reread,attribute_moves)
        reopened_cells=None
        for op in operations:
            e=reread.entitydb.get(op.ref.split('/')[-1])
            if op.action=='append_geometry':
                import json
                from cad.geometry import snapshot,near
                if not near(snapshot(e),json.loads(op.before)):raise ValueError('Thêm cạnh đã làm thay đổi khung nguồn')
                for item in added_by_ref[op.ref]:
                    created=reread.entitydb.get(item['handle'])
                    if created is None or not near(snapshot(created),item['geometry']) or created.dxf.layer!=item['layer'] or created.dxf.owner!=item['owner']:
                        raise ValueError('Validation cạnh CAD bổ sung thất bại')
            elif op.action=='remove_insert':
                if e is not None:raise ValueError('Validation instance bỏ khỏi bản cắt thất bại')
            elif op.action=='move_text':
                from cad.text_motion import snapshot as text_snapshot
                from cad.geometry import near
                expected=next(item['text_motion_after'] for item in audit if item['ref']==op.ref)
                if not near(text_snapshot(e),expected):raise ValueError('Validation vị trí chữ/căn lề thất bại')
            elif op.action=='replace_geometry':
                import json
                from cad.geometry import snapshot,near
                if not near(snapshot(e),json.loads(op.after)):raise ValueError('Validation geometry thất bại')
            elif op.action=='table_cell':
                from cad.table_data import table_cells
                if reopened_cells is None:reopened_cells=table_cells(temporary)
                cells=reopened_cells.get(e.dxf.handle,[])
                if next((c['raw_text'] for c in cells if c['index']==op.cell_index),None)!=op.after:raise ValueError('Validation ô bảng thất bại')
            elif op.action=='replace_text':
                actual=e.text if e.dxftype()=='MTEXT' else e.dxf.text
                if actual!=op.after:raise ValueError('Validation text thất bại')
            else:
                actual=list(e.dxf.end if op.action=='line_end' else e.dxf.insert)
                if any(abs(a-b)>1e-8 for a,b in zip(actual,op.xyz)):raise ValueError('Validation tọa độ thất bại')
        if sum(e.dxftype()=='ACAD_TABLE' for e in doc.entitydb.values())!=sum(e.dxftype()=='ACAD_TABLE' for e in reread.entitydb.values()):
            raise ValueError('Số bảng CAD thay đổi ngoài kế hoạch')
        from cad.dimension_associations import verify
        verify(reread,associations)
        if digest(source)!=source_hash:raise ValueError('File nguồn đã đổi trong lúc tạo bản mới; chưa chấp nhận bản sửa')
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {'status':'validated','source_hash':source_hash,'output_hash':digest(destination),'source_unchanged':True,'write_policy':'new_file_only','changes':audit,'native_associations':associations,'association_sources':association_sources,
            'attribute_moves':[{k:v for k,v in item.items() if k not in ('raw','start','end')} for item in attribute_moves],
            'limitations':['Kiểm tra dữ liệu và phạm vi; chưa kiểm chứng cơ học/lắp ghép hoặc fidelity trong CAD đích.']}
