"""Versioned cancellation filter; retains CAD source and its frame geometry."""
import json
from cad.catalog import CAD_LOCK,load_document
from cad.sheets import excluded_regions,discarded,geometry_index
from backend.services import catalog_service as storage

VERSION=5


def exclusions(document_id,items):
    path=storage.folder(document_id);source=path/storage.read_status(document_id)['dxf'];stat=source.stat()
    cache=path/'exclusions-v1.json'
    saved=json.loads(cache.read_text(encoding='utf8')) if cache.exists() else {}
    signature=dict(version=VERSION,mtime_ns=stat.st_mtime_ns,size=stat.st_size)
    if all(saved.get(k)==v for k,v in signature.items()):return saved
    with CAD_LOCK:
        doc=load_document(str(source))
        regions=excluded_regions(doc);ids=set()
        from cad.sheets import inside
        indexes={name:geometry_index(str(source),name) for name in {i.get('layout','Model') for i in items}} if regions else {}
        for item in items:
            layout=item.get('layout','Model')
            extent=indexes.get(layout,{}).get(item.get('id'))
            pos=item.get('position',[])[:2]
            if extent and discarded(extent,layout,regions):
                ids.add(item['id'])
            elif pos and any(r['layout']==layout and inside(pos,r['bbox']) for r in regions):
                ids.add(item['id'])
        # Also check block instances directly struck through by a diagonal
        diagonals = []
        for space in doc.layouts:
            for e in space:
                layer = doc.layers.get(e.dxf.layer)
                if layer and (layer.is_off() or layer.is_frozen() or e.dxf.get('invisible', 0)): continue
                pairs = []
                if e.dxftype() == 'LINE': pairs = [(e.dxf.start, e.dxf.end)]
                elif e.dxftype() == 'LWPOLYLINE' and not e.closed:
                    pts = list(e.get_points('xyb'))
                    pairs = [((a[0],a[1],0),(b[0],b[1],0)) for a,b in zip(pts, pts[1:]) if not a[2]]
                for a, b in pairs:
                    dx, dy = abs(a[0]-b[0]), abs(a[1]-b[1])
                    if dx > 15 and dy > 15:diagonals.append((space.name,a,b))
        if diagonals and not indexes:
            # Bare selected blocks also support cancellation. Avoid building
            # bounds for every loose vector just to inspect catalogue items.
            from ezdxf import bbox
            cache_bounds=bbox.Cache()
            for item in items:
                e=doc.entitydb.get(item.get('id'))
                if e is None:continue
                try:
                    b=bbox.extents([e],fast=True,cache=cache_bounds)
                    if b.has_data:indexes.setdefault(item.get('layout','Model'),{})[item['id']]=[b.extmin.x,b.extmin.y,b.extmax.x,b.extmax.y]
                except (ValueError,TypeError,AttributeError):continue
        for item in items:
            if item.get('kind') != 'block' or item['id'] in ids: continue
            extent = indexes.get(item.get('layout', 'Model'), {}).get(item.get('id'))
            if not extent: continue
            bw, bh = extent[2] - extent[0], extent[3] - extent[1]
            if bw < 30 or bh < 20: continue
            for layout,a,b in diagonals:
                if layout!=item.get('layout','Model'):continue
                p,q=[((v[0]-extent[0])/bw,(v[1]-extent[1])/bh) for v in (a,b)]
                if not all(-.06<=v<=1.06 for v in p+q):continue
                if max(abs(p[0]-q[0]),abs(p[1]-q[1]))<.75:continue
                crosses_horizontal=(min(p[0],q[0])<=.12 and max(p[0],q[0])>=.88 and abs(p[0]-q[0])>=.70)
                crosses_vertical=(min(p[1],q[1])<=.12 and max(p[1],q[1])>=.88 and abs(p[1]-q[1])>=.70)
                if (all(min(p[k],q[k])<=.25 and max(p[k],q[k])>=.75 for k in (0,1))
                        or crosses_horizontal or crosses_vertical):
                    ids.add(item['id']);break
        ids.update(r[k] for r in regions for k in ('frame_id','frame_insert') if r.get(k))
        result=dict(**signature,regions=regions,ids=sorted(ids))
        storage.write_json(cache,result)
        return result
