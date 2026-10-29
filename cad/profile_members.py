"""Prove full-span interior lines of one source-owned detail profile."""
from cad.geometry import near


def through_lines(recipe,context,frame,polygon,axis,normal,low,high,z):
    features=context.get('source_features',{}).get('features',[])
    owned=[f for f in features if set(f['refs'])==set(recipe.outline_refs) and
           f.get('part_code')==recipe.part_code and
           f.get('ownership_proof') in ('unique_source_detail_sheet','native_part_identity','selected_native_instance','local_bom_leader_profile')]
    if len(owned)!=1:return []
    feature=owned[0];sheets=set(feature['sheet_ids']);result=[]
    from shapely.geometry import LineString
    def dot(p,v):return sum(a*b for a,b in zip(p,v))
    for e in context['entities']:
        if e['ref'] in recipe.outline_refs or e['type']!='LINE' or e.get('review_only'):continue
        if e.get('coordinate_frame')!=frame or e.get('layout')!=feature['layout']:continue
        if feature['ownership_proof'] in ('native_part_identity','selected_native_instance') or feature['ownership_proof']=='local_bom_leader_profile' and feature.get('instance_ref'):
            owner=feature.get('instance_ref')
            if not owner or not e['ref'].startswith(owner+'/'):continue
        elif not sheets or set(e.get('source_sheet_ids',[]))!=sheets:continue
        g=e.get('geometry',{});points=[g.get('start'),g.get('end')]
        if not all(points) or any(abs(p[2]-z)>1e-6 for p in points):continue
        u=[dot(p,axis) for p in points];v=[dot(p,normal) for p in points]
        if not near(sorted(u),[low,high],1e-5):continue
        line=LineString(list(zip(u,v)))
        if not polygon.buffer(1e-7).covers(line):continue
        # A coincident boundary is ambiguous duplicate geometry, not a seam.
        if polygon.boundary.buffer(1e-7).covers(line):continue
        result.append(e)
    return result
