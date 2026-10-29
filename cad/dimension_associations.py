"""Rebind measured endpoints, straight midpoints and centers in DIMASSOC.

DXF point-reference codes: Autodesk DIMASSOC reference, GUID-C0B96256.
Copied polylines can retain stale GS markers; bind the unique measured vertex
to an incident straight edge instead of trusting those copied markers.
"""
import json,math
from cad.geometry import near,snapshot
from cad.osnap_references import point_references


def perpendicular_point(geometry,edge,anchor):
    if not geometry['closed'] or not near(geometry['extrusion'],[0,0,1]):raise ValueError('DIMASSOC perpendicular cần biên đóng XY')
    points=geometry['points'];p=points[edge];q=points[(edge+1)%len(points)];a=points[anchor]
    if abs(p[4])>1e-10:raise ValueError('DIMASSOC perpendicular chưa hỗ trợ cạnh cung')
    dx,dy=q[0]-p[0],q[1]-p[1];length2=dx*dx+dy*dy
    if length2<=1e-18:raise ValueError('DIMASSOC perpendicular có cạnh suy biến')
    t=((a[0]-p[0])*dx+(a[1]-p[1])*dy)/length2
    if not math.isfinite(t) or t < -1e-8 or t > 1+1e-8:raise ValueError('DIMASSOC perpendicular nằm ngoài đoạn nguồn')
    t=max(0.,min(1.,t))
    return [p[0]+t*dx,p[1]+t*dy,geometry['elevation']],t


def bound_point(kind,geometry,binding):
    """Evaluate a source-bound snap, never a cached DIMASSOC point."""
    field=binding['endpoint']
    if field=='perpendicular':
        if kind!='LWPOLYLINE':raise ValueError('DIMASSOC perpendicular cần LWPOLYLINE')
        return perpendicular_point(geometry,binding['vertex_index'],binding['anchor_vertex_index'])[0]
    if field=='center':
        if kind not in ('CIRCLE','ARC') or not near(geometry['extrusion'],[0,0,1]):raise ValueError('DIMASSOC center cần đường tròn/cung XY')
        return geometry['center']
    if field=='midpoint':return [(a+b)/2 for a,b in zip(geometry['start'],geometry['end'])]
    if field in ('vertex','edge_midpoint'):
        i=binding['vertex_index'];points=geometry['points'];p=points[i]
        if field=='vertex':return [p[0],p[1],geometry['elevation']]
        q=points[(i+1)%len(points)]
        if abs(p[4])>1e-10:raise ValueError('DIMASSOC midpoint chưa hỗ trợ cạnh cung')
        return [(p[0]+q[0])/2,(p[1]+q[1])/2,geometry['elevation']]
    return geometry[field]


