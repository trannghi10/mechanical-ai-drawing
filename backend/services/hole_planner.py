"""Compile unambiguous left/right or single circular hole changes on new CAD."""
import re
from bom.reader import normalized
from cad.geometry import near
from cad.frame_geometry import world
from cad.hole_resize import HoleResize


def compile_plan(context,request,clarifications=None):
    text=normalized(request+' '+' '.join(c.get('answer','') for c in clarifications or []))
    m=re.search(r'duong kinh\s+lo\s*(?:(?:ben\s*)?(trai|phai)\s*)?(?:tu\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*)?(?:thanh|xuong|len|->|→)\s*(\d+(?:[.,]\d+)?)\s*mm',text)
    if not m or 'giu' not in text or not re.search(r'giu\s+(?:nguyen\s+)?tam',text) or context.get('units')!=4:return None
    if any(w in text for w in ('tat ca','toan bo','them lo','bo lo','di chuyen','ket cau','do day')):return None
    side,old,new=m.groups();old=float(old.replace(',','.')) if old else None;new=float(new.replace(',','.'))
    by={e['ref']:e for e in context['entities']};roots=set(context.get('root_target_ids',[]));candidates=[]
    from graph.part_graph import seed_codes
    requested_codes=seed_codes(context,request,context.get('part_graph'))
    from cad.measured_features import index
    features=(context.get('source_features') or index(context,context.get('part_graph')))['features']
    from shapely.geometry import Polygon,Point
    for f in features:
        if not f.get('part_code') or f.get('ownership_proof')=='unverified' or not f.get('dimensions'):continue
        if requested_codes and f['part_code'] not in requested_codes:continue
        if roots and not roots.intersection(f.get('sheet_ids',[])) and f.get('instance_ref') not in roots and not any(r.split('/')[0] in roots for r in f['refs']):continue
        polygon=Polygon([p[:2] for p in f['points']]);holes=[]
        d=f['dimensions'][0];factor=abs(world(by[d['ref']]).get('linear_factor',1))
        for e in context['entities']:
            if e['type']!='CIRCLE' or not e.get('geometry') or e.get('layout')!=f['layout']:continue
            try:g=world(e)['geometry']
            except ValueError:continue
            if abs(g['center'][2]-f['points'][0][2])<1e-5 and polygon.contains(Point(g['center'][:2])):holes.append((e['ref'],g))
        if not holes:continue
        selected=holes
        if side:
            x=(min if side=='trai' else max)(g['center'][0] for _,g in holes)
            selected=[(r,g) for r,g in holes if near(g['center'][0],x,1e-5)]
        if len(selected)!=1:continue
        ref,g=selected[0]
        if old is not None and not near(2*g['radius']*factor,old,1e-5):continue
        candidates.append(HoleResize(part_code=f['part_code'],circle_ref=ref,new_diameter_mm=new,measurement_dimension_ref=d['ref'],
            outline_refs=f['refs'],hole_refs=[r for r,_ in holes],evidence_refs=sorted(set(f['evidence_refs']+[r for r,_ in holes]))))
    if len(candidates)!=1:return None
    from backend.services.change_service import DrawingChangePlan
    plan=DrawingChangePlan(summary='Đổi đường kính lỗ; giữ tâm, kiểm tra phôi và các lỗ còn lại.',target_part=candidates[0].part_code,
        edits=[],dependencies=[],questions=[],warnings=[],hole_recipes=candidates)
    # A grouped hole specification needs a dedicated source binding; do not
    # replace every equal number in a material size to fake synchronization.
    owned={s for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==plan.target_part for s in n.get('detail_sheets',[])}
    pattern=r'lo\s*(?:%%c|[øØ⌀]|phi)|(?:[øØ⌀]|%%c)\s*\d'
    if any(e['type'] in ('TEXT','MTEXT') and (owned.intersection(e.get('source_sheet_ids',[])) or e['ref'].split('/')[0] in roots) and re.search(pattern,e.get('text',''),re.I) for e in context['entities']):return None
    if any(r.get('part_code')==plan.target_part and re.search(pattern,r.get('description',''),re.I) for e in context['entities'] for r in e.get('bom',{}).get('rows',[])):return None
    from backend.services.parametric_service import compile_recipes
    try:return compile_recipes(plan,context)
    except ValueError:return None
