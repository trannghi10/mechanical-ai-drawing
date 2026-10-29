"""Add explicit assembly edges without reserializing untouched DXF sections."""
import json,math
from cad.geometry import snapshot,near
from cad.dimensions import serialize


def add_lines(doc,frame,before,after,allowed_refs):
    if frame.dxftype()!='LWPOLYLINE' or not frame.closed or not near(snapshot(frame),json.loads(before)):
        raise ValueError('Thêm cạnh cần khung nguồn kín đã kiểm chứng')
    owner=doc.entitydb.get(frame.dxf.owner)
    if owner is None or not owner.dxf.get('layout') or not near(list(frame.dxf.extrusion),[0,0,1]):
        raise ValueError('Chỉ thêm cạnh trong layout, không sửa block dùng chung')
    spec=json.loads(after)
    if set(spec)!={'style_ref','style_geometry','lines'} or spec['style_ref'] not in allowed_refs or '/' in spec['style_ref']:
        raise ValueError('Style cạnh mới ngoài phạm vi hoặc thiếu binding')
    style=doc.entitydb.get(spec['style_ref'])
    if style is None or style.dxftype()!='LINE' or style.dxf.owner!=frame.dxf.owner or not near(snapshot(style),spec['style_geometry']):
        raise ValueError('Style cạnh mới không khớp LINE nguồn cùng layout')
    points=list(frame.get_points('xyseb'))
    if len(points)!=4 or any(any(v!=0 for v in p[2:]) for p in points):raise ValueError('Khung thêm cạnh phải là hình chữ nhật thẳng')
    xs=sorted({p[0] for p in points});ys=sorted({p[1] for p in points})
    if len(xs)!=2 or len(ys)!=2:raise ValueError('Khung nguồn không phải hình chữ nhật')
    specs=spec['lines']
    if not isinstance(specs,list) or not 1<=len(specs)<=100:raise ValueError('Số cạnh thêm không hợp lệ')
    for g in specs:
        if not isinstance(g,dict) or set(g)!={'start','end'}:raise ValueError('Chỉ thêm LINE có hai đầu rõ ràng')
        for p in g.values():
            if not isinstance(p,list) or len(p)!=3 or not all(type(v) in (int,float) and math.isfinite(v) for v in p):raise ValueError('Điểm cạnh mới không hữu hạn')
            if not xs[0]<=p[0]<=xs[1] or not ys[0]<=p[1]<=ys[1] or abs(p[2]-frame.dxf.elevation)>1e-8:
                raise ValueError('Cạnh thêm ngoài khung nguồn đã chọn')
        if near(g['start'],g['end']):raise ValueError('Cạnh thêm có chiều dài bằng 0')
    attrs={k:v for k,v in style.dxfattribs().items() if k in ('layer','color','linetype','lineweight','ltscale','true_color','transparency')}
    layout=doc.layouts.get_layout_for_entity(frame)
    result=[]
    for g in specs:
        entity=layout.add_line(g['start'],g['end'],dxfattribs=attrs)
        result.append(dict(handle=entity.dxf.handle,geometry=snapshot(entity),layer=entity.dxf.layer,owner=entity.dxf.owner,raw=serialize(entity)))
    return result


def insertions(lines,entities,doc,existing):
    if not entities:return existing
    result=dict(existing);section=None;found=False
    for i in range(0,len(lines)-2,2):
        code,value=lines[i].strip(),lines[i+1].strip()
        if code==b'0' and value==b'SECTION':section=lines[i+3].strip()
        elif code==b'0' and value==b'ENDSEC':
            if section==b'ENTITIES':
                result.setdefault(i,[]).extend(raw for entity in entities for raw in entity['raw']);found=True
            section=None
        elif code==b'9' and value==b'$HANDSEED':
            if lines[i+2].strip()!=b'5':raise ValueError('HANDSEED không hợp lệ')
            newline=b'\r\n' if lines[i+3].endswith(b'\r\n') else b'\n'
            lines[i+3]=str(doc.entitydb.handles).encode()+newline
    if not found:raise ValueError('Thiếu section ENTITIES để thêm cạnh')
    return result
