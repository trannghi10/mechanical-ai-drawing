"""Regenerate linear/aligned dimension pictures without serializing the document."""
from io import StringIO
from ezdxf.lldxf.tagwriter import TagWriter
from cad.geometry import near


def native_tolerance(entity):
    override=entity.override()
    return {key:override.get(key,default) for key,default in
            [('dimtol',0),('dimlim',0),('dimtp',0.),('dimtm',0.),('dimdec',2),('dimtdec',2)]}


def matches_displayed_nominal(record,value):
    """Compare BOM nominal with real DIM at its recorded decimal precision.

    This never changes actual geometry or treats a literal override as a
    measurement. Unknown formatting retains the old strict comparison.
    """
    import math
    from decimal import Decimal,ROUND_HALF_UP
    if record.get('type')!='DIMENSION' or record.get('dimension_type',0) not in (0,1):return False
    if record.get('geometry',{}).get('text') not in ('','<>') or record.get('linear_factor',1)!=1:return False
    measured=record.get('scaled_measurement',0)
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (value,measured)):return False
    if abs(measured-value)<1e-6:return True
    precision=record.get('dimension_tolerance',{}).get('dimdec')
    if type(precision)!=int or not 0<=precision<=8 or record.get('dimension_rounding')!=0:return False
    quantum=Decimal(1).scaleb(-precision)
    actual=Decimal(str(measured)).quantize(quantum,rounding=ROUND_HALF_UP)
    return actual==Decimal(str(value))


def verify_tolerance(before,after):
    if not near(native_tolerance(before),native_tolerance(after),1e-9):
        raise ValueError('DWG xuất không giữ dung sai/độ chính xác DIM native')


def linear_axis(record):
    """Return the native measurement direction, independent of display angle.

    Aligned DIMs measure their extension points. Their optional DXF angle can
    be zero or stale and must never determine the stretch direction.
    """
    import math
    g=record.get('geometry',{})
    kind=record.get('dimension_type',0)
    if record.get('type')!='DIMENSION' or kind not in (0,1) or g.get('text') not in ('','<>'):
        raise ValueError('Cần DIM linear/aligned đo thật, không ghi đè số')
    points=[g.get(k) for k in ('defpoint2','defpoint3')]
    if any(not isinstance(p,(list,tuple)) or len(p)!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in p) for p in points):
        raise ValueError('Điểm đo DIM không hợp lệ')
    a,b=points
    if abs(a[2]-b[2])>1e-6:
        raise ValueError('DIM đo xiên ra ngoài mặt phẳng 2D chưa hỗ trợ')
    if kind==1:
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length<=1e-9:raise ValueError('DIM có độ dài 0')
        return [dx/length,dy/length,0.]
    angle=g.get('angle')
    if not isinstance(angle,(int,float)) or not math.isfinite(angle):raise ValueError('Góc DIM không hợp lệ')
    angle=math.radians(angle)
    return [math.cos(angle),math.sin(angle),0.]


def dimension_snapshot(entity):
    if entity.dxftype()=='DIMENSION' and entity.dxf.dimtype & 15==2:
        return {key:list(entity.dxf.get(key)) for key in ('defpoint','defpoint2','defpoint3','defpoint4','defpoint5')}|{'text':entity.dxf.get('text','<>')}
    if entity.dxftype()=='DIMENSION' and entity.dxf.dimtype & 15 in (3,4):
        return {key:list(entity.dxf.get(key)) for key in ('defpoint','defpoint4')}|{'text':entity.dxf.get('text','<>')}
    if entity.dxftype()!='DIMENSION' or entity.dxf.dimtype & 15 not in (0,1):
        raise ValueError('Chỉ hỗ trợ kích thước linear/aligned')
    return {key:list(entity.dxf.get(key)) for key in ('defpoint','defpoint2','defpoint3')}|{
        'angle':entity.dxf.get('angle',0),'text':entity.dxf.get('text','<>')}


