"""Select placed CAD entities without rewriting unsupported native TABLE data.

Definitions/resources are retained deliberately. This is a drawing-scope export,
not a confidential-data purge of unused block definitions.
"""
from collections import Counter
from pathlib import Path
import math
from cad.catalog import load_document
from cad.edit_engine import digest

POLICY_VERSION = 5


def fit_initial_view(lines, selected):
    """A scoped DWG must open on its retained drawings, not the old file view."""
    from ezdxf import bbox
    if not len(selected.modelspace()):return lines,None
    bounds=bbox.extents(selected.modelspace(),fast=True)
    if not bounds.has_data:return lines,None
    low,high=bounds.extmin,bounds.extmax
    coordinates=[low.x,low.y,low.z,high.x,high.y,high.z]
    if not all(math.isfinite(v) for v in coordinates):raise ValueError('Phạm vi CAD có tọa độ không hữu hạn')
    center=[(low.x+high.x)/2,(low.y+high.y)/2]
    width,height=high.x-low.x,high.y-low.y
    wanted={'$EXTMIN':{10:low.x,20:low.y,30:low.z},'$EXTMAX':{10:high.x,20:high.y,30:high.z},
            '$LIMMIN':{10:low.x,20:low.y},'$LIMMAX':{10:high.x,20:high.y},'$TILEMODE':{70:1},'$CTAB':{1:'Model'}}
    def value(index, replacement):
        newline=b'\r\n' if lines[index].endswith(b'\r\n') else b'\n'
        lines[index]=str(replacement).encode('utf8')+newline
    header=False;key=None
    view_height=None
    for start,end,tags in records(lines):
        if tags[0]==(0,'SECTION'):header=(2,'HEADER') in tags
        if header:
            for i in range(start,end,2):
                code=int(lines[i]);text=lines[i+1].strip().decode('utf8')
                if code==9:key=text
                elif key in wanted and code in wanted[key]:value(i+1,wanted[key][code])
        if tags[0]==(0,'VPORT') and (2,'*Active') in tags:
            ratio=next((float(v) for c,v in tags if c==41),1.5)
            if not math.isfinite(ratio) or ratio<=0:ratio=1.5
            view_height=max(height,width/ratio,1)*1.1
            values={12:center[0],22:center[1],40:view_height,16:0,26:0,36:1,17:0,27:0,37:0,51:0}
            for i in range(start,end,2):
                code=int(lines[i])
                if code in values:value(i+1,values[code])
        if tags[0]==(0,'ENDSEC'):header=False
        if tags[0]==(0,'SECTION') and any(s in tags for s in ((2,'BLOCKS'),(2,'ENTITIES'))):break
    return lines,dict(layout='Model',bbox=coordinates,center=center,height=view_height)


def records(lines):
    if len(lines) % 2:
        raise ValueError('DXF không có các cặp group code đầy đủ')
    starts = [i for i in range(0, len(lines), 2) if lines[i].strip() == b'0']
    starts.append(len(lines))
    for start, end in zip(starts, starts[1:]):
        tags = [(int(lines[i]), lines[i+1].strip().decode('utf8')) for i in range(start, end, 2)]
        yield start, end, tags


