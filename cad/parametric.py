"""Resize bound rectangular profiles and circular holes from measured dimensions."""
import copy
import json
import math
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict
from cad.edit_engine import Operation
from cad.geometry import near
from graph.fit_constraints import measurement


class LinearResize(BaseModel):
    model_config = ConfigDict(extra='ignore')
    part_code: str
    dimension_ref: str
    new_measurement: float | None
    outline_refs: list[str]
    hole_refs: list[str]
    anchor: Literal['first', 'second', 'center']
    evidence_refs: list[str]


def stepped_hole_pair(a,b,records,dimension_ref=None):
    """Recognize nested rings from a native stepped diameter DIM.

    %%C5-<> on an actual diameter 9 is evidence for one 5/9 countersink,
    whereas two coincident circles alone are not two noninterfering holes.
    """
    inner,outer=sorted([a,b],key=lambda g:g['radius']);small,large=inner['radius'],outer['radius']
    if small<=0 or math.dist(inner['center'],outer['center'])+small>=large-1e-6:return False
    for record in records.values():
        if dimension_ref is not None and record['ref']!=dimension_ref:continue
        g=record.get('radial_geometry',{})
        if record.get('type')!='DIMENSION' or record.get('dimension_type')!=3 or not g:continue
        match=re.fullmatch(r'%%[cC](\d+(?:[.,]\d+)?)\s*[-–]\s*<>',g.get('text',''))
        factor=abs(record.get('linear_factor',1))
        if not math.isfinite(factor) or factor<=0:continue
        # A magnified view's literal inner diameter is in measured units;
        # circle radii and native DIM endpoints are in its drawing frame.
        if not match or abs(float(match[1].replace(',','.'))-small*2*factor)>1e-5:continue
        center=[(p+q)/2 for p,q in zip(g['defpoint'],g['defpoint4'])]
        if near(center,outer['center'],1e-5) and abs(math.dist(g['defpoint'],g['defpoint4'])-large*2)<1e-5:return True
    return False


