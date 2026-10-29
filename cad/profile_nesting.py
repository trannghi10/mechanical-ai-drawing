"""Conservative, source-bounded packing of static rounded plate instances.

Keeps source rotations/mirrors, stock and all margins. Uses the largest measured
adjacent source clearance so paired/mirrored cuts do not lose their clearance.
No new instances or unverified interlocking/nesting optimizations are invented.
"""
import json,math
from collections import defaultdict
from pydantic import BaseModel,ConfigDict
from ezdxf.math import Matrix44
from cad.geometry import near
from cad.edit_engine import Operation
from cad.rounded_profile import inspect,resize,TOL


class ProfilePacking(BaseModel):
    model_config=ConfigDict(extra='forbid')
    part_code:str
    sheet_id:str
    stock_dimension_refs:list[str]
    instance_refs:list[str]
    count_text_ref:str
    old_size:list[float]
    new_size:list[float]
    new_radius:float|None=None


def _box(profile,matrix):
    lo,bt,hi,tp=profile.bbox
    ps=[matrix.transform([x,y,0]) for x in (lo,hi) for y in (bt,tp)]
    return [min(p.x for p in ps),min(p.y for p in ps),max(p.x for p in ps),max(p.y for p in ps)]


def _signature(profile):
    lo,bt,hi,tp=profile.bbox
    return (tuple(sorted((x,y,round(r,5)) for (x,y),r in profile.corners.items())),
            tuple(sorted((round(h['geometry']['center'][0]-lo,5),round(h['geometry']['center'][1]-bt,5),round(h['geometry']['radius'],5)) for h in profile.holes)))


def _nonoverlap(boxes,gap):
    # Spatial buckets bound the comparison count for thousands of cut pieces.
    cell=max(max(b[2]-b[0],b[3]-b[1]) for b in boxes)+gap;grid=defaultdict(list)
    for b in boxes:
        key=(math.floor(b[0]/cell),math.floor(b[1]/cell))
        for x in range(key[0]-1,key[0]+2):
            for y in range(key[1]-1,key[1]+2):
                for a in grid.get((x,y),[]):
                    if not (a[2]+gap<=b[0]+TOL or b[2]+gap<=a[0]+TOL or a[3]+gap<=b[1]+TOL or b[3]+gap<=a[1]+TOL):
                        raise ValueError('Phôi chồng lấn hoặc mất khoảng cách cắt')
        grid[key].append(b)


