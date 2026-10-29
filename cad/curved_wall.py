"""Change a source-closed concentric curved strip, keeping its outer boundary.

The inner arc ends stay on their measured cut planes. Parallel straight legs
and their cap endpoints follow the new analytic intersections. This does not
calculate bend allowance, developed blank length or an assembly fit.
"""
import copy
import json
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict
from cad.geometry import near
from cad.curved_profiles import profile_from, primitives, distance, contains_angle
from cad.edit_engine import Operation


class CurvedWallResize(BaseModel):
    model_config=ConfigDict(extra='forbid')
    part_code:str
    outer_arc_ref:str
    inner_arc_ref:str
    outline_refs:list[str]
    new_thickness:float
    anchor:Literal['outer']='outer'
    end_policy:Literal['source_cut_planes']='source_cut_planes'
    evidence_refs:list[str]


def resize(recipe,context):
    if context.get('units')!=4:raise ValueError('Mặt cắt cong cần đơn vị mm')
    by={e['ref']:e for e in context['entities']};refs=recipe.outline_refs
    if len(refs) not in (4,8) or len(set(refs))!=len(refs) or not set(refs)<=by.keys():
        raise ValueError('Cần đường bao gồm hai cung và sáu đoạn nối nguồn')
    if not {recipe.outer_arc_ref,recipe.inner_arc_ref}<=set(refs) or not set(refs)<=set(recipe.evidence_refs) or not set(recipe.evidence_refs)<=by.keys():
        raise ValueError('Thiếu bằng chứng mặt cắt cong')
    items=[by[r] for r in refs]
    if any(e.get('review_only') for e in items):raise ValueError('Mặt cắt chưa mở đầy đủ')
    frames={(e.get('coordinate_frame'),e.get('layout')) for e in items}
    if len(frames)!=1:raise ValueError('Mặt cắt cong phải cùng frame/layout')
    if any(not e.get('geometry') for e in items):raise ValueError('Thiếu geometry mặt cắt')
    source=profile_from(items)
    outer,inner=by[recipe.outer_arc_ref],by[recipe.inner_arc_ref]
    if sum(e['type']=='ARC' for e in items)!=2 or outer['type']!='ARC' or inner['type']!='ARC' or any(e['type'] not in ('LINE','ARC') for e in items):
        raise ValueError('Mặt cắt cần đúng hai cung tròn đồng tâm')
    og,ig=outer['geometry'],inner['geometry'];old=og['radius']-ig['radius'];new=recipe.new_thickness
    if not near(og['center'],ig['center'],1e-5) or old<=0 or not math.isfinite(new) or not 0<new<og['radius'] or near(old,new):
        raise ValueError('Độ dày/bán kính hoặc tâm cung không hợp lệ')
    arc=primitives(inner)[0];after=copy.deepcopy(ig);after['radius']=og['radius']-new
    changes={};moving=[];used=set()
    if len(refs)==4:
        # A circular strip without straight legs has two source cap planes.
        # Intersect each unchanged cap line with the new inner circle.
        from ezdxf.math import Vec2
        for key in ('start','end'):
            point=arc[key]
            caps=[e for e in items if e['type']=='LINE' and any(near(e['geometry'][k],point,1e-5) for k in ('start','end'))]
            if len(caps)!=1 or caps[0]['ref'] in used:raise ValueError('Cung trong chưa có hai mặt cắt nguồn duy nhất')
            cap=caps[0];used.add(cap['ref']);g=cap['geometry'];a=Vec2(g['start']);v=Vec2(g['end'])-a
            if v.magnitude<1e-8:raise ValueError('Mép mặt cắt cong suy biến')
            center=Vec2(ig['center']);relative=a-center
            aa=v.dot(v);bb=2*relative.dot(v);cc=relative.dot(relative)-after['radius']**2
            disc=bb*bb-4*aa*cc
            if disc<=1e-10:raise ValueError('Mặt cắt không giao duy nhất với nhánh cung trong')
            choices=[a+v*((-bb+sign*math.sqrt(disc))/(2*aa)) for sign in (-1,1)]
            q=min(choices,key=lambda p:(p-Vec2(point)).magnitude)
            if abs((choices[0]-Vec2(point)).magnitude-(choices[1]-Vec2(point)).magnitude)<1e-6:
                raise ValueError('Hai nghiệm mặt cắt cong mơ hồ')
            q=[q.x,q.y,point[2]];updated=copy.deepcopy(g)
            field=next(k for k in ('start','end') if near(g[k],point,1e-5))
            updated[field]=q;changes[cap['ref']]=updated;moving.append((point,q))
            after[key+'_angle']=math.degrees(math.atan2(q[1]-ig['center'][1],q[0]-ig['center'][0]))%360
    for key in ('start','end'):
        if len(refs)==4:break
        point=arc[key]
        legs=[e for e in items if e['type']=='LINE' and any(near(e['geometry'][k],point,1e-5) for k in ('start','end'))]
        if len(legs)!=1 or legs[0]['ref'] in used:raise ValueError('Cung trong chưa có hai chân nối duy nhất')
        leg=legs[0];used.add(leg['ref']);g=leg['geometry']
        vector=[b-a for a,b in zip(g['start'],g['end'])]
        axes=[i for i in (0,1) if abs(vector[i])>1e-5]
        if len(axes)!=1:raise ValueError('Chân mặt cắt cần thẳng theo trục nguồn')
        along=axes[0];cross=1-along;center=ig['center']
        square=after['radius']**2-(point[along]-center[along])**2
        if square<=1e-10:raise ValueError('Độ dày mới làm mất giao điểm tại mặt cắt nguồn')
        q=list(point);q[cross]=center[cross]+math.copysign(math.sqrt(square),point[cross]-center[cross])
        angle=math.degrees(math.atan2(q[1]-center[1],q[0]-center[0]))%360
        after[key+'_angle']=angle
        shift=q[cross]-point[cross];updated=copy.deepcopy(g)
        for end in ('start','end'):
            updated[end][cross]+=shift
            moving.append((g[end],updated[end]))
        changes[leg['ref']]=updated
    changes[inner['ref']]=after
    # Caps must attach to each moved leg once and then to an unchanged outer
    # leg. No unbound line is stretched just because it is nearby.
    cap_refs=set()
    for e in items:
        if e['type']!='LINE' or e['ref'] in used:continue
        g=e['geometry'];updated=copy.deepcopy(g);count=0
        for key in ('start','end'):
            hits=[q for p,q in moving if near(g[key],p,1e-5)]
            if len(hits)>1:raise ValueError('Mép nối có binding trùng')
            if hits:updated[key]=hits[0];count+=1
        if count:
            if count!=1:raise ValueError('Mép nối không thuộc biên ngoài cố định')
            changes[e['ref']]=updated;cap_refs.add(e['ref'])
    if len(refs)==8 and len(cap_refs)!=2:raise ValueError('Thiếu hai mép đóng mặt cắt cong')
    actual=[dict(e,geometry=changes.get(e['ref'],e['geometry'])) for e in items]
    result=profile_from(actual)
    if not near(next(e['geometry'] for e in actual if e['ref']==outer['ref']),og):raise ValueError('Biên ngoài đã bị thay đổi')
    old_lines=[by[r] for r in used] if len(refs)==8 else []; frame,layout=next(iter(frames))

    def move_point(point):
        hits=[q for p,q in moving if near(point,p,1e-5)]
        if len(hits)>1 and any(not near(q,hits[0],1e-6) for q in hits):raise ValueError('Mép cong có chuyển động mâu thuẫn')
        if hits:return hits[0]
        shifts=[]
        for e in old_lines:
            edge=primitives(e)[0]
            if abs(point[2]-edge['start'][2])<1e-5 and distance(edge,point)<1e-5:
                a,b=e['geometry']['start'],changes[e['ref']]['start']
                shifts.append([y-x for x,y in zip(a,b)])
        if len(shifts)>1:raise ValueError('DIM mặt cắt gắn vào nhiều chân')
        if shifts:return [a+b for a,b in zip(point,shifts[0])]
        if abs(point[2]-ig['center'][2])<1e-5 and distance(arc,point)<1e-5:
            return [a+(b-a)*after['radius']/ig['radius'] for a,b in zip(ig['center'],point)]
        return point

    for e in by.values():
        if (e.get('coordinate_frame'),e.get('layout'))!=(frame,layout) or e['type']!='DIMENSION':continue
        g=e.get('geometry');rad=e.get('radial_geometry')
        if g:
            points={k:move_point(g[k]) for k in ('defpoint2','defpoint3') if k in g}
            if any(not near(g[k],q) for k,q in points.items()):
                if e.get('dimension_type') not in (0,1) or g.get('text') not in ('','<>'):
                    raise ValueError('DIM gắn chân mặt cắt chưa hỗ trợ hoặc ghi đè số')
                changes[e['ref']]=dict(copy.deepcopy(g),**points,text='<>')
        elif rad and near(rad['defpoint'],ig['center'],1e-5) and abs(math.dist(rad['defpoint'],rad['defpoint4'])-ig['radius'])<1e-5:
            if rad.get('text') not in ('','<>'):raise ValueError('DIM bán kính trong ghi đè số')
            updated=copy.deepcopy(rad)
            updated['defpoint4']=[a+(b-a)*after['radius']/ig['radius'] for a,b in zip(rad['defpoint'],rad['defpoint4'])]
            if not contains_angle(primitives(dict(inner,geometry=after))[0],math.atan2(updated['defpoint4'][1]-ig['center'][1],updated['defpoint4'][0]-ig['center'][0])):
                raise ValueError('Mũi tên DIM bán kính ra ngoài cung mới')
            changes[e['ref']]=updated
    # References to a third unowned edge at a moving joint cannot be omitted.
    for e in by.values():
        if e['ref'] in refs or (e.get('coordinate_frame'),e.get('layout'))!=(frame,layout):continue
        g=e.get('geometry',{})
        anchors=[g[k] for k in ('start','end','center') if k in g]
        anchors += [[p[0],p[1],g['elevation']] for p in g.get('points',[])]
        if e['type'] in ('LINE','ARC','CIRCLE','LWPOLYLINE','POLYLINE','ELLIPSE','SPLINE') and any(near(p,old,1e-5) for p in anchors for old,_ in moving):
            raise ValueError('Có hình học khác tại mép cong chưa gán ownership: '+e['ref'])
    operations=[]
    for ref,updated in changes.items():
        before=by[ref].get('geometry') or by[ref].get('radial_geometry')
        if not near(before,updated):operations.append(Operation(ref=ref,action='replace_geometry',before=json.dumps(before),after=json.dumps(updated),xyz=[],
            reason='Giữ biên ngoài mặt cắt cong; sửa cung trong, chân/mép nối và DIM theo độ dày mới'))
    return operations,dict(before_thickness_mm=old,after_thickness_mm=new,outer_radius_mm=og['radius'],inner_radius_mm=after['radius'],
        closed_contour=True,bend_allowance='unresolved: no developed blank length inferred',outline_refs=refs)
