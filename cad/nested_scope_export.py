"""Prune static drawing containers using source-selected native instance paths.

Keep native coordinates and resource definitions. Conflicting static placements
are isolated in the export copy before pruning; source paths map to their copies.
Unknown dependencies are an error, never an excuse to detach associations.
"""
from collections import defaultdict


class ScopeConflict(ValueError):
    """Valid native paths require different members of a shared definition."""
    def __init__(self, conflicts):
        self.conflicts=conflicts
        super().__init__('Các instance dùng chung block cần tách phạm vi khác nhau: '+', '.join(sorted(conflicts)))


def path_entity(doc,ref):
    parts=ref.split('/');current=doc.entitydb.get(parts[0])
    if current is None:raise ValueError('Thiếu đối tượng trong đường dẫn xuất: '+ref)
    for h in parts[1:]:
        child=doc.entitydb.get(h)
        if child is None:raise ValueError('Thiếu đối tượng trong đường dẫn xuất: '+ref)
        if current.dxftype()=='INSERT' and child.dxftype()=='ATTRIB' and child.dxf.owner==current.dxf.handle:
            current=child;continue
        name=current.dxf.name if current.dxftype()=='INSERT' else current.dxf.get('geometry','') if current.dxftype()=='ACAD_TABLE' else None
        block=doc.blocks.get(name) if name else None
        if block is None or child.dxf.owner!=block.block_record_handle:raise ValueError('Đường dẫn CAD không thuộc block nguồn: '+ref)
        current=child
    return current


def zoned_border(block):
    """Recognize a flat zone-grid resource, not a drawing/title container.

    One rectangular polyline, edge-band rules and single letter/number labels
    prove a border. Interior geometry, DIMs, inserts and product text fail.
    """
    import re
    from cad.block_frames import rectangles
    from cad.catalog import text_of
    entities=list(block)
    if not entities or any(e.dxftype() not in ('LWPOLYLINE','LINE','TEXT','MTEXT') for e in entities):return False
    outlines=[e for e in entities if e.dxftype()=='LWPOLYLINE']
    if len(outlines)!=1:return False
    borders=list(rectangles(outlines))
    if len(borders)!=1:return False
    points=borders[0][1];x0,y0=min(p[0] for p in points),min(p[1] for p in points);x1,y1=max(p[0] for p in points),max(p[1] for p in points)
    if min(x1-x0,y1-y0)<20:return False
    # The outer edge band also includes short crop marks just outside the
    # border. These are source annotations, never interior drawing geometry.
    margin=min(x1-x0,y1-y0)*.08;letters=set();numbers=set()
    def band(p):
        x,y,z=p
        return abs(z)<1e-7 and x0-margin<=x<=x1+margin and y0-margin<=y<=y1+margin and min(abs(x-x0),abs(x-x1),abs(y-y0),abs(y-y1))<=margin
    for e in entities:
        if e.dxftype()=='LINE':
            p,q=e.dxf.start,e.dxf.end
            if abs(p.x-q.x)>1e-7 and abs(p.y-q.y)>1e-7 or not all(band(v) for v in (p,q,(p+q)/2)):return False
        elif e.dxftype() in ('TEXT','MTEXT'):
            text=(text_of(e) or '').strip().upper()
            if not re.fullmatch(r'[A-Z]|\d{1,2}',text) or not band(e.dxf.insert):return False
            (letters if text.isalpha() else numbers).add(text)
    return len(letters)>=2 and len(numbers)>=2


