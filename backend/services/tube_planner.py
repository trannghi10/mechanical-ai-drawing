"""Checked rectangular-tube wall compiler. No generated CAD coordinates from an LLM."""
import copy
import json
import math
import re
from bom.reader import normalized,requested_numbers
from cad.edit_engine import Operation


def intent(request):
    text=normalized(request).replace(',', '.')
    parts=requested_numbers(request)
    wall=re.search(r'day\s*(?:hop\s*)?(?:tu\s*)?(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:thanh|xuong|len|->|→)\s*(?:day\s*)?(\d+(?:\.\d+)?)',text)
    if not wall or 'hop' not in text:return None
    if len(parts)>1:return None
    if any(word in text for word in ('inox','nhom','dong thau','doi vat lieu','thay vat lieu')):return None
    # Only the single wall-thickness command is handled by this compiler.
    dimensions=re.sub(r'\bgiu\s+(?:nguyen\s+)?(?:kich thuoc ngoai\s+va\s+)?chieu dai(?=\s*(?:[;,.]|$))','',text)
    if any(word in dimensions for word in ('chieu cao','chieu dai','tat ca','ket cau')):return None
    old,new=map(float,wall.groups())
    if not 0<new or abs(new-old)<1e-9:return None
    return parts[0] if parts else None,old,new


def specification_candidates(rows,request):
    """Resolve an unnumbered wall request in the selected verified BOM only.

    A physical specification locates candidates; it never proves a fit or
    authorizes geometry. None means no supported selector; otherwise return
    all source codes matching it, without choosing among duplicate sizes.
    """
    parsed=intent(request)
    if parsed is None or parsed[0] is not None:return None
    text=normalized(request).replace(',','.')
    section=re.search(r'\bhop\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)',text)
    if not section:return None
    wanted=sorted(map(float,section.groups()));old=parsed[1];codes=set()
    for row in rows:
        from cad.tube_stock import parse
        stock=parse(row.get('description',''),old)
        if not stock:continue
        wall=stock.wall;width,height=stock.section
        if abs(wall-old)<1e-6 and all(abs(a-b)<1e-6 for a,b in zip(sorted((width,height)),wanted)):
            code=row.get('part_code','').strip()
            if code:codes.add(code)
    return codes


def specification_codes(rows,request):
    candidates=specification_candidates(rows,request)
    return candidates if candidates is None or len(candidates)==1 else set()


