"""Rigid translation of source-bound text, retaining both justification points."""
import json,math
from cad.geometry import near


def anchor(entity):
    if entity.dxftype() not in ('TEXT','MTEXT'):raise ValueError('Chỉ dịch TEXT/MTEXT độc lập')
    if entity.dxftype()=='TEXT' and (entity.dxf.get('halign',0) or entity.dxf.get('valign',0)):
        return list(entity.dxf.get('align_point',entity.dxf.insert))
    return list(entity.dxf.insert)


def snapshot(entity):
    result=dict(insert=list(entity.dxf.insert),text=entity.text if entity.dxftype()=='MTEXT' else entity.dxf.text,
        anchor=anchor(entity),rotation=entity.dxf.get('rotation',0),style=entity.dxf.get('style','Standard'),
        extrusion=list(entity.dxf.get('extrusion',(0,0,1))))
    if entity.dxf.hasattr('align_point'):result['align_point']=list(entity.dxf.align_point)
    return result


def patch(entity,raw,operation):
    current=snapshot(entity);expected=json.loads(operation.before)
    if expected!={'anchor':anchor(entity),'text':current['text']} or operation.after:
        raise ValueError('Vị trí/nội dung chữ trước dịch không khớp nguồn')
    if not near(current['extrusion'],[0,0,1]) or len(operation.xyz)!=3 or not all(math.isfinite(v) for v in operation.xyz):
        raise ValueError('Dịch chữ cần mặt phẳng XY và ba tọa độ hữu hạn')
    shift=[b-a for a,b in zip(current['anchor'],operation.xyz)];after=dict(current)
    for name,code in (('insert',10),('align_point',11)):
        if name not in current:continue
        after[name]=[a+b for a,b in zip(current[name],shift)]
        for offset,value in enumerate(after[name]):
            positions=[i for i in range(0,len(raw),2) if raw[i].strip()==str(code+offset*10).encode()]
            if len(positions)>1 or (not positions and (offset<2 or abs(value)>1e-8)):
                raise ValueError('Tọa độ chữ thiếu hoặc trùng trong DXF')
            if positions:
                i=positions[0];nl=b'\r\n' if raw[i+1].endswith(b'\r\n') else b'\n';raw[i+1]=str(value).encode()+nl
    after['anchor']=list(operation.xyz)
    return raw,after
