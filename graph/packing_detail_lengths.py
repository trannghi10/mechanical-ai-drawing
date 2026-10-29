"""Source-bound packaging cut lengths confirmed by the drawing's engineer.

An executed measured carton change drives the same delta in a confirmed stock
length. Only an independently titled, DIM-bound rectangular detail is edited;
unmapped exploded/perspective illustrations are never credited as complete.
"""
import copy,json,math,re
from bom.reader import normalized,plain
from cad.geometry import near
from cad.frame_geometry import world,local_geometry
from cad.edit_engine import Operation
from graph.packing_side_layers import rect,dim_bound,bound_hatches

TOL=1e-5
SPEC=re.compile(r'(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)')


def spec(text):
    matches=list(SPEC.finditer(plain(text)))
    return tuple(float(x.replace(',','.')) for x in matches[0].groups()) if len(matches)==1 else None


def length_text(raw,before,after):
    matches=list(SPEC.finditer(plain(raw)))
    native=list(SPEC.finditer(raw))
    if len(matches)!=1 or len(native)!=1 or spec(raw)!=tuple(before):raise ValueError('Quy cách lót góc không khớp lựa chọn nguồn')
    m=native[0];return raw[:m.start(3)]+f'{after[-1]:g}'+raw[m.end(3):]


def detail_operations(context,shape,dimensions,new_length):
    """Keep native end details only if their whole paths stay in the fixed zone."""
    from shapely.geometry import Polygon,LineString,Point
    records={e['ref']:e for e in context['entities']};source=records[shape['ref']]
    axis=next(a for a in (0,1) if near(shape['size'][a],dimensions[0]['scaled_measurement'],TOL))
    lo,hi=shape['low'][axis],shape['high'][axis];middle=(lo+hi)/2
    polygon=Polygon([p[:2] for p in shape['geometry']['points']]);internal=[]
    same=[e for e in records.values() if e['ref']!=source['ref'] and not e.get('review_only') and
        e.get('layout')==source.get('layout') and e.get('coordinate_frame')==source.get('coordinate_frame') and e.get('geometry') and
        set(source.get('source_sheet_ids',[])).intersection(e.get('source_sheet_ids',[]))]
    for e in same:
        if e['type'] not in ('LINE','LWPOLYLINE','POLYLINE','CIRCLE','ARC','ELLIPSE','SPLINE','INSERT'):continue
        w=world(e);g=w['geometry']
        if e['type']=='LINE':points=[g['start'],g['end']]
        elif e['type'] in ('LWPOLYLINE','POLYLINE') and not any(any(p[2:]) for p in g['points']):
            points=[[p[0],p[1],g['elevation']] for p in g['points']]
            if g['closed']:points=points+points[:1]
        else:
            from graph.part_map import locator_bounds
            b=locator_bounds(w)
            if b is None:
                from cad.curved_profiles import primitives
                edges=primitives(w);bounds=[]
                for edge in edges:
                    if edge['kind']=='line':bounds.extend((edge['start'][:2],edge['end'][:2]))
                    elif edge['kind']=='arc':
                        x,y=edge['center'][:2];r=edge['radius'];bounds.extend(([x-r,y-r],[x+r,y+r]))
                    else:bounds=[];break
                if bounds:b=[min(p[0] for p in bounds),min(p[1] for p in bounds),max(p[0] for p in bounds),max(p[1] for p in bounds)]
            if b and (b[2]<polygon.bounds[0]-TOL or b[0]>polygon.bounds[2]+TOL or b[3]<polygon.bounds[1]-TOL or b[1]>polygon.bounds[3]+TOL):continue
            raise ValueError('Lót góc còn hình học chưa gắn trong vùng sửa: '+e['ref'])
        if max(abs(p[2]-shape['geometry']['elevation']) for p in points)>TOL:continue
        path=LineString([p[:2] for p in points])
        if not polygon.buffer(TOL).intersects(path):continue
        internal.append((e,points,path))
    options=[]
    for fixed_low in (True,False):
        a,b=(lo,lo+new_length) if fixed_low else (hi-new_length,hi)
        after=copy.deepcopy(shape['geometry'])
        moving=hi if fixed_low else lo;target=b if fixed_low else a
        for p in after['points']:
            if near(p[axis],moving,TOL):p[axis]=target
        changed=Polygon([p[:2] for p in after['points']])
        if not changed.is_valid or changed.area<=TOL:continue
        if any(not all(p[axis]<middle-TOL if fixed_low else p[axis]>middle+TOL for p in points) or
            not changed.buffer(TOL).covers(path) for _,points,path in internal):continue
        options.append((fixed_low,after))
    if not options:raise ValueError('Lót góc có chi tiết bên trong chưa xác định mốc giữ')
    # With no end feature, a symmetric stock rectangle has equivalent cut
    # results; use its low coordinate. Otherwise the source detail fixes it.
    fixed_low,after=options[0]
    ops=[Operation(ref=source['ref'],action='replace_geometry',before=json.dumps(source['geometry']),after=json.dumps(local_geometry(source,after)),xyz=[],reason='Chiều dài đóng gói đã chốt; giữ tiết diện và toàn bộ chi tiết ở đầu nguồn cố định')]
    ops.extend(bound_hatches(context,source,local_geometry(source,after)))
    from cad.vertex_dimensions import synchronize
    ops.extend(synchronize(context,ops,source['source_sheet_ids']))
    if not {d['ref'] for d in dimensions}<={o.ref for o in ops}:raise ValueError('Thiếu DIM theo chiều dài lót góc')
    return ops,[e['ref'] for e,_,_ in internal],('low' if fixed_low else 'high')


