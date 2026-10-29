"""Translate an INSERT and its instance-owned attributes without serialization.

Definitions, including opaque definition metadata, are never edited here.
External reactors and instance dictionaries require native reevaluation and
are rejected. Attribute coordinates are in the parent's WCS/attribute OCS,
not in the inserted definition's rotated/scaled coordinate system.
"""
from ezdxf.math import Vec3,OCS
from cad.geometry import near


def attribute_updates(entity,delta,spans,lines,changes):
    if entity.has_extension_dict or entity.get_reactors():
        raise ValueError('INSERT có association/dữ liệu instance ngoài hình học; cần adapter CAD native trước khi dịch')
    result=[]
    for attr in entity.attribs:
        if attr.dxf.owner!=entity.dxf.handle or attr.has_extension_dict or attr.get_reactors():
            raise ValueError('ATTRIB có ownership/association chưa hỗ trợ dịch')
        handle=attr.dxf.handle
        if getattr(attr,'has_embedded_mtext_entity',False):raise ValueError('ATTRIB nhiều dòng cần adapter native riêng')
        if handle not in spans:raise ValueError('Thiếu ATTRIB native trong file nguồn')
        start,end=spans[handle];raw=list(changes[start][1] if start in changes else lines[start:end])
        newline=b'\r\n' if raw[0].endswith(b'\r\n') else b'\n'
        vector=OCS(attr.dxf.extrusion).from_wcs(Vec3(delta));points={}
        for field,code in [('insert',10),('align_point',11)]:
            if not attr.dxf.hasattr(field):continue
            before=list(attr.dxf.get(field));after=list(Vec3(before)+vector)
            for axis,value in enumerate(after):
                tag=code+10*axis
                slots=[i for i in range(0,len(raw),2) if raw[i].strip()==str(tag).encode()]
                # R2018 repeats the same alignment point in AcDbText and
                # AcDbAttribute. Keep both native copies synchronized.
                if len(slots)>(2 if field=='align_point' else 1):raise ValueError('ATTRIB nhiều dòng cần adapter native riêng')
                if any(abs(float(raw[i+1])-before[axis])>1e-7 for i in slots):raise ValueError('Hai bản điểm ATTRIB nguồn không khớp')
                if slots:
                    for i in slots:raw[i+1]=repr(float(value)).encode()+newline
                elif abs(value)>1e-12:
                    # Omitted DXF Z components default to zero. Add the group
                    # beside its point only when a 3D translation needs it.
                    preceding=[i for i in range(0,len(raw),2) if raw[i].strip() in [str(code+10*j).encode() for j in range(axis)]]
                    if not preceding:raise ValueError('Thiếu tọa độ ATTRIB nguồn')
                    at=max(preceding)+2;raw[at:at]=[str(tag).encode()+newline,repr(float(value)).encode()+newline]
            points[field]=dict(before=before,after=after)
        if not points:raise ValueError('ATTRIB không có điểm chèn')
        result.append(dict(handle=handle,start=start,end=end,raw=raw,points=points))
    return result


def verify(document,updates):
    for update in updates:
        attr=document.entitydb.get(update['handle'])
        if attr is None or attr.dxftype()!='ATTRIB':raise ValueError('Mất ATTRIB sau dịch block')
        for field,points in update['points'].items():
            if not near(list(attr.dxf.get(field)),points['after'],1e-7):raise ValueError('ATTRIB chưa dịch đồng bộ với block')