def serialize(entity):
    stream=StringIO();entity.export_dxf(TagWriter(stream,dxfversion=entity.doc.dxfversion))
    return stream.getvalue().encode('utf8').splitlines(keepends=True)


def rigid_label_motion(before,after):
    """Existing literal leaders may move rigidly without changing their value."""
    if before.keys()!=after.keys() or before.get('text')!=after.get('text'):return False
    keys=[k for k in before if k.startswith('defpoint')]
    if not keys:return False
    shifts=[[b-a for a,b in zip(before[k],after[k])] for k in keys]
    return all(near(s,shifts[0]) for s in shifts) and all(near(before[k],after[k]) for k in before if k not in keys)


def text_side(entity,g):
    """Source glyph side for a simple planar linear DIM, when unambiguous."""
    import math
    if entity.dxf.dimtype & 15 not in (0,1):return None
    block=entity.doc.blocks.get(entity.dxf.get('geometry',''))
    if block is None:return None
    texts=[t for t in block if t.dxftype() in ('TEXT','MTEXT')]
    if len(texts)!=1 or not near(list(texts[0].dxf.extrusion),[0,0,1]):return None
    if entity.dxf.dimtype & 15==1:
        a,b=g['defpoint2'],g['defpoint3'];angle=math.atan2(b[1]-a[1],b[0]-a[0])
    else:angle=math.radians(g['angle'])
    normal=[-math.sin(angle),math.cos(angle)]
    insert=texts[0].dxf.insert
    offset=sum((insert[i]-g['defpoint'][i])*normal[i] for i in (0,1))
    return (normal,offset,texts[0]) if abs(offset)>1e-6 else None