def bindings(plan,context,envelopes=None):
    choices=context.get('design_choices',{})
    if plan.questions or not plan.operations or context.get('units')!=4 or choices.get('source_hash')!=context.get('source_hash'):return []
    decisions=[x for x in choices.get('confirmed_choices',[]) if x.get('key')=='packaging_cut_length' and x.get('keep_cross_section') is True and x.get('keep_source_clearances') is True]
    if not decisions:return []
    if envelopes is None:
        from graph.packing_envelope_sync import bindings as envelope_bindings
        envelopes=[p for p,_ in envelope_bindings(plan,context)]
    from graph.native_instances import equivalent_operation
    records={e['ref']:e for e in context['entities']};actual={o.ref:o for o in plan.operations};result=[]
    for decision in decisions:
        code=decision.get('part_code');before=decision.get('before_spec_mm',[]);after=decision.get('after_spec_mm',[])
        if len(before)!=3 or len(after)!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in before+after) or before[:2]!=after[:2]:raise ValueError('Lựa chọn chiều dài đóng gói không hợp lệ')
        related=[p for p in envelopes if p['product_code']==decision.get('product_code')]
        if not related:continue
        matches=[p for p in related if near(p['carton_target_mm']-p['carton_before_mm'],after[-1]-before[-1],TOL)]
        if len(matches)!=1:raise ValueError('Lót góc đã chốt chưa khớp thay đổi thùng đã kiểm chứng')
        envelope=matches[0]
        ref=envelope['carton_outline_ref'];op=actual.get(ref)
        if not op or op.action!='replace_geometry' or not near(json.loads(op.before),records[ref]['geometry'],TOL):raise ValueError('Thiếu sửa hình thùng trước khi tính lót góc')
        moved=rect(dict(records[ref],geometry=json.loads(op.after)))
        if moved is None or not near(moved['size'][1],envelope['carton_target_mm'],TOL):raise ValueError('Chiều cao thùng khác quy tắc lót góc')
        groups=[g for g in context.get('part_graph',{}).get('packaging_groups',[]) if g['product_code']==envelope['product_code'] and code in g['package_codes']]
        if len(groups)!=1:raise ValueError('Mã lót góc không thuộc nhóm đóng gói nguồn')
        rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
        if not rows or any(t['bom'].get('status')!='verified_template' or spec(r['description'])!=tuple(before) or not re.match(r'lot goc carton\b',normalized(r['description'])) for t,r in rows):raise ValueError('BOM lót góc khác lựa chọn đã chốt')
        owned={sid for n in context['part_graph']['nodes'] if n['code']==code for sid in n.get('detail_sheets',[])}
        targets=[t for t in context['targets'] if t['id'] in owned and any(plain(x)==code for x in t.get('texts',[])) and any(spec(x)==tuple(before) for x in t.get('texts',[]))]
        if not targets:raise ValueError('Thiếu khung chi tiết lót góc có mã và quy cách nguồn')
        operations=[];proofs=[]
        for target in targets:
            local=[e for e in records.values() if target['id'] in e.get('source_sheet_ids',[]) and not e.get('review_only')]
            candidates=[]
            for e in local:
                box=rect(e)
                if not box:continue
                axes=[a for a in (0,1) if near(box['size'][a],before[-1],TOL) and near(box['size'][1-a],before[0],TOL)]
                if len(axes)!=1:continue
                dims=[d for d in local if dim_bound(d,box,axes[0])]
                if dims:candidates.append((box,dims))
            if len(candidates)!=1:raise ValueError('Chưa gắn duy nhất DIM và hình chi tiết lót góc')
            box,dims=candidates[0];ops,stationary,anchor=detail_operations(context,box,dims,after[-1]);operations.extend(ops)
            proofs.append(dict(sheet_id=target['id'],outline_ref=box['ref'],dimension_refs=[d['ref'] for d in dims],stationary_refs=stationary,detail_fixed_end=anchor))
        from bom.operations import cell_operations
        from backend.services.change_service import EditProposal
        edits=[]
        for t,row in rows:
            cell=row['cells']['description'];raw=cell['raw_text']
            for op in cell_operations(t,cell,length_text(raw,before,after),records,'Đồng bộ chiều dài lót góc theo quyết định kỹ thuật và thùng đã sửa'):
                operations.append(op);edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='bom',before=op.before,after=op.after,reason=op.reason))
        mirrors={v.get('mirror_ref') for t,r in rows for v in r.get('cells',{}).values()}
        for e in records.values():
            raw=e.get('raw_text',e.get('text',''))
            if e['type'] not in ('TEXT','MTEXT') or e['ref'] in mirrors or not owned.intersection(e.get('source_sheet_ids',[])) or spec(raw)!=tuple(before):continue
            op=Operation(ref=e['ref'],action='replace_text',before=raw,after=length_text(raw,before,after),xyz=[],reason='Đồng bộ chiều dài trên khung tên chi tiết lót góc');operations.append(op)
        result.append(dict(product_code=envelope['product_code'],part_code=code,before_spec_mm=before,after_spec_mm=after,details=proofs,
            source_hash=context['source_hash'],status='confirmed_source_packaging_cut_length',complete_packaging=False,operations=operations,edits=edits))
    return result


def synchronize(plan,context,audit=None):
    from backend.services.change_service import EditProposal
    from backend.services.compound_planner import operation_key,same_operation
    checked=bindings(plan,context);by={operation_key(o):o for o in plan.operations};additions=[]
    for proof in checked:
        manifest={e.entity_ref:e for e in proof['edits']}
        for op in proof['operations']:
            key=operation_key(op)
            if key in by:
                if not same_operation(by[key],op):raise ValueError('Lót góc có thao tác xung đột: '+op.ref)
            else:additions.append((op,proof['part_code'],manifest.get(op.ref)));by[key]=op
    for op,code,edit in additions:
        plan.operations.append(op);plan.edits.append(edit or EditProposal(entity_ref=op.ref,part_number=code,purpose='annotation' if op.action=='replace_text' else 'geometry',before=op.before,after=op.after,reason=op.reason))
    if audit is not None:audit['confirmed_length_bindings']=[{k:v for k,v in proof.items() if k not in ('operations','edits')} for proof in checked]
    return plan
