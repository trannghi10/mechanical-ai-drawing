"""Read source packing envelopes without treating them as completed fit rules.

An explicit, hash-bound finished height is matched to a complete native block
of rectangular body/cap sections, then to a containing carton and its real DIM.
This exposes measured clearances/target height even when part ownership of all
foam, exploded views or manufacturing stages has not yet been established.
"""
import math
import re
from collections import defaultdict
from cad.frame_geometry import world
from cad.measured_features import rectangle
from cad.geometry import near
from bom.reader import normalized


def inspect(context):
    choices=context.get('design_choices',{})
    if choices.get('source_hash')!=context.get('source_hash'):return []
    height=next((c for c in choices.get('confirmed_choices',[]) if c.get('key')=='overall_height'),None)
    if not height:return []
    old,new=height.get('before_mm'),height.get('target_mm')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (old,new)):return []
    groups=context.get('part_graph',{}).get('packaging_groups',[])
    if len(groups)!=1 and not height.get('product_code'):return []
    records={e['ref']:e for e in context['entities']};rects=[];dims=[]
    for e in records.values():
        if e.get('review_only') or not e.get('geometry'):continue
        try:r=world(e)
        except ValueError:continue
        g=r['geometry']
        if e['type']=='LWPOLYLINE' and g.get('closed') and not any(any(p[2:]) for p in g.get('points',[])):
            points=[[p[0],p[1],g['elevation']] for p in g['points']]
            shape=rectangle(points)
            if not shape or any(abs(a[0]*a[1])>1e-7 for a in shape['axes']):continue
            low=[min(p[i] for p in points) for i in (0,1)];high=[max(p[i] for p in points) for i in (0,1)]
            rects.append(dict(ref=e['ref'],low=low,high=high,size=[b-a for a,b in zip(low,high)],
                sheet_ids=e.get('source_sheet_ids',[]),layout=e.get('layout'),frame=e.get('coordinate_frame'),geometry=g))
        elif e['type']=='DIMENSION' and e.get('dimension_type')==0 and g.get('text') in ('','<>') and near(abs(math.sin(math.radians(g['angle']))),1,1e-7):
            dims.append((e,r))
    by_root=defaultdict(list)
    for shape in rects:
        if shape['frame'] and shape['frame'].startswith('instance:'):
            by_root[shape['frame'].removeprefix('instance:')].append(shape)
    output=[]
    for group in groups:
        if height.get('product_code') and height['product_code']!=group['product_code']:continue
        cartons={}
        for e in records.values():
            if e.get('bom',{}).get('status')!='verified_template':continue
            for row in e['bom']['rows']:
                text=normalized(row.get('description',''))
                if row['part_code'] not in group['package_codes'] or not re.search(r'\bthung\s+(?:carton|go)\b',text):continue
                m=re.search(r'(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)',text)
                if m:cartons.setdefault(row['part_code'],set()).add(tuple(float(v.replace(',','.')) for v in m.groups()))
        for sid in group['sheet_ids']:
            products=[]
            for root,shapes in by_root.items():
                if root not in records or not all(sid in s['sheet_ids'] for s in shapes):continue
                children=[e for ref,e in records.items() if ref.startswith(root+'/')]
                # The envelope of an arbitrary collection is not a product.
                # Accept one rectangular body and at most one contacting cap;
                # internal source lines must remain within these sections.
                if not 1<=len(shapes)<=2 or any(e['type'] not in ('LINE','LWPOLYLINE','HATCH') for e in children):continue
                # A hatch is decoration of one proven section only when its
                # complete supported path matches that section in the same
                # local frame. Unknown associations/holes never become an
                # inferred product silhouette.
                from graph.packing_top_layers import same_boundary
                hatch_bindings=[];hatch_owners=set();valid_hatches=True
                for hatch in (e for e in children if e['type']=='HATCH'):
                    paths=(hatch.get('hatch_translation_geometry') or {}).get('paths',[])
                    owners=[s['ref'] for s in shapes if len(paths)==1 and
                            records[s['ref']].get('coordinate_frame')==hatch.get('coordinate_frame') and
                            same_boundary([p[:2] for p in records[s['ref']]['geometry']['points']],
                                          [p[:2] for p in paths[0].get('vertices',[])])]
                    if len(owners)!=1 or owners[0] in hatch_owners:
                        valid_hatches=False;break
                    hatch_owners.add(owners[0]);hatch_bindings.append(dict(ref=hatch['ref'],outline_ref=owners[0]))
                if not valid_hatches:continue
                if len(shapes)==2:
                    a,b=sorted(shapes,key=lambda s:s['low'][1])
                    if not near(a['high'][1],b['low'][1],1e-5) or min(a['size'][1],b['size'][1])>=old/4:continue
                    if min(a['high'][0],b['high'][0])-max(a['low'][0],b['low'][0])<=1e-5:continue
                low=[min(s['low'][i] for s in shapes) for i in (0,1)];high=[max(s['high'][i] for s in shapes) for i in (0,1)]
                if not near(high[1]-low[1],old,1e-5):continue
                if any(any(g[k][i]<low[i]-1e-5 or g[k][i]>high[i]+1e-5 for i in (0,1) for k in ('start','end'))
                       for e in children if e['type']=='LINE' and e.get('geometry') for g in [world(e)['geometry']]):continue
                products.append(dict(root=root,shapes=shapes,low=low,high=high,hatch_bindings=hatch_bindings))
            if len(products)!=1:continue
            product=products[0];matches=[]
            for box in rects:
                if sid not in box['sheet_ids'] or box['ref'].startswith(product['root']+'/'):continue
                if any(product['low'][i]<box['low'][i]-1e-5 or product['high'][i]>box['high'][i]+1e-5 for i in (0,1)):continue
                codes=[code for code,values in cartons.items() if len(values)==1 and any(near(box['size'],[size[0],size[2]],1e-5) or near(box['size'],[size[1],size[2]],1e-5) for size in values)]
                # Extension origins may have a drafting offset at one end.
                # Require an actual corner at the other end, both measured
                # height planes and unit DIM factor; matching Y alone could
                # select a completely unrelated dimension elsewhere.
                bindings=[e['ref'] for e,r in dims if sid in e.get('source_sheet_ids',[]) and e.get('layout')==box['layout'] and
                    near(abs(r.get('linear_factor',1)),1,1e-5) and
                    near(sorted(r['geometry'][k][1] for k in ('defpoint2','defpoint3')),[box['low'][1],box['high'][1]],1e-5) and
                    near(e.get('scaled_measurement'),box['size'][1],1e-5) and
                    any(near(r['geometry'][k][:2],p[:2],1e-5) for k in ('defpoint2','defpoint3') for p in box['geometry']['points'])]
                if len(codes)!=1 or len(bindings)!=1:continue
                clearances=[product['low'][1]-box['low'][1],box['high'][1]-product['high'][1]]
                target=new+sum(clearances)
                matches.append(dict(product_code=group['product_code'],carton_code=codes[0],sheet_id=sid,
                    source_product_root=product['root'],product_section_refs=[s['ref'] for s in product['shapes']],
                    product_hatch_bindings=product['hatch_bindings'],
                    carton_outline_ref=box['ref'],carton_dimension_ref=bindings[0],product_before_mm=old,product_target_mm=new,
                    carton_before_mm=box['size'][1],carton_target_mm=target,clearances_mm=clearances,
                    source_hash=context['source_hash'],status='source_matched_envelope',
                    execution_available=False,complete_packaging=False,
                    remaining='Chưa gắn đủ từng vật tư đệm, hình tách rời và mốc giữ; số đo này chưa cấp quyền duyệt backup.'))
            if len(matches)==1:output.extend(matches)
    return output