def wall_operations(records,old,new,minimum_hidden_walls=4):
    """Use a proven longitudinal DIM axis, independent of drawing rotation.

    Only a rigid XY change of coordinates is used. Source identity, native
    ownership and fit permissions continue to be checked by the caller.
    """
    from cad.frame_geometry import transform
    from cad.geometry import near
    from ezdxf.math import Matrix44
    # Work in layout coordinates, then return exact instance paths/local
    # snapshots to the writer, which isolates shared block definitions.
    from cad.frame_geometry import world,local_geometry
    if any('/' in e['ref'] and e.get('geometry') and e['type'] in ('LINE','ARC','LWPOLYLINE','DIMENSION') for e in records):
        originals={e['ref']:e for e in records};flat=[]
        for e in records:
            r=world(e) if e.get('geometry') and e['type'] in ('LINE','ARC','LWPOLYLINE','DIMENSION') else dict(e)
            r['ref']=e['ref'].replace('/','~')
            flat.append(r)
        refs={e['ref'].replace('/','~'):e['ref'] for e in records}
        if len(refs)!=len(originals):raise ValueError('Tham chiếu instance không duy nhất')
        operations=wall_operations(flat,old,new,minimum_hidden_walls)
        result=[]
        for op in operations:
            source=originals[refs[op.ref]]
            after=local_geometry(source,json.loads(op.after))
            if source['type']=='ARC':after=dict(source['geometry'],radius=after['radius'])
            result.append(op.model_copy(update=dict(ref=source['ref'],before=json.dumps(source['geometry']),after=json.dumps(after))))
        return result
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (old,new)):
        raise ValueError('Độ dày hộp phải là số dương hữu hạn')
    if minimum_hidden_walls not in (3,4):raise ValueError('Số hình thành trong ngoài adapter đã hỗ trợ')
    dimensions=[e for e in records if e['type']=='DIMENSION' and e.get('geometry') and
                e.get('scaled_measurement',0)>100 and
                {'defpoint2','defpoint3'}<=e['geometry'].keys() and e.get('dimension_type',0)&15 in (0,1)]
    if not dimensions:raise ValueError('Thiếu kích thước chiều dài hộp')
    longest=max(e['scaled_measurement'] for e in dimensions)
    axes=[]
    from cad.dimensions import linear_axis
    for e in dimensions:
        if abs(e['scaled_measurement']-longest)>1e-6:continue
        axis=linear_axis(e);angle=math.degrees(math.atan2(axis[1],axis[0]))
        if not math.isfinite(angle):raise ValueError('Góc DIM chiều dài không hợp lệ')
        theta=math.remainder(angle-90,180)
        axes.append(theta)
    if any(abs(math.remainder(a-axes[0],180))>1e-6 for a in axes):raise ValueError('DIM chiều dài cùng số đo có hướng mâu thuẫn')
    theta=axes[0]
    if any(e.get('normal') and not near(e['normal'],[0,0,1],1e-7) for e in records if e['type']=='DIMENSION'):
        raise ValueError('Mặt phẳng DIM/hộp nghiêng chưa được hỗ trợ')
    # Preserve exact source snapshots and angles in the unchanged orientation.
    if abs(theta)<1e-8:
        return _axis_wall_operations(records,old,new,minimum_hidden_walls)
    anchor=dimensions[0]['geometry']['defpoint2']
    to_local=Matrix44.translate(-anchor[0],-anchor[1],0) @ Matrix44.z_rotate(math.radians(-theta))
    to_source=to_local.copy();to_source.inverse()
    normalized=[];original={e['ref']:e for e in records}
    for record in records:
        local=dict(record)
        if record['type'] in ('ARC','LINE','LWPOLYLINE','DIMENSION') and record.get('geometry'):
            if record.get('normal') and not near(record['normal'],[0,0,1],1e-7):raise ValueError('Mặt phẳng DIM/hộp nghiêng chưa được hỗ trợ')
            local['geometry']=transform(record['type'],record['geometry'],to_local)
        normalized.append(local)
    operations=_axis_wall_operations(normalized,old,new,minimum_hidden_walls)
    result=[]
    for op in operations:
        source=original[op.ref];before=source['geometry'];after=transform(source['type'],json.loads(op.after),to_source)
        if source['type']=='ARC':
            # A wall change moves only radius; preserve its authored OCS/angles.
            after=dict(before,radius=after['radius'])
        if source['type']=='DIMENSION' and 'angle' in before:after['angle']=before['angle']
        result.append(op.model_copy(update=dict(before=json.dumps(before),after=json.dumps(after))))
    return result


