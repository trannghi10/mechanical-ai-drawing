"""Preserve independently measured packing clearances in native planar views.

Measured rectangular cartons and foam pads preserve source gaps/thicknesses.
Exploded, rotated-in-3D and unmapped packs remain explicit review requirements.
"""
import copy
import json
import math
import re
import numpy as np
from ezdxf.math import Vec3
from bom.reader import normalized
from cad.frame_geometry import world,matrix
from cad.geometry import near
from cad.parametric import LinearResize
from graph.native_contacts import inventory,bounds,TOL
from graph.measurement_rules import MeasurementEquation,MeasurementTerm


def feature_after(feature,records,ops):
    points=[]
    for ref in feature['refs']:
        e=copy.deepcopy(records[ref]);op=ops.get(ref)
        if op:
            if op.action=='replace_geometry':e['geometry']=json.loads(op.after)
            elif op.action=='line_end' and e['type']=='LINE':e['geometry']['end']=op.xyz
            else:raise ValueError('Đóng gói cần snapshot geometry đầy đủ')
        g=world(e)['geometry']
        ps=[g['start'],g['end']] if e['type']=='LINE' else [[p[0],p[1],g['elevation']] for p in g['points']]
        shift=np.zeros(3)
        for root,move in ops.items():
            if move.action=='move_insert' and ref.startswith(root+'/'):
                native=records[root]
                shift+=np.asarray(matrix(native).transform_direction(Vec3(np.asarray(move.xyz)-native['position'])))
        points.extend((np.asarray(ps)+shift).tolist())
    return bounds(points)


