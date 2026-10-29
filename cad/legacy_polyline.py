"""Preserve classic 2D POLYLINE/VERTEX/SEQEND sequences when editing XY.

No conversion to LWPOLYLINE and no reserialization of unrelated CAD data.
Curve-fit, spline-fit, mesh and 3D polylines require different adapters.
"""
import math


def supported(entity):
    return (entity.dxftype()=='POLYLINE' and entity.is_2d_polyline and
            entity.dxf.flags & ~129==0 and
            all(v.dxf.flags==0 for v in entity.vertices))


def snapshot(entity):
    if not supported(entity):raise ValueError('POLYLINE cần dạng 2D thường; fit/spline/mesh/3D chưa có adapter')
    return dict(points=[[v.dxf.location.x,v.dxf.location.y,v.dxf.get('start_width',0),
                         v.dxf.get('end_width',0),v.dxf.get('bulge',0)] for v in entity.vertices],
                closed=entity.is_closed,elevation=entity.dxf.elevation.z,extrusion=list(entity.dxf.extrusion),
                flags=entity.dxf.flags,vertex_flags=[v.dxf.flags for v in entity.vertices],
                vertex_z=[v.dxf.location.z for v in entity.vertices],
                default_widths=[entity.dxf.get('default_start_width',0),entity.dxf.get('default_end_width',0)])


def sequence_span(entity,spans,lines):
    handles=[v.dxf.handle for v in [entity,*entity.vertices,entity.seqend]]
    if len(handles)!=len(set(handles)) or any(h not in spans for h in handles):
        raise ValueError('POLYLINE thiếu/trùng VERTEX hoặc SEQEND nguồn')
    ranges=[spans[h] for h in handles]
    if any(a[1]!=b[0] for a,b in zip(ranges,ranges[1:])):
        raise ValueError('Chuỗi POLYLINE/VERTEX/SEQEND không liên tục')
    if len(lines[ranges[0][0]:ranges[-1][1]])%2:raise ValueError('Chuỗi POLYLINE có tag thiếu cặp')
    return ranges[0][0],ranges[-1][1]


def patch(entity,raw,before,after):
    from cad.geometry import near
    if entity.has_extension_dict or entity.get_reactors():
        raise ValueError('POLYLINE có association native chưa hỗ trợ; cần adapter liên kết trước khi sửa')
    current=snapshot(entity)
    if not near(current,before) or current.keys()!=after.keys():raise ValueError('POLYLINE snapshot không khớp nguồn')
    for key in current.keys()-{'points'}:
        if not near(current[key],after[key]):raise ValueError('Giữ nguyên cấu trúc/hệ tọa độ POLYLINE: '+key)
    points=after['points']
    if len(points)!=len(current['points']) or any(len(p)!=5 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in p) for p in points):
        raise ValueError('Giữ nguyên số đỉnh POLYLINE và tọa độ hữu hạn')
    if any(not near(a[2:],b[2:]) for a,b in zip(current['points'],points)):
        raise ValueError('Giữ nguyên width/bulge POLYLINE')
    from cad.edit_engine import chunks
    ranges=list(chunks(raw));expected=[e for e in [entity,*entity.vertices,entity.seqend]]
    if [h for h,_,_ in ranges]!=[e.dxf.handle for e in expected]:raise ValueError('Chuỗi tag POLYLINE không khớp source handles')
    newline=b'\r\n' if raw[0].endswith(b'\r\n') else b'\n'
    for (_,a,b),vertex,p in zip(ranges[1:-1],entity.vertices,points):
        if vertex.has_extension_dict or vertex.get_reactors():raise ValueError('VERTEX có association native chưa hỗ trợ')
        for code,value in ((10,p[0]),(20,p[1])):
            locations=[i for i in range(a,b,2) if raw[i].strip()==str(code).encode()]
            if len(locations)!=1:raise ValueError('VERTEX thiếu/trùng tọa độ nguồn')
            raw[locations[0]+1]=str(value).encode('ascii')+newline
    return raw