def _axis_wall_operations(records,old,new,minimum_hidden_walls=4):
    """Recognize a closed concentric four-corner section and paired wall projections."""
    def close(a,b):return abs(a-b)<1e-6
    def point_close(a,b):return all(close(x,y) for x,y in zip(a,b))
    arcs=[e for e in records if e['type']=='ARC' and '/' not in e['ref'] and e.get('geometry')]
    from cad.geometry import near
    if any(not near(e['geometry'].get('extrusion',[0,0,1]),[0,0,1],1e-7) for e in arcs):raise ValueError('Mặt cắt hộp OCS nghiêng chưa được hỗ trợ')
    pairs=[]
    for inner in arcs:
        a=inner['geometry']
        for outer in arcs:
            b=outer['geometry']
            if point_close(a['center'],b['center']) and close(b['radius']-a['radius'],old) and close(a['start_angle'],b['start_angle']) and close(a['end_angle'],b['end_angle']):pairs.append((inner,outer))
    if len(pairs) not in (0,4):raise ValueError('Chưa nhận diện duy nhất mặt cắt hộp gồm 4 cặp góc trong/ngoài')
    centers=[a['geometry']['center'] for a,b in pairs]
    xs=sorted(set(round(p[0],6) for p in centers));ys=sorted(set(round(p[1],6) for p in centers))
    if pairs and (len(xs)!=2 or len(ys)!=2 or len({tuple(round(v,6) for v in p[:2]) for p in centers})!=4):raise ValueError('Góc hộp chưa tạo hình chữ nhật')
    radii={round(b['geometry']['radius'],6) for a,b in pairs}
    if pairs and len(radii)!=1:raise ValueError('Bán kính ngoài mặt cắt không đồng nhất')
    if any(inner['geometry']['radius']+old-new<=0 for inner,_ in pairs):
        raise ValueError('Độ dày mới vượt bán kính góc ngoài; không còn mặt trong hợp lệ')
    lines=[e for e in records if e['type']=='LINE' and '/' not in e['ref'] and e.get('geometry')]
    operations=[];changed={};delta=old-new
    def edit(e,after):
        changed[e['ref']]=after
        operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),after=json.dumps(after),xyz=[],reason='Giữ mặt ngoài; dịch mặt trong theo độ dày mới đã đo'))
    endpoints=[]
    for inner,outer in pairs:
        g=inner['geometry'];after=copy.deepcopy(g);after['radius']+=delta;edit(inner,after)
        for angle in (g['start_angle'],g['end_angle']):
            radians=math.radians(angle)
            endpoints.append(([g['center'][0]+g['radius']*math.cos(radians),g['center'][1]+g['radius']*math.sin(radians),g['center'][2]],
                              [g['center'][0]+after['radius']*math.cos(radians),g['center'][1]+after['radius']*math.sin(radians),g['center'][2]]))
    section_lines=[]
    for e in lines:
        g=e['geometry'];matches=[next((n for o,n in endpoints if point_close(g[k],o)),None) for k in ('start','end')]
        if all(p is not None for p in matches):
            after=copy.deepcopy(g);after['start'],after['end']=matches;edit(e,after);section_lines.append(e['ref'])
    if pairs:
        if len(section_lines)!=4:raise ValueError('Mặt trong hộp chưa có đủ 4 đường nối góc; chưa sửa')
    else:
        from cad.tube_sections import straight_wall
        op=straight_wall(records,old,new);operations.append(op);changed[op.ref]=json.loads(op.after)
    section_operation_count=len(operations)
    # Hidden wall lines in longitudinal projections must have an exact outer partner.
    long_dims=[e for e in records if e['type']=='DIMENSION' and e.get('scaled_measurement',0)>100 and e.get('geometry')]
    if not long_dims:raise ValueError('Thiếu kích thước chiều dài hộp')
    length=max(e['scaled_measurement'] for e in long_dims)
    projections=[]
    for e in lines:
        g=e['geometry']
        if not close(g['start'][0],g['end'][0]):continue
        span=abs(g['start'][1]-g['end'][1])
        if span<100 or span>length+1e-6:continue
        candidates=[]
        for other in lines:
            h=other['geometry']
            if not close(h['start'][0],h['end'][0]):continue
            if not close(abs(g['start'][0]-h['start'][0]),old):continue
            if sorted(round(g[k][1],6) for k in ('start','end'))!=sorted(round(h[k][1],6) for k in ('start','end')):continue
            candidates.append(other)
        if len(candidates)==1:projections.append((e,candidates[0]))
    # Use the inner lines of each pair only: hidden layer identifies them explicitly.
    for e,outer in projections:
        if 'hidden' not in e.get('layer','').lower():continue
        g=e['geometry'];h=outer['geometry'];shift=-delta*math.copysign(1,g['start'][0]-h['start'][0])
        after=copy.deepcopy(g)
        for key in ('start','end'):after[key][0]+=shift
        edit(e,after)
    if minimum_hidden_walls not in (3,4):raise ValueError('Số hình thành trong ngoài adapter đã hỗ trợ')
    if len(operations)<section_operation_count+minimum_hidden_walls:raise ValueError('Chưa chứng minh đủ đường thành trong ở hình chiếu dọc')
    # The wall dimension endpoint must be tied to a changed inner projection.
    dimensions=[]
    for e in records:
        if e['type']!='DIMENSION' or not e.get('geometry') or not {'defpoint2','defpoint3'}<=e['geometry'].keys() or not close(e.get('scaled_measurement',0),old):continue
        g=e['geometry'];after=copy.deepcopy(g);found=False
        for key in ('defpoint2','defpoint3'):
            for line in lines:
                if line['ref'] not in changed:continue
                for endpoint in ('start','end'):
                    if point_close(g[key],line['geometry'][endpoint]):after[key]=changed[line['ref']][endpoint];found=True
            for contour in records:
                if contour['type']!='LWPOLYLINE' or contour['ref'] not in changed:continue
                original=contour['geometry'];updated=changed[contour['ref']]
                for index,point in enumerate(original['points']):
                    if point_close(g[key],[*point[:2],original['elevation']]):
                        after[key]=[*updated['points'][index][:2],updated['elevation']];found=True
        if found:
            after['text']='<>';edit(e,after);dimensions.append(e['ref'])
    if len(dimensions)!=1:raise ValueError('Thiếu kích thước độ dày gắn đúng thành hộp')
    return operations


