"""Match a plate's edge view to its face through shared source end planes.

Requires one verified part, the same detail sheet, a rectangular section whose
width is bound to the BOM's thickness, and exact aligned end planes. Internal
measurement records exist only while running the kernel and are never written
to CAD or accepted from model input.
"""
import copy
import math
import re
from cad.geometry import near
from cad.measured_features import index,rectangle
from cad.frame_geometry import world
from cad.parametric import LinearResize


def augment(recipes,context,values):
    by={e['ref']:e for e in context['entities']}
    features=(context.get('source_features') or index(context,context.get('part_graph')))['features']
    virtuals={};additional=[];updated=dict(values);stationary={}
    for recipe in recipes:
        source=next((f for f in features if f.get('part_code')==recipe.part_code and set(f['refs'])==set(recipe.outline_refs) and
            f.get('ownership_proof')!='unverified' and any(d['ref']==recipe.dimension_ref for d in f['dimensions'])),None)
        if not source:continue
        from cad.dimensions import linear_axis
        dim=world(by[recipe.dimension_ref]);g=dim['geometry'];axis=linear_axis(dim)[:2];cross=[-axis[1],axis[0]]
        project=lambda p,v:sum(a*b for a,b in zip(p[:2],v))
        ends=sorted(project(g[k],axis) for k in ('defpoint2','defpoint3'))
        specs=[];nominal_axes=[]
        for table in by.values():
            if table.get('bom',{}).get('status')!='verified_template':continue
            for row in table['bom']['rows']:
                if row['part_code']!=recipe.part_code:continue
                match=re.search(r'(?<![\d.])(\d+(?:[.,]\d+)?)\s*[x×]',row.get('description',''))
                if match:specs.append(float(match[1].replace(',','.')))
                matches=re.findall(r'(?<![\d.])(\d+(?:[.,]\d+)?)(?=\s*(?:[x×]|mm\b))',row.get('description',''))
                nominal_axes.append([float(v.replace(',','.')) for v in matches])
        if not specs or not all(near(t,specs[0],1e-6) for t in specs):continue
        thickness=specs[0]
        if ends[1]-ends[0]<=thickness+1e-5:continue
        for target in features:
            if target is source or target.get('part_code')!=recipe.part_code or target.get('ownership_proof')=='unverified':continue
            if target['layout']!=source['layout'] or not set(target['sheet_ids'])&set(source['sheet_ids']) or not rectangle(target['points']):continue
            if set(target['refs'])==set(source['refs']):continue
            spans=[project(p,cross) for p in target['points']];axial=[project(p,axis) for p in target['points']]
            if not near([min(axial),max(axial)],ends,1e-5):continue
            width=max(spans)-min(spans)
            # A thin section is tied to stock thickness. A wider orthographic
            # view requires the common axial size to occur exactly once in
            # every verified physical specification (not a drawing label).
            thin=near(width,thickness,1e-5)
            if not thin and (not nominal_axes or any(sum(near(v,ends[1]-ends[0],1e-5) for v in dims)!=1 for dims in nominal_axes)):continue
            matching=[d for d in target['dimensions'] if near(d['measurement'],width,1e-5) and abs(sum(a*b for a,b in zip(d['axis'],cross)))>1-1e-7]
            if len(matching)!=1:continue
            # A receiving view already bound to this axis needs no synthetic
            # measurement. Its own real DIM must drive an explicit recipe.
            if any(abs(sum(a*b for a,b in zip(d['axis'],axis)))>1-1e-7 for d in target['dimensions']):continue
            ref='internal-section:'+recipe.dimension_ref+':'+','.join(target['refs'])
            synthetic=copy.deepcopy(dim);synthetic['ref']=ref
            # This is a calculation-only measurement in another view, not the
            # original native DIM. Its source body's DIMASSOC must not be copied.
            synthetic.pop('dimension_association',None)
            for key in ('defpoint2','defpoint3'):
                desired=project(g[key],axis)
                point=next(p for p in target['points'] if near(project(p,axis),desired,1e-5) and near(project(p,cross),min(spans),1e-5))
                synthetic['geometry'][key]=list(point)
            synthetic['frame_to_layout']=dim['frame_to_layout'];synthetic['coordinate_frame']='layout:'+str(dim['layout'])
            virtuals[ref]=synthetic;updated[ref]=values[recipe.dimension_ref]
            binding=stationary_hole_section(recipe,source,target,context,axis,cross,ends,spans)
            if binding:stationary[ref]=binding
            additional.append(LinearResize(part_code=recipe.part_code,dimension_ref=ref,new_measurement=values[recipe.dimension_ref],
                outline_refs=target['refs'],hole_refs=[],anchor=recipe.anchor,evidence_refs=sorted(set([ref]+target['evidence_refs']+source['evidence_refs']))))
    return additional,dict(context,entities=context['entities']+list(virtuals.values()),stationary_hole_sections=stationary),updated,set(virtuals)


