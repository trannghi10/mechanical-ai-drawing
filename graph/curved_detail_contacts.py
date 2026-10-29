"""Bind clipped curve/leg gauge DIMs to executed source shell/cap recipes."""
import json,math,re
from bom.reader import normalized
from cad.geometry import near
from cad.frame_geometry import world,local_geometry
from cad.clipped_curved_detail import rebuild
from graph.confirmed_inner_panels import proofs as panel_proofs
from graph.native_instances import equivalent_operation

TOL=1e-4


def proofs(plan,context):
    if context.get('units')!=4:return []
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash'):return []
    corrections=[c for c in choices.get('confirmed_choices',[]) if c.get('key')=='assembly_tube_gauge_correction' and c.get('policy')=='use_verified_bom_wall_thickness']
    if not corrections:return []
    frames=panel_proofs(plan,context);by={e['ref']:e for e in context['entities']};result=[]
    for correction in corrections:
        eligible=[f for f in frames if f['product_code']==correction['product_code']]
        if len(eligible)!=1:continue
        frame=eligible[0]
        mates=[m for m in choices.get('confirmed_choices',[]) if m.get('key')=='panel_inner_mate' and m.get('panel_part_code')==frame['part_code'] and m.get('product_code')==frame['product_code']]
        if len(mates)!=1:continue
        walls=[r for r in plan.curved_wall_recipes if r.part_code==mates[0]['side_wall_part_code'] and len(r.outline_refs)==4]
        if len(walls)!=1:continue
        wall=walls[0];radius=by[wall.outer_arc_ref]['geometry']['radius'];old_gauge=radius-by[wall.inner_arc_ref]['geometry']['radius']
        sids=set(correction['sheet_ids']);items=[]
        for e in by.values():
            if e.get('review_only') or not sids.intersection(e.get('source_sheet_ids',[])) or not e.get('geometry'):continue
            try:items.append(world(e))
            except ValueError:continue
        dims=[d for d in items if d['type']=='DIMENSION' and d.get('dimension_type') in (0,1) and d['geometry'].get('text') in ('','<>')]
        for circle in [e for e in items if e['type']=='CIRCLE']:
            clip=circle['geometry'];near_dims=[d for d in dims if all(math.dist(d['geometry'][k][:2],clip['center'][:2])<clip['radius'] for k in ('defpoint2','defpoint3'))]
            for radial in near_dims:
                factor=radial.get('linear_factor',1)
                if not factor>0 or not near(radial.get('scaled_measurement'),old_gauge,TOL):continue
                g=radial['geometry'];arcs=[e for e in items if e['type']=='ARC' and near(e['geometry']['extrusion'],[0,0,1])]
                matches=[]
                for outer in arcs:
                    if not near(outer['geometry']['radius']*factor,radius,TOL):continue
                    for inner in arcs:
                        if not near(outer['geometry']['center'],inner['geometry']['center'],TOL) or not near((outer['geometry']['radius']-inner['geometry']['radius'])*factor,old_gauge,TOL):continue
                        pairs=[(a,b) for a,b in [('defpoint2','defpoint3'),('defpoint3','defpoint2')] if
                               near(math.dist(g[a],inner['geometry']['center']),inner['geometry']['radius'],TOL) and
                               near(math.dist(g[b],outer['geometry']['center']),outer['geometry']['radius'],TOL)]
                        if len(pairs)==1:matches.append((outer,inner))
                if len(matches)!=1:continue
                outer,inner=matches[0];tolvalues=set()
                for e in by.values():
                    if not sids.intersection(e.get('source_sheet_ids',[])):continue
                    text=normalized(e.get('text',''))
                    if not any(v in text for v in ('dung sai cac kich thuoc khac','general dimensional tolerance')):continue
                    m=re.search(r'(?:±|%%p)\s*(\d+(?:[.,]\d+)?)\s*mm',text)
                    if m:tolvalues.add(float(m[1].replace(',','.')))
                if len(tolvalues)!=1:continue
                tolerance=next(iter(tolvalues))/factor
                if not 0<tolerance<clip['radius']/20:continue
                leg_candidates=[d for d in near_dims if d['ref']!=radial['ref'] and near(d.get('linear_factor',1),factor,TOL) and
                    near(d.get('scaled_measurement'),frame['cap_before_mm'][1],TOL) and near(d['geometry']['defpoint2'][0],d['geometry']['defpoint3'][0],TOL)]
                if len(leg_candidates)!=1:continue
                leg_dim=leg_candidates[0];ylo,yhi=sorted(leg_dim['geometry'][k][1] for k in ('defpoint2','defpoint3'));x=leg_dim['geometry']['defpoint2'][0]
                def segment_at(y):
                    return [e for e in items if e['type']=='LINE' and near(e['geometry']['start'][1],y,TOL) and near(e['geometry']['end'][1],y,TOL)
                            and min(e['geometry'][k][0] for k in ('start','end'))-TOL<x<max(e['geometry'][k][0] for k in ('start','end'))+TOL
                            and all(math.dist(e['geometry'][k][:2],clip['center'][:2])<=clip['radius']+tolerance for k in ('start','end'))]
                low,high=segment_at(ylo),segment_at(yhi)
                if len(low)!=1 or len(high)!=1:continue
                lowrad=min(abs(math.dist(p,outer['geometry']['center'])-outer['geometry']['radius']) for p in low[0]['geometry'].values())
                hirad=min(abs(math.dist(p,outer['geometry']['center'])-outer['geometry']['radius']) for p in high[0]['geometry'].values())
                if abs(lowrad-hirad)<=TOL:continue
                outer_leg,inner_leg=(low[0],high[0]) if lowrad<hirad else (high[0],low[0])
                connectors=[e for e in items if e['type']=='LINE' and near(e['geometry']['start'][0],e['geometry']['end'][0],TOL)
                    and near(sorted(e['geometry'][k][1] for k in ('start','end')),[ylo,yhi],TOL)
                    and any(near(e['geometry']['start'][0],inner_leg['geometry'][k][0],TOL) for k in ('start','end'))]
                if len(connectors)!=1:continue
                objects=dict(outer=outer,inner=inner,outer_leg=outer_leg,inner_leg=inner_leg,connector=connectors[0],clip=circle,radial_dim=radial,leg_dim=leg_dim)
                changes,audit=rebuild(**{k:e['geometry'] for k,e in objects.items()},new_wall_mm=wall.new_thickness,new_leg_mm=frame['cap_after_mm'][1],factor=factor,tolerance=tolerance)
                bindings=dict(inner_arc=inner['ref'],inner_leg=inner_leg['ref'],connector=connectors[0]['ref'],radial_dimension=radial['ref'],leg_dimension=leg_dim['ref'])
                result.append(dict(status='verified_clipped_curved_gauges',sheet_ids=sorted(sids.intersection(circle['source_sheet_ids'])),part_code=wall.part_code,
                    circle_ref=circle['ref'],outer_arc_ref=outer['ref'],outer_leg_ref=outer_leg['ref'],bindings=bindings,
                    source_shell_refs=wall.outline_refs,changes=changes,audit=audit))
    refs=[p['bindings']['inner_arc'] for p in result]
    if len(set(refs))!=len(refs):raise ValueError('Detail cong có nhiều liên kết nguồn mâu thuẫn')
    return result


