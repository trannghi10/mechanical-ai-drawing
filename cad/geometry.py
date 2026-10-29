"""Explicit geometry snapshots and type-preserving raw tag updates."""
import math


def snapshot(entity):
    kind=entity.dxftype()
    if kind=='HATCH':
        from cad.hatch_translation import snapshot as hatch_snapshot
        return hatch_snapshot(entity)
    if kind=='DIMENSION':
        from cad.dimensions import dimension_snapshot
        return dimension_snapshot(entity)
    if kind=='LINE':return {'start':list(entity.dxf.start),'end':list(entity.dxf.end)}
    if kind=='LEADER':return {'vertices':[list(p) for p in entity.vertices]}
    if kind=='POLYLINE':
        from cad.legacy_polyline import snapshot as polyline_snapshot
        return polyline_snapshot(entity)
    if kind=='LWPOLYLINE':return {'points':[list(p) for p in entity.get_points('xyseb')],'closed':entity.closed,
                                'elevation':entity.dxf.elevation,'extrusion':list(entity.dxf.extrusion)}
    if kind in ('CIRCLE','ARC'):
        data={'center':list(entity.dxf.center),'radius':entity.dxf.radius,'extrusion':list(entity.dxf.extrusion)}
        if kind=='ARC':data.update(start_angle=entity.dxf.start_angle,end_angle=entity.dxf.end_angle)
        return data
    if kind=='ELLIPSE':return {'center':list(entity.dxf.center),'major_axis':list(entity.dxf.major_axis),
                              'ratio':entity.dxf.ratio,'start_param':entity.dxf.start_param,'end_param':entity.dxf.end_param,
                              'extrusion':list(entity.dxf.extrusion)}
    if kind=='SPLINE':return {'control_points':[list(p) for p in entity.control_points],
                             'fit_points':[list(p) for p in entity.fit_points],
                             'knots':list(entity.knots),'weights':list(entity.weights),
                             'degree':entity.dxf.degree,'flags':entity.dxf.flags}
    raise ValueError('Entity chưa hỗ trợ snapshot geometry: '+kind)


def near(a,b,tolerance=1e-7):
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(near(v,b[k],tolerance) for k,v in a.items())
    if isinstance(a,(list,tuple)):return isinstance(b,(list,tuple)) and len(a)==len(b) and all(near(x,y,tolerance) for x,y in zip(a,b))
    if isinstance(a,(int,float)):return isinstance(b,(int,float)) and math.isfinite(b) and abs(a-b)<=tolerance
    return a==b


def patch_geometry(entity,raw,before,after):
    if entity.dxftype()=='HATCH':
        from cad.hatch_translation import patch
        return patch(entity,raw,before,after)
    if entity.dxftype()=='POLYLINE':
        from cad.legacy_polyline import patch
        return patch(entity,raw,before,after)
    current=snapshot(entity)
    if not near(current,before):raise ValueError('Geometry before không khớp nguồn')
    if current.keys()!=after.keys():raise ValueError('Geometry after thiếu hoặc thừa thuộc tính')
    def finite(value):
        if isinstance(value,dict):return all(finite(v) for v in value.values())
        if isinstance(value,list):return all(finite(v) for v in value)
        return isinstance(value,(int,float)) and math.isfinite(value)
    if not finite(after):raise ValueError('Geometry chứa giá trị không hữu hạn hoặc sai kiểu')
    newline=b'\r\n' if raw[0].endswith(b'\r\n') else b'\n'
    def set_values(code,values):
        positions=[i for i in range(0,len(raw),2) if raw[i].strip()==str(code).encode()]
        if len(positions)!=len(values):raise ValueError(f'Group {code} không khớp topology; cần adapter native')
        for index,value in zip(positions,values):raw[index+1]=str(value).encode()+newline
    def point(code,points):
        if any(len(p)!=3 for p in points):raise ValueError('Tọa độ phải có 3 thành phần')
        for offset in range(3):set_values(code+offset*10,[p[offset] for p in points])
    kind=entity.dxftype()
    if kind=='LINE':
        point(10,[after['start']]);point(11,[after['end']])
        if near(after['start'],after['end']):raise ValueError('LINE không được có chiều dài 0')
    elif kind=='LEADER':
        if len(after['vertices'])!=len(current['vertices']) or len(after['vertices'])<2:
            raise ValueError('Giữ nguyên topology đường dẫn chi tiết')
        point(10,after['vertices'])
    elif kind=='LWPOLYLINE':
        points=after['points']
        if len(points)!=len(current['points']) or any(len(p)!=5 for p in points):raise ValueError('Chưa hỗ trợ đổi topology polyline')
        for key in ('closed','elevation','extrusion'):
            if not near(current[key],after[key]):raise ValueError('Giữ nguyên hệ tọa độ và trạng thái đóng polyline')
        # Preserve widths and bulges; only reposition existing vertices.
        if any(not near(a[2:],b[2:]) for a,b in zip(current['points'],points)):raise ValueError('Chưa hỗ trợ đổi bulge/width khi stretch polyline')
        set_values(10,[p[0] for p in points]);set_values(20,[p[1] for p in points])
    elif kind in ('CIRCLE','ARC'):
        if after['radius']<=0:raise ValueError('Bán kính phải lớn hơn 0')
        if not near(current['extrusion'],after['extrusion']):raise ValueError('Không đổi extrusion')
        point(10,[after['center']]);set_values(40,[after['radius']])
        if kind=='ARC':set_values(50,[after['start_angle']]);set_values(51,[after['end_angle']])
    elif kind=='ELLIPSE':
        if not 0<after['ratio']<=1 or near(after['major_axis'],[0,0,0]):raise ValueError('Ellipse không hợp lệ')
        if not near(current['extrusion'],after['extrusion']):raise ValueError('Không đổi extrusion ellipse')
        point(10,[after['center']]);point(11,[after['major_axis']]);set_values(40,[after['ratio']]);set_values(41,[after['start_param']]);set_values(42,[after['end_param']])
    elif kind=='SPLINE':
        for key in ('knots','weights','degree','flags'):
            if not near(current[key],after[key]):raise ValueError('Giữ nguyên topology/nội suy spline')
        for key,code in (('control_points',10),('fit_points',11)):
            if len(current[key])!=len(after[key]):raise ValueError('Không đổi số control/fit points')
            point(code,after[key])
    return raw
