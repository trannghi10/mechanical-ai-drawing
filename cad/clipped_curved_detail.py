"""Analytic reconstruction of a circular strip/straight leg inside a callout.

Keeps the exterior radius and foot; the inner arc and horizontal leg follow
their real gauge DIMs. Printed source tolerance bounds old trim residuals.
Never scales a sketch, screw, tube section or the circular callout itself.
"""
import copy,math
from cad.geometry import near


def circle_intersections(center,radius,clip):
    c=clip['center'];r=clip['radius'];dx,dy=c[0]-center[0],c[1]-center[1];d=math.hypot(dx,dy)
    if min(radius,r,d)<=0 or not all(math.isfinite(v) for v in (*center,radius,r,d)):
        raise ValueError('Tâm/bán kính vòng trích không hợp lệ')
    a=(radius*radius-r*r+d*d)/(2*d);h2=radius*radius-a*a
    if h2<=1e-10:raise ValueError('Cung không còn hai giao điểm với vòng trích')
    x,y=center[0]+a*dx/d,center[1]+a*dy/d;h=math.sqrt(h2)
    return [[x-h*dy/d,y+h*dx/d,center[2]],[x+h*dy/d,y-h*dx/d,center[2]]]


def nearest(points,source):
    ordered=sorted(points,key=lambda p:math.dist(p[:2],source[:2]))
    if len(ordered)<2 or abs(math.dist(ordered[0][:2],source[:2])-math.dist(ordered[1][:2],source[:2]))<1e-5:
        raise ValueError('Nhánh giao điểm vòng trích mơ hồ')
    return ordered[0]


def arc_point(g,key):
    a=math.radians(g[key+'_angle']);return [g['center'][0]+g['radius']*math.cos(a),g['center'][1]+g['radius']*math.sin(a),g['center'][2]]


def horizontal_intersections(center,radius,y):
    h2=radius*radius-(y-center[1])**2
    if h2<=1e-10:raise ValueError('Chân thẳng không còn giao cung trong')
    h=math.sqrt(h2);return [[center[0]-h,y,center[2]],[center[0]+h,y,center[2]]]


