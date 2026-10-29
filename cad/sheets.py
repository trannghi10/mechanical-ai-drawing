"""Heuristic rectangular sheet discovery, distinct from block definitions."""
import ezdxf
from functools import lru_cache
from pathlib import Path
from ezdxf import bbox
from ezdxf.addons.drawing import Frontend, RenderContext, svg, layout
from ezdxf.addons.drawing.config import Configuration, ColorPolicy, BackgroundPolicy
from ezdxf.math import BoundingBox2d
from cad.catalog import text_of, load_document
import cad.renderer_patch

SHEET_VERSION = 8


def inside(point, box):
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def red(entity, doc):
    color = entity.dxf.get('color',256)
    rgb = entity.dxf.get('true_color')
    if color == 256:
        layer = doc.layers.get(entity.dxf.layer)
        color, rgb = abs(layer.dxf.color), layer.dxf.get('true_color',rgb)
    if rgb is not None:
        return (rgb >> 16 & 255) > 180 and (rgb >> 8 & 255) < 100 and (rgb & 255) < 100
    return color == 1


def excluded_regions(doc):
    result=[]
    for space in doc.layouts:
        diagonals=[]
        for e in space:
            layer=doc.layers.get(e.dxf.layer)
            if layer and (layer.is_off() or layer.is_frozen() or e.dxf.get('invisible',0)):
                continue
            if e.dxftype()=='LINE':
                segments=[(e.dxf.start,e.dxf.end)]
            elif e.dxftype()=='LWPOLYLINE':
                points=list(e.get_points('xy'))
                segments=list(zip(points,points[1:]))
            else:
                continue
            is_red=red(e,doc)
            for a,b in segments:
                dx,dy=b[0]-a[0],b[1]-a[1]
                if abs(dx)<100 or abs(dy)<50:
                    continue
                diagonals.append(([min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])],dx*dy>0,is_red,e.dxf.handle))
        for i,(box,direction,is_red,h1) in enumerate(diagonals):
            for other,opposite,o_red,h2 in diagonals[i+1:]:
                if direction==opposite:
                    continue
                tol=max(.05*min(box[2]-box[0],box[3]-box[1]),25.0)
                if max(abs(a-b) for a,b in zip(box,other))<=tol:
                    rbox=[min(box[0],other[0]),min(box[1],other[1]),max(box[2],other[2]),max(box[3],other[3])]
                    reason='red_cross' if (is_red or o_red) else 'cross_mark'
                    region={'layout':space.name,'bbox':list(map(float,rbox)),'reason':reason,'mark_ref':f"{h1}/{h2}"}
                    if not any(r['layout']==space.name and max(abs(a-b) for a,b in zip(r['bbox'],rbox))<10 for r in result):
                        result.append(region)
    from cad.discard_marks import single_slash_regions
    for s in single_slash_regions(doc):
        if not any(r['layout']==s['layout'] and max(abs(a-b) for a,b in zip(r['bbox'],s['bbox']))<10 for r in result):
            result.append(s)
    return result


def discarded(box, space, regions):
    for r in regions:
        if r['layout'] != space:
            continue
        rb = r['bbox']
        tol = max(0.02 * min(rb[2] - rb[0], rb[3] - rb[1]), 10.0)
        if r.get('reason')=='sheet_cancellation_slash':
            # A recognized slash may end just beyond the border. Its own
            # overhang must not resurrect the sheet via layout fallback.
            tol=max(tol,.06*max(rb[2]-rb[0],rb[3]-rb[1]))
        if rb[0] - tol <= box[0] and box[2] <= rb[2] + tol:
            if rb[1] - tol <= box[1] and box[3] <= rb[3] + tol:
                return True
    return False


@lru_cache(maxsize=2)
def _geometry_index(path, space, mtime_ns, size):
    doc=load_document(path)
    cache=bbox.Cache()
    result={}
    for e in doc.layouts.get(space):
        try:
            bounds=bbox.extents([e],fast=True,cache=cache)
            if bounds.has_data:
                result[e.dxf.handle]=[bounds.extmin.x,bounds.extmin.y,bounds.extmax.x,bounds.extmax.y]
        except (ValueError,TypeError,AttributeError):
            continue
    return result


def geometry_index(path,space):
    source=Path(path).resolve();stat=source.stat()
    return _geometry_index(str(source),space,stat.st_mtime_ns,stat.st_size)


geometry_index.cache_clear=_geometry_index.cache_clear


def overlaps(a,b):
    return a[0]<=b[2] and a[2]>=b[0] and a[1]<=b[3] and a[3]>=b[1]


