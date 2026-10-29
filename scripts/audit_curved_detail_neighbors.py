"""Read source-native neighbours of verified clipped details; never edit CAD."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from dotenv import load_dotenv
from backend.services import catalog_service as storage
from backend.services.change_service import DrawingChangePlan
from verify_dauphine_core_stage import checked_context
from graph.curved_detail_contacts import proofs
from cad.edit_engine import digest
from cad.frame_geometry import world
from backend.services.geometry_retrieval import local_bounds


def render_fit(detail):
    import math,copy
    fit=detail['fit_proposals'][0];proof=detail['proof'];records={e['ref']:e for e in detail['neighbours']}
    changes={proof['bindings'][key]:g for key,g in proof['changes'].items()}
    tube=set(fit['outer_refs']+fit['inner_refs']);strip={proof['outer_arc_ref'],proof['outer_leg_ref'],*changes}
    box=detail['query_box'];width=box[2]-box[0];height=box[3]-box[1];result=['<svg xmlns="http://www.w3.org/2000/svg" width="1590" height="650" viewBox="0 0 1590 650"><rect width="1590" height="650" fill="white"/>']
    titles=['Nguồn CAD','Sau đổi dải cong — hộp giữ vị trí','Đề xuất giữ khe — chưa xác nhận']
    for i,title in enumerate(titles):
        result.append(f'<text x="{i*530+20}" y="30" font-family="sans-serif" font-size="18">{title}</text>')
        result.append(f'<g transform="translate({i*530+10} 55) scale({510/max(width,height)}) translate({-box[0]} {box[3]})">')
        for ref,e in records.items():
            if ref not in tube|strip and e['type'] not in ('CIRCLE','ARC'):continue
            g=copy.deepcopy(changes.get(ref,e.get('geometry',{})) if i else e.get('geometry',{}))
            if not g:continue
            if i==2 and ref in tube:
                for key in ('start','end'):g[key]=[a+b for a,b in zip(g[key],fit['delta'])]
            color='#008c95' if i==2 and ref in tube else '#df6c13' if i and ref in changes else '#334155' if ref in tube|strip else '#aeb7c2'
            style=f'stroke="{color}" stroke-width=".5" fill="none"'
            if e['type']=='LINE':
                a,b=g['start'],g['end'];result.append(f'<line x1="{a[0]}" y1="{-a[1]}" x2="{b[0]}" y2="{-b[1]}" {style}/>')
            elif e['type']=='CIRCLE':result.append(f'<circle cx="{g["center"][0]}" cy="{-g["center"][1]}" r="{g["radius"]}" {style}/>')
            elif e['type']=='ARC':
                x,y=g['center'][:2];r=g['radius'];a,b=[math.radians(g[k]) for k in ('start_angle','end_angle')];span=(g['end_angle']-g['start_angle'])%360
                result.append(f'<path d="M {x+r*math.cos(a)} {-y-r*math.sin(a)} A {r} {r} 0 {int(span>180)} 0 {x+r*math.cos(b)} {-y-r*math.sin(b)}" {style}/>')
        result.append('</g>')
        radial=fit['source_radial_gap_mm'] if i!=1 else fit['fixed_position_radial_gap_mm'];floor=fit['source_floor_gap_mm'] if i!=1 else fit['fixed_position_floor_gap_mm']
        result.append(f'<text x="{i*530+20}" y="590" font-family="sans-serif" font-size="16">Khe kê {floor:.3f} mm · Khe hướng kính {radial:.3f} mm</text>')
    result.append('<text x="20" y="630" font-family="sans-serif" font-size="15" fill="#705022">Chỉ đề xuất chuyển hộp màu xanh; chốt và liên kết cả cụm chưa được xác nhận. Chưa sửa DWG khách.</text></svg>')
    return ''.join(result)


def fit_proposals(proof,neighbours,context,records):
    import networkx as nx
    import numpy as np
    from cad.broken_tube import tube_spec
    from cad.geometry import near
    from cad.clipped_detail_fit import propose
    graph=nx.Graph();edge_refs={};native_points={}
    for e in neighbours:
        if e['type']!='LINE' or not e.get('geometry'):continue
        a,b=[tuple(round(v,5) for v in e['geometry'][k][:2]) for k in ('start','end')]
        if a==b:continue
        native_points.setdefault(a,e['geometry']['start'][:2]);native_points.setdefault(b,e['geometry']['end'][:2])
        graph.add_edge(a,b);edge_refs.setdefault(tuple(sorted((a,b))),[]).append(e['ref'])
    rectangles=[]
    for cycle in nx.cycle_basis(graph):
        if len(cycle)!=4:continue
        points=np.asarray([native_points[p] for p in cycle]);low=points.min(axis=0);high=points.max(axis=0)
        if min(high-low)<=1e-5 or any(sum(abs(a-b)>1e-5)!=1 for a,b in zip(points,np.roll(points,-1,axis=0))):continue
        refs=sorted(r for a,b in zip(cycle,cycle[1:]+cycle[:1]) for r in edge_refs[tuple(sorted((a,b)))])
        rectangles.append(dict(points=points,low=low,high=high,refs=refs))
    choices=context.get('design_choices',{});result=[]
    factor=records[proof['bindings']['radial_dimension']]['linear_factor']
    for choice in choices.get('confirmed_choices',[]):
        if choice.get('key')!='assembly_tube_gauge_correction' or not set(choice.get('sheet_ids',[])).intersection(proof['sheet_ids']):continue
        code=choice['part_code'];specs={tube_spec(r['description']) for e in records.values() for r in e.get('bom',{}).get('rows',[]) if r['part_code']==code}
        if len(specs)!=1 or None in specs:continue
        w,h,t,length=next(iter(specs));pairs=[]
        for outer in rectangles:
            if not near(((outer['high']-outer['low'])*factor).tolist(),[w,h],1e-4):continue
            for inner in rectangles:
                if near(((inner['high']-inner['low'])*factor).tolist(),[w-2*t,h-2*t],1e-4) and near((outer['high']+outer['low']).tolist(),(inner['high']+inner['low']).tolist(),1e-4):pairs.append((outer,inner))
        if len(pairs)!=1:continue
        outer,inner=pairs[0];arc=world(records[proof['bindings']['inner_arc']])['geometry'];floor=world(records[proof['bindings']['inner_leg']])['geometry']
        points=[[x,y,arc['center'][2]] for x,y in outer['points']]
        try:fit=propose(points,arc,proof['changes']['inner_arc'],floor,proof['changes']['inner_leg'],factor)
        except ValueError as error:result.append(dict(proposed_part_code=code,status='unresolved_fit',reason=str(error)));continue
        contacts=[];moved=np.asarray(fit['points'])[:,:2]
        for e in neighbours:
            if e['type']!='CIRCLE' or e['ref']==proof['circle_ref'] or not e.get('geometry'):continue
            g=e['geometry']
            if not near(g.get('extrusion'),[0,0,1]) or abs(g['center'][2]-arc['center'][2])>1e-5:continue
            center=np.asarray(g['center'][:2]);source_distance=float(np.linalg.norm(center-np.clip(center,outer['low'],outer['high'])))-g['radius']
            if abs(source_distance)>1e-4:continue
            target_distance=float(np.linalg.norm(center-np.clip(center,moved.min(axis=0),moved.max(axis=0))))-g['radius']
            contacts.append(dict(ref=e['ref'],source_gap_mm=source_distance*factor,proposed_gap_if_circle_fixed_mm=target_distance*factor,
                status='requires_whole_group_correspondence' if abs(target_distance-source_distance)>1e-4 else 'preserved'))
        result.append(dict(fit,proposed_part_code=code,bom_spec_mm=[w,h,t,length],outer_refs=outer['refs'],inner_refs=inner['refs'],
            identity_status='candidate_cross_section_matches_bom_and_existing_detail_choice',source_circle_contacts=contacts,
            whole_group_confirmed=False,customer_revision_created=False))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('document_id');p.add_argument('plan_id');p.add_argument('--output',required=True);args=p.parse_args()
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    folder=storage.folder(args.document_id);source=folder/storage.read_status(args.document_id)['dxf'];before=digest(source)
    proposal=json.loads((folder/'change-plans'/(args.plan_id+'.json')).read_text(encoding='utf8'))
    c=checked_context(source,proposal);plan=DrawingChangePlan.model_validate(proposal.get('checked_preview_plan') or proposal['plan']);records={e['ref']:e for e in c['entities']}
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True);details=[]
    for i,proof in enumerate(proofs(plan,c)):
        clip=world(records[proof['circle_ref']])['geometry'];x,y=clip['center'][:2];r=clip['radius'];box=[x-r*1.1,y-r*1.1,x+r*1.1,y+r*1.1];neighbours=[]
        for e in c['entities']:
            if not set(e.get('source_sheet_ids',[])).intersection(proof['sheet_ids']):continue
            try:w=world(e);bounds=local_bounds(w)
            except ValueError:continue
            if bounds is None or bounds[1][0]<box[0] or bounds[0][0]>box[2] or bounds[1][1]<box[1] or bounds[0][1]>box[3]:continue
            neighbours.append({k:w[k] for k in ('ref','type','geometry','text','source_sheet_ids','coordinate_frame','dimension_association') if k in w})
        from cad.sheets import render_sheet
        from cad.vision import rasterize_svg
        svg=render_sheet(source,dict(layout=records[proof['circle_ref']]['layout'],bbox=box))
        (output/f'detail-{i+1}.svg').write_text(svg,encoding='utf8');(output/f'detail-{i+1}.png').write_bytes(rasterize_svg(svg,width=1600))
        details.append(dict(proof=proof,query_box=box,neighbours=neighbours,fit_proposals=fit_proposals(proof,neighbours,c,records)))
    result=dict(document_id=args.document_id,plan_id=args.plan_id,source_hash=before,source_unchanged=digest(source)==before,details=details,
                policy='Read-only source geometry and existing proofs. Query bounds/pictures do not authorize edits or identify adjacent parts.')
    assert result['source_unchanged'];storage.write_json(output/'audit.json',result)
    for i,detail in enumerate(details):
        if detail['fit_proposals'] and detail['fit_proposals'][0]['status']=='unconfirmed_geometric_fit':
            svg=render_fit(detail);(output/f'fit-{i+1}.svg').write_text(svg,encoding='utf8');(output/f'fit-{i+1}.png').write_bytes(rasterize_svg(svg,width=1590))
    print(json.dumps(dict(detail_count=len(details),neighbour_counts=[len(d['neighbours']) for d in details],fits=[d['fit_proposals'] for d in details],output=str(output),source_unchanged=True),ensure_ascii=True))


if __name__=='__main__':main()
