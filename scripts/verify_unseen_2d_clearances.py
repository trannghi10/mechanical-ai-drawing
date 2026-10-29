"""New DIM-clearance DWGs, including separate exploded detail and assembly.

Generate fixture/oracles independently of the production planner. Submit only
the new DWG and Vietnamese whole-document request; never inject source labels
or relations into the live web API. Local CAD only, preview artifacts only.
"""
import json
from scripts.verify_unseen_loose_relations import ROOT,run_cases,require_local,save,digest
from test_flat_contacts import unseen_drawing
from test_planar_clearances import add_detail


def render_proof(case,output):
    """Render source and independently reopened native output at equal bounds."""
    import ezdxf
    from ezdxf import bbox
    from backend.services import catalog_service as storage
    from cad.sheets import render_sheet
    from cad.vision import rasterize_svg
    paths=[]
    for did in (case['document_id'],case['independent_document_id']):
        paths.append(storage.folder(did)/storage.read_status(did)['dxf'])
    docs=[ezdxf.readfile(path) for path in paths];ids=case['ids']
    assembly=[r for group in ids['bodies'] for r in group]+ids['dims']+ids['holes']+ids['arrows']
    assembly.extend(r for group in ids['bubbles'] for r in group);assembly.extend([ids['total'],*ids['gap_dims']])
    scenes=[('assembly','Model',assembly)]
    detail=case.get('detail')
    if detail:scenes.append(('detail',detail.get('layout','Model'),detail['refs']+[detail[k] for k in ('hole','dimension','arrow','bubble','label')]))
    for name,layout,refs in scenes:
        bounds=bbox.extents([d.entitydb[r] for d in docs for r in refs]);margin=max(bounds.size.x,bounds.size.y)*.06
        box=[bounds.extmin.x-margin,bounds.extmin.y-margin,bounds.extmax.x+margin,bounds.extmax.y+margin]
        for phase,path in zip(('before','after'),paths):
            content=render_sheet(path,dict(id='proof',layout=layout,bbox=box))
            (output/f'{name}-{phase}.svg').write_text(content,encoding='utf8')
            (output/f'{name}-{phase}.png').write_bytes(rasterize_svg(content,width=1000))


def main():
    require_local()
    output=ROOT/'storage/validation-fixtures/unseen-2d-clearances-2026-10-23';output.mkdir(exist_ok=True)
    manifest=output/'run.json'
    run=json.loads(manifest.read_text(encoding='utf8')) if manifest.exists() else dict(status='running',synthetic=True,cloud_used=False,production_release=False,cases=[])
    for seed,angle,lines,gap,detail_angle,layout_name in [(3161,0,False,8,90,None),(7319,31,True,12.5,None,None),(8423,119,False,17,241,None),(9107,17,False,14,90,'Manufacturing detail')]:
        if any(c['seed']==seed for c in run['cases']):continue
        directory=output/str(seed);directory.mkdir(exist_ok=True)
        source,context,_,ids=unseen_drawing(directory,seed,angle,lines,gap,measured_gap=True)
        detail=None
        if detail_angle is not None:
            context,detail=add_detail(source,context,ids,detail_angle,layout_name)
            detail=dict(detail,placement=list(detail['placement']))
        run['cases'].append(dict(seed=seed,angle=angle,lines=lines,input=str(source.relative_to(ROOT)),input_sha256=digest(source),
            request=f'Mã {ids["codes"][0]} chiều dài từ {ids["heights"][0]} thành {ids["heights"][0]+23} mm, giữ tâm',
            codes=ids['codes'],heights=ids['heights'],hold='center',expected_shift=list(ids['transform'].transform_direction((0,11.5,0))),
            source_clearance_total_mm=gap,detail=detail,
            ids={key:ids[key] for key in ('bodies','dims','holes','arrows','bubbles','total','outside','gap_dims')}))
        save(manifest,run)
    for case in run['cases']:case['hold']='center'
    save(manifest,run)
    run_cases(run,manifest,output)
    render_proof(run['cases'][0],output)


if __name__=='__main__':main()
