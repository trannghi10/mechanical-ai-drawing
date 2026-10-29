"""Confirmed numeric design relationships, independent of file name/handles.

Only real DIMs on uniquely owned measured profiles can be bound. Confirmation
establishes a dimensional rule, not hidden 3D contact or assembly certification.
"""
import copy,json,math,re
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from graph.measurement_rules import MeasurementEquation,MeasurementTerm,solve,validate_equations
from graph.fit_constraints import measurement

class ParameterLink(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['equal_delta','wall_clearance']
    driver_ref:str=Field(min_length=1,max_length=256)
    receiver_ref:str=Field(min_length=1,max_length=256)
    outside_ref:str|None=Field(default=None,max_length=256)
    wall_count:Literal[1,2]=2
    driver_anchor:Literal['first','second','center']
    receiver_anchor:Literal['first','second','center']


def equation(link):
    values={link.driver_ref:1.,link.receiver_ref:-1.} if link.kind=='equal_delta' else {
        link.outside_ref:1.,link.driver_ref:-float(link.wall_count),link.receiver_ref:-1.}
    return MeasurementEquation(terms=[MeasurementTerm(dimension_ref=r,coefficient=c) for r,c in values.items()],evidence_refs=list(values))


def feature(context,ref):
    matches=[f for f in context.get('source_features',{}).get('features',[])
             if f.get('part_code') and f.get('ownership_proof') in ('native_part_identity','unique_source_detail_sheet','local_bom_leader_profile')
             and any(d['ref']==ref for d in f['dimensions'])]
    if len(matches)!=1:raise ValueError('DIM chưa gắn duy nhất với chi tiết có mã nguồn: '+ref)
    return matches[0]


def validate_binding(link,context):
    if context.get('units')!=4:raise ValueError('Liên kết tham số hiện yêu cầu đơn vị mm đã xác định')
    refs=[link.driver_ref,link.receiver_ref]+([link.outside_ref] if link.kind=='wall_clearance' else [])
    if (link.kind=='wall_clearance' and not link.outside_ref) or (link.kind=='equal_delta' and link.outside_ref):
        raise ValueError('Quy tắc khe hở cần DIM ngoài; quy tắc cùng mức thay đổi không dùng DIM ngoài')
    if len(set(refs))!=len(refs):raise ValueError('Cần các DIM riêng biệt cho liên kết')
    by={e['ref']:e for e in context['entities']};features=[feature(context,r) for r in refs]
    capabilities={e['ref']:e for e in context.get('cad_capabilities',{}).get('entities',[])}
    for ref,f in zip(refs,features):
        e=by.get(ref,{})
        if e.get('type')!='DIMENSION' or e.get('dimension_type') not in (0,1) or e.get('geometry',{}).get('text') not in ('','<>'):
            raise ValueError('Chỉ gắn DIM linear/aligned đo thật, không dùng số ghi đè: '+ref)
        if any(by.get(r,{}).get('review_only') or capabilities.get(r,{}).get('status')=='native_required' for r in [ref,*f['refs']]):
            raise ValueError('Phạm vi liên kết cần mở đầy đủ và có CAD adapter được hỗ trợ')
    values={r:measurement(by[r],by[r]['geometry']) for r in refs};solve(context,[equation(link)],values)
    if link.kind=='wall_clearance' and values[link.outside_ref]-link.wall_count*values[link.driver_ref]-values[link.receiver_ref]<-1e-6:
        raise ValueError('Kích thước nguồn không tạo khe hở lắp hợp lệ')
    return features


def read(folder,source_hash):
    path=Path(folder)/'parameter-links-v1.json'
    if not path.exists():return []
    data=json.loads(path.read_text(encoding='utf8'))
    if data.get('source_hash')!=source_hash:raise ValueError('Liên kết đã lưu thuộc nguồn CAD khác; cần xác nhận lại')
    links=data.get('links',[]);exclusions=Path(folder)/'exclusions-v1.json'
    if exclusions.exists():
        excluded=set(json.loads(exclusions.read_text(encoding='utf8')).get('ids',[]))
        for entry in links:entry['unavailable_scope_ids']=sorted(excluded.intersection(t['id'] for t in entry['targets']))
    return links


def attach(context,source):
    from backend.services import catalog_service as storage
    p=Path(source).resolve();folder=p.parent.parent if p.parent.name=='converted' else p.parent
    try:relative=p.relative_to(storage.ROOT.resolve())
    except ValueError:relative=None
    if relative and len(relative.parts)>1 and re.fullmatch('[0-9a-f]{32}',relative.parts[0]):
        folder=storage.ROOT/relative.parts[0]
        status_file=folder/'status.json'
        status=json.loads(status_file.read_text(encoding='utf8')) if status_file.exists() else {}
        registered=status.get('dxf')
        # Revisions/export readbacks must not inherit bindings to the source.
        if not registered or p!=(folder/registered).resolve():
            context['confirmed_parameter_links']=[]
            return context
    context['confirmed_parameter_links']=read(folder,context['source_hash'])
    return context


def inject(graph,links):
    result=copy.deepcopy(graph);known={n['code'] for n in result['nodes']}
    for saved in links:
        if saved.get('unavailable_scope_ids'):
            result.setdefault('warnings',[]).append(dict(code='confirmed_link_scope_excluded',confirmation_id=saved['id'],message='Liên kết dùng khung đã bỏ; cần xóa hoặc gắn lại trước khi sửa chi tiết liên quan.'))
            continue
        if not {saved['driver_code'],saved['receiver_code']}<=known:
            raise ValueError('Mã vật tư của liên kết đã lưu không còn trong BOM nguồn')
        result['edges'].append(dict(id='confirmed-'+saved['id'],source=saved['driver_code'],target=saved['receiver_code'],
            kind='confirmed_parameter',status='confirmed_numeric_rule',executable=False,
            evidence=[dict(sheet_id=t['id'],confirmation_id=saved['id']) for t in saved['targets']],
            missing=['assembly contact/projection coverage is validated independently']))
    return result


def active(context,refs):
    pool=context.get('confirmed_parameter_links',[]);reached=set(refs);result=[]
    while True:
        added=False
        for saved in pool:
            if saved in result:continue
            link=ParameterLink.model_validate(saved['rule']);terms={t.dimension_ref for t in equation(link).terms}
            if not reached.intersection(terms):continue
            if saved.get('unavailable_scope_ids'):raise ValueError('Liên kết dùng khung đã bỏ; cần xóa hoặc gắn lại')
            result.append(saved);reached.update(terms);added=True
        if not added:return result


def add_recipe(plan,context,ref,anchor):
    existing=next((r for r in plan.resize_recipes if r.dimension_ref==ref),None)
    if existing:
        if existing.anchor!=anchor:raise ValueError('Mốc giữ trong yêu cầu khác liên kết đã lưu: '+ref)
        return existing
    from cad.parametric import LinearResize
    from cad.frame_geometry import world
    from shapely.geometry import Polygon,Point
    f=feature(context,ref);by={e['ref']:e for e in context['entities']};polygon=Polygon([p[:2] for p in f['points']]);holes=[]
    for e in by.values():
        if e['type']!='CIRCLE' or not e.get('geometry') or e.get('layout')!=f['layout'] or e.get('review_only'):continue
        if f.get('instance_ref'):
            if not e['ref'].startswith(f['instance_ref']+'/'):continue
        elif not set(f['sheet_ids']).intersection(e.get('source_sheet_ids',[])):continue
        g=world(e)['geometry'];p=g['center']
        if abs(p[2]-f['points'][0][2])<1e-5 and polygon.contains(Point(p[:2])):holes.append(e['ref'])
    recipe=LinearResize(part_code=f['part_code'],dimension_ref=ref,new_measurement=None,anchor=anchor,
        outline_refs=f['refs'],hole_refs=holes,evidence_refs=sorted(set(f['evidence_refs']+holes)))
    plan.resize_recipes.append(recipe);return recipe


def sync_text(plan,context,recipe,value):
    from bom.operations import cell_operations
    from backend.services.change_service import EditProposal
    from cad.edit_engine import Operation
    from bom.stage_links import physical_spec
    by={e['ref']:e for e in context['entities']};record=by[recipe.dimension_ref];old=measurement(record,record['geometry'])
    if math.isclose(old,value,abs_tol=1e-6):return
    pattern=re.compile(r'(?<![\d.])'+re.escape(f'{old:g}').replace(r'\.',r'[.,]')+r'(?![\d.])')
    rows=[(e,r) for e in by.values() for r in e.get('bom',{}).get('rows',[]) if r['part_code']==recipe.part_code]
    specs={physical_spec(r['description']) for _,r in rows};mirror_refs={c.get('mirror_ref') for t in by.values() for r in t.get('bom',{}).get('rows',[]) for c in r.get('cells',{}).values()}
    operations=[]
    for table,row in rows:
        cell=row.get('cells',{}).get('description',{});raw=cell.get('raw_text','')
        if len(pattern.findall(raw))!=1:raise ValueError('Chưa xác định duy nhất kích thước trong mô tả BOM: '+recipe.part_code)
        operations.extend(cell_operations(table,cell,pattern.sub(f'{value:g}',raw),by,'Đồng bộ BOM theo ràng buộc kích thước đã xác nhận'))
    f=feature(context,recipe.dimension_ref)
    for e in by.values():
        if e['type'] not in ('TEXT','MTEXT') or e['ref'] in mirror_refs:continue
        owned=e['ref'].startswith(f['instance_ref']+'/') if f.get('instance_ref') else bool(set(f['sheet_ids']).intersection(e.get('source_sheet_ids',[])))
        raw=e.get('raw_text',e.get('text',''))
        if owned and physical_spec(raw) in specs and len(pattern.findall(raw))==1:
            operations.append(Operation(ref=e['ref'],action='replace_text',before=raw,after=pattern.sub(f'{value:g}',raw),xyz=[],reason='Đồng bộ quy cách hình nguồn theo liên kết đã xác nhận'))
    for op in operations:
        oldop=next((o for o in plan.operations if o.ref==op.ref and o.cell_index==op.cell_index),None)
        if oldop:
            if oldop.action!=op.action or oldop.before!=op.before or oldop.after!=op.after:raise ValueError('Thay đổi BOM xung đột với liên kết đã lưu')
            continue
        plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=recipe.part_code,purpose='bom' if op.ref in mirror_refs or op.action=='table_cell' else 'annotation',before=op.before,after=op.after,reason=op.reason))


