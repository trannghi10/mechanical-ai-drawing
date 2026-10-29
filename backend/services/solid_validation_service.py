"""Verify source-bound plate changes with a local OpenCASCADE kernel."""
import copy
import json
import os
from pathlib import Path
import subprocess
from cad.geometry import near
from cad.rounded_profile import inspect,find_profiles,_segments,TOL


def runtime():
    configured=os.environ.get('FREECAD_PYTHON')
    candidates=[Path(configured)] if configured else sorted(Path('C:/Program Files').glob('FreeCAD */bin/python.exe'),reverse=True)
    return next((p for p in candidates if p.is_file()),None)


def numeric_profile(profile):
    cx,cy=(profile.bbox[0]+profile.bbox[2])/2,(profile.bbox[1]+profile.bbox[3])/2
    def p(q):return [q[0]-cx,q[1]-cy]
    return dict(segments=[[kind,p(a),p(b),p(c) if c else None,r] for kind,a,b,c,r in _segments(profile.boundary)],
        holes=[dict(center=p(h['geometry']['center']),radius=h['geometry']['radius']) for h in profile.holes])


def cavity(arcs):
    """Four verified equal-radius axial arcs, joined by their tangent edges."""
    segments=_segments(arcs)
    if len(segments)!=4:raise ValueError('Thiếu bốn cung góc trong hộp')
    lines=[]
    points=[p for s in segments for p in s[1:3]]
    for axis in (0,1):
        for value in (min(p[axis] for p in points),max(p[axis] for p in points)):
            endpoints=[p for p in points if near(p[axis],value,TOL)]
            if len(endpoints)!=2:raise ValueError('Góc trong hộp chưa tạo được biên kín')
            lines.append(dict(ref='cavity-'+str(len(lines)),type='LINE',geometry=dict(start=endpoints[0]+[0],end=endpoints[1]+[0])))
    return inspect(arcs+lines)


def payload_for(plan,context):
    from graph.drawing_sync import assembly_sheet_ids
    assembly_ids=assembly_sheet_ids(context)
    by={e['ref']:e for e in context['entities']}
    ops={o.ref:o for o in plan.operations if o.action=='replace_geometry'}
    wall_arcs=[by[r] for r,o in ops.items() if by[r]['type']=='ARC' and not near(json.loads(o.before)['radius'],json.loads(o.after)['radius']) and not assembly_ids.intersection(by[r].get('source_sheet_ids',[])) and not any(by[r].get('source_sheet_ids',[])==[recipe.sheet_id] for recipe in plan.profile_cut_recipes)]
    checks=[]
    for recipe in plan.profile_cut_recipes:
        # Detail frames and cut frames share a part code; only the detail has a
        # measured radius DIMENSION and no nested source INSERT geometry.
        candidates=[]
        for target in context['targets']:
            if target['id'] in assembly_ids:continue
            if target['id']==recipe.sheet_id or recipe.part_code not in target.get('texts',[]):continue
            records=[e for e in context['entities'] if target['id'] in e.get('source_sheet_ids',[]) and '/' not in e['ref']]
            for p in find_profiles(records):
                size=[p.bbox[2]-p.bbox[0],p.bbox[3]-p.bbox[1]]
                if p.corners and near(sorted(size),sorted(recipe.old_size),TOL) and any(e['ref'] in ops for e in p.boundary):candidates.append((target,records,p))
        if len(candidates)!=1:raise ValueError('Chưa gắn duy nhất solid với bản chi tiết bas')
        target,records,p=candidates[0]
        holes=[e for e in records if e['type']=='CIRCLE' and p.bbox[0]<e['geometry']['center'][0]<p.bbox[2] and p.bbox[1]<e['geometry']['center'][1]<p.bbox[3]]
        before=inspect(p.boundary,holes)
        after=inspect([dict(e,geometry=json.loads(ops[e['ref']].after)) if e['ref'] in ops else e for e in p.boundary],holes)
        # Gauge must come from the unchanged narrow side projection, not AI text.
        sides=[s for s in find_profiles(records) if not s.corners and near([s.bbox[0],s.bbox[2]],[p.bbox[0],p.bbox[2]],TOL) and s.bbox[3]<p.bbox[1]-TOL]
        if len(sides)!=1:raise ValueError('Thiếu hình chiếu cạnh để xác định chiều dày solid')
        item=dict(part_code=recipe.part_code,gauge=sides[0].bbox[3]-sides[0].bbox[1],scope='part_solid',before=numeric_profile(before),after=numeric_profile(after))
        if len(before.corners)==4:
            # This fit is only established for a two-axis, centered full cap.
            groups={}
            for e in wall_arcs:
                for sid in e.get('source_sheet_ids',[]):groups.setdefault(sid,[]).append(e)
            fits=[]
            for arcs in groups.values():
                if len(arcs)!=4:continue
                try:old=cavity(arcs);new=cavity([dict(e,geometry=json.loads(ops[e['ref']].after)) for e in arcs])
                except ValueError:continue
                gap=[old.bbox[i+2]-old.bbox[i]-(before.bbox[i+2]-before.bbox[i]) for i in (0,1)]
                if all(0<=v<=1 for v in gap) and near(gap[0],gap[1],TOL):fits.append((old,new))
            if len(fits)!=1:raise ValueError('Chưa chứng minh duy nhất tiết diện lắp solid')
            old,new=fits[0];item.update(scope='centered_section_fit',cavity_before=numeric_profile(old),cavity_after=numeric_profile(new))
        checks.append(item)
    from cad.planar_profiles import checks as planar_checks
    checks.extend(planar_checks(plan,context))
    return dict(checks=checks)


def validate_solids(plan,context):
    if not plan.profile_cut_recipes and not getattr(plan,'resize_recipes',[]) and not getattr(plan,'curved_wall_recipes',[]) and not getattr(plan,'hole_recipes',[]):return dict(status='not_applicable',checks=[])
    python=runtime()
    if python is None:raise ValueError('Cần FreeCAD cục bộ để kiểm tra mặt/solid trước khi tạo bản sửa này; cấu hình FREECAD_PYTHON.')
    payload=payload_for(plan,context)
    worker=Path(__file__).resolve().parents[2]/'cad/freecad_worker.py'
    try:
        result=subprocess.run([str(python),str(worker)],input=json.dumps(payload,allow_nan=False),text=True,
            capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        report=json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired,json.JSONDecodeError,OSError) as error:raise ValueError('FreeCAD chưa kiểm tra được solid; bản gốc được giữ nguyên') from error
    if result.returncode or report.get('status')!='passed':raise ValueError('Kiểm tra solid FreeCAD thất bại: '+str(report.get('error','Chi tiết giao nhau sau thay đổi')))
    report['policy_version']=2
    return report