def compile_plan(context,request,clarifications):
    parsed=intent(request)
    if parsed is None or context.get('units')!=4:return None
    part,old,new=parsed
    entities=context['entities'];by_ref={e['ref']:e for e in entities}
    matches=[(table,row) for table in entities for row in table.get('bom',{}).get('rows',[]) if part is not None and str(row['part_number']).strip().upper()==part and 'sat hop' in normalized(row['description'])]
    seed=context.get('part_graph',{}).get('seed_codes',[])
    if part is None:
        from graph.part_graph import seed_codes
        seed=sorted(seed_codes(context,request,context.get('part_graph')))
        if not seed:
            roots=set(context.get('root_bom_refs',[]))
            rows=[r for t in entities if t.get('bom',{}).get('status')=='verified_template' and (not roots or t['ref'] in roots)
                  for r in t['bom']['rows']]
            if not rows:
                rows=[r for t in entities if t.get('bom',{}).get('status')=='verified_template' for r in t['bom']['rows']]
            candidates=specification_candidates(rows,request)
            if candidates is not None:
                from backend.services.change_service import DrawingChangePlan
                question=('Nhiều mã vật tư cùng quy cách hộp và độ dày trong bảng kê đã chọn: '+', '.join(sorted(candidates))+'. Chọn mã chi tiết cần sửa.' if len(candidates)>1 else
                          'Mã chi tiết trong yêu cầu chưa khớp vật tư thuộc phạm vi đã chọn. Kiểm tra mã và bảng kê nguồn.' if candidates else
                          'Không tìm thấy quy cách hộp và độ dày nguồn này trong bảng kê đã chọn. Kiểm tra quy cách hoặc chọn đúng bản vẽ có vật tư cần sửa.')
                return DrawingChangePlan(summary='Cần xác định đúng vật tư trước khi sửa hình học.',target_part='',edits=[],dependencies=[],questions=[question],warnings=[])
    if len(seed)>=1 and not matches:
        matches=[(t,r) for t in entities for r in t.get('bom',{}).get('rows',[]) if r['part_code'] in seed and 'sat hop' in normalized(r['description'])]
    if not matches or len({r['part_code'] for _,r in matches})!=1:return None
    table,row=matches[0];code=row['part_code']
    if part is None:part=row['part_number']
    bom_matches=[(t,r) for t in entities for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
    if len({normalized(r['description']) for _,r in bom_matches})!=1:
        raise ValueError('Các dòng BOM cùng mã hộp có quy cách khác nhau; cần đối chiếu phiên bản')
    from cad.tube_stock import parse
    stock=parse(row['description'],old)
    if stock is None:return None
    values=(stock.wall,*stock.section,stock.length)
    value=lambda i:values[i-1]
    requested_section=re.search(r'hop\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)',normalized(request).replace(',','.'))
    if requested_section and sorted(map(float,requested_section.groups()))!=sorted([value(2),value(3)]):
        raise ValueError('Quy cách hộp trong yêu cầu không khớp dòng chi tiết đã chọn trong BOM')
    details=[t for t in context['targets'] if code in t.get('texts',[]) and t['id'] not in {target['id'] for target in context['targets'] if table['ref']==target['id']}]
    # The native BOM sheet may also have the code; only accept a measured tube section.
    candidates=[]
    for target in details:
        bounds=target.get('bbox')
        if not bounds:continue
        def belongs(e):
            from cad.frame_geometry import world
            try:positioned=world(e) if e.get('geometry') else e
            except ValueError:return False
            g=positioned.get('geometry',{})
            anchor=g.get('start') or g.get('center') or g.get('defpoint') or e.get('text_placement',{}).get('anchor')
            if anchor is None and e['type']=='LWPOLYLINE' and g.get('points'):
                anchor=[*g['points'][0][:2],g['elevation']]
            return bool(anchor and bounds[0]<=anchor[0]<=bounds[2] and bounds[1]<=anchor[1]<=bounds[3])
        records=[e for e in entities if belongs(e)]
        try:ops=wall_operations(records,old,new)
        except ValueError:continue
        candidates.append((target,records,ops))
    if len(candidates)!=1:return None
    target,records,ops=candidates[0]
    required_sizes=[value(2),value(3),value(4)]
    from cad.dimensions import matches_displayed_nominal
    measured=[e for e in records if e['type']=='DIMENSION']
    if any(not any(matches_displayed_nominal(e,value) for e in measured) for value in required_sizes):return None
    from backend.services.change_service import DrawingChangePlan,EditProposal
    warnings=['Giữ nguyên kích thước ngoài, chiều dài và lỗ; mặt trong dịch theo độ dày. Cần đối chiếu mã vật tư mua hàng mới trước sản xuất.']
    old_spec=stock.raw;new_spec=stock.with_wall(new)
    cell=row['cells']['description'];mirror=cell.get('mirror_ref')
    if not mirror or mirror not in by_ref:raise ValueError('Thiếu binding bảng kê chi tiết hộp')
    before=cell['raw_text'];after=before.replace(old_spec,new_spec)
    if cell.get('storage')!='text':
        ops.append(Operation(ref=table['ref'],action='table_cell',cell_index=cell['index'],mirror_ref=mirror,before=before,after=after,xyz=[],reason='Đồng bộ đúng dòng vật tư hộp'))
    mirror_record=by_ref[mirror];raw=mirror_record.get('raw_text',mirror_record.get('text'))
    ops.append(Operation(ref=mirror,action='replace_text',before=raw,after=raw.replace(old_spec,new_spec),xyz=[],reason='Đồng bộ hình bảng kê với dữ liệu ô native'))
    for other_table,other_row in bom_matches:
        other_cell=other_row['cells']['description']
        if other_table['ref']==table['ref'] and other_cell['index']==cell['index']:continue
        other_mirror=other_cell.get('mirror_ref')
        if other_mirror not in by_ref:raise ValueError('Thiếu binding của một dòng BOM hộp liên quan')
        before=other_cell['raw_text'];after=before.replace(old_spec,new_spec)
        if before==after:raise ValueError('Quy cách tại dòng BOM hộp liên quan không khớp nguyên văn')
        if other_cell.get('storage')!='text':
            ops.append(Operation(ref=other_table['ref'],action='table_cell',cell_index=other_cell['index'],mirror_ref=other_mirror,before=before,after=after,xyz=[],reason='Đồng bộ quy cách hộp tại bảng kê liên quan'))
        raw=by_ref[other_mirror].get('raw_text',by_ref[other_mirror]['text'])
        ops.append(Operation(ref=other_mirror,action='replace_text',before=raw,after=raw.replace(old_spec,new_spec),xyz=[],reason='Đồng bộ hình bảng kê liên quan'))
    # A detail may share its Model/frame with the BOM. Its bound text has
    # already been updated above; do not emit a second annotation operation.
    bom_refs={c.get('mirror_ref') for t in entities for r in t.get('bom',{}).get('rows',[]) for c in r.get('cells',{}).values()}
    for e in records:
        if e['ref'] in bom_refs:continue
        raw=e.get('raw_text',e.get('text',''))
        after=raw.replace(old_spec,new_spec)
        stock=re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x'+re.escape(f'{old:g}')+r'x6000',raw)
        if stock:after=after.replace(stock.group(0),stock.group(1)+'x'+stock.group(2)+f'x{new:g}x6000')
        if raw!=after:ops.append(Operation(ref=e['ref'],action='replace_text',before=raw,after=after,xyz=[],reason='Đồng bộ mô tả chi tiết và quy cách phôi'))
    answers=normalized(' '.join(str(c.get('answer','')) for c in clarifications or []))
    policy=normalized(request)+' '+answers
    from bom.reader import plain
    graph_notes={e['note'] for edge in context.get('part_graph',{}).get('edges',[])
                 if edge['kind']=='fit' and edge['source']==code for e in edge['evidence']}
    notes=[e for e in entities if plain(e.get('text','')) in graph_notes or
           'vua khit' in normalized(e.get('text','')) and code.rsplit('.',1)[0] in e.get('text','')]
    questions=[]
    dependencies=[];cut_recipes=[];labels={}
    explicit_fit=any(word in policy for word in ('giu khe ho cu','giu do vua khit','giu nguyen khe ho'))
    keep_bas='giu nguyen bas' in policy or 'giu bas' in policy
    # The default design policy preserves a source-proven snug fit. Explicitly
    # keeping the old bas remains a separate user choice.
    keep_fit=explicit_fit or bool(notes) and not keep_bas
    if notes and not ('giu nguyen bas' in policy or 'giu bas' in policy):
        questions=['Hộp giảm dày làm khe hở với bas tăng. Chọn "giữ nguyên bas" nếu chấp nhận khe hở mới; hoặc "giữ khe hở cũ" để cần tăng bas và bố trí lại bản cắt.']
    if questions and keep_fit:
        from backend.services.tube_fit_planner import compile_fits
        try:
            fit_ops,dependencies,cut_recipes,fit_warnings,labels=compile_fits(context,code,records,ops,old,new,notes)
            ops.extend(fit_ops);warnings.extend(fit_warnings);questions=[]
        except ValueError as error:
            questions=['Chưa kiểm chứng được bản sửa giữ khe hở cũ: '+str(error)]
    if explicit_fit and keep_bas:
        questions=['Hai lựa chọn giữ nguyên bas và giữ khe hở cũ mâu thuẫn; cần chọn một phương án.']
    if notes and not questions and not dependencies:warnings.append('Theo yêu cầu giữ nguyên bas: khe hở tăng thêm '+f'{2*(old-new):g} mm; không sửa bas hay bản cắt bas.')
    if not questions:
        from backend.services.assembly_projection_planner import compile_projections
        projection_ops,projection_reviews=compile_projections(context,ops)
        ops.extend(projection_ops)
        for review in projection_reviews:
            labels.update({(ref,None):number for ref,number in review.get('part_numbers',{}).items()})
        if projection_ops:
            warnings.append('Các hình chiếu đã gắn được sửa từ tọa độ CAD và kiểm tra lại binding nguồn; góc ngoài minh họa giữ nguyên. Kích thước gia công lấy bản chi tiết có DIM đo thật.')
    edits=[EditProposal(entity_ref=op.ref,part_number=labels.get((op.ref,op.cell_index if op.action=='table_cell' else None),part),purpose='bom' if op.action=='table_cell' or op.ref in bom_refs else 'geometry' if op.action in ('replace_geometry','move_insert','remove_insert','append_geometry') else 'annotation',before=op.before,after=op.after,reason=op.reason) for op in ops]
    from cad.profile_nesting import ProfilePacking
    return DrawingChangePlan(summary=f'Đổi độ dày hộp chi tiết {part}: {old:g} → {new:g} mm bằng quy tắc hình học được kiểm tra.',target_part=part,edits=edits if not questions else [],dependencies=dependencies,cut_recipes=[r for r in cut_recipes if not isinstance(r,ProfilePacking)],profile_cut_recipes=[r for r in cut_recipes if isinstance(r,ProfilePacking)],questions=questions,warnings=warnings,operations=ops if not questions else [])