def zoned_form(block):
    """A complete static paper form is atomic, including native text fields.

    Require a zone grid and title labels with an empty central drawing area.
    Geometry in that area, dimensions or tables make it a drawing container,
    which must continue through the ordinary selection/dependency checks.
    """
    import re
    from ezdxf import bbox
    from cad.block_frames import rectangles
    from cad.catalog import text_of
    from bom.reader import normalized
    items=list(block)
    if not items or any(e.dxftype() not in ('LINE','LWPOLYLINE','CIRCLE','ARC','ELLIPSE','TEXT','MTEXT','SOLID','INSERT') for e in items):return False
    borders=list(rectangles([e for e in items if e.dxftype()=='LWPOLYLINE']))
    if len(borders)!=1:return False
    _,points=borders[0];x0,x1=min(p[0] for p in points),max(p[0] for p in points);y0,y1=min(p[1] for p in points),max(p[1] for p in points)
    w,h=x1-x0,y1-y0
    if min(w,h)<20:return False
    margin=min(w,h)*.08;letters=set();numbers=set();labels=set()
    keys=('nguoi lap','kiem tra','duyet','ten san pham','ma tp','ma btp','vat lieu','so luong','ngay ve','muc dich su dung')
    for e in items:
        if e.dxf.handle==borders[0][0]:continue
        box=bbox.extents([e],fast=True)
        if not box.has_data:return False
        a,b=box.extmin,box.extmax
        if max(abs(a.z),abs(b.z))>1e-6 or a.x<x0-margin or b.x>x1+margin or a.y<y0-margin or b.y>y1+margin:return False
        # Whole entity bounds, not only insertion points, must stay out of
        # the central drawing field. Includes the nested company logo.
        band=b.y<=y0+.18*h or a.y>=y1-margin or b.x<=x0+margin or a.x>=x1-margin
        if e.dxftype()=='LINE':
            p,q=e.dxf.start,e.dxf.end
            band=band or abs(p.y-q.y)<1e-7 and p.y<=y0+.18*h
        if not band:return False
        if e.dxftype() in ('TEXT','MTEXT'):
            text=(text_of(e) or '').strip();plain=normalized(text)
            if re.fullmatch(r'[A-Z]|\d{1,2}',text):
                (letters if text.isalpha() else numbers).add(text)
            if e.dxf.insert.y<=y0+.18*h:
                labels.update(k for k in keys if plain.startswith(k))
    return len(letters)>=2 and len(numbers)>=2 and len(labels)>=6


def clone_mappings(clones):
    return {p:c['handle_map'] for c in clones for p in c.get('instance_paths',[c['instance_path']])}


def mapped_ref(ref,clones=(),*,maps=None):
    maps=clone_mappings(clones) if maps is None else maps
    path=ref.split('/');result=[path[0]]
    for i,handle in enumerate(path[1:],1):
        mapped=handle
        for n in range(i,0,-1):
            mapping=maps.get('/'.join(path[:n]),{})
            if handle in mapping:mapped=mapping[handle];break
        result.append(mapped)
    return '/'.join(result)


def check_clone_dependencies(doc,parts,clones):
    """Only remap dependencies proved internal to one copied definition.

    Shared resources (styles/layers) can remain shared. Cross-definition native
    geometry pointers need an association adapter, not a guess at placement.
    """
    from ezdxf.entities import DXFGraphic
    groups=defaultdict(set)
    for i,clone in enumerate(clones):
        for handle in clone['handle_map']:groups[handle].add(i)
        for prefix in clone.get('instance_paths',[clone['instance_path']]):
            parent=path_entity(doc,prefix);block=doc.blocks[parent.dxf.name]
            if parent.has_extension_dict or parent.get_reactors() or block.block_record.get_reactors():
                raise ValueError('Chưa hỗ trợ cô lập instance có association/động khi xuất: '+prefix)
    for _,_,tags in parts:
        tags=without_blkrefs(tags)
        handle=next((v for c,v in tags if c==5),None)
        for code,target in tags:
            if not (code==1005 or 330<=code<=369 or 390<=code<=399 or code in (480,481)):continue
            same=groups.get(handle,set())&groups.get(target,set())
            if target in groups and not same:
                raise ValueError('Tham chiếu ngoài definition cần adapter trước khi cô lập xuất: '+target)
            if handle in groups and not same and isinstance(doc.entitydb.get(target),DXFGraphic):
                raise ValueError('Liên kết hình học vượt definition khi cô lập xuất: '+target)


