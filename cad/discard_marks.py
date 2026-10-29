"""Sheet-sized cancellation slashes, independent of display colour.

A short diagonal can be a mechanical edge.  A long diagonal that crosses a
title frame from one page side to the other is an intentional discard mark.
"""
from ezdxf.math import Matrix44
from cad.catalog import text_of


def single_slash_regions(doc):
    from cad.block_frames import placed_frames,TITLE_WORDS
    from cad.sheets import anchor,inside
    result=[]

    def clipped_segment(a, b, box):
        """Return the visible section of a segment inside a frame rectangle."""
        ax, ay, bx, by = float(a.x), float(a.y), float(b.x), float(b.y)
        dx, dy = bx - ax, by - ay
        points = []
        for x in (box[0], box[2]):
            if abs(dx) > 1e-9:
                t = (x - ax) / dx
                y = ay + t * dy
                if 0 <= t <= 1 and box[1] <= y <= box[3]:
                    points.append((x, y))
        for y in (box[1], box[3]):
            if abs(dy) > 1e-9:
                t = (y - ay) / dy
                x = ax + t * dx
                if 0 <= t <= 1 and box[0] <= x <= box[2]:
                    points.append((x, y))
        if box[0] <= ax <= box[2] and box[1] <= ay <= box[3]:
            points.append((ax, ay))
        if box[0] <= bx <= box[2] and box[1] <= by <= box[3]:
            points.append((bx, by))
        unique = list(dict.fromkeys((round(x, 8), round(y, 8)) for x, y in points))
        if len(unique) < 2:
            return None
        return max(((p, q) for i, p in enumerate(unique) for q in unique[i + 1:]),
                   key=lambda pair: (pair[0][0] - pair[1][0]) ** 2 + (pair[0][1] - pair[1][1]) ** 2)
    for space in doc.layouts:
        frames=list(placed_frames(doc,space));texts=[]
        for e in space:
            t=text_of(e);p=anchor(e)
            if t and p is not None:texts.append((t,p))
        for e in space.query('LWPOLYLINE'):
            if not e.closed or len(e)!=4:continue
            q=list(e.get_points('xyb'))
            if any(p[2] for p in q) or any(abs(q[i][0]-q[(i+1)%4][0])>1e-5 and abs(q[i][1]-q[(i+1)%4][1])>1e-5 for i in range(4)):continue
            b=[min(p[0] for p in q),min(p[1] for p in q),max(p[0] for p in q),max(p[1] for p in q)]
            content=[t for t,p in texts if inside(p,b)]
            if any(any(w in t.upper() for w in TITLE_WORDS) for t in content):
                frames.append(dict(id=e.dxf.handle,layout=space.name,bbox=b))

        def segments(entities,matrix,path=(),ancestors=()):
            for e in entities:
                layer=doc.layers.get(e.dxf.layer)
                if layer.is_off() or layer.is_frozen() or e.dxf.get('invisible',0):continue
                ref='/'.join(path+(e.dxf.handle,));kind=e.dxftype();pairs=[]
                if kind=='LINE':pairs=[(e.dxf.start,e.dxf.end)]
                elif kind=='LWPOLYLINE' and not e.closed:
                    q=list(e.get_points('xyb'))
                    pairs=[([a[0],a[1],e.dxf.elevation],[b[0],b[1],e.dxf.elevation]) for a,b in zip(q,q[1:]) if not a[2]]
                elif kind=='POLYLINE' and not e.is_closed:
                    q=list(e.points())
                    pairs=list(zip(q,q[1:]))
                elif kind=='SPLINE' and e.dxf.degree == 1:
                    # Cancellation marks imported from PDF/DWG are sometimes
                    # retained as a degree-1 spline instead of a LINE.
                    q=list(e.control_points)
                    pairs=list(zip(q,q[1:]))
                elif kind=='LEADER':
                    q=list(e.vertices)
                    pairs=list(zip(q,q[1:]))
                for a,b in pairs:
                    a,b=matrix.transform(a),matrix.transform(b)
                    if abs(a.x-b.x)>1e-5 and abs(a.y-b.y)>1e-5:yield ref,a,b
                if kind=='INSERT' and e.dxf.name not in ancestors and len(ancestors)<128:
                    block=doc.blocks.get(e.dxf.name)
                    if block is not None:yield from segments(block,e.matrix44()*matrix,path+(e.dxf.handle,),ancestors+(e.dxf.name,))
        for ref,a,b in segments(space,Matrix44()):
            for f in frames:
                box=f['bbox'];w,h=box[2]-box[0],box[3]-box[1]
                if w<100 or h<50 or not .35<w/h<3:continue
                visible=clipped_segment(a,b,box)
                if visible is None:continue
                p,q=[((v[0]-box[0])/w,(v[1]-box[1])/h) for v in visible]
                if max(abs(p[0]-q[0]),abs(p[1]-q[1]))<.65:continue
                def corner(v):return (0 if v[0]<=.25 else 1 if v[0]>=.75 else -1,
                                      0 if v[1]<=.25 else 1 if v[1]>=.75 else -1)
                c,d=corner(p),corner(q)
                opposite_corners=(-1 not in c+d and c[0]!=d[0] and c[1]!=d[1])
                # Some production drawings use a single long slash from the
                # left edge to the right edge rather than exact corners.  It
                # still cancels the entire frame; a short diagonal on a part
                # remains valid CAD and is not classified as a cancellation.
                crosses_horizontal=(min(p[0],q[0])<=.12 and max(p[0],q[0])>=.88 and
                                    abs(p[0]-q[0])>=.70)
                crosses_vertical=(min(p[1],q[1])<=.12 and max(p[1],q[1])>=.88 and
                                  abs(p[1]-q[1])>=.70)
                if not (opposite_corners or crosses_horizontal or crosses_vertical):continue
                region=dict(layout=space.name,bbox=box,reason='sheet_cancellation_slash',mark_ref=ref,frame_id=f['id'])
                if f.get('frame_insert'):region['frame_insert']=f['frame_insert']
                if not any(r['layout']==space.name and r['bbox']==box for r in result):result.append(region)
    return result