def pack_profiles(recipe,context):
    if context.get('units')!=4:raise ValueError('Bản cắt cần đơn vị mm')
    by={e['ref']:e for e in context['entities']}
    sheet=next((t for t in context['targets'] if t['id']==recipe.sheet_id),None)
    if not sheet or recipe.part_code not in sheet.get('texts',[]):raise ValueError('Bản cắt chưa thuộc đúng mã chi tiết')
    if len(recipe.instance_refs)!=len(set(recipe.instance_refs)) or not recipe.instance_refs:raise ValueError('Danh sách phôi trùng/rỗng')
    if len(recipe.old_size)!=2 or len(recipe.new_size)!=2 or any(not math.isfinite(v) or v<=0 for v in recipe.old_size+recipe.new_size):raise ValueError('Kích thước phôi không hợp lệ')
    dims=[by.get(r,{}) for r in recipe.stock_dimension_refs]
    if len(dims)!=2 or {d.get('geometry',{}).get('angle',-1)%180 for d in dims}!={0,90}:raise ValueError('Thiếu cặp DIMENSION đo tấm nguồn')
    for d in dims:
        if d.get('type')!='DIMENSION' or d.get('linear_factor',1)!=1 or d.get('dimension_type',0)!=0 or d['geometry']['text'] not in ('','<>'):raise ValueError('Kích thước tấm cần đo thật')
    dx=next(d for d in dims if d['geometry']['angle']%180==0);dy=next(d for d in dims if d['geometry']['angle']%180==90)
    xs=sorted(dx['geometry'][k][0] for k in ('defpoint2','defpoint3'));ys=sorted(dy['geometry'][k][1] for k in ('defpoint2','defpoint3'));stock=[*xs[:1],*ys[:1],xs[1],ys[1]]
    boundary=[]
    for e in context['entities']:
        if e['type'] not in ('LWPOLYLINE','POLYLINE') or '/' in e['ref'] or recipe.sheet_id not in e.get('source_sheet_ids',[recipe.sheet_id]):continue
        try:p=inspect([e])
        except ValueError:continue
        if not p.corners and near(p.bbox,stock,TOL):boundary.append(e)
    if len(boundary)!=1:raise ValueError('Chưa chứng minh đường bao tấm theo cặp kích thước')
    children=defaultdict(list)
    for e in context['entities']:
        if '/' in e['ref']:children[e['ref'].rsplit('/',1)[0]].append(e)
    groups=defaultdict(list);signature=None;all_boxes=[]
    for ref in recipe.instance_refs:
        root=by.get(ref,{})
        if root.get('type')!='INSERT' or '/' in ref or root.get('rotation',0)%90 or not near([abs(v) for v in root.get('scale',[])],[1,1,1]):raise ValueError('Phôi cần block tĩnh theo trục, scale ±1')
        rs=children[ref];outline=[e for e in rs if e['type'] in ('LINE','ARC','LWPOLYLINE','POLYLINE')];holes=[e for e in rs if e['type']=='CIRCLE']
        if len(outline)+len(holes)!=len(rs):raise ValueError('Block phôi có nội dung chưa hỗ trợ')
        profile=inspect(outline,holes)
        if not near([profile.bbox[2]-profile.bbox[0],profile.bbox[3]-profile.bbox[1]],recipe.old_size,TOL):raise ValueError('Template phôi không khớp quy cách đo nguồn')
        key=_signature(profile)
        if signature is None:signature=key
        if key!=signature:raise ValueError('Phôi không đồng nhất góc bo/lỗ')
        matrix=Matrix44([v for row in rs[0]['frame_to_layout'] for v in row])
        expected=Matrix44.scale(*root['scale'])*Matrix44.z_rotate(math.radians(root.get('rotation',0)))*Matrix44.translate(*root['position'])
        if not near(list(matrix),list(expected),TOL) or any(not near(e['frame_to_layout'],rs[0]['frame_to_layout'],TOL) for e in rs):raise ValueError('Hệ tọa độ block phôi không khớp layout')
        box=_box(profile,matrix)
        if box[0]<stock[0]-TOL or box[1]<stock[1]-TOL or box[2]>stock[2]+TOL or box[3]>stock[3]+TOL:raise ValueError('Phôi nguồn vượt tấm')
        all_boxes.append(box);orientation=root.get('rotation',0)%180==90
        groups[orientation].append((root,profile,matrix,box))
    _nonoverlap(all_boxes,0)
    # Derive clearances only between adjacent aligned members of each zone.
    gaps=[]
    for members in groups.values():
        for axis in (0,1):
            rows=defaultdict(list)
            for _,_,_,b in members:rows[round(b[1-axis],4)].append(b)
            for row in rows.values():
                row=sorted(row,key=lambda b:b[axis])
                gaps.extend(b[axis]-a[axis+2] for a,b in zip(row,row[1:]))
    if not gaps or min(gaps)<=TOL or max(gaps)>min(recipe.old_size):raise ValueError('Khoảng cách cắt nguồn chưa kiểm chứng')
    gap=max(gaps)
    minx=min(b[0] for b in all_boxes);miny=min(b[1] for b in all_boxes);maxx=max(b[2] for b in all_boxes);maxy=max(b[3] for b in all_boxes)
    main=max(groups,key=lambda k:len(groups[k]));order=[main]+[k for k in groups if k!=main]
    operations=[];new_boxes=[];right_start=minx
    for index,orientation in enumerate(order):
        w,h=recipe.new_size[::-1] if orientation else recipe.new_size
        available=maxx-right_start
        cols=max(0,math.floor((available+gap+TOL)/(w+gap)));rows=max(0,math.floor((maxy-miny+gap+TOL)/(h+gap)))
        targets=[(right_start+i*(w+gap),maxy-j*(h+gap)-h) for i in range(cols) for j in range(rows)]
        members=sorted(groups[orientation],key=lambda m:(round(m[3][0],4),-round(m[3][1],4),m[0]['ref']))
        for n,(root,profile,matrix,oldbox) in enumerate(members):
            if n>=len(targets):
                operations.append(Operation(ref=root['ref'],action='remove_insert',before=json.dumps({k:root[k] for k in ('name','position','scale','rotation')}),after='',xyz=[],reason='Bỏ phôi dư khi bố trí lại theo kích thước mới'));continue
            ops,after=resize(profile,recipe.new_size,recipe.new_radius);operations.extend(ops)
            altered=_box(after,matrix);x,y=targets[n];shift=[x-altered[0],y-altered[1],0]
            position=[a+b for a,b in zip(root['position'],shift)]
            if not near(position,root['position']):operations.append(Operation(ref=root['ref'],action='move_insert',before=json.dumps(root['position']),after='',xyz=position,reason='Xếp phôi trong tấm; giữ biên và khoảng cách cắt nguồn'))
            new_boxes.append([x,y,x+w,y+h])
        right_start+=cols*(w+gap)
    if not new_boxes:raise ValueError('Tấm không chứa được phôi mới')
    _nonoverlap(new_boxes,gap)
    if any(b[0]<minx-TOL or b[1]<miny-TOL or b[2]>maxx+TOL or b[3]>maxy+TOL for b in new_boxes):raise ValueError('Bố trí mới mất biên tấm')
    return operations,new_boxes,gap


def validate_profile_packs(operations,recipes,context):
    by={e['ref']:e for e in context['entities']};verified=set();slots=defaultdict(list)
    for op in operations:slots[(op.ref,op.action,op.cell_index)].append(op)
    for recipe in recipes:
        expected,boxes,gap=pack_profiles(recipe,context)
        for op in expected:
            found=slots[(op.ref,op.action,op.cell_index)]
            if len(found)!=1 or found[0]!=op:raise ValueError('Thao tác xếp profile thiếu, trùng hoặc khác quy tắc đo nguồn')
        verified.update(o.ref for o in expected if o.action=='remove_insert')
        count=by[recipe.count_text_ref].get('raw_text',by[recipe.count_text_ref].get('text',''))
        import re
        new=re.sub(r'(?<!\d)'+str(len(recipe.instance_refs))+r'(?=\s*pcs\b)',str(len(boxes)),count)
        if count==new and len(boxes)!=len(recipe.instance_refs):raise ValueError('Số lượng tấm không khớp nguồn')
        if count!=new and not any(o.ref==recipe.count_text_ref and o.action=='replace_text' and o.before==count and o.after==new for o in operations):raise ValueError('Thiếu cập nhật số lượng bản cắt profile')
    return verified
