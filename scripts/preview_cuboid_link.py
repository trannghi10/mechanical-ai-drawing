"""Prepare a source-checked, unconfirmed cuboid change picture; never apply CAD."""
import argparse,html,json,re,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.services import catalog_service as storage
from backend.services.cuboid_link_service import cached,context
from backend.services.change_service import DrawingChangePlan
from graph.cuboid_projections import inventory,drivers,clear_after
from cad.cuboid_projection import resize
from cad.frame_geometry import world,matrix
from cad.edit_engine import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('document_id','plan_id','candidate_id','body_id','vertex','output'):parser.add_argument(name)
    args=parser.parse_args();folder=storage.folder(args.document_id);source=folder/storage.read_status(args.document_id)['dxf'];fingerprint=digest(source)
    candidate=cached(args.document_id,args.candidate_id,fingerprint);c,_=context(args.document_id,candidate['targets'])
    body=next(b for b in inventory(c,proposed_part_code=candidate['part_code']) if b['id']==args.body_id)
    if not re.fullmatch('[0-9a-f]{32}',args.plan_id):raise ValueError('Plan ID không hợp lệ')
    proposal=json.loads((folder/'change-plans'/(args.plan_id+'.json')).read_text(encoding='utf8'))
    plan=DrawingChangePlan.model_validate(proposal.get('checked_preview_plan') or proposal['plan']);recipe,after=drivers(plan,c,body)[0]
    point=next(v['point'] for v in candidate['candidates'] if v['id']==args.body_id for v in v['vertices'] if v['label']==args.vertex)
    records={e['ref']:e for e in c['entities']};changed=resize(body,records,body['before_spec_mm'],after,'vertex',point)
    assert clear_after(c,body,changed),'Proposed datum does not preserve source contacts/clearance'
    before={r:world(records[r])['geometry'] for r in body['refs']}
    after_g={r:world(dict(records[r],geometry=g))['geometry'] for r,g in changed.items()}
    points=[g[k] for g in before.values() for k in ('start','end')];low=[min(p[i] for p in points) for i in (0,1)];high=[max(p[i] for p in points) for i in (0,1)]
    scale=min(400/(high[0]-low[0]),430/(high[1]-low[1]));fixed=matrix(records[body['refs'][0]]).transform(point)
    def panel(geometry,offset,title):
        def xy(p):return [offset+60+(p[0]-low[0])*scale,95+(high[1]-p[1])*scale]
        strokes=[]
        for ref,g in geometry.items():
            a,b=[xy(g[k]) for k in ('start','end')];color='#1767b2' if ref in changed else '#64748b'
            strokes.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{color}" stroke-width="2"/>')
        x,y=xy(fixed);strokes.append(f'<circle cx="{x}" cy="{y}" r="6" fill="#15803d"/><text x="{x+12}" y="{y-10}" fill="#166534" font-size="17">{html.escape(args.vertex)} · giữ cố định</text>')
        return f'<text x="{offset+55}" y="60" font-size="20" fill="#0f172a">{html.escape(title)}</text>'+''.join(strokes)
    text=f'{body["part_code"]} · {body["before_spec_mm"][-1]:g} → {after[-1]:g} mm · đề xuất chưa xác nhận'
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="620" viewBox="0 0 1080 620"><rect width="1080" height="620" fill="white"/><g font-family="sans-serif"><text x="35" y="27" font-size="18" fill="#334155">{html.escape(text)}</text>{panel(before,0,"CAD nguồn")}{panel(after_g,530,"Hình dự kiến sau sửa")}<text x="35" y="580" font-size="16" fill="#334155">Giữ các điểm nối nét CAD hiện có. Chưa lưu liên kết, chưa tạo bản sửa cho file khách.</text></g></svg>'
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True);(out/'proposal.svg').write_text(svg,encoding='utf8')
    from cad.vision import rasterize_svg
    (out/'proposal.png').write_bytes(rasterize_svg(svg,width=1500))
    receipt=dict(proposal_only=True,document_id=args.document_id,source_hash=fingerprint,part_code=body['part_code'],source_dimension_ref=recipe.dimension_ref,
        candidate_id=args.candidate_id,body_id=args.body_id,vertex=args.vertex,before_spec_mm=body['before_spec_mm'],after_spec_mm=after,
        boundary_contacts=body['boundary_contacts'],source_identity_confirmed=False,customer_revision_created=False,source_unchanged=digest(source)==fingerprint)
    assert receipt['source_unchanged'];storage.write_json(out/'proposal.json',receipt);print(json.dumps(receipt,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