def stationary_hole_section(recipe,source,target,context,axis,cross,ends,spans):
    """Bind a stationary drilled/countersunk section to measured face rings.

    Each ring needs a native side diameter DIM at the exact projected source
    circle limits. Only straight details whose endpoints lie on those limits
    are retained. Other geometry in the section is still rejected by resize.
    """
    if recipe.anchor!='center' or not recipe.hole_refs:return None
    records={e['ref']:world(e) for e in context['entities'] if e['type'] in ('LINE','CIRCLE','DIMENSION','INSERT') and
        (e.get('geometry') or e['type']=='INSERT') and set(e.get('source_sheet_ids',[]))&set(source['sheet_ids'])}
    rings=[records[r]['geometry'] for r in recipe.hole_refs]
    inner=min(rings,key=lambda g:g['radius']);project=lambda p,v:sum(a*b for a,b in zip(p[:2],v))
    center=project(inner['center'],axis)
    if not near(center,sum(ends)/2,1e-5):return None
    low,high=min(spans),max(spans);levels=[];dims=[];points=[]
    for ring in rings:
        expected=[project(ring['center'],axis)-ring['radius'],project(ring['center'],axis)+ring['radius']]
        matches=[]
        for e in records.values():
            if e['type']!='DIMENSION' or e.get('dimension_type') not in (0,1) or e.get('layout')!=source['layout']:continue
            g=e.get('geometry',{})
            if g.get('text')!='%%C<>' or not set(e.get('source_sheet_ids',[]))&set(target['sheet_ids']):continue
            from cad.dimensions import linear_axis
            # Diameter prefix leaves the measured placeholder intact; this
            # local normalization reads the direction without rewriting CAD.
            if abs(sum(a*b for a,b in zip(linear_axis(dict(e,geometry=dict(g,text='<>'))),axis)))<1-1e-7:continue
            from graph.fit_constraints import measurement
            if not near(measurement(e,g),ring['radius']*2,1e-5):continue
            ends_at=sorted(project(g[k],axis) for k in ('defpoint2','defpoint3'))
            across=[project(g[k],cross) for k in ('defpoint2','defpoint3')]
            if near(ends_at,expected,1e-5) and all(low-1e-5<=v<=high+1e-5 for v in across):matches.append(e)
        if len(matches)!=1:return None
        dims.append(matches[0]['ref']);levels.extend(expected)
        points.extend(matches[0]['geometry'][k] for k in ('defpoint2','defpoint3'))
    refs=[]
    for e in records.values():
        if e['type']!='LINE' or e['ref'] in target['refs'] or e.get('layout')!=source['layout']:continue
        if not set(e.get('source_sheet_ids',[]))&set(target['sheet_ids']):continue
        g=e['geometry'];ps=[g['start'],g['end']]
        if all(low-1e-5<=project(p,cross)<=high+1e-5 and abs(p[2]-inner['center'][2])<1e-5 and any(near(project(p,axis),v,1e-5) for v in levels) for p in ps):
            refs.append(e['ref']);points.extend(ps)
    # A single native centerline perpendicular to the section axis is a
    # stationary datum when its insertion is at the projected inner hole.
    for e in records.values():
        if e['type']!='INSERT' or e.get('layout')!=source['layout'] or e.get('attributes'):continue
        p=e.get('position');children=[r for r in records.values() if r['ref'].startswith(e['ref']+'/')]
        if not p or not near(project(p,axis),center,1e-5) or not near(project(p,cross),(low+high)/2,1e-5) or len(children)!=1:continue
        child=children[0];g=child.get('geometry',{});proof=child.get('reference_line',{})
        if child['type']!='LINE' or proof.get('kind')!='centerline' or not proof.get('simple'):continue
        if not all(near(project(g[k],axis),center,1e-5) for k in ('start','end')):continue
        if not near(project(g['start'],cross)+project(g['end'],cross),low+high,1e-5):continue
        refs.extend([e['ref'],child['ref']])
    return dict(refs=refs,dimension_refs=dims,points=points)
