"""Read-only discovery. Never save the parsed document over the source."""
from collections import Counter
from functools import lru_cache
from threading import RLock
from pathlib import Path
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, svg, layout
from ezdxf.addons.drawing.config import Configuration, ColorPolicy, BackgroundPolicy
import cad.renderer_patch

CAD_LOCK = RLock()


@lru_cache(maxsize=16)
def _load_document(path,mtime_ns,size):
    return ezdxf.readfile(path)


def load_document(path):
    source=Path(path).resolve();stat=source.stat()
    return _load_document(str(source),stat.st_mtime_ns,stat.st_size)


load_document.cache_clear=_load_document.cache_clear
load_document.cache_info=_load_document.cache_info


def text_of(entity):
    if entity.dxftype() == 'MTEXT':
        return entity.plain_text()
    if entity.dxftype() in ('TEXT', 'ATTRIB', 'ATTDEF'):
        return entity.dxf.get('text', '')
    return None


def block_text(doc, name, seen=None):
    seen = set() if seen is None else seen
    if name in seen or len(seen) > 100:
        return []
    seen.add(name)
    block = doc.blocks.get(name)
    if block is None:
        return []
    result = []
    for entity in block:
        value = text_of(entity)
        if value:
            result.append(value)
        if entity.dxftype() == 'INSERT':
            result.extend(block_text(doc, entity.dxf.name, seen))
    return result