def update(entity,before,after,operations,raw_objects):
    if not entity.has_extension_dict and not entity.get_reactors():return []
    if getattr(entity.dxf,'dimtype',0) & 15 not in (0,1,2):raise ValueError('DIMASSOC bán kính/đường kính cần adapter native; không tháo liên kết để sửa')
    if not entity.has_extension_dict:raise ValueError('Dimension có reactor ngoài DIMASSOC; chưa hỗ trợ sửa liên kết này')
    extension=entity.get_extension_dict()
    if set(extension.keys())!={'ACAD_DIMASSOC'}:raise ValueError('Extension dimension ngoài DIMASSOC chưa hỗ trợ')
    assoc=extension['ACAD_DIMASSOC']
    if assoc.dxftype()!='DIMASSOC' or set(entity.get_reactors())!={assoc.dxf.handle}:raise ValueError('Dimension có association/reactor khác chưa hỗ trợ')
    raw=list(raw_objects[assoc.dxf.handle]);pairs=[(int(raw[i]),raw[i+1].strip().decode('utf8')) for i in range(0,len(raw),2)]
    start=next(i for i,(c,v) in enumerate(pairs) if c==100 and v=='AcDbDimAssoc')
    data=pairs[start+1:]
    flags=next((int(v) for c,v in data if c==90),None)
    angular=getattr(entity.dxf,'dimtype',0) & 15==2
    if flags not in ((15,) if angular else (1,2,3)) or next((v for c,v in data if c==330),None)!=entity.dxf.handle:
        raise ValueError('DIMASSOC không khớp dimension/bitmask hai điểm linear')
    if any(c in (70,71) and int(v)!=0 for c,v in data):raise ValueError('DIMASSOC không dùng hệ tọa độ WCS linear')
    nodes=point_references(pairs)
    bindings=((1,'defpoint2'),(2,'defpoint3'),(4,'defpoint4'),(8,'defpoint')) if angular else ((1,'defpoint2'),(2,'defpoint3'))
    keys=[k for bit,k in bindings if flags&bit]
    if len(nodes)!=len(keys):raise ValueError('DIMASSOC thiếu/thừa point reference')
    edited=[]
    for node,key in zip(nodes,keys):
        offset,end=node.start,node.own_end;tags=pairs[offset:end]
        if any(c not in (1,72,331,73,91,40,10,20,30,75,332,74,92) for c,v in tags):raise ValueError('DIMASSOC point reference có dữ liệu khác chưa hỗ trợ')
        def single(code):
            values=[v for c,v in tags if c==code]
            if len(values)!=1:raise ValueError('DIMASSOC point reference không duy nhất')
            return values[0]
        snap=int(single(72))
        if snap not in (1,2,3,13,11,8) or int(single(73))!=2 or (node.child is not None)!=(snap==8):
            raise ValueError('DIMASSOC chưa hỗ trợ kiểu snap/hệ tọa độ này')
        source=entity.doc.entitydb.get(single(331));parameter=float(single(40))
        if not math.isfinite(parameter):raise ValueError('DIMASSOC có tham số snap không hữu hạn')
        if source is None or source.dxftype() not in ('LINE','LWPOLYLINE','CIRCLE','ARC'):raise ValueError('DIMASSOC chưa bind geometry nguồn được hỗ trợ')
        original=snapshot(source);vertex=None;normalization={};last_binding=None;last_normalization={}
        if snap==8:
            if angular or getattr(entity.dxf,'dimtype',0)&15!=0 or flags!=3 or key!='defpoint3' or source.dxftype()!='LWPOLYLINE' or any(c in (332,74,92) for c,v in tags):
                raise ValueError('DIMASSOC perpendicular chỉ hỗ trợ điểm thứ hai của DIM rotated trên cùng LWP')
            child=node.child
            if child.child is not None:raise ValueError('DIMASSOC perpendicular cần last point endpoint trực tiếp')
            child_tags=pairs[child.start:child.own_end]
            def child_single(code):
                values=[v for c,v in child_tags if c==code]
                if len(values)!=1:raise ValueError('DIMASSOC last point reference không duy nhất')
                return values[0]
            if any(c not in (1,72,331,73,91,40,10,20,30,75) for c,v in child_tags) or child_single(331)!=source.dxf.handle or int(child_single(72)) not in (1,13) or int(child_single(73))!=2:
                raise ValueError('DIMASSOC last point cần endpoint cùng LWP nguồn')
            points=original['points'];child_parameter=float(child_single(40));segment=int(child_single(91))-1
            if child_parameter not in (0.,1.) or not 0<=segment<len(points) or abs(points[segment][4])>1e-10:
                raise ValueError('DIMASSOC last point endpoint có marker/tham số chưa hỗ trợ')
            anchor=(segment+int(child_parameter))%len(points)
            anchor_point=bound_point('LWPOLYLINE',original,dict(endpoint='vertex',vertex_index=anchor))
            if not edited or edited[0]['source_ref']!=source.dxf.handle or edited[0]['endpoint']!='vertex' or edited[0]['vertex_index']!=anchor or not near(anchor_point,before['defpoint2'],1e-6):
                raise ValueError('DIMASSOC last point không khớp điểm đo đầu nguồn')
            edge=int(single(91))-1
            if not 0<=edge<len(points):raise ValueError('DIMASSOC perpendicular thiếu marker cạnh nguồn')
            point,t=perpendicular_point(original,edge,anchor)
            matches=[]
            for i,p in enumerate(points):
                if abs(p[4])>1e-10:continue
                try:candidate,_=perpendicular_point(original,i,anchor)
                except ValueError:continue
                if near(candidate,before[key],1e-6):matches.append(i)
            if matches!=[edge]:raise ValueError('DIMASSOC perpendicular không bind duy nhất cạnh nguồn')
            # The explicit GS marker and independently projected measurement must agree.
            if not near(point,before[key],1e-6):raise ValueError('DIMASSOC perpendicular không khớp điểm đo nguồn')
            vertex=edge;field='perpendicular'
            normalization={72:8,91:edge+1,40:t,75:1}
            last_normalization={72:13 if child_parameter==0 else 1,91:segment+1,40:child_parameter,75:0}
            last_binding=dict(source_ref=source.dxf.handle,endpoint='vertex',vertex_index=anchor)
        elif source.dxftype() in ('CIRCLE','ARC'):
            if snap!=3 or any(c in (332,74,92) for c,v in tags):raise ValueError('DIMASSOC đường tròn/cung chỉ hỗ trợ snap center')
            field='center'
            if not near(bound_point(source.dxftype(),original,dict(endpoint=field)),before[key],1e-6):raise ValueError('DIMASSOC center không khớp tâm nguồn')
        elif source.dxftype()=='LINE':
            if snap not in (1,2,13) or int(single(91))!=0 or any(c in (332,74,92) for c,v in tags) or snap!=2 and parameter not in (0.,1.):raise ValueError('DIMASSOC LINE cần snap endpoint/midpoint trực tiếp')
            field='midpoint' if snap==2 else 'start' if parameter==0 else 'end'
            normalization={72:2 if snap==2 else 13 if parameter==0 else 1,91:0,40:.5 if snap==2 else parameter}
            if not near(bound_point('LINE',original,dict(endpoint=field)),before[key]):raise ValueError('DIMASSOC không trỏ đúng điểm LINE theo hình nguồn')
        else:
            if snap not in (1,2,11,13):raise ValueError('DIMASSOC LWP chưa hỗ trợ snap này')
            if not original['closed'] or not near(original['extrusion'],[0,0,1]):raise ValueError('DIMASSOC LWP cần biên đóng XY')
            points=original['points']
            if snap==2:
                if any(c in (332,74,92) for c,v in tags):raise ValueError('DIMASSOC midpoint có intersection ngoài phạm vi')
                matches=[i for i,p in enumerate(points) if abs(p[4])<1e-10 and near(bound_point('LWPOLYLINE',original,dict(endpoint='edge_midpoint',vertex_index=i)),before[key],1e-6)]
            else:matches=[i for i,p in enumerate(points) if near([p[0],p[1],original['elevation']],before[key],1e-6)]
            if len(matches)!=1:raise ValueError('DIMASSOC không bind duy nhất đỉnh LWP đo thật')
            vertex=matches[0];incoming=(vertex-1)%len(points)
            if snap==11:
                if single(332)!=source.dxf.handle or int(single(74))!=2 or {int(single(91)),int(single(92))}!={incoming+1,vertex+1}:
                    raise ValueError('DIMASSOC giao điểm chưa chứng minh là hai cạnh kề tại đỉnh LWP')
            elif any(c in (332,74,92) for c,v in tags):raise ValueError('DIMASSOC endpoint có intersection ngoài phạm vi')
            # GS edge markers are one based; prefer an outgoing straight edge.
            if snap==2:segment=vertex;parameter=.5
            elif abs(points[vertex][4])<1e-10:segment=vertex;parameter=0.
            elif abs(points[incoming][4])<1e-10:segment=incoming;parameter=1.
            else:raise ValueError('DIMASSOC đỉnh chưa có cạnh thẳng để bind')
            normalization={72:2 if snap==2 else 13 if parameter==0 else 1,91:segment+1,40:parameter}
            field='edge_midpoint' if snap==2 else 'vertex'
        op=next((o for o in operations if o.ref==source.dxf.handle and o.action in ('replace_geometry','line_end')),None)
        new_geometry=json.loads(op.after) if op and op.action=='replace_geometry' else dict(original,end=op.xyz) if op else original
        expected=original['end'] if op and op.action=='line_end' else original
        if op and not near(json.loads(op.before),expected):raise ValueError('DIMASSOC geometry before không khớp')
        if vertex is not None:
            if len(new_geometry['points'])!=len(original['points']) or new_geometry['closed']!=original['closed'] or any(not near(a[2:],b[2:]) for a,b in zip(original['points'],new_geometry['points'])):
                raise ValueError('DIMASSOC LWP không cho thay topology/bulge')
        binding=dict(endpoint=field,**({'vertex_index':vertex} if vertex is not None else {}),**({'anchor_vertex_index':last_binding['vertex_index']} if last_binding else {}))
        new_point=bound_point(source.dxftype(),new_geometry,binding)
        if not near(new_point,after[key],1e-6):raise ValueError('DIMASSOC sau sửa không bám đúng cạnh mới')
        for code,value in normalization.items():
            indices=[i for i in range(offset,end) if pairs[i][0]==code]
            if len(indices)!=1:raise ValueError('DIMASSOC thiếu/thừa thông số snap')
            line=2*indices[0]+1;newline=b'\r\n' if raw[line].endswith(b'\r\n') else b'\n'
            raw[line]=str(value).encode('ascii')+newline
        for i in range(offset,end):
            if pairs[i][0] in (332,74,92):raw[2*i]=raw[2*i+1]=b''
        for axis,code in enumerate((10,20,30)):
            indices=[i for i in range(offset,end) if pairs[i][0]==code]
            if len(indices)!=1:raise ValueError('DIMASSOC thiếu điểm WCS')
            line=2*indices[0]+1;newline=b'\r\n' if raw[line].endswith(b'\r\n') else b'\n'
            raw[line]=str(after[key][axis]).encode('ascii')+newline
        last_report={}
        if last_binding:
            last_point=bound_point('LWPOLYLINE',new_geometry,last_binding)
            if not near(last_point,after['defpoint2'],1e-6):raise ValueError('DIMASSOC last point sau sửa không khớp DIM')
            for code,value in {**last_normalization,10:last_point[0],20:last_point[1],30:last_point[2]}.items():
                indices=[i for i in range(node.child.start,node.child.own_end) if pairs[i][0]==code]
                if len(indices)!=1:raise ValueError('DIMASSOC last point thiếu/thừa thông số')
                line=2*indices[0]+1;newline=b'\r\n' if raw[line].endswith(b'\r\n') else b'\n';raw[line]=str(value).encode('ascii')+newline
            last_report=dict(last_point_ref=dict(last_binding,point=last_point,snap=last_normalization,osnap_type=last_normalization[72]))
        edited.append({'source_ref':source.dxf.handle,'dimension_field':key,**binding,'point':after[key],**({'snap':normalization} if normalization else {}),'osnap_type':normalization.get(72,snap),**last_report})
    return [(assoc.dxf.handle,[line for line in raw if line],{'ref':assoc.dxf.handle,'dimension_ref':entity.dxf.handle,'points':edited})]


