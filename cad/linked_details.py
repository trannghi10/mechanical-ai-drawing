"""Recover small, code-owned detail frames for dependency analysis only.

The user's sheet gallery and its detection cache are deliberately unchanged.
These frames must carry an exact BOM code and the native title-block labels;
part outlines, revision tables, red-cross areas and ambiguous ownership fail.
"""
from cad.catalog import load_document, text_of
from cad.sheets import anchor, inside, discarded, excluded_regions
from bom.reader import plain, normalized


def linked_details(path, sheets, codes):
    doc = load_document(str(path)); known = {s['id'] for s in sheets}
    regions = excluded_regions(doc); result = []
    for space in doc.layouts:
        texts = [(e, plain(text_of(e)), anchor(e)) for e in space
                 if e.dxftype() in ('TEXT', 'MTEXT') and text_of(e)]
        for frame in space.query('LWPOLYLINE'):
            if frame.dxf.handle in known or not frame.closed or len(frame) != 4:
                continue
            points = list(frame.get_points('xyb'))
            if any(abs(p[2]) > 1e-9 for p in points): continue
            box = [min(p[0] for p in points), min(p[1] for p in points),
                   max(p[0] for p in points), max(p[1] for p in points)]
            width, height = box[2]-box[0], box[3]-box[1]
            # Only fill the small-frame gap; never broaden the existing gallery.
            if width <= 0 or height <= 0 or width >= 200 and height >= 100 or not 1.2 < width/height < 1.65:
                continue
            if any(abs(a[0]-b[0]) > 1e-6 and abs(a[1]-b[1]) > 1e-6
                   for a,b in zip(points, points[1:]+points[:1])): continue
            if discarded(box, space.name, regions): continue
            content = [value for _, value, point in texts if point is not None and inside(point, box)]
            owners = set(content) & set(codes)
            labels = {normalized(t) for t in content}
            if len(owners) != 1 or not any('cong ty' in t for t in labels): continue
            if not any('ma btp' in t for t in labels) or not any('so to' in t and '01/' in t for t in labels): continue
            if not any('ten san pham' in t for t in labels): continue
            result.append(dict(id=frame.dxf.handle,kind='sheet',layout=space.name,
                name='Chi tiết '+next(iter(owners)),bbox=list(map(float,box)),texts=content,
                linked_detail=True,part_code=next(iter(owners)),read_status='source_verified_title'))
    # Nested/duplicated title frames would make ownership ambiguous.
    return [s for s in result if not any(t['id'] != s['id'] and t['layout']==s['layout'] and
            inside(t['bbox'][:2],s['bbox']) and inside(t['bbox'][2:],s['bbox']) for t in result)]