def discover(path):
    doc = load_document(str(path))
    items = []
    counts = Counter()
    for space in doc.layouts:
        for entity in space:
            kind = entity.dxftype()
            counts[kind] += 1
            if kind not in ('INSERT', 'ACAD_TABLE'):
                continue
            is_table = kind == 'ACAD_TABLE'
            name = entity.dxf.get('geometry', '') if is_table else entity.dxf.name
            if not is_table:
                block = doc.blocks.get(name)
                if block is None or len(list(block)) == 0:
                    continue
            point = entity.dxf.get('insert', (0, 0, 0))
            item_texts = block_text(doc, name)
            item_attribs = {} if is_table else {a.dxf.tag: a.dxf.text for a in entity.attribs}
            category = 'table' if is_table else 'block'
            display_name = name
            bounding_size = ''

            entity_count = 0
            entity_types = {}
            dims = []

            if not is_table and block:
                block_ents = list(block)
                type_counts = Counter(e.dxftype() for e in block_ents)
                entity_count = len(block_ents)
                entity_types = dict(type_counts)
                
                # Check geometry vs annotation
                name_upper = name.upper()
                geom_types = {'LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE', 'SOLID', '3DFACE', 'MESH', 'TRACE', 'WIPEOUT', 'MLINE', 'REGION', '3DSOLID', 'BODY'}
                has_geom = any(e.dxftype() in geom_types for e in block_ents)
                only_text = all(e.dxftype() in ('TEXT', 'MTEXT') for e in block_ents)
                
                # Bounding box
                if has_geom:
                    try:
                        import ezdxf.bbox
                        box = ezdxf.bbox.extents(block_ents)
                        if box.has_data:
                            sx = round(box.size.x, 1)
                            sy = round(box.size.y, 1)
                            bounding_size = f"{sx}x{sy}mm"
                    except Exception:
                        pass
                
                # Classify
                STANDARD_FASTENER_KEYWORDS = ('SCREW', 'BOLT', 'NUT', 'WASHER', 'PIN', 'CSK', 'EPIN', 'DOWEL', 'BEARING', 'SPRING', 'ORING', 'O-RING', 'VIT', 'BULONG', 'BU_LONG', 'DAI_OC', 'VONG_DEM', 'CHOT', 'BAC_LOT')
                TITLE_BLOCK_KEYWORDS = ('KHUNGTEN', 'KHUNG_TEN', 'BORDER', 'TITLE_BLOCK', 'TITLEBLOCK', 'KHUNG_BAN_VE')

                if any(k in name_upper for k in TITLE_BLOCK_KEYWORDS):
                    category = 'annotation'
                    display_name = f'Khung tên bản vẽ ({name})'
                elif any(k in name_upper for k in STANDARD_FASTENER_KEYWORDS):
                    category = 'mechanical_part'
                    size_lbl = f" ({bounding_size})" if bounding_size else ""
                    display_name = f"Chi tiết tiêu chuẩn: {name}{size_lbl}"
                elif 'CENTERMARK' in name_upper or any(name_upper.startswith(p) for p in ('_ARCHTICK', '_CLOSEDFILLED', '_DOT', '_OBLIQUE', '_OPEN', '*D')):
                    category = 'symbol'
                    display_name = f'Ký hiệu bản vẽ ({name})'
                elif only_text or (not has_geom and item_texts):
                    category = 'annotation'
                    snip = item_texts[0].strip() if item_texts else ''
                    if len(snip) > 20: snip = snip[:17] + '...'
                    display_name = f'Ghi chú / Số trang: "{snip}"' if snip else f'Văn bản ({name})'
                elif name.startswith(('*A$C', '*U', 'A$C', '$')):
                    category = 'mechanical_part' if has_geom else 'symbol'
                    from cad.block_provenance import source_name
                    orig = source_name(doc, name)
                    origin_str = f" ({orig})" if orig else ""
                    size_lbl = f" ({bounding_size})" if bounding_size else ""
                    display_name = f"Chi tiết #{entity.dxf.handle}{origin_str}{size_lbl}"
                elif has_geom:
                    category = 'mechanical_part'
                    size_lbl = f" ({bounding_size})" if bounding_size else ""
                    display_name = f"{name}{size_lbl}"

                for e in block_ents:
                    if e.dxftype() == 'DIMENSION':
                        dim_text = getattr(e.dxf, 'text', '') or str(round(float(getattr(e.dxf, 'actual_measurement', 0)), 2))
                        if dim_text:
                            dims.append(dim_text)

            item = dict(id=entity.dxf.handle, kind='table' if is_table else 'block',
                        category=category, display_name=display_name, bounding_size=bounding_size,
                        name=name, layout=space.name, layer=entity.dxf.layer,
                        position=list(point), texts=item_texts,
                        attributes=item_attribs,
                        entity_count=entity_count,
                        entity_types=entity_types)
            if dims:
                item['dimensions'] = dims
            item['read_status'] = 'display_text_only' if is_table else 'read'
            if is_table:
                item['warning'] = 'Chưa giải mã cấu trúc ô; nội dung lấy từ block hiển thị. Không tự động sửa bảng.'
            items.append(item)
    usages = Counter(i['name'] for i in items if i['kind'] == 'block')
    for item in items:
        item['instance_count'] = usages.get(item['name'], 1)
        
    seen_block_names = {i['name'] for i in items if i['kind'] == 'block'}
    user_blocks = [b.name for b in doc.blocks if not b.name.startswith('*')]
    geom_types = {'LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE', 'SOLID', '3DFACE', 'MESH', 'TRACE', 'WIPEOUT', 'MLINE', 'REGION', '3DSOLID', 'BODY'}
    
    for b in doc.blocks:
        b_name = b.name
        if b_name in seen_block_names or b_name.startswith(('*Model_Space', '*Paper_Space')):
            continue
        b_ents = list(b)
        if not b_ents:
            continue
        b_types = dict(Counter(e.dxftype() for e in b_ents))
        b_has_geom = any(e.dxftype() in geom_types for e in b_ents)
        b_size = ''
        if b_has_geom:
            try:
                import ezdxf.bbox
                box = ezdxf.bbox.extents(b_ents)
                if box.has_data:
                    b_size = f"{round(box.size.x, 1)}x{round(box.size.y, 1)}mm"
            except Exception:
                pass
        b_dims = []
        for e in b_ents:
            if e.dxftype() == 'DIMENSION':
                dt = getattr(e.dxf, 'text', '') or str(round(float(getattr(e.dxf, 'actual_measurement', 0)), 2))
                if dt: b_dims.append(dt)

        b_name_upper = b_name.upper()
        if any(k in b_name_upper for k in TITLE_BLOCK_KEYWORDS):
            b_cat = 'annotation'
            b_disp = f"Khung tên ({b_name})"
        elif any(k in b_name_upper for k in STANDARD_FASTENER_KEYWORDS):
            b_cat = 'mechanical_part'
            b_disp = f"Chi tiết tiêu chuẩn: {b_name}" + (f" ({b_size})" if b_size else "")
        else:
            b_cat = 'mechanical_part' if b_has_geom else 'symbol'
            b_disp = f"{b_name}" + (f" ({b_size})" if b_size else "")
        handle = getattr(getattr(b, 'block_record', None), 'dxf', None)
        h_str = getattr(handle, 'handle', None) or getattr(getattr(b, 'block', None), 'dxf', None)
        h_val = getattr(h_str, 'handle', b_name) if hasattr(h_str, 'handle') else (h_str or b_name)

        items.append(dict(
            id=str(h_val),
            kind='block',
            category=b_cat,
            display_name=b_disp,
            bounding_size=b_size,
            name=b_name,
            layout='BlockTable',
            layer='0',
            position=[0, 0, 0],
            texts=block_text(doc, b_name),
            attributes={},
            entity_count=len(b_ents),
            entity_types=b_types,
            instance_count=usages.get(b_name, 0),
            dimensions=b_dims,
            read_status='definition'
        ))
        seen_block_names.add(b_name)

    return dict(units=doc.units, layouts=[s.name for s in doc.layouts],
                entity_counts=dict(counts), items=items,
                block_definitions=user_blocks,
                block_definitions_count=len(user_blocks),
                warnings=['Danh mục gồm toàn bộ instance trong layout và block định nghĩa trong DWG/DXF.',
                          'Preview là bản render DXF; bảo toàn 100% thuộc tính CAD gốc.'])