def select_entities(source, destination, keep_handles, keep_refs=None):
    """Isolate conflicting static placements in an export-only temporary copy."""
    from tempfile import TemporaryDirectory
    from cad.nested_scope_export import ScopeConflict,mapped_ref,clone_mappings,check_clone_dependencies,verify_copies,verify
    source,destination=Path(source),Path(destination)
    from cad.edit_engine import separate_output
    separate_output(source,destination,destination.with_suffix('.tmp.dxf'))
    keep_handles=set(keep_handles);keep_refs=None if keep_refs is None else set(keep_refs)
    source_hash=digest(source)
    try:return _select_entities(source,destination,keep_handles,keep_refs)
    except ScopeConflict as conflict:conflicts=conflict.conflicts
    destination.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='scope-isolation-',dir=destination.parent) as scratch:
        folder=Path(scratch);doc=load_document(str(source));witnesses=[]
        for name,paths in sorted(conflicts.items()):
            members=sorted(e.dxf.handle for e in doc.blocks[name])
            for path,mask in sorted(paths.items()):
                # Even an empty mask needs its own definition, then is pruned.
                witnesses.append(path+'/'+min(mask or members))
        from cad.block_isolation import isolate
        isolated,_,clones=isolate(source,folder/'isolated.dxf',witnesses)
        if isolated is None:raise ValueError('Không cô lập được các instance xuất khác phạm vi')
        check_clone_dependencies(doc,records(source.read_bytes().splitlines(keepends=True)),clones)
        mappings=clone_mappings(clones)
        refs={mapped_ref(ref,maps=mappings) for ref in keep_refs}
        staged=folder/'selection.dxf'
        report=_select_entities(isolated,staged,keep_handles,refs)
        selected=load_document(str(staged));omitted=report['nested_selection']['removed_handles']
        verify_copies(doc,selected,clones,omitted)
        blocks=[]
        for clone in clones:
            block=selected.blocks[clone['new_block']]
            entry=dict(name=block.name,kept_members=[dict(handle=e.dxf.handle,type=e.dxftype()) for e in block])
            if block.block_record.has_extension_dict:
                sort=block.block_record.get_extension_dict()['ACAD_SORTENTS']
                entry.update(sortents_handle=sort.dxf.handle,sortents=dict(sort.table))
            blocks.append(entry)
        report.update(source_hash=source_hash,export_isolation=clones,isolated_blocks=blocks)
        verify(selected,report)
        if digest(source)!=source_hash:raise ValueError('File nguồn đã đổi khi cô lập phạm vi xuất')
        staged.replace(destination)
        return report