def rebuild(outer,inner,outer_leg,inner_leg,connector,clip,radial_dim,leg_dim,
            new_wall_mm,new_leg_mm,factor,tolerance):
    if not 0<factor or not math.isfinite(factor) or not 0<tolerance or not math.isfinite(tolerance):raise ValueError('Thiếu tỷ lệ/tolerance nguồn')
    if not near(outer['center'],inner['center'],1e-5) or not near(outer['extrusion'],[0,0,1]) or not near(inner['extrusion'],[0,0,1]):
        raise ValueError('Detail cần cung đồng tâm trong mặt phẳng')
    z=outer['center'][2]
    points=[clip['center']]+[g[k] for g in (outer_leg,inner_leg,connector) for k in ('start','end')]+[g[k] for g in (radial_dim,leg_dim) for k in ('defpoint2','defpoint3')]
    if not near(clip.get('extrusion',[0,0,1]),[0,0,1]) or any(not near(p[2],z,1e-5) for p in points):
        raise ValueError('Vòng trích, chân và DIM phải cùng mặt phẳng Detail')
    old_wall=outer['radius']-inner['radius'];new_radius=outer['radius']-new_wall_mm/factor
    if not 0<new_wall_mm/factor<outer['radius'] or not math.isfinite(new_radius) or not 0<new_leg_mm or not math.isfinite(new_leg_mm):
        raise ValueError('Độ dày Detail không hợp lệ')
    if not near(outer_leg['start'][1],outer_leg['end'][1],1e-5) or not near(inner_leg['start'][1],inner_leg['end'][1],1e-5):
        raise ValueError('Detail cần chân thẳng nằm ngang có DIM thật')
    if not near(connector['start'][0],connector['end'][0],1e-5):raise ValueError('Mép nối chân/cung cần đường đứng')
    y0=outer_leg['start'][1];y1=inner_leg['start'][1];sign=1 if y1>y0 else -1;ynew=y0+sign*new_leg_mm/factor
    if not near(abs(y1-y0),math.dist(leg_dim['defpoint2'],leg_dim['defpoint3']),1e-4) or not near(old_wall,math.dist(radial_dim['defpoint2'],radial_dim['defpoint3']),1e-4):
        raise ValueError('DIM Detail không đo đúng hai mặt vật liệu')
    inner_points=[radial_dim[k] for k in ('defpoint2','defpoint3') if abs(math.dist(radial_dim[k],inner['center'])-inner['radius'])<1e-5]
    if len(inner_points)!=1:raise ValueError('DIM radial chưa gắn đúng cung trong')
    outer_points=[radial_dim[k] for k in ('defpoint2','defpoint3') if abs(math.dist(radial_dim[k],outer['center'])-outer['radius'])<1e-5]
    if len(outer_points)!=1 or abs(math.dist(inner_points[0],outer_points[0])-old_wall)>1e-4:raise ValueError('Hai chân DIM không theo cùng tia bán kính')
    endpoints=[arc_point(inner,k) for k in ('start','end')]
    clip_keys=[k for k,p in zip(('start','end'),endpoints) if abs(math.dist(p[:2],clip['center'][:2])-clip['radius'])<=tolerance]
    if len(clip_keys)!=1:raise ValueError('Không gắn duy nhất đầu cung vào vòng trích')
    clip_key=clip_keys[0];join_key='start' if clip_key=='end' else 'end'
    # The source inner arc may be overdrawn into the band. Its actual join
    # is independently established by the native leg and vertical seam.
    leg_join_key=min(('start','end'),key=lambda k:abs(inner_leg[k][0]-connector['start'][0]))
    leg_clip_key='end' if leg_join_key=='start' else 'start';join0=inner_leg[leg_join_key]
    if abs(math.dist(join0,inner['center'])-inner['radius'])>tolerance or abs(join0[0]-connector['start'][0])>1e-5:
        raise ValueError('Chân Detail không chạm cung trong theo tolerance nguồn')
    if abs(math.dist(inner_leg[leg_clip_key][:2],clip['center'][:2])-clip['radius'])>tolerance:
        raise ValueError('Chân trong chưa cắt ở vòng trích')
    outer_join=nearest(horizontal_intersections(outer['center'],outer['radius'],y0),join0)
    if not any(near(p,outer_join,tolerance) for p in outer_leg.values() if isinstance(p,list)):
        raise ValueError('Biên ngoài chân không chạm cung ngoài')
    if not min(y0,y1)-tolerance<=endpoints[0 if join_key=='start' else 1][1]<=max(y0,y1)+tolerance:
        raise ValueError('Đầu cung nguồn không nằm trong dải chân đã đo')
    join=nearest(horizontal_intersections(inner['center'],new_radius,ynew),join0)
    clipped=nearest(circle_intersections(inner['center'],new_radius,clip),arc_point(inner,clip_key))
    leg_end=nearest(horizontal_intersections(clip['center'],clip['radius'],ynew),inner_leg[leg_clip_key])
    arc=copy.deepcopy(inner);arc['radius']=new_radius
    for k,p in ((join_key,join),(clip_key,clipped)):arc[k+'_angle']=math.degrees(math.atan2(p[1]-inner['center'][1],p[0]-inner['center'][0]))%360
    span=(arc['end_angle']-arc['start_angle'])%360
    oldspan=(inner['end_angle']-inner['start_angle'])%360
    if min(span,oldspan)<=1e-6 or max(span,oldspan)>=180 or abs(span-oldspan)>10:raise ValueError('Cung Detail đổi nhánh/hướng hoặc suy biến')
    line=copy.deepcopy(inner_leg);line[leg_join_key]=join;line[leg_clip_key]=leg_end
    seam=copy.deepcopy(connector)
    for k in ('start','end'):
        if near(seam[k][1],y1,1e-5):seam[k]=list(join)
        elif near(seam[k][1],y0,1e-5):seam[k]=[join[0],y0,seam[k][2]]
        else:raise ValueError('Mép nối không kết thúc tại hai chân đo được')
    rd=copy.deepcopy(radial_dim)
    for k in ('defpoint2','defpoint3'):
        p=radial_dim[k]
        if near(p,inner_points[0],1e-5):rd[k]=[inner['center'][i]+(p[i]-inner['center'][i])*new_radius/inner['radius'] for i in range(3)]
    ld=copy.deepcopy(leg_dim)
    for k in ('defpoint2','defpoint3'):
        if near(ld[k][1],y1,1e-4):ld[k][1]=ynew
        elif not near(ld[k][1],y0,1e-4):raise ValueError('DIM chân không gắn hai mặt')
    rd['text']=ld['text']='<>'
    if not near(arc_point(arc,join_key),join,1e-5) or abs(math.dist(clipped[:2],clip['center'][:2])-clip['radius'])>1e-5:
        raise ValueError('Giao điểm Detail sau sửa chưa đạt')
    return dict(inner_arc=arc,inner_leg=line,connector=seam,radial_dimension=rd,leg_dimension=ld),dict(
        source_wall_mm=old_wall*factor,target_wall_mm=new_wall_mm,source_leg_mm=abs(y1-y0)*factor,target_leg_mm=new_leg_mm,
        exterior_fixed=True,clip_fixed=True,inner_join=join,clip_join=clipped,
        policy='Source DIM-bound clipped strip. Analytic intersections prove these five entities only; other contact/assembly views remain separately gated.')