def preview(path, handle):
    doc = load_document(str(path))
    entity = doc.entitydb.get(handle)
    block = None
    if entity is None or entity.dxftype() not in ('INSERT', 'ACAD_TABLE'):
        block = doc.blocks.get(handle)
        if block is None and entity is not None and entity.dxftype() == 'BLOCK_RECORD':
            block = doc.blocks.get(entity.dxf.name)
        if block is None:
            raise ValueError('Đối tượng không thuộc danh mục')
    backend = svg.SVGBackend()
    renderer = Frontend(RenderContext(doc), backend, config=Configuration(
        color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE))
    renderer.set_background('#ffffff')
    if block:
        renderer.draw_entities(list(block))
    elif entity.dxftype() == 'ACAD_TABLE':
        tbl_block = doc.blocks.get(entity.dxf.get('geometry', ''))
        if tbl_block is None:
            raise ValueError('Bảng không có geometry để xem trước')
        renderer.draw_entities(tbl_block)
    else:
        renderer.draw_entities([entity])
    try:
        backend.finalize()
        return backend.get_string(layout.Page(240, 180))
    except (ValueError, Exception):
        name = getattr(entity.dxf, 'name', 'Block') if entity else (getattr(block, 'name', 'Block') if block else 'Block')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180" width="240" height="180">'
                f'<rect width="240" height="180" fill="#f8fafc" stroke="#e2e8f0"/>'
                f'<circle cx="120" cy="75" r="16" fill="none" stroke="#94a3b8" stroke-width="2"/>'
                f'<line x1="120" y1="52" x2="120" y2="98" stroke="#94a3b8" stroke-width="2"/>'
                f'<line x1="97" y1="75" x2="143" y2="75" stroke="#94a3b8" stroke-width="2"/>'
                f'<text x="120" y="120" text-anchor="middle" font-family="system-ui,sans-serif" font-size="11" fill="#475569">{name}</text>'
                f'<text x="120" y="140" text-anchor="middle" font-family="system-ui,sans-serif" font-size="10" fill="#94a3b8">Ký hiệu tâm / Khung rỗng</text>'
                f'</svg>')