def copy_snapshot(entity):
    """Stable geometric/display properties preserved by static isolation/ODA."""
    from cad.geometry import snapshot
    kind=entity.dxftype();result=dict(type=kind)
    geometric={'LINE','LWPOLYLINE','POLYLINE','CIRCLE','ARC','ELLIPSE','SPLINE','DIMENSION','HATCH'}
    if kind in geometric:
        if kind=='HATCH':
            try:result['geometry']=snapshot(entity)
            except ValueError:
                from cad.hatch_translation import preserved_snapshot
                if entity.dxf.associative:
                    from cad.hatch_association import source_snapshot
                    result['geometry']=source_snapshot(entity)
                else:result['geometry']=preserved_snapshot(entity)
        else:result['geometry']=snapshot(entity)
    fields={
        'DICTIONARY':('hard_owned','cloning'),
        'INSERT':('insert','xscale','yscale','zscale','rotation','extrusion','row_count','column_count','row_spacing','column_spacing'),
        'TEXT':('text','insert','align_point','height','rotation','width','oblique','extrusion','halign','valign','style'),
        'ATTRIB':('text','tag','insert','align_point','height','rotation','width','oblique','extrusion','halign','valign','style','flags'),
        'ATTDEF':('text','tag','prompt','insert','align_point','height','rotation','width','oblique','extrusion','halign','valign','style','flags'),
        'MTEXT':('insert','char_height','width','rotation','text_direction','extrusion','attachment_point','style'),
        'SOLID':('vtx0','vtx1','vtx2','vtx3','extrusion'),
        'TRACE':('vtx0','vtx1','vtx2','vtx3','extrusion'),
        '3DFACE':('vtx0','vtx1','vtx2','vtx3','invisible_edges'),
        'POINT':('location','extrusion','angle'),
    }
    if kind=='MTEXT':result['text']=entity.text
    if kind=='DICTIONARY':result['entries']=sorted(entity.keys())
    for key in (*fields.get(kind,()),'layer','linetype','color','invisible'):
        if not entity.dxf.is_supported(key):continue
        value=entity.dxf.get_default(key)
        # Missing MTEXT width and an explicit zero both mean unbounded text.
        if kind=='MTEXT' and key=='width' and value is None:value=0.0
        if value is not None and not isinstance(value,(str,int,float,bool)):value=list(value)
        result[key]=value
    return result


def verify_copies(original,selected,clones,omitted=()):
    from cad.geometry import near
    omitted=set(omitted)
    for clone in clones:
        from cad.hatch_association import verify_mapping
        verify_mapping(original,selected,clone['handle_map'],omitted)
        for old,new in clone['handle_map'].items():
            if new in omitted:continue
            a,b=original.entitydb.get(old),selected.entitydb.get(new)
            if a is None or b is None or not near(copy_snapshot(a),copy_snapshot(b),1e-6):
                raise ValueError('Cô lập khi xuất không giữ đúng đối tượng nguồn: '+old)


