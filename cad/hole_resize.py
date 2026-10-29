"""Change one source-owned circular hole; retain center and reject lost clearance."""
import copy
import json
import math
from pydantic import BaseModel,ConfigDict
from cad.geometry import near
from cad.frame_geometry import world,local_geometry
from cad.edit_engine import Operation


class HoleResize(BaseModel):
    model_config=ConfigDict(extra='forbid')
    part_code:str
    circle_ref:str
    new_diameter_mm:float
    measurement_dimension_ref:str
    outline_refs:list[str]
    hole_refs:list[str]
    evidence_refs:list[str]


def resize(recipe,context):
    if context.get('units')!=4 or not math.isfinite(recipe.new_diameter_mm) or recipe.new_diameter_mm<=0:raise ValueError('Đường kính lỗ cần số mm dương')
    by={e['ref']:e for e in context['entities']}
    refs=recipe.outline_refs+recipe.hole_refs+[recipe.measurement_dimension_ref]
    if recipe.circle_ref not in recipe.hole_refs or not set(refs)<=set(recipe.evidence_refs)<=by.keys():raise ValueError('Thiếu bằng chứng nguồn của lỗ và phôi')
    if any(by[r].get('review_only') for r in refs):raise ValueError('Chưa mở đầy đủ hình học lỗ/phôi')
    matches=[f for f in context.get('source_features',{}).get('features',[]) if f.get('part_code')==recipe.part_code and
        f.get('ownership_proof')!='unverified' and set(f['refs'])==set(recipe.outline_refs) and any(d['ref']==recipe.measurement_dimension_ref for d in f['dimensions'])]
    if len(matches)!=1:raise ValueError('Lỗ chưa gắn duy nhất với đường bao có chủ sở hữu và DIM nguồn')
    from cad.dimensions import linear_axis
    dimension=world(by[recipe.measurement_dimension_ref]);linear_axis(dimension)
    factor=abs(dimension.get('linear_factor',1))
    if not math.isfinite(factor) or factor<=0:raise ValueError('Thiếu tỷ lệ đo của phôi')
    profile=[world(by[r]) for r in recipe.outline_refs]
    from cad.curved_profiles import profile_from,distance,primitives
    if matches[0]['kind']=='measured_straight_profile':
        from cad.closed_profiles import polygon_from
        polygon_from(profile)
        boundary=dict(edges=[edge for e in profile for edge in primitives(e)])
    else:boundary=profile_from(profile)
    from shapely.geometry import Polygon,Point
    polygon=Polygon([p[:2] for p in matches[0]['points']]);z=matches[0]['points'][0][2]
    holes=[]
    for r,e in by.items():
        if e['type']!='CIRCLE' or not e.get('geometry') or e.get('layout')!=dimension.get('layout'):continue
        try:g=world(e)['geometry']
        except ValueError:continue
        if abs(g['center'][2]-z)<1e-5 and polygon.contains(Point(g['center'][:2])):holes.append(r)
    if set(holes)!=set(recipe.hole_refs):raise ValueError('Recipe chưa chứa đủ lỗ trong phôi nguồn')
    circle=world(by[recipe.circle_ref]);old=circle['geometry'];new=copy.deepcopy(old);new['radius']=recipe.new_diameter_mm/(2*factor)
    if near(old['radius'],new['radius']):raise ValueError('Đường kính đích trùng nguồn')
    for state in (False,True):
        actual=[]
        for ref in recipe.hole_refs:
            g=new if state and ref==recipe.circle_ref else world(by[ref])['geometry']
            if not near(g['extrusion'],[0,0,1]) or g['radius']<=0 or min(distance(edge,g['center']) for edge in boundary['edges'])<=g['radius']+1e-5:
                raise ValueError('Lỗ chạm hoặc vượt đường bao phôi')
            for other in actual:
                if math.dist(g['center'],other['center'])<=g['radius']+other['radius']+1e-5:raise ValueError('Lỗ chạm hoặc chồng lỗ khác')
            actual.append(g)
    def operation(e,after):
        before=e.get('geometry') or e.get('radial_geometry')
        return Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(before),after=json.dumps(local_geometry(e,after)),xyz=[],reason='Đổi đường kính lỗ đo thật; giữ nguyên tâm và kiểm tra khoảng hở')
    operations=[operation(by[recipe.circle_ref],new)]
    # Radial DIMs are bound by their actual source center and arrow point.
    # Other diameter/annotation forms cannot be silently left unchanged.
    for e in by.values():
        if e['type']!='DIMENSION' or e.get('layout')!=dimension.get('layout'):continue
        measured_dimension=world(e);d=measured_dimension.get('radial_geometry')
        if not d:continue
        if e.get('dimension_type')==4 and near(d['defpoint'],old['center'],1e-5) and near(math.dist(d['defpoint'],d['defpoint4']),old['radius'],1e-5):
            if not near(abs(measured_dimension.get('linear_factor',1)),factor,1e-7):raise ValueError('Tỷ lệ DIM lỗ mâu thuẫn với DIM phôi')
            if d.get('text') not in ('','<>'):raise ValueError('DIM lỗ ghi đè số; cần liên kết chú thích nguồn')
            changed=copy.deepcopy(d);changed['defpoint4']=[a+(b-a)*new['radius']/old['radius'] for a,b in zip(old['center'],d['defpoint4'])]
            operations.append(operation(e,changed))
        elif e.get('dimension_type')==3 and near([(a+b)/2 for a,b in zip(d['defpoint'],d['defpoint4'])],old['center'],1e-5) and near(math.dist(d['defpoint'],d['defpoint4']),2*old['radius'],1e-5):
            if not near(abs(measured_dimension.get('linear_factor',1)),factor,1e-7):raise ValueError('Tỷ lệ DIM lỗ mâu thuẫn với DIM phôi')
            if d.get('text') not in ('','<>'):raise ValueError('DIM đường kính ghi đè số')
            changed=copy.deepcopy(d)
            for key in ('defpoint','defpoint4'):changed[key]=[a+(b-a)*new['radius']/old['radius'] for a,b in zip(old['center'],d[key])]
            operations.append(operation(e,changed))
    return operations
