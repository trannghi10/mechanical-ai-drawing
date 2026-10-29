"""Source-bound material schedules drawn with LINE/LWPOLYLINE and text.

Only closed, axis-aligned cells in one native coordinate frame are accepted.
There is no OCR or nearest-text assignment. Each nonempty cell must contain
exactly one TEXT/MTEXT; split text, merged body cells and incomplete grids stay
unsupported. A placed block may be rotated/scaled: its local grid is unchanged.
"""
from bisect import bisect_right
from collections import defaultdict
import hashlib
import re
from ezdxf.math import Matrix44
from bom.reader import normalized, plain
from bom.processes import process_tags


ALIASES = {
    'number': {'stt', 'so tt', 'so thu tu', 'no', 'item', 'n0', 'no.', 'ref.no.', 'ref.no', 'so ct', 'ref no'},
    'code': {'ma', 'ma hang', 'ma vat tu', 'ma chi tiet', 'part no', 'part number', 'so ct'},
    'description': {'ten', 'vat tu', 'ten vat tu', 'ten chi tiet', 'ten hang', 'description', 'material/component', 'part name', 'tnlk', 'material / component'},
    'material': {'vl', 'vat lieu', 'chat lieu', 'material', 'nl'},
    'quantity': {'sl', 'so luong', 'qty', 'quantity', 'quantity or times', 'total part'},
    'notes': {'ghi chu', 'note', 'notes', 'remark', 'revision note', 'xlbm'},
}
CANONICAL = {alias: key for key, values in ALIASES.items() for alias in values}
REQUIRED = {'number', 'code', 'description', 'material', 'quantity'}
TOL = 1e-5


def _covers(segments, start, end, tol=2.5):
    """Union coverage accepts segmented CAD borders and manual drafting gaps."""
    cursor = start
    for lo, hi, _ in sorted(segments):
        if hi < cursor-tol: continue
        if lo > cursor+tol: return False
        cursor = max(cursor, hi)
        if cursor >= end-tol: return True
    return False


def _grid(records):
    h = defaultdict(list); v = defaultdict(list); texts = []
    def edge(a, b, ref):
        if abs(a[2]) > TOL or abs(b[2]) > TOL: return
        if abs(a[1]-b[1]) < TOL and abs(a[0]-b[0]) > TOL:
            h[round(a[1], 5)].append((min(a[0], b[0]), max(a[0], b[0]), ref))
        elif abs(a[0]-b[0]) < TOL and abs(a[1]-b[1]) > TOL:
            v[round(a[0], 5)].append((min(a[1], b[1]), max(a[1], b[1]), ref))
    for e in records:
        g = e.get('geometry', {})
        if e['type'] == 'LINE' and g: edge(g['start'], g['end'], e['ref'])
        elif e['type'] in ('LWPOLYLINE','POLYLINE') and g and not any(p[4] for p in g['points']):
            if any(g.get('default_widths',[])) or any(any(p[2:4]) for p in g['points']):continue
            if any(abs(a-b) > TOL for a,b in zip(g['extrusion'], [0,0,1])): continue
            points = [[p[0], p[1], g['elevation']] for p in g['points']]
            for a,b in zip(points, points[1:] + (points[:1] if g['closed'] else [])): edge(a,b,e['ref'])
        if e['type'] in ('TEXT', 'MTEXT') and e.get('text_placement'):
            p = e['text_placement']
            if (abs(p.get('rotation',0) % 360) < TOL and abs(p['anchor'][2])<TOL
                and all(abs(a-b)<TOL for a,b in zip(p.get('extrusion',[0,0,1]),[0,0,1]))
                and all(abs(a-b)<TOL for a,b in zip(p.get('direction',[1,0,0]),[1,0,0]))): texts.append(e)
    return h, v, texts