def expected_operations(proof,context):
    from cad.edit_engine import Operation
    by={e['ref']:e for e in context['entities']};result=[]
    for key,after in proof['changes'].items():
        ref=proof['bindings'][key];record=by[ref];local=local_geometry(record,after)
        if not near(record['geometry'],local,1e-7):result.append(Operation(ref=ref,action='replace_geometry',before=json.dumps(record['geometry']),after=json.dumps(local),xyz=[],reason='Detail cong: giữ biên ngoài/chân/vòng trích, tái tính cung trong và giao điểm theo DIM vật liệu'))
    return result


def synchronize(plan,context):
    from backend.services.change_service import EditProposal
    result=plan.model_copy(deep=True);actual={o.ref:o for o in result.operations}
    for proof in proofs(plan,context):
        for op in expected_operations(proof,context):
            if op.ref in actual and not equivalent_operation(op,actual[op.ref]):raise ValueError('Detail cong có thao tác xung đột: '+op.ref)
            if op.ref not in actual:result.operations.append(op);actual[op.ref]=op
            result.edits=[e for e in result.edits if e.entity_ref!=op.ref]
            result.edits.append(EditProposal(entity_ref=op.ref,part_number=proof['part_code'],purpose='geometry',before=op.before,after=op.after,reason=op.reason))
    return result


def validate(plan,context):
    actual={o.ref:o for o in plan.operations}
    verified=proofs(plan,context)
    for proof in verified:
        for expected in expected_operations(proof,context):
            if expected.ref not in actual or not equivalent_operation(expected,actual[expected.ref]):raise ValueError('Thiếu/sai thao tác Detail cong: '+expected.ref)
    return verified
