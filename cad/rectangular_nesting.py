"""Repack a source-proven mixed rectangular grid on its original stock sheet."""
import copy
import json
import math
from collections import Counter,defaultdict
from ezdxf.math import Matrix44
from pydantic import BaseModel, ConfigDict
from cad.edit_engine import Operation
from cad.geometry import near


class CutPacking(BaseModel):
    model_config=ConfigDict(extra='forbid')
    part_code: str
    sheet_id: str
    stock_dimension_refs: list[str]
    instance_refs: list[str]
    count_text_ref: str
    old_width: float
    new_width: float
    length: float


def geometry_box(records, root, geometries=None):
    points=[]
    for e in records:
        if e['ref'].rsplit('/',1)[0]!=root or e['type']!='LINE':continue
        matrix=Matrix44([n for row in e['frame_to_layout'] for n in row])
        g=(geometries or {}).get(e['ref'],e['geometry'])
        points.extend(list(matrix.transform(g[k])) for k in ('start','end'))
    if len(points)!=8:raise ValueError('Bản cắt cần đúng bốn LINE tạo biên chữ nhật')
    return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]


def pack(recipe, context):
    records=context['entities'];by={e['ref']:e for e in records}
    children_by_root=defaultdict(list)
    for e in records:
        if '/' in e['ref']:children_by_root[e['ref'].rsplit('/',1)[0]].append(e)
    sheet=next((t for t in context['targets'] if t['id']==recipe.sheet_id),None)
    if context.get('units')!=4 or not sheet or recipe.part_code not in sheet.get('texts',[]):
        raise ValueError('Thiếu mã chi tiết/khung bản cắt và đơn vị mm')
    if len(set(recipe.instance_refs))!=len(recipe.instance_refs) or not recipe.instance_refs:
        raise ValueError('Danh sách instance bản cắt trùng/rỗng')
    roots=[by[ref] for ref in recipe.instance_refs]
    if any(e['type']!='INSERT' or '/' in e['ref'] or not near(e['scale'],[1,1,1]) or e['rotation'] not in (0,90) for e in roots):
        raise ValueError('Bản cắt chỉ hỗ trợ block tĩnh tỷ lệ 1, góc 0/90')
    # Previous revisions isolate shared blocks, so equal templates may have
    # different names. Geometry and drilling, rather than names, define identity.
    dims=[by[r] for r in recipe.stock_dimension_refs]
    if len(dims)!=2 or any(e['type']!='DIMENSION' or e.get('dimension_type')!=0 or e['geometry']['text'] not in ('','<>') or e.get('linear_factor')!=1 for e in dims):
        raise ValueError('Tấm gốc cần hai kích thước đo thật')
    xs=[e for e in dims if abs(e['geometry']['angle'])<1e-6];ys=[e for e in dims if abs(e['geometry']['angle']-90)<1e-6]
    if len(xs)!=1 or len(ys)!=1:raise ValueError('Thiếu hai trục kích thước tấm')
    gx,gy=xs[0]['geometry'],ys[0]['geometry']
    left,right=sorted(gx[k][0] for k in ('defpoint2','defpoint3'))
    bottom,top=sorted(gy[k][1] for k in ('defpoint2','defpoint3'))
    if not near(gx['defpoint2'][1],gx['defpoint3'][1]) or not near(gy['defpoint2'][0],gy['defpoint3'][0]):raise ValueError('Kích thước tấm không song song cạnh')
    expected={(left,top,right,top),(left,bottom,right,bottom),(left,bottom,left,top),(right,bottom,right,top)}
    polylines=[e for e in records if e['type']=='LWPOLYLINE' and '/' not in e['ref'] and e.get('geometry',{}).get('closed') and len(e['geometry']['points'])==4 and all(not any(p[2:]) for p in e['geometry']['points']) and near(e['geometry']['extrusion'],[0,0,1])]
    corners={(left,bottom),(left,top),(right,bottom),(right,top)}
    def stock_polyline(e):
        points=[p[:2] for p in e['geometry']['points']]
        if not all(any(near(p,corner) for corner in corners) for p in points) or len({tuple(p) for p in points})!=4:return False
        return all(near(a[0],b[0]) or near(a[1],b[1]) for a,b in zip(points,points[1:]+points[:1]))
    bound=any(stock_polyline(e) for e in polylines)
    for edge in ([] if bound else expected):
        if not any(e['type']=='LINE' and '/' not in e['ref'] and (near(e.get('geometry',{}).get('start',[])[:2],edge[:2]) and near(e.get('geometry',{}).get('end',[])[:2],edge[2:]) or near(e.get('geometry',{}).get('end',[])[:2],edge[:2]) and near(e.get('geometry',{}).get('start',[])[:2],edge[2:])) for e in records):
            raise ValueError('Không chứng minh được đường bao tấm theo DIMENSION')
    boxes={r['ref']:geometry_box(children_by_root[r['ref']],r['ref']) for r in roots}
    if any(b[0]<left or b[1]<bottom or b[2]>right or b[3]>top for b in boxes.values()):raise ValueError('Bản cắt nguồn vượt tấm')
    def group(rot):return sorted([r for r in roots if r['rotation']==rot],key=lambda r:(round(boxes[r['ref']][0],5),-round(boxes[r['ref']][3],5)))
    vertical,horizontal=group(0),group(90)
    if not vertical or not horizontal:raise ValueError('Chỉ hỗ trợ grid hai vùng 0/90 đã có trong nguồn')
    # Uniform source rows/columns prove the original cutting gap, not a model guess.
    xv=sorted({round(boxes[r['ref']][0],5) for r in vertical})
    yv=sorted({round(boxes[r['ref']][3],5) for r in vertical},reverse=True)
    xh=sorted({round(boxes[r['ref']][0],5) for r in horizontal})
    yh=sorted({round(boxes[r['ref']][3],5) for r in horizontal},reverse=True)
    gaps=[b-a-recipe.old_width for a,b in zip(xv,xv[1:])]+[a-b-recipe.length for a,b in zip(yv,yv[1:])]+[b-a-recipe.length for a,b in zip(xh,xh[1:])]+[a-b-recipe.old_width for a,b in zip(yh,yh[1:])]
    if not gaps or min(gaps)<=0 or max(gaps)-min(gaps)>1e-4:raise ValueError('Khoảng cách cắt nguồn không đồng nhất')
    gap=round(sum(gaps)/len(gaps),5)
    if len(vertical)!=len(xv)*len(yv) or len(horizontal)!=len(xh)*len(yh):raise ValueError('Grid nguồn thiếu ô/trùng instance')
    drilling_profiles=[]
    for r in roots:
        b=boxes[r['ref']];w,h=b[2]-b[0],b[3]-b[1]
        if not near([w,h],[recipe.old_width,recipe.length] if r['rotation']==0 else [recipe.length,recipe.old_width],1e-5):raise ValueError('Template không khớp kích thước bas nguồn')
        children=[e for e in records if e['ref'].startswith(r['ref']+'/')]
        if Counter(e['type'] for e in children)['LINE']!=4 or any(e['type'] not in ('LINE','CIRCLE') for e in children):raise ValueError('Template bản cắt chứa hình học chưa hỗ trợ')
        lines=[e for e in children if e['type']=='LINE']
        xx=[e['geometry'][k][0] for e in lines for k in ('start','end')];yy=[e['geometry'][k][1] for e in lines for k in ('start','end')]
        l,h,bot,tp=min(xx),max(xx),min(yy),max(yy)
        expected_edges={tuple(sorted((a,b))) for a,b in [((l,bot),(h,bot)),((l,tp),(h,tp)),((l,bot),(l,tp)),((h,bot),(h,tp))]}
        actual_edges={tuple(sorted((tuple(e['geometry']['start'][:2]),tuple(e['geometry']['end'][:2])))) for e in lines}
        if actual_edges!=expected_edges:raise ValueError('Template bản cắt chưa có biên chữ nhật đóng')
        drilling_profiles.append(sorted([e['geometry']['center'][0]-l,tp-e['geometry']['center'][1],e['geometry']['radius']] for e in children if e['type']=='CIRCLE'))
    if any(not near(drilling_profiles[0],profile,1e-5) for profile in drilling_profiles[1:]):raise ValueError('Template bản cắt khác pattern lỗ')
    minx=min(b[0] for b in boxes.values());maxy=max(b[3] for b in boxes.values())
    margin_x=minx-left;margin_top=top-maxy
    margin_bottom=min(b[1] for b in boxes.values())-bottom
    old_expected=[(round(minx+i*(recipe.old_width+gap),5),round(maxy-j*(recipe.length+gap),5)) for i in range(len(xv)) for j in range(len(yv))]
    old_expected += [(round(minx+i*(recipe.length+gap),5),round(maxy-len(yv)*(recipe.length+gap)-j*(recipe.old_width+gap),5)) for i in range(len(xh)) for j in range(len(yh))]
    actual_positions=[(round(b[0],5),round(b[3],5)) for b in boxes.values()]
    if sorted(actual_positions)!=sorted(old_expected):raise ValueError('Bản cắt nguồn không khớp hai vùng grid liên tục')
    # Preserve at least the source top/left margins at both opposite sheet edges.
    free_w=right-left-2*margin_x;free_h=top-bottom-margin_top-min(margin_top,margin_bottom)
    if recipe.new_width<=0 or not math.isfinite(recipe.new_width):raise ValueError('Bề rộng mới không hợp lệ')
    rows=len(yv);cols=math.floor((free_w+gap)/(recipe.new_width+gap)+1e-8)
    used_h=rows*(recipe.length+gap)-gap
    cols_h=len(xh);rows_h=math.floor((free_h-used_h)/(recipe.new_width+gap)+1e-8)
    # A narrower profile fits the existing quantity. Keep that quantity and
    # reflow its spacing; adding production instances requires a separate rule.
    if recipe.new_width<recipe.old_width:cols=min(cols,len(xv));rows_h=min(rows_h,len(yh))
    if cols<=0 or rows_h<0 or cols*rows>len(vertical) or cols_h*rows_h>len(horizontal):raise ValueError('Bố trí mới cần thêm instance hoặc thay cấu trúc grid; chưa hỗ trợ')
    positions=[(0,minx+i*(recipe.new_width+gap),maxy-j*(recipe.length+gap)-recipe.length) for i in range(cols) for j in range(rows)]
    positions += [(90,minx+i*(recipe.length+gap),maxy-used_h-gap-j*(recipe.new_width+gap)-recipe.new_width) for i in range(cols_h) for j in range(rows_h)]
    operations=[];new_boxes=[]
    def operation(e,action,before,after='',xyz=None):
        operations.append(Operation(ref=e['ref'],action=action,before=json.dumps(before) if not isinstance(before,str) else before,after=json.dumps(after) if not isinstance(after,str) else after,xyz=xyz or [],reason='Xếp lại bas theo kích thước mới, giữ khoảng cách cắt và biên tấm nguồn'))
    for group_roots,targets in ((vertical,[p for p in positions if p[0]==0]),(horizontal,[p for p in positions if p[0]==90])):
        for index,r in enumerate(group_roots):
            if index>=len(targets):
                before={k:r[k] for k in ('name','position','scale','rotation')};operation(r,'remove_insert',before);continue
            altered={};children=children_by_root[r['ref']]
            lines=[e for e in children if e['type']=='LINE']
            lo=min(e['geometry'][k][0] for e in lines for k in ('start','end'));hi=max(e['geometry'][k][0] for e in lines for k in ('start','end'))
            if not near(hi-lo,recipe.old_width,1e-5):raise ValueError('Trục bề rộng template chưa xác định')
            delta=(recipe.new_width-recipe.old_width)/2
            for e in lines:
                after=copy.deepcopy(e['geometry'])
                for key in ('start','end'):
                    if near(after[key][0],lo):after[key][0]-=delta
                    elif near(after[key][0],hi):after[key][0]+=delta
                    else:raise ValueError('Template không tạo biên chữ nhật đóng')
                altered[e['ref']]=after;operation(e,'replace_geometry',e['geometry'],after)
            for e in children:
                if e['type']=='CIRCLE':
                    g=e['geometry'];x,y,z=g['center'];rad=g['radius']
                    ys0=[l['geometry'][k][1] for l in lines for k in ('start','end')]
                    if rad<=0 or not(lo-delta+rad<x<hi+delta-rad and min(ys0)+rad<y<max(ys0)-rad):raise ValueError('Lỗ bản cắt vượt biên bas mới')
            b=geometry_box(children,r['ref'],altered);_,x,y=targets[index];dx,dy=x-b[0],y-b[1]
            new_boxes.append([b[0]+dx,b[1]+dy,b[2]+dx,b[3]+dy])
            xyz=[r['position'][0]+dx,r['position'][1]+dy,r['position'][2]]
            if not near(xyz,r['position']):operation(r,'move_insert',r['position'],xyz=xyz)
    for i,a in enumerate(new_boxes):
        if a[0]<left+margin_x-1e-5 or a[1]<bottom-1e-5 or a[2]>right-margin_x+1e-5 or a[3]>top-margin_top+1e-5:raise ValueError('Bas mới vượt biên tấm')
        for b in new_boxes[i+1:]:
            if not (a[2]+gap<=b[0]+1e-5 or b[2]+gap<=a[0]+1e-5 or a[3]+gap<=b[1]+1e-5 or b[3]+gap<=a[1]+1e-5):raise ValueError('Bas bản cắt chồng lấn hoặc thiếu khoảng cách')
    return operations,new_boxes,gap