def anchor(entity):
    for key in ('insert', 'center', 'start', 'defpoint', 'location'):
        value = entity.dxf.get(key) if entity.dxf.is_supported(key) else None
        if value is not None:
            return value
    if entity.dxftype() == 'LWPOLYLINE' and len(entity):
        return entity[0]
    if entity.dxftype() == 'SPLINE':
        points = list(entity.control_points)
        return points[0] if points else None
    return None


# A title block is itself made of CAD primitives, so the mere existence of a
# rectangular border and title text is not enough to call it a drawing.  We
# look for geometry in the usable drawing area, away from the page border and
# the title block along the bottom edge.  This keeps empty A4/A3 templates out
# of the drawing selector while retaining line-only mechanical drawings.
DRAWING_GEOMETRY = {
    'LINE', 'LWPOLYLINE', 'POLYLINE', 'CIRCLE', 'ARC', 'ELLIPSE', 'SPLINE',
    'HATCH', 'INSERT', 'SOLID', 'TRACE', '3DFACE', 'MLINE', 'WIPEOUT',
    'VIEWPORT', 'IMAGE', 'RASTERIMAGE', 'REGION', '3DSOLID', 'BODY', 'MESH',
}


def mechanical_geometry(space):
    """Return drawable entity extents once per layout for sheet filtering."""
    cache = bbox.Cache()
    result = []
    for entity in space:
        if entity.dxftype() not in DRAWING_GEOMETRY:
            continue
        try:
            bounds = bbox.extents([entity], fast=True, cache=cache)
        except (ValueError, TypeError, AttributeError):
            continue
        if bounds.has_data:
            result.append((entity.dxf.handle, [float(bounds.extmin.x), float(bounds.extmin.y),
                                                float(bounds.extmax.x), float(bounds.extmax.y)]))
    return result


def has_mechanical_cad_content(space, box, ignored_handles=(), geometry=None):
    """Return True when a sheet contains real drawing geometry, not its frame."""
    w, h = box[2] - box[0], box[3] - box[1]
    if w <= 0 or h <= 0:
        return False
    # The bottom strip is normally the title block.  The small edge margin
    # removes page borders, zone grids, and revision-table outlines.
    content_box = [box[0] + .06 * w, box[1] + .16 * h,
                   box[2] - .06 * w, box[3] - .06 * h]
    ignored = set(ignored_handles)
    for handle, entity_box in (mechanical_geometry(space) if geometry is None else geometry):
        if handle in ignored:
            continue
        center = ((entity_box[0] + entity_box[2]) / 2,
                  (entity_box[1] + entity_box[3]) / 2)
        if not inside(center, content_box):
            continue
        # A line spanning nearly an entire page is normally a border or zone
        # grid.  It cannot by itself establish that the page has a part view.
        if ((entity_box[2] - entity_box[0]) >= .88 * w or
                (entity_box[3] - entity_box[1]) >= .88 * h):
            continue
        return True
    return False


def preview_auxiliary_dynamic_marker(doc, entity, entity_box, sheet_box):
    """Identify tiny line-only anonymous dynamic-block helpers.

    AutoCAD keeps some dynamic block parameter graphics in anonymous ``*U``
    definitions.  They are not printable part geometry, but ezdxf renders
    their SHX-like marker strokes as stray symbols.  A small anonymous block
    can still be a real detail, so this only excludes line/point-only helpers
    whose placed extent is tiny compared with the drawing sheet.
    """
    if entity.dxftype() != 'INSERT' or not str(entity.dxf.get('name', '')).upper().startswith('*U'):
        return False
    block = doc.blocks.get(entity.dxf.name)
    if block is None:
        return False
    members = list(block)
    if not members or len(members) > 12 or any(member.dxftype() not in {'LINE', 'POINT'} for member in members):
        return False
    width, height = entity_box[2] - entity_box[0], entity_box[3] - entity_box[1]
    sheet_width, sheet_height = sheet_box[2] - sheet_box[0], sheet_box[3] - sheet_box[1]
    if sheet_width <= 0 or sheet_height <= 0:
        return False
    return width <= .025 * sheet_width and height <= .025 * sheet_height