def regenerate(entity,before,after,association_checked=False,nominal_checked=False):
    if not near(dimension_snapshot(entity),before):raise ValueError('Dimension before không khớp nguồn')
    if after.keys()!=before.keys():raise ValueError('Dimension thiếu/thừa thông số')
    if (entity.has_extension_dict or entity.get_reactors()) and not association_checked:raise ValueError('Dimension có association native ngoài entity; cần CAD SDK xử lý liên kết')
    fixed_motion=rigid_label_motion(before,after)
    original_side=text_side(entity,before)
    if nominal_checked:
        from cad.broken_tube import label
        old,new=label(before.get('text')),label(after.get('text'))
        if not old or not new or old[1]!=new[1] or not near({k:v for k,v in before.items() if k!='text'},{k:v for k,v in after.items() if k!='text'}):
            raise ValueError('DIM danh nghĩa chỉ đổi chiều dài cắt, giữ hình rút ngắn và dung sai nguồn')
    elif after['text'] not in ('','<>') and '<>' not in after['text'] and not fixed_motion:raise ValueError('Không ghi đè số đo bằng text cố định')
    if not near(list(entity.dxf.extrusion),[0,0,1]):raise ValueError('Dimension OCS nghiêng cần CAD SDK')
    import math
    radial=entity.dxf.dimtype & 15 in (3,4)
    angular=entity.dxf.dimtype & 15==2
    for key in (('defpoint','defpoint2','defpoint3','defpoint4','defpoint5') if angular else ('defpoint','defpoint4') if radial else ('defpoint','defpoint2','defpoint3')):
        if len(after[key])!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in after[key]):raise ValueError('Điểm dimension không hợp lệ')
        entity.dxf.set(key,after[key])
    if not radial and not angular:
        if not isinstance(after['angle'],(int,float)) or not math.isfinite(after['angle']):raise ValueError('Góc dimension không hợp lệ')
        entity.dxf.angle=after['angle']
    entity.dxf.text=after['text']
    endpoints=(after['defpoint'],after['defpoint4']) if radial else (after['defpoint2'],after['defpoint3'])
    if not angular and near(*endpoints):raise ValueError('Dimension có độ dài 0')
    doc=entity.doc;old_blocks={block.name for block in doc.blocks}
    if entity.dxf.dimtype & 15==1:
        a,b=after['defpoint2'],after['defpoint3']
        entity.dxf.angle=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
    angular_value=None
    if angular:
        from ezdxf.math import Vec2,intersection_line_line_2d
        keys=(('defpoint','defpoint4'),('defpoint3','defpoint2'))
        def rays(g,toward_label=False):
            legs=[[Vec2(g[k]) for k in pair] for pair in keys]
            center=intersection_line_line_2d(*legs)
            if center is None:raise ValueError('DIM góc không có giao điểm hai cạnh')
            label=Vec2(g['defpoint5'])-center
            if label.magnitude<1e-8:raise ValueError('DIM góc thiếu vị trí cung đo')
            directions=[]
            for leg in legs:
                direction=(leg[1]-leg[0]).normalize()
                reference=label if toward_label else max(leg,key=lambda p:(p-center).magnitude)-center
                if abs(direction.dot(reference))<1e-8:raise ValueError('DIM góc chưa xác định được tia đo')
                directions.append(direction if direction.dot(reference)>0 else -direction)
            return center,legs,directions,label
        def sector(directions,label):
            a,b=[v.angle for v in directions];span=(b-a)%(2*math.pi)
            inside=(label.angle-a)%(2*math.pi)<=span+1e-8
            return span if inside else 2*math.pi-span,inside
        old_center,old_legs,old_directions,old_label=rays(before)
        old_value,_=sector(old_directions,old_label)
        # AutoCAD's optional group 42 is in radians for angular dimensions.
        # It disambiguates cases where a leg crosses its intersection and
        # the farther endpoint represents the opposite ray of the CAD view.
        cached=entity.dxf.get('actual_measurement')
        if isinstance(cached,(int,float)) and 0<cached<2*math.pi and abs(old_value-cached)>1e-6:
            old_center,old_legs,old_directions,old_label=rays(before,True)
            old_value,_=sector(old_directions,old_label)
            if abs(old_value-cached)>1e-6:raise ValueError('DIM góc nguồn có sector/mốc cung mâu thuẫn; cần xác định lại')
        legs=[[Vec2(after[k]) for k in pair] for pair in keys]
        center=intersection_line_line_2d(*legs)
        if center is None:raise ValueError('DIM góc không có giao điểm hai cạnh')
        directions=[]
        for old_leg,new_leg,chosen in zip(old_legs,legs,old_directions):
            old_axis=(old_leg[1]-old_leg[0]).normalize();new_axis=(new_leg[1]-new_leg[0]).normalize()
            directions.append(new_axis if old_axis.dot(chosen)>0 else -new_axis)
        value,inside=sector(directions,Vec2(after['defpoint5'])-center)
        if (value>math.pi+1e-7)!=(old_value>math.pi+1e-7):raise ValueError('Vị trí cung DIM góc đổi sector sau sửa')
        angular_value=math.degrees(value)
        # The renderer uses a leg's first endpoint unless it equals the
        # intersection. Canonicalize only its visual rays; restore all native
        # extension points below so associations and measurements are intact.
        for pair,leg,direction in zip(keys,legs,directions):
            length=max((p-center).magnitude for p in leg)
            end=center+direction*length
            entity.dxf.set(pair[0],[center.x,center.y,after[pair[0]][2]])
            entity.dxf.set(pair[1],[end.x,end.y,after[pair[1]][2]])
        if not inside:
            # Native CAD selects the sector containing defpoint5. ezdxf's
            # renderer uses the ordered legs, so swap only while generating
            # its display block, then restore all native association points.
            visual={k:list(entity.dxf.get(k)) for pair in keys for k in pair}
            for key,other in (('defpoint','defpoint3'),('defpoint4','defpoint2'),('defpoint3','defpoint'),('defpoint2','defpoint4')):
                entity.dxf.set(key,visual[other])
    def render_visual():
        renderer=entity.override().render()
        if angular and abs(renderer.arc_angle_span_rad-math.radians(angular_value))>1e-7:
            raise ValueError('Hình DIM góc dựng lại khác sector đo thật')
    if nominal_checked or fixed_motion:
        # ezdxf appends native tolerance even when a fixed nominal override
        # already contains it. Render that literal suffix once, then restore
        # the exact source ACAD style overrides before serializing the DIM.
        tolerance=native_tolerance(entity)
        from cad.broken_tube import label
        parsed_label=label(after['text']);suffix=parsed_label[1] if parsed_label else ''
        if suffix and (tolerance['dimtol'] or tolerance['dimlim']):
            nominal_tol=float(suffix[3:].replace(',','.'))
            if tolerance['dimlim'] or not near([tolerance['dimtp'],tolerance['dimtm']],[nominal_tol,nominal_tol],1e-7):
                raise ValueError('Dung sai ghi trong DIM danh nghĩa không khớp dung sai native nguồn')
            had_acad=entity.has_xdata('ACAD')
            source_acad=list(entity.get_xdata('ACAD')) if had_acad else None
            visual=entity.override();visual['dimtol']=0;visual['dimlim']=0
            try:visual.render()
            finally:
                if had_acad:entity.set_xdata('ACAD',source_acad)
                else:entity.discard_xdata('ACAD')
        else:render_visual()
    else:render_visual()
    if original_side and not angular and not radial:
        rendered_side=text_side(entity,after)
        if rendered_side and original_side[1]*rendered_side[1]<0:
            # CAD exporters and ezdxf can choose opposite text sides for a
            # reversed linear measurement. Keep the source side without
            # changing DIM endpoints, units, tolerance or numeric text.
            normal,offset,text=rendered_side
            target=math.copysign(abs(offset),original_side[1]);delta=target-offset
            shift=[delta*normal[0],delta*normal[1],0]
            text.dxf.insert=[a+b for a,b in zip(text.dxf.insert,shift)]
            midpoint=entity.dxf.get('text_midpoint')
            if midpoint is not None:entity.dxf.text_midpoint=[a+b for a,b in zip(midpoint,shift)]
    if angular:
        for key in ('defpoint','defpoint2','defpoint3','defpoint4','defpoint5'):entity.dxf.set(key,after[key])
    elif not radial:entity.dxf.angle=after['angle']
    # Rendering canonicalizes defpoint to an extension-line endpoint. Preserve the
    # requested dimension-line location after constructing its display block.
    # The projection along the dimension axis does not affect the dimension line.
    entity.dxf.defpoint=after['defpoint']
    entity.dxf.actual_measurement=math.radians(angular_value) if angular else math.dist(entity.dxf.defpoint2,entity.dxf.defpoint3) if entity.dxf.dimtype & 15==1 else entity.get_measurement()
    new_blocks=[b for b in doc.blocks if b.name not in old_blocks]
    return serialize(entity),new_blocks