def plan(doc,keep,refs):
    refs=set(refs);children=defaultdict(set);masks={};paths=defaultdict(list);borders={};atomic={};variants=defaultdict(dict)
    for ref in refs:
        parts=ref.split('/')
        if parts[0] not in keep:raise ValueError('Đường dẫn CAD ngoài phạm vi xuất: '+ref)
        path_entity(doc,ref)
        for i in range(1,len(parts)):children['/'.join(parts[:i])].add(parts[i])
    def visit(entity,path,trail=(),retain=False):
        if entity.dxftype()!='INSERT':return
        name=entity.dxf.name
        if name in trail or len(trail)>=128:raise ValueError('Block vòng/quá sâu khi tách phạm vi DWG')
        block=doc.blocks.get(name)
        if block is None:raise ValueError('Thiếu definition khi tách phạm vi: '+name)
        direct={e.dxf.handle:e for e in block};selected=children.get(path,set())
        # Instance ATTRIBs are serialized with their INSERT, not members of its
        # definition. Retain the entire native attribute sequence.
        selected=selected-{a.dxf.handle for a in entity.attribs}
        if not selected<=direct.keys():raise ValueError('Đường dẫn CAD không thuộc block: '+path)
        if name not in borders:borders[name]='native_zoned_border' if zoned_border(block) else 'native_drawing_form' if zoned_form(block) else None
        if retain or borders[name]:
            selected=set(direct)
            atomic[name]=dict(name=name,policy=borders[name] or 'native_form_resource',kept_members=[dict(handle=e.dxf.handle,type=e.dxftype()) for e in block])
        variants[name][path]=frozenset(selected)
        masks[name]=selected;paths[name].append(path)
        for h in selected:visit(direct[h],path+'/'+h,trail+(name,),retain=retain or bool(borders[name]))
    for h in keep:
        entity=doc.entitydb[h]
        visit(entity,h)
    conflicts={name:variants[name] for name in variants if len(set(variants[name].values()))>1}
    if conflicts:raise ScopeConflict(conflicts)
    removed=set();trimmed=[];sorts={}
    for name,mask in masks.items():
        block=doc.blocks[name];members=list(block)
        if len(mask)==len(members):continue
        if block.block.dxf.get('flags',0)&(4|8|16|32|64):raise ValueError('Không tách nội dung XREF/block phụ thuộc ngoài: '+name)
        if block.block_record.get_reactors() or block.block.has_extension_dict or block.block.get_reactors():
            raise ValueError('Block có association chưa hỗ trợ tách phạm vi: '+name)
        sort=None
        if block.block_record.has_extension_dict:
            extension=block.block_record.get_extension_dict()
            if set(extension.keys())!={'ACAD_SORTENTS'} or extension['ACAD_SORTENTS'].dxftype()!='SORTENTSTABLE':
                raise ValueError('Block động/proxy cần CAD host để tách phạm vi: '+name)
            sort=extension['ACAD_SORTENTS']
        for path in paths[name]:
            for h in path.split('/'):
                parent=doc.entitydb[h];ancestor=doc.blocks[parent.dxf.name]
                if parent.has_extension_dict or parent.get_reactors():raise ValueError('Instance có dữ liệu động/association chưa hỗ trợ tách phạm vi: '+path)
                keys=set(ancestor.block_record.get_extension_dict().keys()) if ancestor.block_record.has_extension_dict else set()
                if keys-{'ACAD_SORTENTS'} or ancestor.block_record.get_reactors() or ancestor.block.dxf.get('flags',0)&(4|8|16|32|64):
                    raise ValueError('Block cha có dữ liệu động/association chưa hỗ trợ tách phạm vi: '+path)
        for e in members:
            if e.dxf.handle in mask:continue
            if e.has_extension_dict or e.get_reactors() or e.dxftype() in ('ACAD_PROXY_ENTITY','ACAD_TABLE'):
                raise ValueError('Không tự loại đối tượng có dữ liệu native/association: '+e.dxf.handle)
            owned=[e]
            if e.dxftype()=='INSERT':owned.extend(e.attribs)
            if e.dxftype()=='POLYLINE':owned.extend(e.vertices)
            if e.dxftype() in ('INSERT','POLYLINE') and e.seqend is not None:owned.append(e.seqend)
            removed.update(x.dxf.handle for x in owned)
        entry=dict(name=name,paths=sorted(paths[name]),kept_members=[dict(handle=e.dxf.handle,type=e.dxftype()) for e in members if e.dxf.handle in mask])
        if sort is not None:
            table={h:s for h,s in sort.table.items() if h in mask}
            sorts[sort.dxf.handle]=table;entry.update(sortents_handle=sort.dxf.handle,sortents=table)
        trimmed.append(entry)
    # Exclude unused original definitions: only these placed paths constitute
    # the selected drawing. Native TABLE geometry stays atomic and unchanged.
    live=set();visited=set()
    def visible(e,trail=(),atomic=False):
        live.add(e.dxf.handle)
        if e.dxftype()=='POLYLINE':live.update(x.dxf.handle for x in e.vertices)
        if e.dxftype()=='INSERT':live.update(x.dxf.handle for x in e.attribs)
        name=e.dxf.name if e.dxftype()=='INSERT' else e.dxf.get('geometry','') if e.dxftype()=='ACAD_TABLE' else None
        if not name:return
        if name in trail or len(trail)>=128:raise ValueError('Block vòng/quá sâu khi kiểm tra phạm vi DWG')
        block=doc.blocks.get(name)
        if block is None:raise ValueError('Thiếu block trong phạm vi xuất: '+name)
        atomic=atomic or e.dxftype()=='ACAD_TABLE'
        if atomic and name in masks and len(masks[name])!=len(block):raise ValueError('Không tách riêng một phần geometry của TABLE native: '+name)
        if (name,atomic) in visited:return
        visited.add((name,atomic))
        for child in block:
            if child.dxf.handle not in removed:visible(child,trail+(name,),atomic)
    for h in keep:visible(doc.entitydb[h])
    for ref in refs:
        if ref.split('/')[-1] not in live or any(h in removed for h in ref.split('/')):raise ValueError('Tách phạm vi làm mất đường dẫn đã chọn: '+ref)
    placements=[dict(path=path,name=name,properties=copy_snapshot(path_entity(doc,path))) for name,items in paths.items() for path in items]
    return dict(removed_handles=sorted(removed),trimmed_blocks=trimmed,atomic_borders=list(atomic.values()),sortents=sorts,live_handles=live,placed_blocks=placements)