def candidates(plan,context):
    if not context.get('part_graph',{}).get('packaging_groups'):return []
    records,features,_=inventory(context);ops={o.ref:o for o in plan.operations}
    output=[]
    for group in context.get('part_graph',{}).get('packaging_groups',[]):
        for sid in group['sheet_ids']:
            local=[f for f in features.values() if sid in f['sheet_ids']]
            products=[f for f in local if f['part_code'] in group['product_part_codes']]
            specs={code:[r['description'] for e in records.values() for r in e.get('bom',{}).get('rows',[]) if r['part_code']==code] for code in group['package_codes']}
            boxes=[f for f in local if f['part_code'] in specs and specs[f['part_code']] and
                   all(re.search(r'\b(?:thung|hop)\s+(?:carton|go)\b',normalized(d)) for d in specs[f['part_code']])]
            pads=[f for f in local if f['part_code'] in specs and specs[f['part_code']] and
                  all(re.match(r'(?:xop tam|tam xop|foam)\b',normalized(d)) for d in specs[f['part_code']])]
            codes={r['part_code'] for e in records.values() if sid in e.get('source_sheet_ids',[]) for r in e.get('bom',{}).get('rows',[])}
            if len(products)!=1 or len(boxes)!=1 or codes!={f['part_code'] for f in products+boxes+pads}:continue
            product,box=products[0],boxes[0]
            descriptions=[r['description'] for e in records.values() for r in e.get('bom',{}).get('rows',[]) if r['part_code']==box['part_code']]
            if not descriptions or not all(re.search(r'\b(?:thung|hop)\s+(?:carton|go)\b',normalized(d)) for d in descriptions):continue
            p0=bounds(product['points']);b0=bounds(box['points']);p1=feature_after(product,records,ops)
            if not near(p0[:,2].tolist(),b0[:,2].tolist(),TOL):continue
            clearances=np.array([p0[0,:2]-b0[0,:2],b0[1,:2]-p0[1,:2]])
            if np.any(clearances<-TOL):continue
            delta=p1-p0
            axes=[a for a in (0,1) if abs(delta[1,a]-delta[0,a])>TOL]
            if len(axes)!=1:continue
            axis=axes[0];other=1-axis
            if np.max(abs(delta[:,other]))>TOL:continue
            # Keep the source package origin/anchor only when that endpoint is
            # truly fixed, or when both ends move symmetrically.
            dl,dh=map(float,delta[:,axis])
            if abs(dl)>TOL and abs(dh)>TOL and abs(dl+dh)>TOL:continue
            pd=[d for d in product['dimensions'] if abs(abs(d['axis'][axis])-1)<TOL and d['ref'] in ops]
            bd=[d for d in box['dimensions'] if abs(abs(d['axis'][axis])-1)<TOL]
            if len(pd)!=1 or len(bd)!=1:continue
            pd,bd=pd[0],bd[0]
            if any(abs(d['linear_factor']-1)>TOL for d in (pd,bd)):continue
            value=bd['measurement']+dh-dl
            if not math.isfinite(value) or value<=0:raise ValueError('Thùng đóng gói sau sửa có kích thước không hợp lệ')
            dg=world(records[bd['ref']])['geometry']
            if abs(dl+dh)<TOL and abs(dl)>TOL:anchor='center'
            else:
                fixed_low=abs(dl)<TOL
                first_low=dg['defpoint2'][axis]<dg['defpoint3'][axis]
                anchor='first' if fixed_low==first_low else 'second'
            evidence=sorted(set(product['evidence_refs']+box['evidence_refs']))
            recipe=LinearResize(part_code=box['part_code'],dimension_ref=bd['ref'],new_measurement=value,
                outline_refs=box['refs'],hole_refs=[],anchor=anchor,evidence_refs=evidence)
            from graph.fit_constraints import measurement
            pg=world(records[pd['ref']])['geometry']
            if abs(dl+dh)<TOL and abs(dl)>TOL:product_anchor='center'
            else:product_anchor='first' if (abs(dl)<TOL)==(pg['defpoint2'][axis]<pg['defpoint3'][axis]) else 'second'
            product_recipe=LinearResize(part_code=product['part_code'],dimension_ref=pd['ref'],
                new_measurement=measurement(records[pd['ref']],json.loads(ops[pd['ref']].after)),
                outline_refs=product['refs'],hole_refs=[],anchor=product_anchor,evidence_refs=product['evidence_refs'])
            equation=MeasurementEquation(terms=[MeasurementTerm(dimension_ref=pd['ref'],coefficient=-1),
                MeasurementTerm(dimension_ref=bd['ref'],coefficient=1)],evidence_refs=evidence)
            proof=dict(product=product,box=box,recipe=recipe,product_recipe=product_recipe,equation=equation,role='carton',
                sheet_id=sid,product_code=group['product_code'],clearances_mm=clearances.tolist(),
                before_mm=bd['measurement'],after_mm=value,axis=axis,expected_bounds=b0+delta,pad_motions=[],pad_expectations=[])
            from graph.packing_pads import rules as pad_rules
            pad_result=pad_rules(proof,pads,records,ops)
            if pad_result is None:continue
            resized,moved,expectations=pad_result
            proof.update(pad_motions=moved,pad_expectations=expectations)
            output.extend([proof,*resized])
    return output