def source_binding(entity):
    """Expose only exact, independently rechecked linear DIM snap ownership."""
    if not entity.has_extension_dict:return None
    if 'ACAD_DIMASSOC' not in entity.get_extension_dict():return None
    from cad.dimensions import dimension_snapshot,serialize
    refs=[]
    try:
        assoc=entity.get_extension_dict()['ACAD_DIMASSOC'];raw=serialize(assoc)
        refs=sorted({raw[i+1].strip().decode('utf8') for i in range(0,len(raw),2) if raw[i].strip() in (b'331',b'332')})
        if entity.dxf.dimtype&15 not in (0,1):raise ValueError('Loại DIM association chưa có bộ theo điểm tuyến tính')
        geometry=dimension_snapshot(entity);checked=update(entity,geometry,geometry,[],{assoc.dxf.handle:raw})
        return dict(status='verified_source_points',association_ref=assoc.dxf.handle,source_refs=refs,points=checked[0][2]['points'])
    except (ValueError,KeyError,StopIteration,TypeError) as error:return dict(status='unsupported_source_points',source_refs=refs,reason=str(error) or 'Không đọc được DIMASSOC nguồn')


def follow(record,before,after,records,operations,*,operation_index=None):
    """Follow real centers/midpoints, not the nearest end of a resized edge."""
    binding=record.get('dimension_association',{})
    if binding.get('status')!='verified_source_points':return None
    ops=operation_index if operation_index is not None else {o.ref:o for o in operations if o.action=='replace_geometry'}
    points=binding['points']
    if not any(p['source_ref'] in ops for p in points):return None
    import copy
    result=copy.deepcopy(after)
    for point in points:
        ref=point['source_ref'];source=records.get(ref)
        if source is None or source.get('review_only') or source.get('coordinate_frame')!=record.get('coordinate_frame'):
            raise ValueError('DIMASSOC chưa mở đủ geometry nguồn cùng hệ tọa độ: '+ref)
        original=source.get('geometry');field=point['dimension_field']
        if not original or not near(bound_point(source['type'],original,point),before[field],1e-6):
            raise ValueError('DIMASSOC binding không còn khớp điểm nguồn: '+ref)
        op=ops.get(ref)
        if op and not near(json.loads(op.before),original):raise ValueError('DIMASSOC snapshot trước sửa không khớp nguồn')
        result[field]=bound_point(source['type'],json.loads(op.after) if op else original,point)
    for axis in range(3):
        result['defpoint'][axis]=before['defpoint'][axis]+sum(result[k][axis]-before[k][axis] for k in ('defpoint2','defpoint3'))/2
    return result