def discover(records):
    groups = defaultdict(list)
    # Native TABLE display geometry must not be mistaken for a second BOM.
    native = {e['ref'] for e in records if e['type'] == 'ACAD_TABLE'}
    for e in records:
        if any(e['ref'].startswith(r+'/') for r in native): continue
        groups[(e.get('coordinate_frame'), e.get('layout'))].append(e)
    result = []; seen = set()
    for (frame, layout), group in groups.items():
        h, v, texts = _grid(group)
        def in_cell(x0,y0,x1,y1):
            return [e for e in texts if x0-0.5 < e['text_placement']['anchor'][0] < x1+0.5
                    and y0-2.5 < e['text_placement']['anchor'][1] < y1+2.5]
        for head in texts:
            if normalized(head.get('text','')) not in ALIASES['number']: continue
            x,y,_ = head['text_placement']['anchor']
            # The immediate horizontal boundaries around the header anchor
            # must span its column; unrelated lines elsewhere cannot close it.
            around = [yy for yy,segments in h.items() if any(lo-2.5 < x < hi+2.5 for lo,hi,_ in segments)]
            lower = [yy for yy in around if yy < y-1.0]; upper = [yy for yy in around if yy > y+1.0]
            if not lower or not upper: continue
            bottom, top = max(lower), min(upper)
            xs = sorted(xx for xx,segments in v.items() if _covers(segments,bottom,top))
            col = bisect_right(xs,x)-1
            if col < 0 or col >= len(xs)-1: continue
            # Find the connected run of closed header cells containing STT.
            first = col; last = col+1
            def closed(a,b): return _covers(h[bottom],a,b) and _covers(h[top],a,b)
            while first > 0 and closed(xs[first-1],xs[first]): first -= 1
            while last < len(xs)-1 and closed(xs[last],xs[last+1]): last += 1
            xs = xs[first:last+1]
            if not 4 <= len(xs)-1 <= 12 or not closed(xs[0],xs[-1]): continue
            labels = [in_cell(a,bottom,b,top) for a,b in zip(xs,xs[1:])]
            if any(len(items)!=1 for items in labels): continue
            keys = [CANONICAL.get(normalized(items[0]['text'])) for items in labels]
            known = [k for k in keys if k]
            if len(known)!=len(set(known)): continue
            is_4col = len(xs)-1 == 4
            if is_4col:
                if not {'number', 'quantity'} <= set(known) or not ({'description', 'material'} & set(known)): continue
            else:
                if not REQUIRED <= set(known): continue
            columns = {k:i for i,k in enumerate(keys) if k}
            signature = tuple(items[0]['ref'] for items in labels)
            if signature in seen: continue
            ys = sorted((yy for yy in h if yy <= bottom+2.5 and _covers(h[yy],xs[0],xs[-1])),reverse=True)
            rows = []; used = {e['ref'] for items in labels for e in items}; rejected = None
            final_y = bottom
            for high, low in zip(ys,ys[1:]):
                # A finished grid can sit above a drawing containing numeric
                # balloons. The frame's bottom edge is not another BOM row.
                # Stop only when no column border continues below this edge;
                # a partially broken body row remains rejected below.
                if not any(lo<high-TOL and hi>=high-TOL for xx in xs for lo,hi,_ in v[xx]):break
                contents = [in_cell(a,low,b,high) for a,b in zip(xs,xs[1:])]
                number_items = contents[columns['number']]
                # A footer or a different table ends this BOM. A broken edge
                # around an otherwise numbered row rejects the entire schedule.
                if not number_items: break
                if len(number_items)!=1:
                    rejected='Nhiều số thứ tự trong một ô; bảng thiếu đường phân hàng';break
                if not re.fullmatch(r'(?:\d+|[A-Za-z]\d*)',plain(number_items[0]['text'])): break
                if not all(_covers(v[xx],low,high) for xx in xs) or any(len(c)>1 for c in contents):
                    rejected = 'Ô gộp, thiếu đường biên hoặc nhiều đối tượng chữ trong một ô'; break
                values = {key:plain(contents[i][0]['text']) if contents[i] else '' for key,i in columns.items()}
                needed={'number','quantity'} if is_4col else REQUIRED
                if not all(values.get(key) for key in needed) or is_4col and not (values.get('description') or values.get('material')):
                    rejected = 'Dòng vật tư thiếu số thứ tự, mã, mô tả, vật liệu hoặc số lượng'; break
                if values.get('code') in ('!!','?','??','-','...'): final_y=low; continue
                cells = {}
                for key,i in columns.items():
                    if not contents[i]: continue
                    e=contents[i][0]; used.add(e['ref'])
                    cells[key]={'index':len(rows)*len(keys)+i, 'storage':'text', 'raw_text':e.get('raw_text',e['text']), 'mirror_ref':e['ref']}
                rows.append(dict(part_number=values['number'],part_code=values.get('code',''),description=values.get('description',''),
                    material=values.get('material',''),quantity_text=values['quantity'],notes=values.get('notes',''),
                    processes=process_tags(values.get('description','')),cells=cells))
                final_y=low
            numbers=[r['part_number'] for r in rows]
            if len(numbers)!=len(set(numbers)): rejected='Số thứ tự vật tư bị trùng'
            # Grid ownership is exact, bounded by the accepted table rectangle.
            border_ys={top,*[yy for yy in ys if final_y-TOL<=yy<=bottom+TOL]}
            for yy,segments in h.items():
                if yy in border_ys:
                    used.update(ref for lo,hi,ref in segments if lo>=xs[0]-TOL and hi<=xs[-1]+TOL)
            for xx,segments in v.items():
                if xx in xs:
                    used.update(ref for lo,hi,ref in segments if lo>=final_y-TOL and hi<=top+TOL)
            matrix=head.get('frame_to_layout')
            anchor=[xs[0],top,head['text_placement']['anchor'][2]]
            position=list(Matrix44([a for row in matrix for a in row]).transform(anchor)) if matrix else anchor
            memberships=set(head.get('source_sheet_ids',[]))
            for e in group:
                if e['ref'] in used: memberships &= set(e.get('source_sheet_ids',[]))
            ref='graphic-table:'+hashlib.sha256('|'.join(signature).encode()).hexdigest()[:24]
            result.append(dict(ref=ref,type='GRAPHIC_TABLE',layout=layout,coordinate_frame=frame,
                position=position,local_bbox=[xs[0],final_y,xs[-1],top],frame_to_layout=matrix,
                source_sheet_ids=sorted(memberships),source_refs=sorted(used),
                review_only=any(e.get('review_only') for e in group if e['ref'] in used),
                bom=dict(status='unsupported' if rejected or not rows else 'readable_schedule' if is_4col else 'verified_template',source_kind='graphic_grid',rows=[] if rejected else rows,columns=len(keys),
                         column_mapping=columns,header_labels=[items[0]['text'] for items in labels],
                         warning=rejected or ('Bảng chưa có dòng vật tư đầy đủ' if not rows else
                         'Đã đọc bảng 4 cột và gắn ô nguồn; chưa đủ cột mã/mô tả/vật liệu để xác nhận danh tính chi tiết. Không tự tạo mã từ tên hay số thứ tự.' if is_4col else
                         'Bảng LINE/TEXT đã gắn từng ô với entity nguồn; liên kết cơ khí cần bằng chứng riêng.'))))
            seen.add(signature)
    return result