def discover_sheets(path):
    from cad.block_frames import placed_frames, describe_frame
    doc = load_document(str(path))
    sheets = []
    regions=excluded_regions(doc)
    TITLE_KEYWORDS = (
        'CÔNG TY', 'TÊN SẢN PHẨM', 'SẢN PHẨM', 'BẢN VẼ', 'KHUNG TÊN', 'KHUNGTEN', 'KHUNG_TEN',
        'DRAWING', 'PROJECT', 'DUNG SAI', 'TIÊU CHUẨN', 'TỶ LỆ', 'SCALE', 'TITLE', 'TITLE_BLOCK',
        'PART NAME', 'PART NO', 'PART NUMBER', 'PART LIST', 'NGƯỜI VẼ', 'THIẾT KẾ', 'KÝ DUYỆT',
        'SỐ BẢN VẼ', 'DWG NO', 'DWG. NO', 'DRAWING NO', 'DATE', 'DESIGN', 'DRAWN', 'CHECKED',
        'APPROVED', 'MATERIAL', 'VẬT LIỆU', 'CHI TIẾT', 'ASSEMBLY', 'PART', 'REVISION', 'MÃ SẢN PHẨM'
    )
    from bom.reader import normalized
    normalized_titles=tuple(normalized(k) for k in TITLE_KEYWORDS)
    for space in doc.layouts:
        texts = [(e, text_of(e), anchor(e)) for e in space if e.dxftype() in ('TEXT', 'MTEXT')]
        geometry = mechanical_geometry(space)
        for entity in space.query('LWPOLYLINE'):
            if not entity.closed or len(entity) != 4:
                continue
            points = list(entity.get_points('xyb'))
            if any(abs(p[2]) > 1e-9 for p in points):
                continue
            xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
            box = [min(xs), min(ys), max(xs), max(ys)]
            if discarded(box,space.name,regions):
                continue
            w, h = box[2]-box[0], box[3]-box[1]
            if w < 100 or h < 50:
                continue
            ratio = w / h if h > 0 else 0
            if not (0.35 < ratio < 3.0):
                continue
            if any(abs(points[i][0]-points[(i+1)%4][0]) > 1e-4 and
                   abs(points[i][1]-points[(i+1)%4][1]) > 1e-4 for i in range(4)):
                continue
            content = [text for _, text, point in texts if point is not None and inside(point,box) and text]
            if not any(any(kw in normalized(t) for kw in normalized_titles) for t in content):
                continue
            if not has_mechanical_cad_content(space, box, (entity.dxf.handle,), geometry):
                continue
            title = next((t for t in content if any(k in t.upper() for k in ('TÊN SẢN PHẨM', 'BẢN VẼ TỔ', 'BẢN VẼ', 'KHUNG TÊN', 'LEG6949'))), 'Khung bản vẽ')
            sheets.append(dict(id=entity.dxf.handle, kind='sheet', layout=space.name,
                               name=title[:60].replace('\n', ' '), texts=content, bbox=box,
                               read_status='needs_confirmation',
                               warning='Khung được nhận diện bằng hình chữ nhật và text khung tên; cần đối chiếu preview.'))

        # INSERT-owned frames can contain loose geometry and tables which are
        # not children of the title block. Their scope is the placed border.
        for sheet in placed_frames(doc,space):
            box=sheet['bbox']
            if discarded(box,space.name,regions):
                continue
            if any(s['layout']==space.name and max(abs(a-b) for a,b in zip(s['bbox'],box))<1e-3 for s in sheets):
                continue
            sheet['texts']=list(dict.fromkeys(sheet['texts']+[t for _,t,p in texts if p is not None and inside(p,box) and t]))
            if not has_mechanical_cad_content(space, box, (sheet.get('frame_insert'),), geometry):
                continue
            sheets.append(describe_frame(sheet))

        # Fallback: if no individual sheets were found for this layout, check if layout has content
        layout_sheets = [s for s in sheets if s['layout'] == space.name]
        if not layout_sheets and (len(texts) > 0 or len(list(space)) > 5):
            try:
                from ezdxf import bbox
                bounds = bbox.extents(space, fast=True)
                if bounds.has_data:
                    box = [float(bounds.extmin.x), float(bounds.extmin.y), float(bounds.extmax.x), float(bounds.extmax.y)]
                    w, h = box[2] - box[0], box[3] - box[1]
                    has_content = has_mechanical_cad_content(space, box, geometry=geometry) or len(list(space)) > 5
                    if (w > 10 and h > 10 and not discarded(box, space.name, regions)
                            and has_content):
                        content = [t for _, t, pt in texts if pt is not None and inside(pt, box) and t]
                        sheets.append(dict(
                            id=f'layout_{space.name}',
                            kind='sheet',
                            layout=space.name,
                            name=f'Toàn bộ {space.name}',
                            texts=content,
                            bbox=box,
                            read_status='layout_extent',
                            warning='Toàn bộ layout; không tìm thấy khung tên riêng.'
                        ))
            except Exception:
                pass

    def concentric_margin(inner, outer):
        w_in, h_in = inner['bbox'][2]-inner['bbox'][0], inner['bbox'][3]-inner['bbox'][1]
        w_out, h_out = outer['bbox'][2]-outer['bbox'][0], outer['bbox'][3]-outer['bbox'][1]
        area_in, area_out = w_in * h_in, w_out * h_out
        return area_out > 0 and (area_in / area_out) >= 0.7

    # Preserve legacy loose-frame IDs/scopes when adding block-owned borders.
    native=[s for s in sheets if not s.get('detection')]
    native=[s for s in native if not any(t['id'] != s['id'] and t['layout']==s['layout'] and
                inside((t['bbox'][0],t['bbox'][1]),s['bbox']) and
                inside((t['bbox'][2],t['bbox'][3]),s['bbox']) and
                concentric_margin(t, s) for t in native)]
    added=[s for s in sheets if s.get('detection') and not any(t['layout']==s['layout'] and
           inside(s['bbox'][:2],t['bbox']) and inside(s['bbox'][2:],t['bbox']) for t in native)]
    added=[s for s in added if not any(t['id']!=s['id'] and t['frame_insert']==s['frame_insert'] and
           inside(t['bbox'][:2],s['bbox']) and inside(t['bbox'][2:],s['bbox']) for t in added)]
    for sheet in native:
        description=describe_frame(dict(sheet))
        sheet['category']=description['category'];sheet['source_codes']=description['source_codes'];sheet['name']=description.get('name',sheet.get('name'))
    combined = native + added

    def encloses_multiple_sheets(outer, pool):
        count = 0
        for inner in pool:
            if inner['id'] == outer['id'] or inner.get('layout') != outer.get('layout'):
                continue
            if inside(inner['bbox'][:2], outer['bbox']) and inside(inner['bbox'][2:], outer['bbox']):
                count += 1
                if count >= 2:
                    return True
        return False

    return [s for s in combined if not encloses_multiple_sheets(s, combined)]