def expand(plan,context):
    codes={r.part_code for r in plan.resize_recipes}
    if any(e.get('unavailable_scope_ids') and codes.intersection([e['driver_code'],e['receiver_code']]) for e in context.get('confirmed_parameter_links',[])):
        raise ValueError('Liên kết của chi tiết dùng khung đã bỏ; cần xóa hoặc gắn lại')
    saved=active(context,[r.dimension_ref for r in plan.resize_recipes])
    if not saved:return plan
    from backend.services.change_service import DependencyProposal
    by={e['ref']:e for e in context['entities']};equations=[];fixed={};affected=set()
    for entry in saved:
        link=ParameterLink.model_validate(entry['rule']);validate_binding(link,context);eq=equation(link);equations.append(eq)
        a=add_recipe(plan,context,link.driver_ref,link.driver_anchor);b=add_recipe(plan,context,link.receiver_ref,link.receiver_anchor);affected.update([link.driver_ref,link.receiver_ref])
        if link.kind=='wall_clearance':fixed[link.outside_ref]=measurement(by[link.outside_ref],by[link.outside_ref]['geometry'])
        evidence=sorted(set(eq.evidence_refs+a.evidence_refs+b.evidence_refs))
        if not any(d.relationship=='confirmed-parameter:'+entry['id'] for d in plan.dependencies):
            plan.dependencies.append(DependencyProposal(source_part=a.part_code,target_part=b.part_code,relationship='confirmed-parameter:'+entry['id'],
                evidence_refs=evidence,required_change='Giữ chênh lệch DIM nguồn' if link.kind=='equal_delta' else 'Giữ kích thước ngoài và khe hở DIM nguồn',needs_confirmation=True,equation_rule=eq))
    requested={r.dimension_ref:r.new_measurement for r in plan.resize_recipes if r.new_measurement is not None}
    if any(r in requested and not math.isclose(requested[r],v,abs_tol=1e-6) for r,v in fixed.items()):raise ValueError('Yêu cầu xung đột DIM ngoài giữ cố định trong liên kết')
    requested.update(fixed);solved=solve(context,equations,requested)
    for r in plan.resize_recipes:
        if r.dimension_ref in affected:
            sync_text(plan,context,r,solved[r.dimension_ref])
            # Measured-view correspondence also needs the solved target before
            # it can bind another native representation of the receiving part.
            if r.new_measurement is None:r.new_measurement=solved[r.dimension_ref]
    return plan