def synchronize(plan,context):
    """Keep proven layout DIM anchors on edited bodies, even at equal measure.

    A thickness DIM can still measure 2 mm after both source endpoints move.
    Leaving its points stationary breaks its existing native association.
    This adds no guessed snaps and never expands the editable CAD scope.
    """
    if plan.questions or not plan.operations:return plan
    from cad.edit_engine import Operation
    records={e['ref']:e for e in context['entities']}
    ops={o.ref:o for o in plan.operations if o.action=='replace_geometry'}
    changed=set(ops)
    for record in context['entities']:
        if record['type']!='DIMENSION' or '/' in record['ref']:continue
        binding=record.get('dimension_association',{})
        if not changed.intersection(binding.get('source_refs',[])):continue
        if binding.get('status')!='verified_source_points':
            raise ValueError('DIMASSOC chưa chứng minh điểm nguồn để đồng bộ: '+record['ref'])
        if record.get('review_only'):raise ValueError('DIMASSOC liên quan còn nằm trong phạm vi chỉ xem: '+record['ref'])
        before=record['geometry'];existing=ops.get(record['ref'])
        current=json.loads(existing.after) if existing else before
        after=follow(record,before,current,records,plan.operations,operation_index=ops)
        # A compiler may deliberately keep a dimension line on a fixed side.
        # Native snaps constrain the two measured points, not that line's
        # chosen display offset. Preserve an already planned placement.
        if after is not None and existing:after['defpoint']=current['defpoint']
        if after is None or near(current,after,1e-6):continue
        if existing:
            # Native following cannot reinterpret an explicitly planned size.
            # Compare the actual linear measurements independently of text.
            import math
            def measure(g):
                vector=[b-a for a,b in zip(g['defpoint2'],g['defpoint3'])]
                return math.dist(g['defpoint2'],g['defpoint3']) if record.get('dimension_type',0)&15==1 else abs(vector[0]*math.cos(math.radians(g['angle']))+vector[1]*math.sin(math.radians(g['angle'])))
            if abs(measure(current)-measure(after))>1e-6:
                raise ValueError('Kích thước dự kiến không khớp liên kết DIMASSOC nguồn: '+record['ref'])
        reason='Theo điểm gắn DIMASSOC đã kiểm chứng khi cạnh dịch; giữ số đo và mốc đo native.'
        operation=Operation(ref=record['ref'],action='replace_geometry',before=json.dumps(before),after=json.dumps(after),xyz=[],reason=reason)
        if existing:plan.operations[plan.operations.index(existing)]=operation
        else:plan.operations.append(operation)
        ops[record['ref']]=operation
        from backend.services.change_service import EditProposal
        edits=[e for e in plan.edits if e.entity_ref==record['ref']]
        if edits:
            for edit in edits:edit.after=operation.after;edit.reason=reason
        else:
            owners={n['code'] for n in context.get('part_graph',{}).get('nodes',[]) if set(record.get('source_sheet_ids',[])).intersection(n.get('detail_sheets',[]))}
            plan.edits.append(EditProposal(entity_ref=record['ref'],part_number=next(iter(owners)) if len(owners)==1 else 'DIMASSOC',purpose='geometry',before=operation.before,after=operation.after,reason=reason))
    return plan


