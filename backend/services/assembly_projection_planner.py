"""Checked adapters for detached 2D views.

Adapters are bound to the original DXF hash. Unknown drawings retain the
assembly gate; merely finding a similar-looking block is never sufficient.
"""
import copy,json,re
import math
from pathlib import Path
from cad.edit_engine import Operation
from cad.geometry import near
from cad.projection_mapping import Projection
from cad.projected_plate import rebuild as rebuild_plate

TEMPLATE=Path(__file__).resolve().parents[2]/'cad'/'templates'/'leg6949-projections.json'
REASON='Đồng bộ hình chiếu 2D đã gắn tọa độ chi tiết: '


def compile_projections(context,base_operations):
    if not TEMPLATE.exists():return [],[]
    from cad.template_sources import resolve
    template=resolve(TEMPLATE,context.get('source_hash'))
    if template is None:return [],[]
    by={e['ref']:e for e in context['entities']}
    changes=[]
    for op in base_operations:
        if op.action!='table_cell':continue
        before=re.search(r'(?<![\d.])(\d+(?:\.\d+)?)x30x60x571\.5',op.before)
        after=re.search(r'(?<![\d.])(\d+(?:\.\d+)?)x30x60x571\.5',op.after)
        if before and after:changes.append((float(before.group(1)),float(after.group(1))))
    if not changes or len(set(changes))!=1 or changes[0][0]!=2:return [],[]
    old,new=changes[0];delta=old-new
    if not 0<new<4:raise ValueError('Độ dày ngoài miền góc minh họa của adapter 2D')
    operations=[];reviews=[]
    changed_plate=any(o.action=='table_cell' and '2x25.6x444.5' in o.before and f'2x{25.6+2*delta:g}x444.5' in o.after for o in base_operations)

    def edit(ref,after,reason):
        e=by[ref];before=e['geometry']
        if not near(before,after):operations.append(Operation(ref=ref,action='replace_geometry',before=json.dumps(before),after=json.dumps(after),xyz=[],reason=REASON+reason))

    def point_after(p):
        p=list(p)
        # Only explicitly recovered INNER tube coordinates are moved.
        for i,outside in ((0,60),(1,30)):
            if abs(p[i]-old)<1e-8:p[i]=new
            elif abs(p[i]-(outside-old))<1e-8:p[i]=outside-new
        return p

    active_ids={t['id'] for t in context.get('targets',[])}
    for view in template['tube_views']:
        if view['sheet_id'] not in active_ids:continue
        camera=Projection(view['matrix'],view['origin'])
        refs=[]
        for binding in view['bindings']:
            ref=binding['ref'];e=by.get(ref)
            if e is None or e.get('review_only'):raise ValueError('Thiếu toàn bộ nội dung hình chiếu đã gắn: '+ref)
            if e['type']=='LINE':
                before=[binding['start'],binding['end']]
                if binding.get('part_number')=='4':
                    # Separate duplicated seams: the plate and the tube wall
                    # have different widths and must retain their fit gap.
                    width=25.6+2*delta
                    target=[list(p) for p in before]
                    if changed_plate:
                        for p in target:
                            if abs(p[1]-2)<1e-8:p[1]=15-width/2
                            elif abs(p[1]-28)<1e-8:p[1]=15+width/2
                else:target=[point_after(p) for p in before]
                after=camera.line(e['geometry'],before,target)
            elif e['type']=='ELLIPSE':
                after=camera.concentric_arc(e['geometry'],binding['center'],binding['radius'],binding['radius']+delta)
            else:raise ValueError('Binding hình chiếu chưa có adapter native')
            edit(ref,after,view['label']);refs.append(ref)
        reviews.append(dict(sheet_id=view['sheet_id'],view=view['label'],status='verified_view',binding_count=len(refs),refs=refs))

    plate=template['closing_plate']
    if plate['sheet_id'] in active_ids and changed_plate:
        # Plate width is independently established by its native BOM update.
        for binding in plate['bindings']:
            ref=binding['ref'];e=by.get(ref)
            if e is None or not near(e.get('geometry'),binding['geometry'],2e-7):raise ValueError('Biên bas công đoạn 1 không khớp nguồn: '+ref)
            after=copy.deepcopy(e['geometry'])
            for key,coefficient in binding['moves'].items():
                for axis in (0,1):after[key][axis]+=coefficient[axis]*delta
            if e['type']=='DIMENSION':after['text']='<>'
            edit(ref,after,'Bas dài: giãn đều hai cạnh, giữ lỗ và chiều dài')
        reviews.append(dict(sheet_id=plate['sheet_id'],view='Hình chiếu và phối cảnh bas dài công đoạn 1',status='verified_view',binding_count=len(plate['bindings']),refs=[b['ref'] for b in plate['bindings']]))
    for plate in template.get('exploded_plates',[]):
        if plate['sheet_id'] not in active_ids:continue
        if not changed_plate:continue
        part=plate['part'];nominal=plate['nominal']
        size=[nominal[0]+(2*delta if part=='3' else delta if part in ('1','2') else 0),nominal[1]+2*delta]
        old_spec={'1':'2x25.6x45','2':'2x10.6x25.6','3':'2x25.6x55.6'}[part]
        new_spec={'1':f'2x{size[1]:g}x{size[0]:g}','2':f'2x{size[0]:g}x{size[1]:g}','3':f'2x{size[1]:g}x{size[0]:g}'}[part]
        if not any(o.action=='table_cell' and old_spec in o.before and new_spec in o.after for o in base_operations):
            raise ValueError('Thiếu BOM chuẩn để dựng lại bas tách rời '+part)
        result=rebuild_plate(plate,context['entities'],size,3+delta,5.25)
        for ref,after in result.items():edit(ref,after,'Bas '+part+': dựng hình tách rời theo DIM/BOM, giữ tâm lỗ')
        reviews.append(dict(sheet_id=plate['sheet_id'],view='Bas '+part+' tách rời theo bản chi tiết',status='verified_view',binding_count=len(result),refs=list(result)))
    for view in template.get('orthographic_tubes',[]):
        if view['sheet_id'] not in active_ids:continue
        from backend.services.tube_planner import wall_operations
        records=[e for e in context['entities'] if '/' not in e['ref'] and view['sheet_id'] in e.get('source_sheet_ids',[])]
        result=wall_operations(records,old,new,minimum_hidden_walls=3)
        if {o.ref for o in result}!=set(view['refs']):raise ValueError('Thành hộp công đoạn khác đăng ký nguồn')
        for op in result:edit(op.ref,json.loads(op.after),'Mặt cắt và thành trong hình chiếu công đoạn')
        reviews.append(dict(sheet_id=view['sheet_id'],view='Mặt cắt và ba thành trong có DIM nguồn',status='verified_view',binding_count=len(result),refs=[o.ref for o in result]))
    for view in template.get('registered_edges',[]):
        if view['sheet_id'] not in active_ids:continue
        if view.get('requires_fit',True) and not changed_plate:continue
        for binding in view['bindings']:
            e=by.get(binding['ref'])
            if e is None or not near(e.get('geometry'),binding['geometry'],2e-7):raise ValueError('Cạnh đăng ký khác nguồn: '+binding['ref'])
            after=copy.deepcopy(e['geometry'])
            for key,rule in binding['moves'].items():
                for axis in (0,1):after[key][axis]+=rule['delta'][axis]*delta+rule.get('offset',[0,0])[axis]
            for key,circle_ref in binding.get('clips',{}).items():
                circle=by[circle_ref]['geometry'];center=circle['center'];radius=circle['radius']
                if abs(math.dist(e['geometry'][key][:2],center[:2])-radius)>2e-4:raise ValueError('Biên cắt hình phóng to khác đường tròn nguồn')
                dx=after[key][0]-center[0]
                if abs(dx)>=radius:raise ValueError('Thành trong đã vượt biên hình phóng to')
                after[key][1]=center[1]+math.copysign(math.sqrt(radius*radius-dx*dx),e['geometry'][key][1]-center[1])
            edit(e['ref'],after,view['label'])
        reviews.append(dict(sheet_id=view['sheet_id'],view=view['label'],status='verified_view',binding_count=len(view['bindings']),refs=[b['ref'] for b in view['bindings']],
                            part_numbers={b['ref']:b['part_number'] for b in view['bindings'] if b.get('part_number')}))
    for view in template.get('welded_plates',[]):
        if view['sheet_id'] not in active_ids or not changed_plate:continue
        size=[55.6+2*delta,25.6+2*delta]
        new_spec=f'2x{size[1]:g}x{size[0]:g}'
        if view['part']!='3' or not any(o.action=='table_cell' and '2x25.6x55.6' in o.before and new_spec in o.after for o in base_operations):
            raise ValueError('Thiếu BOM chuẩn của bas đáy để đồng bộ hình hàn')
        from cad.assembly_view import rebuild_welded_plate
        result=rebuild_welded_plate(view,context['entities'],size,3+delta,5.25,delta)
        for ref,after in result.items():edit(ref,after,view['label'])
        tube_refs={b['ref'] for field in ('curves','lines') for b in view.get('tube',{}).get(field,[])}
        reviews.append(dict(sheet_id=view['sheet_id'],view=view['label'],status='verified_view',binding_count=len(result),refs=list(result),
                            part_numbers={r:'6' if r in tube_refs else view['part'] for r in result}))
    for view in template.get('assembled_bars',[]):
        if view['sheet_id'] not in active_ids or not changed_plate:continue
        from cad.assembled_bar import rebuild
        result=rebuild(view,context['entities'],delta)
        for ref,after in result.items():edit(ref,after,view['label'])
        reviews.append(dict(sheet_id=view['sheet_id'],view=view['label'],status='verified_view',binding_count=len(result),refs=list(result),
                            part_numbers={r:'4' for r in result}))
    for view in template.get('assembly_additions',[]):
        if view['sheet_id'] not in active_ids or not changed_plate:continue
        frame=by.get(view['sheet_id']);style=by.get(view['style_ref'])
        if frame is None or style is None or not near(frame.get('geometry'),view['frame_geometry'],2e-7) or not near(style.get('geometry'),view['style_geometry'],2e-7):
            raise ValueError('Khung/style cạnh bổ sung khác nguồn')
        lines=[]
        for binding in view['lines']:
            line={}
            for key in ('start','end'):
                rule=binding[key];line[key]=[a+delta*d for a,d in zip(rule['base'],rule['delta'])]
            lines.append(line)
        after=dict(style_ref=view['style_ref'],style_geometry=view['style_geometry'],lines=lines)
        operations.append(Operation(ref=view['sheet_id'],action='append_geometry',before=json.dumps(frame['geometry']),after=json.dumps(after),xyz=[],reason=REASON+view['label']))
        reviews.append(dict(sheet_id=view['sheet_id'],view=view['label'],status='verified_view',binding_count=len(lines),refs=[view['sheet_id']]))
    # Native balloon arrows are attached to the actual moved edge. Keep the
    # balloon end fixed and preserve the arrow's fractional edge position.
    import numpy as np
    source_lines=[o for o in operations if by[o.ref]['type']=='LINE']
    for e in context['entities']:
        if e['type']!='LEADER' or '/' in e['ref'] or e.get('review_only'):continue
        g=e.get('geometry') or {'vertices':e.get('leader_vertices',[])}
        if len(g['vertices'])<2:continue
        point=np.array(g['vertices'][0][:2]);matches=[]
        for op in source_lines:
            a=json.loads(op.before);b=json.loads(op.after)
            start=np.array(a['start'][:2]);vector=np.array(a['end'][:2])-start
            fraction=float((point-start)@vector/(vector@vector))
            if -1e-7<=fraction<=1+1e-7 and np.linalg.norm(point-start-fraction*vector)<1e-4:
                matches.append(np.array(b['start'][:2])+fraction*(np.array(b['end'][:2])-b['start'][:2]))
        if not matches:continue
        if any(np.linalg.norm(p-matches[0])>2e-4 for p in matches):raise ValueError('Đường dẫn chỉ nhiều cạnh sau sửa: '+e['ref'])
        if np.linalg.norm(point-matches[0])<1e-7:continue
        after=copy.deepcopy(g);after['vertices'][0][:2]=matches[0].tolist()
        operations.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(g),after=json.dumps(after),xyz=[],reason=REASON+'Giữ mũi tên số chi tiết gắn đúng cạnh bas sau sửa'))
    return operations,reviews


def validate_projections(plan,context):
    expected,reviews=compile_projections(context,plan.operations)
    additions={o.ref for o in expected if o.action=='append_geometry'}
    if any(o.action=='append_geometry' and o.ref not in additions for o in plan.operations):
        raise ValueError('Cạnh thêm chưa có adapter nguồn đã kiểm chứng')
    if not expected:return reviews
    actual={}
    for op in plan.operations:
        if op.action in ('replace_geometry','append_geometry'):actual.setdefault(op.ref,[]).append(op)
    for op in expected:
        matches=actual.get(op.ref,[])
        present=matches[0] if len(matches)==1 else None
        if present is None or present.action!=op.action or not near(json.loads(present.before),json.loads(op.before)) or not near(json.loads(present.after),json.loads(op.after)):
            raise ValueError('Kế hoạch thiếu/sai hình chiếu 2D kéo theo: '+op.ref)
    # A changed adapter must also invalidate old plans/revisions.
    return reviews