def validate_pack(operations,recipes,context,verified_removals=()):
    by={(o.ref,o.action):o for o in operations}
    removable=set(verified_removals)
    records={e['ref']:e for e in context['entities']}
    for recipe in recipes:
        expected,boxes,_=pack(recipe,context)
        for op in expected:
            actual=by.get((op.ref,op.action))
            if not actual or not near(actual.model_dump(),op.model_dump()):raise ValueError('Kế hoạch thiếu hoặc đổi thao tác xếp bas đã kiểm chứng')
            if op.action=='remove_insert':removable.add(op.ref)
        count=records[recipe.count_text_ref]
        import re
        raw=count.get('raw_text',count.get('text',''))
        pattern=r'(?<!\d)'+str(len(recipe.instance_refs))+r'(?=\s*pcs)'
        expected_text=re.sub(pattern,str(len(boxes)),raw)
        op=by.get((recipe.count_text_ref,'replace_text'))
        if expected_text!=raw and (not op or op.before!=raw or op.after!=expected_text):raise ValueError('Số lượng bas trên tấm chưa đồng bộ với hình học')
        if expected_text==raw and op and (op.before!=raw or op.after!=raw):raise ValueError('Số lượng bas không được đổi khi số instance giữ nguyên')
    if any(o.action=='remove_insert' and o.ref not in removable for o in operations):raise ValueError('Bỏ instance chỉ được dùng trong bản cắt đã kiểm chứng')