def synchronize(plan,context,audit=None):
    if plan.questions or not plan.operations or not context.get('part_graph',{}).get('packaging_groups'):return plan
    from graph.packing_envelope_sync import synchronize as sync_envelopes
    plan=sync_envelopes(plan,context,audit)
    from graph.packing_detail_lengths import synchronize as sync_lengths
    plan=sync_lengths(plan,context,audit)
    from backend.services.change_service import EditProposal,DependencyProposal
    from bom.operations import cell_operations
    from backend.services.parametric_service import compile_recipes
    records={e['ref']:e for e in context['entities']};proofs=candidates(plan,context)
    seen={r.dimension_ref:r for r in plan.resize_recipes};ops={o.ref:o for o in plan.operations}
    for proof in proofs:
        recipe=proof['recipe'];code=recipe.part_code
        driver=proof['product_recipe']
        if driver.dimension_ref not in seen:plan.resize_recipes.append(driver);seen[driver.dimension_ref]=driver
        for motion in proof.get('pad_motions',[]):
            op=motion['operation'];rule=motion['rule']
            if op.ref in ops:
                if ops[op.ref].model_dump()!=op.model_dump():raise ValueError('Vị trí lớp đệm xung đột với đầu sản phẩm')
            else:
                plan.operations.append(op);ops[op.ref]=op
                plan.edits.append(EditProposal(entity_ref=op.ref,part_number=motion['part_code'],purpose='geometry',before=op.before,after=json.dumps(op.xyz),reason=op.reason))
            if not any(d.coordinate_rule and d.coordinate_rule.model_dump()==rule.model_dump() for d in plan.dependencies):
                plan.dependencies.append(DependencyProposal(source_part=motion['source_part'],target_part=motion['part_code'],
                    relationship='Lớp đệm theo đầu sản phẩm trong hình đóng gói 2D nguồn',evidence_refs=motion['evidence_refs'],
                    required_change='Dịch lớp đệm; giữ độ dày, vật liệu và khe hở gốc.',needs_confirmation=True,coordinate_rule=rule))
        old=proof['before_mm'];new=proof['after_mm']
        pattern=re.compile(r'(?<![\d.,])'+re.escape(f'{old:g}').replace(r'\.',r'[.,]')+r'(?![\d.,])')
        rows=[(t,r) for t in records.values() for r in t.get('bom',{}).get('rows',[]) if r['part_code']==code]
        for table,row in rows:
            cell=row.get('cells',{}).get('description',{});raw=cell.get('raw_text','')
            if len(pattern.findall(raw))!=1:raise ValueError('Quy cách thùng có nhiều chiều trùng nhau; cần xác định đúng trục BOM trước khi sửa')
            for op in cell_operations(table,cell,pattern.sub(f'{new:g}',raw),records,'Đồng bộ quy cách thùng; giữ khe hở đóng gói đo từ nguồn'):
                if op.ref in ops:
                    if ops[op.ref].model_dump()!=op.model_dump():raise ValueError('BOM đóng gói xung đột với quy cách tính từ khe hở nguồn')
                    continue
                plan.operations.append(op);ops[op.ref]=op
                plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='bom',before=op.before,after=op.after,reason=op.reason))
        from bom.stage_links import physical_spec
        specs={physical_spec(row['description']) for _,row in rows}
        owned={sid for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==code for sid in n.get('detail_sheets',[])}
        cell_refs={c.get('mirror_ref') for e in records.values() for r in e.get('bom',{}).get('rows',[]) for c in r.get('cells',{}).values()}
        from cad.edit_engine import Operation
        for e in records.values():
            if e['type'] not in ('TEXT','MTEXT') or e['ref'] in cell_refs or physical_spec(e.get('text','')) not in specs:continue
            if not owned.intersection(e.get('source_sheet_ids',[])) and not e['ref'].startswith(proof['box']['instance_ref']+'/'):continue
            raw=e.get('raw_text',e.get('text',''))
            if len(pattern.findall(raw))!=1:raise ValueError('Chưa xác định đúng chiều quy cách trên khung tên thùng')
            op=Operation(ref=e['ref'],action='replace_text',before=raw,after=pattern.sub(f'{new:g}',raw),xyz=[],reason='Đồng bộ quy cách trên khung tên thùng đóng gói')
            if op.ref in ops:
                if ops[op.ref].model_dump()!=op.model_dump():raise ValueError('Khung tên đóng gói xung đột với kích thước thùng')
                continue
            plan.operations.append(op);ops[op.ref]=op
            plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='annotation',before=op.before,after=op.after,reason=op.reason))
        if recipe.dimension_ref in seen:
            if seen[recipe.dimension_ref].model_dump()!=recipe.model_dump():raise ValueError('Recipe thùng xung đột với khe hở nguồn')
        else:plan.resize_recipes.append(recipe);seen[recipe.dimension_ref]=recipe
        same=[d for d in plan.dependencies if d.equation_rule and {t.dimension_ref for t in d.equation_rule.terms}=={t.dimension_ref for t in proof['equation'].terms}]
        if same:
            if any(d.equation_rule.model_dump()!=proof['equation'].model_dump() for d in same):raise ValueError('Ràng buộc đóng gói bị thay đổi')
        else:
            plan.dependencies.append(DependencyProposal(source_part=proof['product']['part_code'],target_part=code,
                relationship='Giữ khe hở từng đầu giữa sản phẩm và thùng trong hình lắp 2D nguồn',
                evidence_refs=recipe.evidence_refs,required_change=f'Chiều thùng {old:g} → {new:g} mm; giữ vật liệu carton và khe hở gốc.',
                needs_confirmation=True,equation_rule=proof['equation']))
        warning='Quy cách đóng gói thay đổi: cần đối chiếu/cấp mã mua hàng theo quy trình nội bộ trước khi đặt thùng.'
        if warning not in plan.warnings:plan.warnings.append(warning)
    if proofs:
        plan=compile_recipes(plan,context)
        from graph.native_instances import synchronize as sync_native
        plan=sync_native(plan,context)
        for proof in proofs:
            actual=feature_after(proof['box'],records,{o.ref:o for o in plan.operations})
            if not near(actual.tolist(),proof['expected_bounds'].tolist(),TOL):raise ValueError('Thùng sau sửa không giữ đúng khe hở từng đầu')
            for pad,expected in proof.get('pad_expectations',[]):
                actual=feature_after(pad,records,{o.ref:o for o in plan.operations})
                if not near(actual.tolist(),expected.tolist(),TOL):raise ValueError('Lớp đệm sau sửa không khớp vị trí/kích thước nguồn')
    if audit is not None:audit['bindings']=[dict({k:v for k,v in p.items() if k in ('sheet_id','product_code','clearances_mm','before_mm','after_mm','axis','role')},part_code=p['recipe'].part_code) for p in proofs]
    return plan