def check_dependencies(doc,parts,selection,top_keep,top):
    removed=set(selection['removed_handles']);live=selection['live_handles']
    trimmed_sorts=set(selection['sortents'])
    for _,_,tags in parts:
        tags=without_blkrefs(tags)
        kind=tags[0][1];handle=next((v for c,v in tags if c==5),None)
        if kind=='DIMASSOC':
            marker=next((i for i,p in enumerate(tags) if p==(100,'AcDbDimAssoc')),None)
            if marker is None:raise ValueError('DIMASSOC thiếu dữ liệu kiểm chứng phạm vi')
            refs={v for c,v in tags[marker+1:] if c in (330,331,332) and v in doc.entitydb}
            if refs&live and refs-live:raise ValueError('Liên kết DIMASSOC vượt phạm vi xuất; cần thêm khung liên quan: '+', '.join(sorted(refs-live)))
        if handle in removed or handle in top and handle not in top_keep or handle in trimmed_sorts:continue
        pointers={v for c,v in tags if c==1005 or 330<=c<=369 or 390<=c<=399 or c in (480,481)}
        if pointers&removed:
            raise ValueError('Association/tham chiếu CAD còn trỏ tới đối tượng ngoài phạm vi: '+', '.join(sorted(pointers&removed)))


def without_blkrefs(tags):
    """BLKREFS is a derived INSERT index; other 331 pointers remain native."""
    if tags[0]!=(0,'BLOCK_RECORD'):return tags
    result=[];inside=False
    for code,value in tags:
        if (code,value)==(102,'{BLKREFS'):
            if inside:raise ValueError('Chỉ mục BLKREFS lồng nhau không hợp lệ')
            inside=True
        elif inside:
            if (code,value)==(102,'}'):inside=False
            elif code!=331:raise ValueError('Chỉ mục BLKREFS có dữ liệu chưa hỗ trợ')
        else:result.append((code,value))
    if inside:raise ValueError('Chỉ mục BLKREFS chưa đóng')
    return result


def rebuild_blkrefs(lines,handles):
    # Validate the exact cache grammar before replacing it, retaining all other
    # raw block-record tags, XDATA, pointers and dictionaries unchanged.
    tags=[(int(lines[i]),lines[i+1].strip().decode('utf8')) for i in range(0,len(lines),2)]
    without_blkrefs(tags)
    newline=b'\r\n' if lines[0].endswith(b'\r\n') else b'\n'
    result=[];inside=False
    for i,(code,value) in enumerate(tags):
        if (code,value)==(102,'{BLKREFS'):
            inside=True
            if handles:
                result.extend([b'102'+newline,b'{BLKREFS'+newline])
                for handle in handles:result.extend([b'331'+newline,handle.encode()+newline])
                result.extend([b'102'+newline,b'}'+newline])
        elif inside:
            if (code,value)==(102,'}'):inside=False
        else:result.extend(lines[i*2:i*2+2])
    return result


