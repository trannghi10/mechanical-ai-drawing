"""Confirmed cut lengths for source-proven cropped hollow-tube detail views.

The native illustration remains cropped. Its nominal DIM text is updated
without inventing a model-space scale or calling the picture a full-length CAD
solid. Assembly placement and complete-product gates remain independent.
"""
import copy
import json
import re
from cad.geometry import near
from cad.edit_engine import Operation
from cad.broken_tube import tube_spec, source_views, valid_binding
from graph.confirmed_inner_panels import proofs as panel_proofs
from bom.stage_links import physical_spec

TOL=1e-4

def proofs(plan,context):
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash') or context.get('units')!=4:return []
    mates=[m for m in choices.get('confirmed_choices',[]) if m.get('key')=='vertical_tube_inner_mate' and m.get('policy')=='preserve_source_clearances']
    core_mates=[m for m in choices.get('confirmed_choices',[]) if m.get('key')=='core_member_clearance' and m.get('policy')=='verified_bom_clearance']
    if not mates and not core_mates:return []
    windows=panel_proofs(plan,context);records={e['ref']:e for e in context['entities']};result=[]
    for mate in mates:
        related=[p for p in windows if all(p.get(k)==mate.get(k) for k in ('product_code','frame_part_code','top_plate_part_code','bottom_plate_part_code'))]
        if len(related)!=1:continue
        frame=related[0];code=mate['part_code']
        rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
        specs={tube_spec(r['description']) for _,r in rows}
        if len(specs)!=1 or None in specs or any(t['bom'].get('status')!='verified_template' for t,_ in rows):continue
        try:quantities={float(r['quantity_text'].replace(',','.')) for _,r in rows}
        except (ValueError,KeyError):continue
        if quantities!={mate.get('quantity')}:continue
        spec=next(iter(specs));length=spec[-1]
        clearances={round(w['height']-length,6) for w in frame['source_windows']}
        if len(clearances)!=1 or min(clearances)<-TOL:continue
        clearance=next(iter(clearances))
        target=round(frame['frame_height_after_mm']-sum(frame['cap_after_mm'])-clearance,3)
        if target<=max(spec[:2])*10:raise ValueError('Thanh giằng không còn đủ chiều dài sau giảm khung')
        views=source_views(context,code,spec)
        if len(views)!=1:continue
        view=views[0];before=records[view['dimension_ref']]['geometry'];after=copy.deepcopy(before)
        after['text']=f'{target:.12g}'+view['suffix']
        binding=dict(view,source_hash=context['source_hash'],target_nominal_mm=target,status='confirmed_cropped_tube_cut',before=before,after=after,
            source_clearance_mm=clearance,confirmed_quantity=mate['quantity'],height_driver_refs=frame['height_driver_refs'])
        if not valid_binding(binding,view['dimension_ref'],before,after,context['source_hash']):
            raise ValueError('Kích thước cắt mới cần dựng lại hình rút ngắn, không sửa nhãn đơn thuần')
        result.append(binding)
    for mate in core_mates:
        related=[p for p in windows if p['product_code']==mate.get('product_code') and p['frame_part_code']==mate.get('frame_part_code')]
        if len(related)!=1:continue
        frame=related[0];code=mate['member_part_code']
        rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
        specs={tube_spec(r['description']) for _,r in rows}
        if len(specs)!=1 or None in specs or any(t['bom'].get('status')!='verified_template' for t,_ in rows):continue
        spec=next(iter(specs));caps=[]
        from backend.services.design_choices import sheet_spec
        for cap in (mate['top_plate_part_code'],mate['bottom_plate_part_code'],mate['middle_plate_part_code']):
            cap_rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==cap]
            old={sheet_spec(r['description']) for t,r in cap_rows if t['bom'].get('status')=='verified_template'}
            new=set()
            for t,r in cap_rows:
                cell=r['cells']['description']
                ops=[o for o in plan.operations if (o.action=='table_cell' and o.ref==t['ref'] and o.cell_index==cell.get('index')) or
                     (cell.get('storage')=='text' and o.action=='replace_text' and o.ref==cell.get('mirror_ref'))]
                if len(ops)!=1:break
                new.add(sheet_spec(ops[0].after))
            else:
                if len(old)==len(new)==1 and None not in old|new:
                    caps.append((next(iter(old))[0],next(iter(new))[0]));continue
            break
        if len(caps)!=3 or not near([v[0] for v in caps[:2]],frame['cap_before_mm'],TOL):continue
        source_core=frame['source_windows'][0]['height']
        new_core=frame['frame_height_after_mm']-sum(frame['cap_after_mm'])
        if not near([source_core,new_core,spec[-1]],[mate['core_height_before_mm'],mate['core_height_after_mm'],mate['member_length_before_mm']],TOL):
            raise ValueError('Mốc cụm xương/thanh cắt khác quyết định đã chốt')
        if not near(source_core-spec[-1]-caps[0][0]-caps[1][0],mate['top_clearance_mm']+mate['bottom_clearance_mm'],TOL):
            raise ValueError('Khe hở thanh nguồn khác quyết định theo BOM')
        target=new_core-caps[0][1]-caps[1][1]-mate['top_clearance_mm']-mate['bottom_clearance_mm']
        if not near(target,mate['member_length_after_mm'],TOL) or min(mate['top_clearance_mm'],mate['bottom_clearance_mm'])<0:
            raise ValueError('Chiều dài thanh không giữ khe hở hai đầu đã chốt')
        views=source_views(context,code,spec)
        if len(views)!=1:continue
        view=views[0];before=records[view['dimension_ref']]['geometry'];after=copy.deepcopy(before)
        after['text']=f'{target:.12g}'+view['suffix']
        binding=dict(view,source_hash=context['source_hash'],target_nominal_mm=target,status='confirmed_cropped_tube_cut',before=before,after=after,
            source_clearance_mm=mate['top_clearance_mm']+mate['bottom_clearance_mm'],height_driver_refs=frame['height_driver_refs'],
            core_height_before_mm=source_core,core_height_after_mm=new_core,cap_gauges=caps,
            confirmed_end_clearances_mm=[mate['bottom_clearance_mm'],mate['top_clearance_mm']],mate_choice=mate)
        binding.update(frame_part_code=frame['frame_part_code'],frame_height_before_mm=frame['frame_height_before_mm'],frame_height_after_mm=frame['frame_height_after_mm'])
        if not valid_binding(binding,view['dimension_ref'],before,after,context['source_hash']):raise ValueError('Thanh cụm xương cần dựng lại hình rút ngắn')
        result.append(binding)
    return result

