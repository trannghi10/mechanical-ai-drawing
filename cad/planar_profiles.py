"""Numeric, source-bound planar profiles for an independent OCC face check."""
import copy
import json
import math
from cad.curved_profiles import primitives,edge_points,arc_point,angle,sweep
from cad.frame_geometry import world


def checks(plan,context):
    recipes=list(getattr(plan,'resize_recipes',[]))+list(getattr(plan,'curved_wall_recipes',[]))+list(getattr(plan,'hole_recipes',[]))
    if not recipes:return []
    by={e['ref']:e for e in context['entities']}
    operations={o.ref:o for o in plan.operations if o.action=='replace_geometry'}
    checked=set();result=[]
    for recipe in recipes:
        hole_refs=getattr(recipe,'hole_refs',[])
        key=(recipe.part_code,tuple(sorted(recipe.outline_refs)),tuple(sorted(hole_refs)))
        if key in checked:continue
        checked.add(key)
        is_hole=hasattr(recipe,'circle_ref')
        is_wall=not hasattr(recipe,'dimension_ref') and not is_hole
        dimension=world(by[recipe.measurement_dimension_ref if is_hole else recipe.dimension_ref]) if not is_wall else {}
        factor=abs(dimension.get('linear_factor',1))
        if not math.isfinite(factor) or factor<=0:raise ValueError('Thiếu tỷ lệ đo thật để kiểm tra mặt CAD')
        def numeric(after,selected_holes=hole_refs):
            outlines=[];holes=[]
            for ref in recipe.outline_refs+list(selected_holes):
                record=copy.deepcopy(by[ref])
                if after and ref in operations:record['geometry']=json.loads(operations[ref].after)
                record=world(record)
                if ref in hole_refs:
                    g=record['geometry'];holes.append(dict(center=g['center'],radius=g['radius']))
                else:outlines.extend(primitives(record))
            if not outlines:raise ValueError('Thiếu đường bao CAD cho kiểm tra mặt độc lập')
            points=[p for edge in outlines for p in edge_points(edge)]
            origin=[(min(p[i] for p in points)+max(p[i] for p in points))/2 for i in (0,1)]
            def p(q):return [(q[i]-origin[i])*factor for i in (0,1)]
            segments=[]
            for e in outlines:
                if e['kind']=='line':segments.append(['LINE',p(e['start']),p(e['end']),None,None])
                elif e['kind']=='nurbs':
                    segments.append(['NURBS',p(e['start']),p(e['end']),None,None,
                        dict(degree=e['degree'],poles=[p(q) for q in e['control_points']],weights=e['weights'])])
                else:
                    midpoint=arc_point(e,angle(e,e['start'])+(1 if e['ccw'] else -1)*sweep(e)/2)
                    segments.append(['ARC',p(e['start']),p(e['end']),p(e['center']),e['radius']*factor,p(midpoint)])
            return dict(segments=segments,holes=[dict(center=p(h['center']),radius=h['radius']*factor) for h in holes])
        from cad.parametric import stepped_hole_pair
        # A countersink has two projected rings at different depths, not two
        # through holes in one face. Verify each projected aperture against
        # the exact outline independently; the resize kernel separately
        # proves nesting and preserved ring offsets from the native DIM.
        world_by={ref:world(e) for ref,e in by.items() if e['type'] in ('CIRCLE','DIMENSION') and
            (e.get('geometry') or e.get('radial_geometry')) and e.get('layout')==by[recipe.outline_refs[0]].get('layout')}
        # Group holes by center to detect stepped / countersink rings (e.g. concentric circles in 2D projection)
        groups={}
        for href in hole_refs:
            g=world_by.get(href,{}).get('geometry')
            if not g:continue
            c_key=None
            for c in groups:
                if math.hypot(c[0]-g['center'][0],c[1]-g['center'][1])<1e-4:
                    c_key=c;break
            if c_key is None:
                c_key=(round(g['center'][0],4),round(g['center'][1],4))
                groups[c_key]=[]
            groups[c_key].append(href)
        stepped=any(len(g)>1 for g in groups.values())
        if stepped:
            for c in groups:
                groups[c].sort(key=lambda href:world_by[href]['geometry']['radius'])
            max_rings=max(len(g) for g in groups.values())
            passes=[[groups[c][k] for c in groups if k<len(groups[c])] for k in range(max_rings)]
        else:
            max_rings=1
            passes=[hole_refs]
        for selected in passes:
            result.append(dict(part_code=recipe.part_code,scope='source_stepped_hole_projection' if stepped else 'source_hole_resize' if is_hole else 'source_curved_wall_section' if is_wall else 'source_measured_planar_profile',mode='planar',
                before=numeric(False,selected),after=numeric(True,selected),
                **(dict(projection_only=True,source_ring_count=max_rings) if stepped else {})))
    return result