def validate(plan,context):
    if plan.questions or not plan.operations or not context.get('part_graph',{}).get('packaging_groups'):return
    checked=synchronize(plan.model_copy(deep=True),context)
    if len(checked.operations)!=len(plan.operations) or len(checked.resize_recipes)!=len(plan.resize_recipes) or len(checked.dependencies)!=len(plan.dependencies):
        raise ValueError('Thiếu đồng bộ hình học/BOM/ràng buộc thùng đóng gói')


def review(plan,context):
    groups=context.get('part_graph',{}).get('packaging_groups',[])
    if not groups or not any(o.action in ('replace_geometry','move_insert','line_end','append_geometry','remove_insert') for o in plan.operations):return []
    records,features,_=inventory(context);ops={o.ref:o for o in plan.operations};result=[]
    from graph.projected_profiles import bindings as projected_bindings
    projections=projected_bindings(plan,context)
    audit={}
    try:
        checked=synchronize(plan.model_copy(deep=True),context,audit)
        complete=len(checked.operations)==len(plan.operations) and len(checked.resize_recipes)==len(plan.resize_recipes) and len(checked.dependencies)==len(plan.dependencies)
    except ValueError:complete=False
    from graph.native_instances import inventory as native_inventory
    _,parts,owner=native_inventory(context)
    for group in groups:
        local_features=[f for f in features.values() if f['part_code'] in group['product_part_codes']]
        covered={r for f in local_features for r in f['evidence_refs']}
        covered.update(ref for proof in projections if proof['part_code'] in group['product_part_codes'] for ref in proof['target_refs'])
        physical={o.ref for o in plan.operations if o.action in ('replace_geometry','line_end','move_insert','append_geometry','remove_insert') and
                  (owner(o.ref) and parts[owner(o.ref)] in group['product_part_codes'] or
                   o.ref in parts and parts[o.ref] in group['product_part_codes'] or
                   set(records.get(o.ref,{}).get('source_sheet_ids',[])).intersection(group['product_sheet_ids']))}
        changed=[f for f in local_features if not near(bounds(f['points']).tolist(),feature_after(f,records,ops).tolist(),TOL)]
        unchanged=bool(physical) and physical<=covered and not changed
        bindings=[b for b in audit.get('bindings',[]) if b['product_code']==group['product_code']]
        # Every packaging frame must be accounted for. Loose illustrations,
        # pads, external dimensions and unknown curves are never certified by
        # an unrelated clean view of the same carton code.
        known_frames=set()
        for sid in group['sheet_ids']:
            local=[e for e in records.values() if sid in e.get('source_sheet_ids',[])]
            tables=[e for e in local if e.get('bom',{}).get('status')=='verified_template']
            resources={r for t in tables for r in [t['ref'],*t.get('source_refs',[])]}
            table_roots={t['ref'] for t in tables if t['type']=='ACAD_TABLE'}
            frame=next((t.get('frame_insert') for t in context.get('targets',[]) if t['id']==sid),None)
            unknown=[e['ref'] for e in local if not (e['ref']==sid or e['ref'] in resources or e['ref'] in parts or owner(e['ref']) or
                any(e['ref']==r or e['ref'].startswith(r+'/') for r in table_roots) or
                frame and (e['ref']==frame or e['ref'].startswith(frame+'/')) or e['type'] in ('TEXT','MTEXT','ATTRIB','ATTDEF'))]
            native_codes={parts[e['ref']] for e in local if e['ref'] in parts}
            if local and not unknown and native_codes and native_codes<=set(group['product_part_codes']+group['package_codes']):known_frames.add(sid)
        verified=complete and bool(bindings) and set(group['sheet_ids'])<=known_frames and bool(physical) and physical<=covered
        status='verified_unchanged_envelope' if unchanged else 'verified_native_2d_packaging' if verified else 'unresolved_packaging'
        result.append(dict(product_code=group['product_code'],sheet_ids=group['sheet_ids'],status=status,bindings=bindings,
            projected_face_bindings=[{k:p[k] for k in ('source_root','target_root','part_code','source_dimension_ref','source_hash','sheet_ids','target_refs','matrix','hole_count','face_count','target_outline_ref','status')}
                for p in projections if p['part_code'] in group['product_part_codes']+group['package_codes']],
            reason='Đường bao sản phẩm giữ nguyên; giữ thùng và lớp đệm nguồn.' if unchanged else
            'Đã kiểm tra khe hở từng đầu, hình thùng và BOM trong các khung native 2D.' if verified else
            'Cần gắn hướng đặt sản phẩm, kích thước lòng thùng, lớp đệm/lót góc và các hình đóng gói với nguồn trước khi duyệt backup đầy đủ.'))
    from graph.packing_envelopes import inspect as inspect_envelopes
    envelopes=inspect_envelopes(context)
    for item in result:
        item['confirmed_length_bindings']=[p for p in audit.get('confirmed_length_bindings',[]) if p['product_code']==item['product_code']]
        item['source_envelopes']=[e for e in envelopes if e['product_code']==item['product_code']]
        item['updated_envelopes']=[e for e in audit.get('envelope_bindings',[]) if e['product_code']==item['product_code']] if complete else []
    return result


def require_complete(plan,context):
    validate(plan,context)
    unresolved=[r for r in review(plan,context) if r['status']=='unresolved_packaging']
    if unresolved:raise ValueError('Chưa đồng bộ đầy đủ đóng gói ở khung '+', '.join(sorted({s for r in unresolved for s in r['sheet_ids']}))+'. Thùng, lớp đệm và hướng đóng gói cần được kiểm chứng theo sản phẩm sau sửa.')