def validate_sources(doc,operations,raw_objects):
    """An edited body must not leave an omitted associated DIM stale."""
    from cad.dimensions import dimension_snapshot
    pending={}
    for op in operations:
        if op.action not in ('replace_geometry','line_end'):continue
        source=doc.entitydb.get(op.ref)
        if source is None or source.dxftype()=='DIMENSION':continue
        for handle in source.get_reactors():
            assoc=doc.entitydb.get(handle)
            if assoc is not None and assoc.dxftype()=='DIMASSOC':pending.setdefault(handle,[]).append(op.ref)
    # Copied files can lose the reverse reactor on the body while retaining
    # the DIMASSOC main-object pointer. Do not rely on the reverse index alone.
    changed={o.ref for o in operations if o.action in ('replace_geometry','line_end') and doc.entitydb.get(o.ref) is not None and doc.entitydb[o.ref].dxftype()!='DIMENSION'}
    for handle,raw in raw_objects.items():
        refs={raw[i+1].strip().decode('utf8') for i in range(0,len(raw),2) if raw[i].strip() in (b'331',b'332')}
        if refs&changed:pending[handle]=sorted(set(pending.get(handle,[]))|(refs&changed))
    audited=[]
    for handle,sources in pending.items():
        raw=raw_objects[handle];pairs=[(int(raw[i]),raw[i+1].strip().decode('utf8')) for i in range(0,len(raw),2)]
        start=next(i for i,(c,v) in enumerate(pairs) if c==100 and v=='AcDbDimAssoc')
        dimension=doc.entitydb.get(next((v for c,v in pairs[start+1:] if c==330),''))
        if dimension is None or dimension.dxftype()!='DIMENSION':raise ValueError('DIMASSOC mất dimension nguồn: '+handle)
        op=next((o for o in operations if o.ref==dimension.dxf.handle),None)
        if op:
            if op.action!='replace_geometry':raise ValueError('DIMASSOC cần snapshot dimension đầy đủ')
            before,after=json.loads(op.before),json.loads(op.after)
        else:before=after=dimension_snapshot(dimension)
        try:update(dimension,before,after,operations,raw_objects)
        except ValueError as error:
            raise ValueError('DIMASSOC #'+handle+' cần đồng bộ DIM #'+dimension.dxf.handle+' liên quan geometry '+', '.join(sources)+': '+str(error)) from error
        audited.append(dict(association_ref=handle,dimension_ref=dimension.dxf.handle,source_refs=sources,dimension_updated=op is not None))
    return audited