def validate(plan,context):
    if plan.questions or not plan.operations:return
    changed={o.ref:o for o in plan.operations if o.action=='replace_geometry' and o.ref in {e['ref'] for e in context['entities'] if e['type']=='DIMENSION'}}
    codes={f['part_code'] for f in context.get('source_features',{}).get('features',[]) if any(d['ref'] in changed for d in f['dimensions'])}
    if any(e.get('unavailable_scope_ids') and codes.intersection([e['driver_code'],e['receiver_code']]) for e in context.get('confirmed_parameter_links',[])):
        raise ValueError('Liên kết của chi tiết dùng khung đã bỏ; cần xóa hoặc gắn lại')
    links=active(context,changed)
    if not links:return
    equations=[];by={e['ref']:e for e in context['entities']}
    for entry in links:
        link=ParameterLink.model_validate(entry['rule']);validate_binding(link,context);equations.append(equation(link))
        if link.kind=='wall_clearance' and link.outside_ref in changed:
            op=changed[link.outside_ref]
            if not math.isclose(measurement(by[op.ref],json.loads(op.after)),measurement(by[op.ref],by[op.ref]['geometry']),abs_tol=1e-6):raise ValueError('DIM ngoài của liên kết phải giữ nguyên')
        for ref,anchor in [(link.driver_ref,link.driver_anchor),(link.receiver_ref,link.receiver_anchor)]:
            if ref not in changed:continue
            recipe=next((r for r in plan.resize_recipes if r.dimension_ref==ref),None)
            if recipe is None or recipe.anchor!=anchor:raise ValueError('Thay đổi liên kết thiếu recipe/mốc giữ đã xác nhận: '+ref)
    validate_equations(plan.operations,equations,context)