def document_tables(doc, sheets):
    """Inspect native containers once; expand only containers with BOM headers."""
    from cad.catalog import text_of
    from cad.geometry import snapshot
    candidates={}
    def has_header(container):
        name=container.block_record_handle
        if name not in candidates:
            candidates[name]=any(e.dxftype() in ('TEXT','MTEXT') and normalized(text_of(e) or '') in ALIASES['number'] for e in container)
        return candidates[name]
    result=[]
    def visit(container, prefix, matrix, layout, ancestry=(),attributes=()):
        if has_header(container):
            records=[]
            for e in container:
                kind=e.dxftype();ref=prefix+e.dxf.handle
                r=dict(ref=ref,type=kind,layout=layout,coordinate_frame='instance:'+prefix[:-1] if prefix else 'layout:'+layout,
                       frame_to_layout=[list(matrix.get_row(i)) for i in range(4)])
                from cad.legacy_polyline import supported
                if kind in ('LINE','LWPOLYLINE') or kind=='POLYLINE' and supported(e): r['geometry']=snapshot(e)
                elif kind in ('TEXT','MTEXT'):
                    r['text']=text_of(e);r['raw_text']=e.text if kind=='MTEXT' else e.dxf.text
                    anchor=e.dxf.insert
                    if kind=='TEXT' and (e.dxf.halign or e.dxf.valign): anchor=e.dxf.get('align_point',anchor)
                    r['text_placement']=dict(anchor=list(anchor),height=e.dxf.char_height if kind=='MTEXT' else e.dxf.height,rotation=e.dxf.get('rotation',0),extrusion=list(e.dxf.get('extrusion',(0,0,1))),direction=list(e.dxf.get('text_direction',(1,0,0))) if kind=='MTEXT' else [1,0,0])
                else: continue
                records.append(r)
            for table in discover(records):
                box=table['local_bbox'];corners=[matrix.transform((x,y,0)) for x in (box[0],box[2]) for y in (box[1],box[3])]
                parents=[s['id'] for s in sheets if s.get('layout')==layout and s.get('bbox') and all(
                    s['bbox'][0]-TOL<=p.x<=s['bbox'][2]+TOL and s['bbox'][1]-TOL<=p.y<=s['bbox'][3]+TOL for p in corners)]
                if parents:
                    table.update(source_sheet_ids=parents,container_ref=prefix[:-1] or None,
                                 container_name=container.name,container_attributes=list(attributes))
                    result.append(table)
        for e in container:
            if e.dxftype()!='INSERT' or e.dxf.name not in doc.blocks:continue
            if e.dxf.name in ancestry:raise ValueError('Block tham chiếu vòng khi đọc bảng kê: '+e.dxf.name)
            if len(ancestry)>=128:raise ValueError('Block lồng quá 128 cấp khi đọc bảng kê')
            visit(doc.blocks[e.dxf.name],prefix+e.dxf.handle+'/',e.matrix44()*matrix,layout,ancestry+(e.dxf.name,),
                  [(a.dxf.tag,a.dxf.text) for a in e.attribs])
    for layout in doc.layouts:visit(layout,'',Matrix44(),layout.name)
    return result