def _select_entities(source, destination, keep_handles, keep_refs=None):
    """Keep complete INSERT/ATTRIB and POLYLINE/VERTEX sequences in ENTITIES."""
    source, destination = Path(source), Path(destination)
    from cad.edit_engine import separate_output
    separate_output(source,destination,destination.with_suffix('.tmp.dxf'))
    before_hash = digest(source)
    doc = load_document(str(source))
    top = {e.dxf.handle: e for layout in doc.layouts for e in layout}
    keep = set(keep_handles)
    if not keep or not keep <= top.keys():
        raise ValueError('Phạm vi xuất thiếu hoặc có đối tượng không thuộc layout')
    raw = source.read_bytes()
    if raw.startswith(b'AutoCAD Binary DXF'):
        raise ValueError('Xuất phạm vi cần DXF ASCII từ bộ chuyển đổi')
    lines = raw.splitlines(keepends=True)
    parts = list(records(lines))
    nested=None
    if keep_refs is not None:
        from cad.nested_scope_export import plan,check_dependencies
        nested=plan(doc,keep,keep_refs)
        serialized={v for _,_,tags in parts for c,v in tags if c==5}
        # ezdxf creates missing, un-serialized SEQEND objects on read. Those
        # temporary handles may be reused and are not source objects to remove.
        nested['removed_handles']=[h for h in nested['removed_handles'] if h in serialized]
        check_dependencies(doc,parts,nested,keep,top)
    removed=set(nested['removed_handles']) if nested else set()
    blockrefs={}
    for e in doc.entitydb.values():
        if e.dxftype()=='INSERT' and e.dxf.handle not in removed and (e.dxf.handle not in top or e.dxf.handle in keep):
            blockrefs.setdefault(e.dxf.name,[]).append(e.dxf.handle)
    # A measured dimension cannot silently lose its native snap reference.
    for _, _, tags in parts:
        if tags[0] != (0, 'DIMASSOC'):
            continue
        marker = next((i for i, pair in enumerate(tags) if pair == (100, 'AcDbDimAssoc')), None)
        if marker is None:
            continue
        refs = {v for c, v in tags[marker+1:] if c in (330, 331, 332) and v in top}
        if refs & keep and refs - keep:
            raise ValueError('Liên kết DIMASSOC vượt phạm vi xuất; cần thêm khung liên quan: '+', '.join(sorted(refs-keep)))
    output = []
    section = None
    sequence = None
    seen = set()
    for start, end, tags in parts:
        kind = tags[0][1]
        handle = next((v for c, v in tags if c == 5), None)
        if kind == 'SECTION':
            section = next((v for c, v in tags if c == 2), None)
        # Non-active paperspaces are serialized inside *Paper_Space BLOCKS.
        # Their placed entities must be filtered too; ordinary definitions stay.
        scoped_record=(section == 'ENTITIES' and kind not in ('SECTION', 'ENDSEC') or
                       section == 'BLOCKS' and (handle in top or handle in removed or sequence is not None))
        if scoped_record:
            if kind in ('VERTEX', 'ATTRIB', 'SEQEND'):
                if sequence is None:
                    raise ValueError('Chuỗi POLYLINE/INSERT không có đối tượng cha')
                retained = sequence
                if kind == 'SEQEND':
                    sequence = None
            else:
                if sequence is not None:
                    raise ValueError('Chuỗi POLYLINE/INSERT thiếu SEQEND')
                if handle not in top and handle not in removed:
                    raise ValueError('Không xác định được chủ sở hữu đối tượng ENTITIES: '+str(handle))
                if handle in top:seen.add(handle)
                retained = handle in keep and handle not in removed
                if kind == 'POLYLINE' or kind == 'INSERT' and (66, '1') in tags:
                    sequence = retained
            if not retained:
                continue
        if kind == 'ENDSEC':
            if sequence is not None:
                raise ValueError('Chuỗi CAD chưa kết thúc khi hết ENTITIES')
            section = None
        if kind=='BLOCK_RECORD' and (102,'{BLKREFS') in tags:
            from cad.nested_scope_export import rebuild_blkrefs
            output.extend(rebuild_blkrefs(lines[start:end],sorted(blockrefs.get(doc.entitydb[handle].dxf.name,[]))))
        elif nested and handle in nested['sortents']:
            from cad.nested_scope_export import filter_sortents
            output.extend(filter_sortents(lines[start:end],nested['sortents'][handle]))
        else:output.extend(lines[start:end])
    if seen != top.keys():
        raise ValueError('Danh mục ENTITIES không khớp dữ liệu CAD đã đọc')
    payload = b''.join(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp.dxf')
    temporary.write_bytes(payload)
    try:
        selected = load_document(str(temporary))
        actual = {e.dxf.handle for layout in selected.layouts for e in layout}
        if actual != keep:
            raise ValueError('Xuất phạm vi không giữ đúng danh mục đối tượng đã chọn')
        nested_report=None
        if nested is not None:
            from cad.nested_scope_export import verify
            nested_report={k:nested[k] for k in ('removed_handles','trimmed_blocks','atomic_borders','placed_blocks')}
            verify(selected,dict(nested_selection=nested_report,block_reference_index_rebuilt=True))
        from cad.table_data import table_cells
        original_cells = table_cells(source)
        selected_cells = table_cells(temporary)
        if selected_cells != {h: v for h, v in original_cells.items() if h in selected.entitydb}:
            raise ValueError('Xuất phạm vi làm thay đổi dữ liệu bảng CAD')
        fitted,initial_view=fit_initial_view(output,selected)
        temporary.write_bytes(b''.join(fitted))
        if digest(source) != before_hash:
            raise ValueError('File nguồn đã đổi khi tách phạm vi')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return dict(policy_version=POLICY_VERSION, source_hash=before_hash, output_hash=digest(destination),
                kept_entity_count=len(keep), removed_entity_count=len(top)-len(keep),
                layouts={layout.name: dict(Counter(e.dxftype() for e in layout)) for layout in selected.layouts},
                retained_resources=True,initial_view=initial_view,nested_selection=nested_report,block_reference_index_rebuilt=True)
