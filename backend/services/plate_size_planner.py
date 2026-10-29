"""Source-measured two-axis plate resizing with an explicit hole-center datum.

Nominal BOM values and actual DIM values have separate roles. No file name,
handle, part code or default side is a design rule in this compiler.
"""
import math
import re
import numpy as np
from bom.reader import normalized
from cad.frame_geometry import world
from cad.parametric import LinearResize
from backend.services.size_commands import interpret_linear_request,NUMBER

SPEC=re.compile(r'(?<![\d.,x×])('+NUMBER+r')\s*[x×]\s*('+NUMBER+r')\s*[x×]\s*('+NUMBER+r')(?![\d.,x×])',re.I)


def replace_spec(raw,before,new,groups=(2,3)):
    """Replace dimension roles inside one exact source plate specification."""
    matches=[m for m in SPEC.finditer(raw) if all(abs(float(v.replace(',','.'))-n)<1e-6 for v,n in zip(m.groups(),before))]
    if len(matches)!=1:raise ValueError('Quy cách tấm chưa có ba trường kích thước duy nhất trong chữ CAD nguồn')
    m=matches[0];result=raw
    for group in sorted(groups,reverse=True):
        start,end=m.span(group);result=result[:start]+f'{new:g}'+result[end:]
    return result


def compile_plan(context,request,clarifications=None):
    reading=interpret_linear_request(context,request,clarifications)
    if not reading:return None
    from backend.services.change_service import DrawingChangePlan,EditProposal
    code=reading['part_code']
    def review(question):
        return DrawingChangePlan(summary='Đã hiểu kích thước đích; cần xác định phép sửa từ CAD nguồn.',target_part=code,edits=[],dependencies=[],operations=[],questions=[question],warnings=[])
    if reading['problems']:return review(' '.join(reading['problems']))
    spec=reading['nominal_spec_mm']
    if not spec or reading['target_mm'] is None:return None
    if reading['nominal_dim_mismatch'] and reading['target_basis'] is None:return None
    both=reading['confirmed_axes']=='both'
    if not both and not reading['keep_hole_center']:return None
    if reading['fixed_side']!='tam' or not reading['keep_hole_center']:
        return review('Cần xác định tâm lỗ hoặc mốc lắp giữ nguyên cho hướng sửa đã chọn.')
    if reading['target_basis']!='actual_dim':return review('Kích thước đích cần được xác nhận theo số đo thực tế, phân biệt với quy cách BOM nguồn.')
    if reading['measurement_mode']!='absolute':return review('Cần kích thước cuối của từng DIM khi sửa cả hai hướng; chưa tự dùng một lượng giảm cho hai DIM khác nhau.')
    target=reading['target_mm'];by={e['ref']:e for e in context['entities']};candidates=[];square_ambiguity=False
    kind=reading['dimension'];selected_axis=reading['selected_dim_axis']
    if not both and kind not in ('length','width'):return None
    for f in context.get('source_features',{}).get('features',[]):
        if f.get('part_code')!=code or f.get('ownership_proof')=='unverified':continue
        dims=[]
        for d in f['dimensions']:
            a=np.asarray(d['axis']);p=np.asarray(f['points']);span=float(np.ptp(p@a));cross=float(np.ptp(p@np.array([-a[1],a[0],0.])))
            if span<=spec[0]+1e-5 or cross<=spec[0]+1e-5 or not math.isclose(d['measurement'],reading['measured_before_mm'] or -1,abs_tol=1e-5):continue
            if not both:
                if selected_axis:
                    if abs(a[0 if selected_axis=='horizontal' else 1])<1-1e-7:continue
                elif abs(span-cross)<1e-5:
                    square_ambiguity=True;continue
                elif kind=='length' and span<cross or kind=='width' and span>cross:continue
            dims.append(d)
        # This compiler resolves one uniquely owned face with two real axes.
        if both and len(dims)==2 and abs(float(np.dot(dims[0]['axis'],dims[1]['axis'])))<1e-7 or not both and len(dims)==1:candidates.append((f,dims))
    if not candidates and square_ambiguity:return review('Tấm có hai cạnh bằng nhau; chọn DIM ngang hoặc DIM đứng cần sửa, hoặc xác nhận sửa cả hai DIM. Giữ tâm lỗ theo yêu cầu.')
    if not candidates:return review('Chưa gắn được mặt tấm và DIM thực tế cần sửa; cần kiểm tra liên kết hình trước khi sửa.')
    roots=set(context.get('root_target_ids',[]))
    local=[item for item in candidates if roots.intersection(item[0].get('sheet_ids',[])) or item[0].get('instance_ref') in roots]
    if selected_axis and len(local or candidates)>1:
        return review('Có nhiều hình mang DIM theo hướng đã chọn; chọn đúng khung chi tiết để xác định hướng sửa trước khi đồng bộ các hình liên quan.')
    local_refs={tuple(sorted(item[0]['refs'])) for item in local}
    candidates.sort(key=lambda item:(tuple(sorted(item[0]['refs'])) not in local_refs,tuple(sorted(item[0]['refs']))))
    f,dims=candidates[0]
    from shapely.geometry import Polygon,Point
    polygon=Polygon([p[:2] for p in f['points']]);holes=[]
    for e in by.values():
        if e['type']!='CIRCLE' or not e.get('geometry') or e.get('layout')!=f['layout']:continue
        g=world(e)['geometry']
        if abs(g['center'][2]-f['points'][0][2])<1e-5 and polygon.contains(Point(g['center'][:2])):holes.append((e['ref'],g))
    if not holes:return review('Chưa xác định được lỗ nguồn để giữ tâm khi co hai hướng.')
    inner=min(holes,key=lambda item:item[1]['radius']);center=inner[1]['center']
    for d in dims:
        g=world(by[d['ref']])['geometry'];axis=d['axis']
        midpoint=sum((a+b)/2*u for a,b,u in zip(g['defpoint2'],g['defpoint3'],axis))
        if abs(sum(p*u for p,u in zip(center,axis))-midpoint)>1e-5:return review('Tâm lỗ chưa trùng tâm hai DIM nguồn; cần phép giữ tâm lỗ riêng, không tự thay bằng tâm đường bao.')
    refs=[ref for ref,_ in holes]
    recipes=[LinearResize(part_code=code,dimension_ref=d['ref'],new_measurement=target,outline_refs=f['refs'],hole_refs=refs,anchor='center',
        evidence_refs=sorted(set(f['evidence_refs']+refs+[d['ref']]))) for d in dims]
    # Multiple views are not multiple independent size commands. Resolve one
    # source driver, then require the existing complete-geometry/DIM mapping
    # to prove every other candidate is a receiving view of that same motion.
    from graph.measured_views import expand
    try:recipes=expand(recipes,context)
    except ValueError as error:return review('Chưa đối chiếu được các hình của chi tiết: '+str(error))
    covered={r.dimension_ref for r in recipes}
    if any(d['ref'] not in covered for _,bindings in candidates for d in bindings):
        return review('Các hình cùng mã chưa có phép đối chiếu hình học và DIM duy nhất; chưa sửa một phần thay cho toàn bộ các hình đo được.')
    plan=DrawingChangePlan(summary=f"{code}: {'cả hai DIM' if both else 'DIM '+dims[0]['ref']} thực tế → {target:g} mm; giữ tâm lỗ, độ dày và bán kính nguồn.",target_part=code,
        edits=[],dependencies=[],operations=[],questions=[],warnings=[],resize_recipes=recipes)
    rows=[(e,r) for e in by.values() for r in e.get('bom',{}).get('rows',[]) if r['part_code']==code]
    if not rows:return review('Chưa có dòng BOM nguồn để đồng bộ quy cách tấm.')
    from bom.operations import cell_operations
    fields=(2,3) if both else (3,) if kind=='length' else (2,)
    for table,row in rows:
        cell=row.get('cells',{}).get('description',{})
        try:after=replace_spec(cell.get('raw_text',''),spec,target,fields)
        except ValueError as error:return review(str(error))
        for op in cell_operations(table,cell,after,by,'Đồng bộ trường kích thước đã chọn theo DIM thực tế; giữ độ dày và các trường khác'):
            plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='bom',before=op.before,after=op.after,reason=op.reason))
    # Only physical titles in this proven single-part detail, never revision
    # history, unrelated numbers or descriptions belonging to other parts.
    from bom.stage_links import physical_spec
    from cad.edit_engine import Operation
    physical={physical_spec(r['description']) for _,r in rows}
    receiving=[feature for feature in context.get('source_features',{}).get('features',[]) if feature.get('part_code')==code and
               feature.get('ownership_proof') not in (None,'unverified') and any(set(feature['refs'])==set(r.outline_refs) for r in recipes)]
    owned_sheets={sid for feature in receiving if feature['ownership_proof']=='unique_source_detail_sheet' for sid in feature['sheet_ids']}
    natives={feature['instance_ref'] for feature in receiving if feature.get('instance_ref')}
    for e in by.values():
        if e['type'] not in ('TEXT','MTEXT'):continue
        if not (owned_sheets.intersection(e.get('source_sheet_ids',[])) or any(e['ref'].startswith(native+'/') for native in natives)):continue
        if physical_spec(e.get('text','')) not in physical or any(op.ref==e['ref'] for op in plan.operations):continue
        raw=e.get('raw_text',e.get('text',''));after=replace_spec(raw,spec,target,fields)
        op=Operation(ref=e['ref'],action='replace_text',before=raw,after=after,xyz=[],reason='Đồng bộ quy cách trên bản chi tiết sở hữu duy nhất')
        plan.operations.append(op);plan.edits.append(EditProposal(entity_ref=op.ref,part_number=code,purpose='annotation',before=raw,after=after,reason=op.reason))
    from backend.services.parametric_service import compile_recipes
    try:return compile_recipes(plan,context)
    except ValueError as error:return review('Chưa thực thi phép sửa hai DIM: '+str(error))


def verify_intent(plan,context,request,clarifications=None):
    """Saved geometry must still implement the original human size/axis choice."""
    expected=compile_plan(context,request,clarifications)
    if expected is None or expected.questions or not expected.operations:
        raise ValueError('Chưa xác định đủ lựa chọn kích thước/mốc từ yêu cầu nguồn để thực thi bản sửa đã lưu.')
    from backend.services.compound_planner import operation_key,same_operation
    actual={operation_key(op):op for op in plan.operations}
    for op in expected.operations:
        if operation_key(op) not in actual or not same_operation(op,actual[operation_key(op)]):
            raise ValueError('Bản sửa đã lưu thiếu hoặc sai thao tác theo yêu cầu kích thước/mốc: '+op.ref)
    requested={(r.part_code,r.dimension_ref,r.new_measurement,r.anchor) for r in expected.resize_recipes}
    if requested!={(r.part_code,r.dimension_ref,r.new_measurement,r.anchor) for r in plan.resize_recipes}:
        raise ValueError('Hướng, đích hoặc mốc DIM trong bản sửa đã lưu không khớp yêu cầu đã xác nhận.')