def verify(doc,report):
    from ezdxf.lldxf.tagwriter import TagCollector
    from cad.dimensions import serialize
    for entry in report:
        obj=doc.entitydb.get(entry['ref']);dimension=doc.entitydb.get(entry['dimension_ref'])
        if obj is None or obj.dxftype()!='DIMASSOC' or dimension is None or not dimension.has_extension_dict or dimension.get_extension_dict()['ACAD_DIMASSOC'].dxf.handle!=entry['ref']:
            raise ValueError('Dimension mất liên kết DIMASSOC sau ghi CAD')
        tags=TagCollector.dxftags(obj)
        points=[list(t.value) for t in tags if t.code==10 and isinstance(t.value,tuple)]
        if not points:
            points=[[tags[i].value,tags[i+1].value,tags[i+2].value] for i,t in enumerate(tags) if t.code==10]
        expected_points=[]
        for point in entry['points']:
            expected_points.append(point['point'])
            if point.get('last_point_ref'):expected_points.append(point['last_point_ref']['point'])
        if not near(points,expected_points,1e-6):raise ValueError('Tọa độ DIMASSOC sau ghi không khớp cạnh mới')
        for point in entry['points']:
            source=doc.entitydb.get(point['source_ref'])
            if source is None:raise ValueError('DIMASSOC mất geometry sau ghi CAD')
            geometry=snapshot(source)
            actual=bound_point(source.dxftype(),geometry,point)
            if not near(actual,point['point'],1e-6):raise ValueError('DIMASSOC không bám cạnh sau ghi CAD')
            last=point.get('last_point_ref')
            if last:
                nested_source=doc.entitydb.get(last['source_ref'])
                if nested_source is None or not near(bound_point(nested_source.dxftype(),snapshot(nested_source),last),last['point'],1e-6):
                    raise ValueError('DIMASSOC mất last point nguồn sau ghi CAD')
        raw=serialize(obj);pairs=[(int(raw[i]),raw[i+1].strip().decode('utf8')) for i in range(0,len(raw),2)]
        nodes=point_references(pairs)
        if len(nodes)!=len(entry['points']):raise ValueError('DIMASSOC mất point reference')
        def check(node,point):
            group=pairs[node.start:node.own_end]
            def value(code):
                values=[v for c,v in group if c==code]
                if len(values)!=1:raise ValueError('DIMASSOC binding sau ghi không duy nhất')
                return values[0]
            if value(331)!=point['source_ref'] or point.get('osnap_type') is not None and int(value(72))!=point['osnap_type'] or any(not near(float(value(int(c))),v,1e-6) for c,v in point.get('snap',{}).items()) or any(c in (332,74,92) for c,v in group):
                raise ValueError('DIMASSOC LWP mất binding cạnh sau ghi CAD')
            last=point.get('last_point_ref')
            if (node.child is not None)!=bool(last):raise ValueError('DIMASSOC mất last point reference')
            if int(value(75))!=(1 if last else 0):raise ValueError('DIMASSOC hasLastPointRef sau ghi không khớp')
            if last:check(node.child,last)
        for node,point in zip(nodes,entry['points']):check(node,point)