def verify_blkrefs(doc,manifest):
    """Converters may rebuild/drop this cache, but any present index is exact."""
    expected=defaultdict(set)
    for entity in doc.entitydb.values():
        if entity.dxftype()=='INSERT':expected[entity.dxf.name].add(entity.dxf.handle)
    from ezdxf.lldxf.tagwriter import TagCollector
    for block in doc.blocks:
        tags=TagCollector.dxftags(block.block_record);inside=False;refs=[];present=False
        for code,value in tags:
            if (code,value)==(102,'{BLKREFS'):inside=True;present=True
            elif inside:
                if (code,value)==(102,'}'):inside=False
                elif code==331:refs.append(value)
                else:raise ValueError('Chỉ mục BLKREFS có dữ liệu chưa hỗ trợ')
        if present and (len(refs)!=len(set(refs)) or set(refs)!=expected[block.name]):
            raise ValueError('Chỉ mục instance không khớp definition thực tế: '+block.name)


def filter_sortents(lines,table):
    result=[];i=0
    while i<len(lines):
        code=int(lines[i]);value=lines[i+1].strip().decode('utf8')
        if code==331:
            if i+3>=len(lines) or int(lines[i+2])!=5:raise ValueError('SORTENTSTABLE có cấu trúc chưa hỗ trợ')
            if value in table:result.extend(lines[i:i+4])
            i+=4
        else:result.extend(lines[i:i+2]);i+=2
    return result


def omitted_entity_present(doc,handle,converter_normalized=False):
    entity=doc.entitydb.get(handle)
    # ODA can allocate new OBJECTS/SCALE resources in holes left by removed
    # graphic handles. This is not the removed entity or a placed drawing.
    return entity is not None and not (converter_normalized and entity.dxftype()=='SCALE')


def verify(doc,manifest,*,converter_normalized=False):
    report=(manifest or {}).get('nested_selection',{})
    for placed in report.get('placed_blocks',[]):
        entity=path_entity(doc,placed['path'])
        if entity.dxftype()!='INSERT' or entity.dxf.name!=placed['name']:
            raise ValueError('DWG đổi definition của instance đã chọn: '+placed['path'])
        if 'properties' in placed:
            from cad.geometry import near
            if not near(copy_snapshot(entity),placed['properties'],1e-6):
                raise ValueError('DWG đổi tọa độ/tỷ lệ/thuộc tính của instance đã chọn: '+placed['path'])
    for entry in [*report.get('trimmed_blocks',[]),*report.get('atomic_borders',[]),*(manifest or {}).get('isolated_blocks',[])]:
        block=doc.blocks.get(entry['name'])
        actual=[dict(handle=e.dxf.handle,type=e.dxftype()) for e in block] if block is not None else None
        if actual!=entry['kept_members']:raise ValueError('DWG không giữ đúng nội dung block đã tách phạm vi: '+entry['name'])
        if 'sortents_handle' in entry:
            if not block.block_record.has_extension_dict:raise ValueError('DWG mất thứ tự vẽ của block đã tách')
            table=block.block_record.get_extension_dict()['ACAD_SORTENTS']
            if table.table!=entry['sortents']:raise ValueError('DWG đổi thứ tự vẽ sau tách phạm vi')
    if any(omitted_entity_present(doc,h,converter_normalized) for h in report.get('removed_handles',[])):
        raise ValueError('DWG vẫn chứa đối tượng đã loại khỏi definition xuất')
    if (manifest or {}).get('block_reference_index_rebuilt'):verify_blkrefs(doc,manifest)