def new_block_insertions(lines,blocks,doc):
    if not blocks:return {}
    records=[];geometry=[]
    for block in blocks:
        records.extend(serialize(block.block_record))
        geometry.extend(serialize(block.block))
        for entity in block:geometry.extend(serialize(entity))
        geometry.extend(serialize(block.endblk))
    section=None;table=None;inserts={}
    for i in range(0,len(lines)-2,2):
        code,value=lines[i].strip(),lines[i+1].strip()
        if code==b'0' and value==b'SECTION':section=lines[i+3].strip()
        if code==b'0' and value==b'TABLE':table=lines[i+3].strip()
        if code==b'0' and value==b'ENDTAB':
            if table==b'BLOCK_RECORD':inserts[i]=records
            table=None
        if code==b'0' and value==b'ENDSEC':
            if section==b'BLOCKS':inserts[i]=geometry
            section=None
        if code==b'9' and value==b'$HANDSEED':
            if lines[i+2].strip()!=b'5':raise ValueError('HANDSEED không hợp lệ')
            newline=b'\r\n' if lines[i+3].endswith(b'\r\n') else b'\n'
            lines[i+3]=str(doc.entitydb.handles).encode()+newline
    if len(inserts)!=2:raise ValueError('Thiếu section để thêm dimension geometry')
    return inserts