def preserve_legacy_sheets(previous, discovered):
    """Upgrade unchanged uploads without altering their established loose scopes."""
    from cad.block_frames import describe_frame
    result=[]
    additions=[s for s in discovered if s.get('detection')=='insert_border']
    for old in previous:
        if old.get('read_status')=='layout_extent' and any(s['layout']==old['layout'] for s in additions):
            continue
        description=describe_frame(dict(old))
        result.append({**old,'category':description['category'],'source_codes':description['source_codes'],'name':description.get('name',old.get('name'))})
    result.extend(s for s in additions if not any(t['layout']==s['layout'] and
                  inside(s['bbox'][:2],t['bbox']) and inside(s['bbox'][2:],t['bbox']) for t in result))

    def encloses_multiple_sheets(outer, pool):
        count = 0
        for inner in pool:
            if inner['id'] == outer['id'] or inner.get('layout') != outer.get('layout'):
                continue
            if inside(inner['bbox'][:2], outer['bbox']) and inside(inner['bbox'][2:], outer['bbox']):
                count += 1
                if count >= 2:
                    return True
        return False

    return [s for s in result if not encloses_multiple_sheets(s, result)]


def render_sheet(path, sheet, *, render_box=None, include_annotations=True):
    doc = load_document(str(path))
    box = render_box or sheet['bbox']
    entities = []
    temporary = []
    bounds=geometry_index(str(path),sheet['layout'])
    for entity in list(doc.layouts.get(sheet['layout'])):
        if not include_annotations and entity.dxftype() in ('DIMENSION','TEXT','MTEXT','LEADER','MLEADER','ACAD_TABLE'):
            continue
        point = anchor(entity)
        extent=bounds.get(entity.dxf.handle)
        if not ((extent is not None and overlaps(extent,box)) or (point is not None and inside(point,box))):
            continue
        if extent is not None and preview_auxiliary_dynamic_marker(doc, entity, extent, box):
            continue
        if entity.dxftype() == 'ACAD_TABLE':
            name = entity.dxf.get('geometry','')
            if name in doc.blocks:
                entity = doc.modelspace().add_blockref(name,entity.dxf.insert)
                temporary.append(entity)
        entities.append(entity)
    backend = svg.SVGBackend()
    frontend = Frontend(RenderContext(doc),backend,config=Configuration(
        color_policy=ColorPolicy.BLACK,background_policy=BackgroundPolicy.WHITE))
    # draw_entities does not initialize the backend background like draw_layout.
    frontend.set_background('#ffffff')
    try:
        frontend.draw_entities(entities)
        backend.finalize()
    finally:
        for entity in temporary:
            doc.modelspace().delete_entity(entity)
    return backend.get_string(layout.Page(297,210),render_box=BoundingBox2d([(box[0],box[1]),(box[2],box[3])]),
                              settings=layout.Settings(crop_at_margins=True))