def resize(recipe, context, value):
    if context.get('units') != 4:
        raise ValueError('Sửa tham số hiện yêu cầu đơn vị mm đã xác định')
    records = {e['ref']: e for e in context['entities']}
    refs = recipe.outline_refs + recipe.hole_refs + [recipe.dimension_ref]
    annotations=[b for b in context.get('source_features',{}).get('leader_profile_bindings',[])
        if b.get('geometry_owner_verified') and b.get('part_codes')==[recipe.part_code] and len(b.get('candidates',[]))==1 and
        set(b['candidates'][0]['geometry_refs'])==set(recipe.outline_refs)]
    annotation_refs={p['ref'] for b in annotations for p in b.get('leader_endpoints',[])}
    if len(set(refs)) != len(refs) or not set(refs) <= records.keys():
        raise ValueError('Recipe chứa ref trùng hoặc ngoài phạm vi')
    if not set(recipe.evidence_refs) <= records.keys() or not set(refs) <= set(recipe.evidence_refs):
        raise ValueError('Recipe thiếu bằng chứng sở hữu profile, lỗ và kích thước')
    dimension = records[recipe.dimension_ref]
    frame = dimension.get('coordinate_frame')
    if not annotation_refs<=records.keys():raise ValueError('Leader đã gắn nguồn không còn trong phạm vi')
    if frame and any(records[ref].get('coordinate_frame')!=frame for ref in [*refs,*annotation_refs]):
        from cad.frame_geometry import world_scope,local_geometry
        normalized=world_scope(context,[*refs,*annotation_refs],recipe.outline_refs)
        operations=resize(recipe,normalized,value)
        for op in operations:
            original=records[op.ref]
            before=original.get('geometry') or original.get('radial_geometry')
            if before is None:raise ValueError('Thiếu snapshot native khi chuyển thao tác về frame nguồn')
            op.before=json.dumps(before);op.after=json.dumps(local_geometry(original,json.loads(op.after)))
        return operations
    if not frame or any(records[ref].get('coordinate_frame') != frame or records[ref].get('layout') != dimension.get('layout') for ref in refs):
        raise ValueError('Profile và kích thước phải nằm trong cùng frame/layout')
    g = dimension.get('geometry', {})
    from cad.dimensions import linear_axis
    axis = linear_axis(dimension)
    normal = [-axis[1], axis[0], 0.]
    def dot(point, vector): return sum(a*b for a,b in zip(point, vector))
    def uv(point): return dot(point, axis), dot(point, normal)
    outline = [records[ref] for ref in recipe.outline_refs]
    segments = []
    curved=any(e['type'] in ('ARC','SPLINE','ELLIPSE') or e['type'] in ('LWPOLYLINE','POLYLINE') and any(p[4] for p in e.get('geometry',{}).get('points',[])) for e in outline)
    curved_profile=None
    if curved:
        from cad.curved_profiles import profile_from,direction_points
        curved_profile=profile_from(outline)
        points=direction_points(curved_profile,axis)
    elif len(outline) == 1 and outline[0]['type'] in ('LWPOLYLINE','POLYLINE'):
        profile = outline[0]['geometry']
        if not profile['closed'] or len(profile['points']) < 4 or any(any(p[2:]) for p in profile['points']) or any(profile.get('default_widths',[])) or not near(profile['extrusion'], [0,0,1]):
            raise ValueError('Cần polyline đóng, thẳng và không có width/bulge')
        points = [[p[0],p[1],profile['elevation']] for p in profile['points']]
        segments = list(zip(points, points[1:] + points[:1]))
    elif len(outline) == 4 and all(e['type'] == 'LINE' for e in outline):
        segments = [(e['geometry']['start'], e['geometry']['end']) for e in outline]
    else:
        from cad.closed_profiles import polygon_from,segments as source_segments
        contour=polygon_from(outline)
        segments=[edge for e in outline for edge in source_segments(e)]
    if not curved:points = [point for edge in segments for point in edge]
    z = points[0][2]
    if any(abs(point[2]-z)>1e-6 for point in points) or any(abs(g[key][2]-z)>1e-6 for key in ('defpoint2','defpoint3')):
        raise ValueError('Profile và kích thước không đồng phẳng')
    us, vs = zip(*(uv(p) for p in points))
    low, high, bottom, top = min(us),max(us),min(vs),max(vs)
    if high-low < 1e-6 or top-bottom < 1e-6:
        raise ValueError('Profile suy biến')
    from cad.closed_profiles import polygon_from
    from shapely.geometry import Polygon,Point
    contour=curved_profile['points'] if curved else polygon_from(outline);polygon=Polygon([uv(p) for p in contour])
    if not polygon.is_valid or polygon.area<=1e-8:raise ValueError('Profile tự giao hoặc suy biến')
    for a,b in segments:
        a,b = tuple(round(v,6) for v in uv(a)),tuple(round(v,6) for v in uv(b))
        if a==b: raise ValueError('Profile suy biến')
        if a[0]!=b[0] and a[1]!=b[1] and not near(sorted([a[0],b[0]]),[low,high],1e-5):
            raise ValueError('Profile cần cạnh thẳng theo trục DIM; cung/chéo cần adapter riêng')
    p,q = dot(g['defpoint2'],axis),dot(g['defpoint3'],axis)
    if not near(sorted([p,q]),[low,high],1e-5):
        raise ValueError('Kích thước không đo đúng hai đầu profile')
    previous = measurement(dimension,g)
    factor = abs(dimension.get('linear_factor',1))
    if not math.isfinite(value) or value<=0 or factor<=0:
        raise ValueError('Kích thước hoặc DIMLFAC không hợp lệ')
    delta = (value-previous)/factor
    anchor = (p if recipe.anchor=='first' else q) if recipe.anchor!='center' else (low+high)/2
    low_delta = -delta/2 if recipe.anchor=='center' else -delta if abs(anchor-high)<1e-6 else 0.
    high_delta = delta/2 if recipe.anchor=='center' else delta if abs(anchor-low)<1e-6 else 0.
    middle = (low+high)/2
    def transform(point):
        # End-zone stretch preserves hole diameters and their nearest-end offset.
        u = dot(point,axis)
        shift = low_delta if u<middle-1e-6 else high_delta if u>middle+1e-6 else (low_delta+high_delta)/2
        return [a+shift*b for a,b in zip(point,axis)]
    after_outline=None;after_curve=None
    if curved:
        from cad.curved_profiles import stretch
        after_outline,after_curve=stretch(outline,curved_profile,transform,axis)
        after_polygon=Polygon([uv(p) for p in after_curve['points']])
    else:after_polygon=Polygon([uv(transform(p)) for p in contour])
    if not after_polygon.is_valid or after_polygon.area<=1e-8:raise ValueError('Profile sau sửa tự giao hoặc bị co mất rãnh')
    operations = []
    def add(record,after):
        before=record.get('geometry') or record.get('radial_geometry')
        if not near(before,after):
            operations.append(Operation(ref=record['ref'],action='replace_geometry',before=json.dumps(before),after=json.dumps(after),xyz=[],reason='Sửa profile theo kích thước đo thật; giữ hình dạng và khoảng cách lỗ tới đầu gần nhất'))
    for record in outline:
        if curved:
            updated=next(e for e in after_outline if e['ref']==record['ref'])
            add(record,updated['geometry'])
            continue
        after = copy.deepcopy(record['geometry'])
        if record['type']=='LINE':
            for key in ('start','end'):after[key]=transform(after[key])
        else:
            for point in after['points']:point[:2]=transform([point[0],point[1],after['elevation']])[:2]
        add(record,after)
    holes = []
    hole_sources=[records[ref].get('geometry',{}) for ref in recipe.hole_refs]
    hole_evidence={ref:e for ref,e in records.items() if e.get('layout')==dimension.get('layout') and e.get('coordinate_frame')==frame}
    grouped={}
    for i,a in enumerate(hole_sources):
        if 'center' not in a or 'radius' not in a:continue
        for j,b in enumerate(hole_sources[i+1:],i+1):
            if 'center' not in b or 'radius' not in b or not stepped_hole_pair(a,b,hole_evidence):continue
            inner=a if a['radius']<b['radius'] else b
            for k in (i,j):
                if k in grouped and not near(grouped[k],inner['center']):raise ValueError('Nhóm lỗ bậc có nhiều tâm dẫn chưa xác định')
                grouped[k]=inner['center']
    for i,ref in enumerate(recipe.hole_refs):
        record=records[ref];before=record.get('geometry',{})
        if record['type']!='CIRCLE' or not near(before.get('extrusion'),[0,0,1]) or abs(before['center'][2]-z)>1e-6:
            raise ValueError('Recipe lỗ hiện chỉ hỗ trợ CIRCLE đồng phẳng')
        after=copy.deepcopy(before)
        driver=grouped.get(i,before['center']);shift=[q-p for p,q in zip(driver,transform(driver))]
        after['center']=[p+d for p,d in zip(before['center'],shift)]
        for center,bounds in ((before['center'],(low,high,bottom,top)),(after['center'],(low+low_delta,high+high_delta,bottom,top))):
            u,v=uv(center);r=before['radius'];a,b,c,d=bounds
            if r<=0 or u-r<=a+1e-6 or u+r>=b-1e-6 or v-r<=c+1e-6 or v+r>=d-1e-6:
                raise ValueError('Lỗ chạm/vượt biên profile trước hoặc sau sửa')
        for point,shape in ((before['center'],polygon),(after['center'],after_polygon)):
            if not shape.contains(Point(uv(point))) or shape.boundary.distance(Point(uv(point)))<=before['radius']+1e-6:
                raise ValueError('Lỗ chạm/vượt rãnh hoặc biên profile')
        if curved:
            from cad.curved_profiles import distance
            for point,profile in ((before['center'],curved_profile),(after['center'],after_curve)):
                if min(distance(e,point) for e in profile['edges'])<=before['radius']+1e-5:
                    raise ValueError('Lỗ chạm/vượt cung của đường bao')
        holes.append(after);add(record,after)
    for i,a in enumerate(holes):
        for j,b in enumerate(holes[i+1:],i+1):
            # Both rings must still be concentric after the operation and
            # backed by the same unmodified native diameter annotation.
            if stepped_hole_pair(hole_sources[i],hole_sources[j],hole_evidence) and near(
                [p-q for p,q in zip(a['center'],b['center'])],
                [p-q for p,q in zip(hole_sources[i]['center'],hole_sources[j]['center'])],1e-6):continue
            if near(hole_sources[i]['center'],hole_sources[j]['center'],1e-5) and not near(hole_sources[i]['radius'],hole_sources[j]['radius'],1e-5):
                if near(a['center'],b['center'],1e-5):continue
            if math.dist(a['center'],b['center'])<=a['radius']+b['radius']+1e-6:
                raise ValueError('Các lỗ chồng lấn sau sửa')
    for record in records.values():
        g=record.get('radial_geometry')
        if record['type']!='DIMENSION' or not g or record.get('coordinate_frame')!=frame or record.get('layout')!=dimension.get('layout'):continue
        center=[(a+b)/2 for a,b in zip(g['defpoint'],g['defpoint4'])] if record.get('dimension_type')==3 else g['defpoint']
        radius=math.dist(g['defpoint'],g['defpoint4'])/(2 if record.get('dimension_type')==3 else 1)
        bound=[(records[ref]['geometry'],after) for ref,after in zip(recipe.hole_refs,holes)
               if near(center,records[ref]['geometry']['center'],1e-5) and
               abs(radius-records[ref]['geometry']['radius'])<1e-5]
        if curved:
            from cad.curved_profiles import distance
            after_edges={(e['ref'],e['segment_index']):e for e in after_curve['edges']}
            for before in curved_profile['edges']:
                if before['kind']!='arc':continue
                after=after_edges[(before['ref'],before['segment_index'])]
                if (near(g['defpoint'],before['center'],1e-5) and
                    abs(math.dist(g['defpoint'],g['defpoint4'])-before['radius'])<1e-5 and
                    distance(before,g['defpoint4'])<1e-5):bound.append((before,after))
        # A native rational SPLINE may represent one circle as several exact
        # Bezier spans. A radius DIM at their shared endpoint has one physical
        # binding when every candidate proves the same circle and motion.
        unique=[]
        for pair in bound:
            if not any(all(near(a['center'],b['center'],1e-5) and near(a['radius'],b['radius'],1e-5)
                           for a,b in zip(pair,other)) for other in unique):unique.append(pair)
        bound=unique
        if not bound:continue
        decorated=(
            ('<>' in g.get('text','')) or
            (record.get('dimension_type')==4 and re.fullmatch(r'[1-9]\d*\s*[xX×]\s*<>',g.get('text',''))) or (
            record.get('dimension_type')==3 and any(stepped_hole_pair(a,b,hole_evidence,record['ref']) for i,a in enumerate(hole_sources) for b in hole_sources[i+1:]) and
            re.fullmatch(r'%%[cC]\d+(?:[.,]\d+)?\s*[-–]\s*<>',g.get('text',''))))
        if len(bound)!=1 or (g.get('text') not in ('','<>') and not decorated):raise ValueError('DIM bán kính lỗ chưa có binding duy nhất hoặc đang ghi đè số')
        before,after=bound[0];shift=[b-a for a,b in zip(before['center'],after['center'])]
        updated=copy.deepcopy(g)
        for key in ('defpoint','defpoint4'):updated[key]=[v+d for v,d in zip(g[key],shift)]
        add(record,updated)
    # Reject omitted/unsupported geometry within this ownership region.
    allowed = set(recipe.outline_refs + recipe.hole_refs)
    stationary=context.get('stationary_hole_sections',{}).get(recipe.dimension_ref,{})
    allowed.update(stationary.get('refs',[]))
    from cad.reference_geometry import stationary_hole_marks, stationary_cross_axis
    allowed.update(stationary_hole_marks(records,hole_sources,transform))
    # Move only the source-bound arrow tip; the label and outside elbow stay
    # where the drafter placed them. Unbound/crossing lines remain rejected.
    for binding in annotations:
        for tip in binding.get('leader_endpoints',[]):
            record=records[tip['ref']];before=record.get('geometry',{})
            if record.get('coordinate_frame')!=frame or record.get('layout')!=dimension.get('layout'):
                raise ValueError('Leader và profile chưa cùng hệ tọa độ')
            vertices=before.get('vertices') if record['type']=='LEADER' else [before.get('start'),before.get('end')] if record['type']=='LINE' else None
            i=tip['vertex_index']
            if not vertices or not 0<=i<len(vertices):raise ValueError('Đầu mũi tên không còn đúng cấu trúc nguồn')
            # Index positions are in layout coordinates; compare to the native
            # point through its source transform even when all edits stay local.
            from cad.frame_geometry import matrix
            from ezdxf.math import Vec3
            layout_point=list(matrix(record).transform(Vec3(vertices[i])))
            if not near(layout_point,tip['point'],1e-5):raise ValueError('Đầu mũi tên đã khác bằng chứng nguồn')
            after=copy.deepcopy(before);moved=transform(vertices[i])
            if not after_polygon.contains(Point(uv(moved))):raise ValueError('Đầu mũi tên sau sửa rời khỏi vùng vật liệu')
            if record['type']=='LEADER':after['vertices'][i]=moved
            else:after['start' if i==0 else 'end']=moved
            add(record,after);allowed.add(record['ref'])
    # Full-span interior seams in a uniquely owned detail are bound to both
    # end planes. Move them with those planes; partial or crossing geometry
    # still requires an explicit adapter and cannot pass this check.
    from cad.profile_members import through_lines
    for record in through_lines(recipe,context,frame,polygon,axis,normal,low,high,z):
        after=copy.deepcopy(record['geometry'])
        for key in ('start','end'):after[key]=transform(after[key])
        add(record,after);allowed.add(record['ref'])
    allowed.update(ref for e in records.values() if e['type']=='INSERT' for ref in [e['ref']]
                   if any(child.startswith(ref+'/') for child in recipe.outline_refs+recipe.hole_refs))
    # Normalizing an external BOM arrow to layout space also exposes the
    # adjacent body at the driver's end plane. A separately owned complete
    # body with a proven face contact is not unclassified interior geometry.
    # The assembly solver still MUST compute/revalidate its ensuing motion.
    from graph.native_contacts import inventory as contact_inventory,profile_contact
    bodies=contact_inventory(context,allow_profiles=True)[1] if annotations else {}
    if annotations:
        from graph.flat_contacts import inventory as flat_inventory
        bodies={**bodies,**flat_inventory(context)[1]}
    drivers=[(root,f) for root,f in bodies.items() if set(f['refs'])==set(recipe.outline_refs) and f['part_code']==recipe.part_code]
    if len(drivers)==1:
        driver,body=drivers[0];driver_polygon=Polygon([p[:2] for p in body['points']])
        from cad.frame_geometry import matrix
        from ezdxf.math import Vec3
        source_frame=matrix(dimension);source_frame.inverse()
        def in_basis(points):
            local=[list(source_frame.transform(Vec3(p))) for p in points]
            return [[*uv(p),p[2]] for p in local]
        for root,neighbor in bodies.items():
            if root==driver or not set(body['sheet_ids']).intersection(neighbor['sheet_ids']):continue
            shape=Polygon([p[:2] for p in neighbor['points']])
            if profile_contact(in_basis(body['points']),in_basis(neighbor['points'])) is None or driver_polygon.intersection(shape).area>1e-10:continue
            allowed.update(ref for ref in records if ref==root or ref.startswith(root+'/'))
            allowed.update(neighbor.get('members',[]))
    for record in records.values():
        if record.get('coordinate_frame')!=frame or record.get('layout')!=dimension.get('layout') or record['ref'] in allowed or record['type'] not in ('LINE','LWPOLYLINE','POLYLINE','CIRCLE','ARC','ELLIPSE','SPLINE','INSERT'):
            continue
        from cad.curve_bounds import projected_simple_bounds
        bound=projected_simple_bounds(record,axis,normal)
        if bound and (bound[1]<low-1e-6 or bound[0]>high+1e-6 or bound[3]<bottom-1e-6 or
                      bound[2]>top+1e-6 or bound[5]<z-1e-6 or bound[4]>z+1e-6):
            continue
        layer_norm = str(record.get('layer', '') or record.get('dxf', {}).get('layer', '')).lower()
        is_center_or_ref = (
            record.get('reference_line') or
            any(w in layer_norm for w in ('center', 'tam', 'centre', 'truc', 'khung', 'title', 'ghi chu', 'text', 'defpoints')) or
            str(record.get('linetype', '')).lower().startswith('center')
        )
        if (value<previous and stationary_cross_axis(record,axis,low,high,bottom,top,z)) or is_center_or_ref:
            continue
        geom=record.get('geometry',{})
        anchors=[geom[k] for k in ('start','end','center') if k in geom]
        anchors += [[p[0],p[1],geom['elevation']] for p in geom.get('points',[])]
        anchors += geom.get('control_points',[]) + geom.get('fit_points',[])
        if record.get('position'):anchors.append(record['position'])
        if any(low-1e-6<=uv(a)[0]<=high+1e-6 and bottom-1e-6<=uv(a)[1]<=top+1e-6 and abs(a[2]-z)<1e-6 for a in anchors):
            raise ValueError('Có hình học chưa gán ownership trong profile: '+record['ref'])
        # Positive-weight control hulls and exact ellipse bounds also allow
        # rejection before Bezier decomposition/knot insertion. Large DWGs
        # contain thousands of remote logo vectors; they do not need a curve
        # solver for every edited gauge section. Fit-only/negative-weight or
        # unsupported curves retain the existing conservative rejection.
        from cad.curve_bounds import positive_control_hull
        bounded_curve=(record['type']=='SPLINE' and positive_control_hull(geom)) or (
            record['type']=='ELLIPSE' and 0<geom.get('ratio',0)<=1 and
            near(geom.get('extrusion',[0,0,1]),[0,0,1]) and abs(geom.get('major_axis',[0,0,1])[2])<1e-7)
        if bounded_curve:
            from backend.services.geometry_retrieval import local_bounds
            from itertools import product
            bound=local_bounds(record)
            if bound:
                corners=list(product(*zip(*bound)));us=[uv(p)[0] for p in corners];vs=[uv(p)[1] for p in corners]
                if (bound[1][2]<z-1e-6 or bound[0][2]>z+1e-6 or max(us)<low-1e-6 or min(us)>high+1e-6 or
                    max(vs)<bottom-1e-6 or min(vs)>top+1e-6):continue
        # A long edge can cross the part with both endpoints outside its
        # bounds. Endpoint-only checks would silently leave that edge behind.
        from cad.curved_profiles import primitives,intersections
        boundary=curved_profile['edges'] if curved else [dict(kind='line',start=a,end=b) for a,b in segments]
        edges=primitives(record)
        if record['type'] in ('SPLINE','ELLIPSE') and not edges:
            from backend.services.geometry_retrieval import local_bounds
            from itertools import product
            bounds=local_bounds(record)
            weights=geom.get('weights',[])
            if (bounds is None or record['type']=='SPLINE' and
                (not geom.get('control_points') or any(w<=0 for w in weights))):
                raise ValueError('Chưa định vị chắc chắn đường cong chưa gán ownership: '+record['ref'])
            corners=list(product(*zip(*bounds)));u=[uv(p)[0] for p in corners];v=[uv(p)[1] for p in corners]
            if (bounds[0][2]-1e-6<=z<=bounds[1][2]+1e-6 and min(u)<=high+1e-6 and max(u)>=low-1e-6
                and min(v)<=top+1e-6 and max(v)>=bottom-1e-6):
                raise ValueError('Đường cong chưa hỗ trợ có thể cắt profile; cần ownership: '+record['ref'])
        for edge in edges:
            if max(abs(edge[k][2]-z) for k in ('start','end'))>1e-6:continue
            for border in boundary:
                hit=intersections(edge,border)
                if hit is None or hit:
                    raise ValueError('Có nét cắt qua profile chưa gán ownership: '+record['ref'])
    # Sync every source dimension whose extension points bind to this profile.
    for record in records.values():
        before=record.get('geometry',{})
        if record['type']!='DIMENSION' or record.get('coordinate_frame')!=frame or record.get('layout')!=dimension.get('layout') or not before:
            continue
        association=record.get('dimension_association',{})
        linked=set(association.get('source_refs',[]))
        if linked and not linked.intersection(o.ref for o in operations):
            # Coordinates inside a silhouette do not own this DIM. A native
            # pointer to another, unchanged body takes precedence over proximity.
            continue
        if record.get('dimension_type')==2:
            from cad.angular_bindings import resize_bound_angle
            after=resize_bound_angle(before,polygon,uv,z,transform)
            if after:add(record,after)
            continue
        if record['ref'] in stationary.get('dimension_refs',[]):continue
        def inside(point):
            u,v=uv(point)
            return low-1e-6<=u<=high+1e-6 and bottom-1e-6<=v<=top+1e-6 and abs(point[2]-z)<1e-6
        inside_profile=all(inside(before[key]) for key in ('defpoint2','defpoint3'))
        after=copy.deepcopy(before)
        if inside_profile:
            for key in ('defpoint','defpoint2','defpoint3'):
                if key!='defpoint' and any(near(before[key],p,1e-5) for p in stationary.get('points',[])):continue
                after[key]=transform(before[key])
        from cad.dimension_associations import follow
        native=follow(record,before,after,records,operations)
        if not inside_profile and native is None:
            if record['ref']==recipe.dimension_ref:raise ValueError('Kích thước nguồn nằm ngoài profile')
            continue
        if near(before,native if native is not None else after):continue
        if before.get('text') not in ('','<>') or record.get('dimension_type',0) not in (0,1):
            raise ValueError('Kích thước gắn profile chưa hỗ trợ hoặc ghi đè số')
        if native is not None:after=native
        after['text']='<>';add(record,after)
    result=next((json.loads(op.after) for op in operations if op.ref==recipe.dimension_ref),g)
    if not math.isclose(measurement(dimension,result),value,rel_tol=0,abs_tol=1e-6):
        raise ValueError('Kích thước profile sau sửa không đạt yêu cầu')
    return operations
