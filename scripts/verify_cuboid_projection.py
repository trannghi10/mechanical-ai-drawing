"""Verify a new metric 3D depiction through website and real DWG readback."""
import argparse,json,sys,time,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import ezdxf,requests
from test_assembly import cuboid_projection_fixture
from cad.converter import DWGConverter,converter_path
from cad.edit_engine import digest
from cad.geometry import snapshot,near
from cad.cuboid_projection import components,cameras
from backend.services import catalog_service as storage
from backend.services.change_service import context_for
from cad.sheets import discover_sheets


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--confirm-uncoded',action='store_true');parser.add_argument('--ocs-hatch',action='store_true');parser.add_argument('--edge-hatch',action='store_true');parser.add_argument('--associated-hatch',action='store_true');parser.add_argument('--dimassoc-hatch',action='store_true');args=parser.parse_args()
    if args.dimassoc_hatch:args.associated_hatch=True
    if args.associated_hatch:args.ocs_hatch=True
    if args.edge_hatch:args.ocs_hatch=True
    token=uuid.uuid4().hex[:8];task=ROOT/'storage/validation-fixtures'/('cuboid-projection-'+token);inputs=task/'input';inputs.mkdir(parents=True)
    source,_,fixture_plan,ids=cuboid_projection_fixture(inputs,mirror=True)
    d=ezdxf.readfile(source);code='UNSEEN-CUBOID-'+token
    if args.ocs_hatch:
        target_block=d.blocks[d.entitydb[ids['target_root']].dxf.name]
        for i,normal in enumerate(([0,0,-1],[1,2,3])):
            hatch=target_block.add_hatch(dxfattribs=dict(extrusion=normal,elevation=(0,0,17)))
            if args.edge_hatch:
                path=hatch.paths.add_edge_path()
                if i==0:
                    path.add_arc((-190,160),10,0,180,ccw=False)
                    path.add_line((-180,160),(-200,160))
                else:
                    path.add_ellipse((-190,160),(10,3),.4,0,360,ccw=False)
                    hatch.set_pattern_fill('ANSI31',scale=.75,angle=23)
                    hatch.set_seed_points([(-190,160)])
            else:hatch.paths.add_polyline_path([(-200,150,1),(-180,150,0),(-180,170,0),(-200,170,0)],is_closed=True)
        if args.associated_hatch:
            boundary=target_block.add_lwpolyline([(150,150),(170,150),(170,170),(150,170)],close=True)
            hatch=target_block.add_hatch();path=hatch.paths.add_polyline_path([(150,150),(170,150),(170,170),(150,170)],is_closed=True)
            hatch.associate(path,[boundary])
            from ezdxf import bbox
            island=target_block.add_mtext('ISLAND',dxfattribs=dict(insert=(153,164),char_height=2))
            bounds=bbox.extents([island]);x,y=bounds.extmin.x,bounds.extmin.y;u,v=bounds.extmax.x,bounds.extmax.y
            hole=hatch.paths.add_polyline_path([(x,y),(u,y),(u,v),(x,v)],is_closed=True,flags=0)
            hatch.associate(hole,[island])
            if args.dimassoc_hatch:
                from test_geometry import native_dimension_binding
                dimension=target_block.add_linear_dim(base=(150,185),p1=(150,150),p2=(170,150));dimension.render()
                native_dimension_binding(d,dimension.dimension,[(boundary,13,[150,150,0]),(boundary,13,[170,150,0])])
    if args.confirm_uncoded:d.entitydb[ids['target_root']].delete_all_attribs()
    d.blocks.rename_block('BOX-UNSEEN',code)
    for layout in d.layouts:
        for e in layout.query('INSERT'):
            if e.dxf.name=='BOX-UNSEEN':e.dxf.name=code
            for a in e.attribs:a.dxf.text=a.dxf.text.replace('BOX-UNSEEN',code)
        for e in layout.query('TEXT MTEXT'):
            if e.dxftype()=='TEXT':e.dxf.text=e.dxf.text.replace('BOX-UNSEEN',code)
            else:e.text=e.text.replace('BOX-UNSEEN',code)
    m=d.modelspace();m.add_lwpolyline([(-100,-100),(1100,-100),(1100,500),(-100,500)],close=True)
    m.add_text('PART NAME',dxfattribs=dict(insert=(-90,-90),height=3));d.saveas(source)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(inputs,task/'dwg');dwg=task/'dwg'/source.with_suffix('.dwg').name
    base='http://127.0.0.1:8765';session=requests.Session();session.trust_env=False
    def api(path,data=None):
        r=session.post(base+path,json=data,timeout=180) if data is not None else session.get(base+path,timeout=180)
        if not r.ok:raise RuntimeError(f'{path}: {r.status_code} {r.text[:2000]}')
        return r.json()
    with dwg.open('rb') as stream:
        r=session.post(base+'/documents',files={'file':('synthetic-cuboid-'+token+'.dwg',stream,'application/octet-stream')},timeout=30);r.raise_for_status();did=r.json()['id']
    route='/documents/'+did;deadline=time.monotonic()+150
    while True:
        status=api(route)
        if status['status']=='ready':break
        if status['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(status)
        time.sleep(.5)
    folder=storage.folder(did);status=storage.read_status(did);status.update(synthetic_test=True,auxiliary=True);storage.write_json(folder/'status.json',status)
    target=next(t for t in api(route+'/sheets')['items'] if t['bbox'][0]<0 and t['bbox'][2]>1000)
    confirmed=None;fixed_point=None
    if args.confirm_uncoded:
        reading=api(route+'/cuboid-candidates',dict(ids=[target['id']],source_hash=digest(folder/status['dxf']),dimension_ref=fixture_plan.resize_recipes[0].dimension_ref))
        candidate,=reading['candidates'];assert candidate['status']=='candidate_cuboid_identity'
        picture=session.get(base+route+f'/cuboid-candidates/{reading["id"]}/{candidate["id"]}/preview',params=dict(source_hash=reading['source_hash']),timeout=180);picture.raise_for_status();(task/'source-candidate.svg').write_text(picture.text,encoding='utf8')
        fixed_point=next(v['point'] for v in candidate['vertices'] if v['label']=='A')
        confirmed=api(route+'/cuboid-links',dict(candidate_id=reading['id'],body_id=candidate['id'],source_hash=reading['source_hash'],anchor='vertex',vertex='A',confirmed=True))
        storage.write_json(task/'confirmed-link.json',confirmed)
    request=f'Mã {code} chiều cao từ 100 thành 76 mm, '+('giữ dưới' if args.confirm_uncoded else 'giữ tâm')
    proposal=api(route+'/change-plans',dict(ids=[target['id']],request=request));storage.write_json(task/'plan.json',proposal)
    assert proposal['execution_available'] or proposal.get('preview_execution_available'),proposal['plan']['questions']
    action='apply' if proposal['execution_available'] else 'apply-checked-preview'
    revision=api(route+f'/change-plans/{proposal["id"]}/{action}',dict(preview_only=True));rid=revision['id'];rev=route+'/revisions/'+rid
    preview=session.get(base+rev+'/sheets/'+target['id']+'/preview',timeout=60);preview.raise_for_status();(task/'after.svg').write_text(preview.text,encoding='utf8')
    assert api(rev+'/approve',dict(confirmed_dependencies=revision['pending_dependencies']))['status']=='approved'
    job=api(rev+'/exports',dict(format='dwg',scope='selection',preview=False));deadline=time.monotonic()+180
    while job['status']!='ready':
        if job['status']=='failed' or time.monotonic()>deadline:raise RuntimeError(job)
        time.sleep(.5);job=api(rev+'/exports/'+job['id'])
    r=session.get(base+job['download_url'],timeout=30);r.raise_for_status();download=task/'download';download.mkdir();backup=download/'cuboid-backup.dwg';backup.write_bytes(r.content)
    converter.convert_dwg_to_dxf(download,task/'reopened');out=ezdxf.readfile(task/'reopened/cuboid-backup.dxf')
    body=out.blocks[out.entitydb[ids['target_root']].dxf.name]
    records=[dict(ref=e.dxf.handle,type='LINE',geometry=snapshot(e)) for e in body.query('LINE')]
    rebuilt,=components(records);assert cameras(rebuilt,[2,80,76]) and not cameras(rebuilt,[2,80,100])
    # Extra native content makes the parent a mixed container: body identity
    # never grants ownership of neighbouring notes in that container.
    expected_note='Foam 2x80x100mm' if args.ocs_hatch else 'Foam 2x80x76mm'
    assert [e.dxf.text for e in body.query('TEXT')]==[expected_note]
    if args.ocs_hatch:
        imported=ezdxf.readfile(folder/status['dxf'])
        original_hatches=list(imported.blocks['VIEW-WITH-DEPTH'].query('HATCH'));reopened_hatches=list(body.query('HATCH'))
        assert len(original_hatches)==len(reopened_hatches)==(3 if args.associated_hatch else 2)
        for before_hatch,after_hatch in zip(original_hatches,reopened_hatches):
            from ezdxf.math import Vec3
            assert near(list(Vec3(before_hatch.dxf.extrusion).normalize()),list(Vec3(after_hatch.dxf.extrusion).normalize()),1e-5)
            assert near(list(before_hatch.dxf.elevation),list(after_hatch.dxf.elevation),1e-5)
            from cad.hatch_translation import preserved_snapshot
            from cad.hatch_association import source_snapshot
            read=source_snapshot if before_hatch.dxf.associative else preserved_snapshot
            assert near(read(before_hatch),read(after_hatch),1e-5)
        if args.associated_hatch:
            from cad.hatch_association import verify_mapping
            report=json.loads((folder/'revisions'/rid/'revision.json').read_text(encoding='utf8'))
            for clone in report['validation']['block_isolation']:verify_mapping(imported,out,clone['handle_map'])
    measured=out.blocks[out.entitydb[ids['source_root']].dxf.name]
    assert near([e.get_measurement() for e in measured.query('DIMENSION')],[76],1e-5)
    outline=next(iter(measured.query('LWPOLYLINE')));ys=[p[1] for p in outline.get_points()];assert abs(max(ys)-min(ys)-76)<1e-5
    path=task/'reopened/cuboid-backup.dxf';context=context_for(path,discover_sheets(path))
    rows=[row for e in context['entities'] for row in e.get('bom',{}).get('rows',[]) if row['part_code']==code]
    assert rows and all(row['description']=='Foam 2x80x76mm' for row in rows)
    original=ezdxf.readfile(source).blocks['VIEW-WITH-DEPTH'];center=lambda es:[(min(e.dxf.get(k)[a] for e in es for k in ('start','end'))+max(e.dxf.get(k)[a] for e in es for k in ('start','end')))/2 for a in (0,1)]
    if args.confirm_uncoded:
        assert any(near(list(e.dxf.get(k)),fixed_point,1e-5) for e in body.query('LINE') for k in ('start','end'))
    else:assert near(center(list(body.query('LINE'))),center(list(original.query('LINE'))),1e-5)
    assert digest(folder/'original.dwg')==digest(dwg)
    receipt=dict(synthetic=True,customer_file=False,document_id=did,revision_id=rid,plan_id=proposal['id'],request=request,approved=True,
        before_mm=[2,80,100],after_mm=[2,80,76],native_target_edges=len(records),orthographic_camera_verified=True,depiction_center_preserved=not args.confirm_uncoded,
        source_identity_confirmed=args.confirm_uncoded,fixed_vertex_verified=bool(confirmed),ocs_hatches_preserved=args.ocs_hatch,analytic_edge_hatches_preserved=args.edge_hatch,unchanged_hatch_association_verified=args.associated_hatch,unchanged_dimassoc_verified=args.dimassoc_hatch,
        source_unchanged=True,source_dim_mm=76,bom_verified=True,projected_note_verified=not args.ocs_hatch,
        unowned_parent_note_preserved=args.ocs_hatch,export_backend=job.get('backend'),download_http=r.status_code,download=str(backup.resolve()),download_url=base+job['download_url'],sha256=digest(backup),roundtrip='validated_roundtrip')
    storage.write_json(task/'receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