def text_operations(proof,context):
    from bom.operations import cell_operations
    records={e['ref']:e for e in context['entities']};code=proof['part_code'];result=[]
    rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
    def changed(raw):
        matches=[m for m in re.finditer(r'[x×]\s*(\d+(?:[.,]\d+)?)(?=\s*mm\b)',raw) if near(float(m[1].replace(',','.')),proof['source_nominal_mm'],TOL)]
        if len(matches)!=1:raise ValueError('Không gắn được chiều dài cắt trong quy cách thanh giằng')
        m=matches[0];return raw[:m.start(1)]+f'{proof["target_nominal_mm"]:.12g}'+raw[m.end(1):]
    for t,r in rows:
        cell=r['cells']['description'];result.extend(cell_operations(t,cell,changed(cell['raw_text']),records,'Đồng bộ chiều dài cắt theo mốc lắp giữa hai tấm đã chốt'))
    specs={physical_spec(r['description']) for _,r in rows}
    sheets={s for n in context['part_graph']['nodes'] if n['code']==code for s in n.get('detail_sheets',[])}
    mirrors={o.ref for o in result if o.action=='replace_text'}
    for e in records.values():
        if e['ref'] in mirrors or e['type'] not in ('TEXT','MTEXT') or not sheets.intersection(e.get('source_sheet_ids',[])):continue
        raw=e.get('raw_text',e.get('text',''))
        if physical_spec(raw) in specs:
            result.append(Operation(ref=e['ref'],action='replace_text',before=raw,after=changed(raw),xyz=[],reason='Đồng bộ quy cách cắt thanh giằng, giữ tiết diện và vật tư mua hàng'))
    return result

def synchronize(plan,context):
    checks=proofs(plan,context)
    if not checks:return plan
    from backend.services.compound_planner import operation_key,same_operation,merge_numeric_text
    from backend.services.change_service import EditProposal
    result=plan.model_copy(deep=True);ops={operation_key(o):o for o in result.operations}
    for proof in checks:
        dim=Operation(ref=proof['dimension_ref'],action='replace_geometry',before=json.dumps(proof['before']),after=json.dumps(proof['after']),xyz=[],
            reason='Hình rút ngắn: đổi chiều dài cắt danh nghĩa; giữ ký hiệu ngắt và dung sai nguồn, không coi nét là chiều dài thật')
        for op in text_operations(proof,context)+[dim]:
            key=operation_key(op);previous=ops.get(key)
            if previous and not same_operation(previous,op):
                merged=merge_numeric_text(previous,op) if op.action in ('replace_text','table_cell') else None
                if merged is None:raise ValueError('Chiều dài cắt thanh giằng có thay đổi xung đột: '+op.ref)
                op=merged
            ops[key]=op
            result.edits=[e for e in result.edits if not (e.entity_ref==op.ref and e.before==op.before)]
            result.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['part_code'],purpose='annotation' if op.action!='table_cell' else 'bom',
                before=op.before,after=op.after,reason=op.reason))
    result.operations=list(ops.values());validate(result,context);return result

def validate(plan,context):
    from backend.services.compound_planner import operation_key,same_operation
    from graph.native_instances import equivalent_operation
    operations={operation_key(o):o for o in plan.operations}
    result={}
    for proof in proofs(plan,context):
        expected=Operation(ref=proof['dimension_ref'],action='replace_geometry',before=json.dumps(proof['before']),after=json.dumps(proof['after']),xyz=[],reason='Nominal cut length')
        op=operations.get(operation_key(expected))
        if not op or not equivalent_operation(op,expected):raise ValueError('DIM danh nghĩa thanh giằng chưa đồng bộ chiều dài cắt')
        for expected in text_operations(proof,context):
            op=operations.get(operation_key(expected))
            if not op or not same_operation(op,expected):raise ValueError('BOM/tên thanh giằng chưa đồng bộ chiều dài cắt')
        result[proof['dimension_ref']]=proof
    return result
