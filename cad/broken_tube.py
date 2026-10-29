"""Prove a cropped tube illustration, keeping nominal and measured sizes apart."""
import math
import re
from cad.frame_geometry import world
from cad.geometry import near
from graph.packing_side_layers import rect
from bom.reader import normalized

TOL=1e-4

def tube_spec(raw):
    n=r'(\d+(?:[.,]\d+)?)'
    m=re.search(r'sat hop\s*(?:(?:vuong|chu nhat|rong)\s+)*'+n+r'\s*[x×]\s*'+n+r'\s*[x×]\s*'+n+r'\s*[x×]\s*'+n,normalized(raw))
    if not m:return None
    values=tuple(float(v.replace(',','.')) for v in m.groups())
    w,d,t,length=values
    return values if 0<t<min(w,d)/2 and length>max(w,d)*10 else None

def label(text):
    m=re.fullmatch(r'(\d+(?:[.,]\d+)?)(%%[Pp]\d+(?:[.,]\d+)?)?',text or '')
    return (float(m[1].replace(',','.')),m[2] or '') if m else None

def source_views(context, code, spec):
    records={e['ref']:e for e in context['entities']}
    nodes=[n for n in context.get('part_graph',{}).get('nodes',[]) if n['code']==code]
    sheets={s for n in nodes for s in n.get('detail_sheets',[])}
    w,depth,gauge,length=spec
    features=context.get('source_features',{}).get('features',[])
    sections=[f for f in features if f.get('part_code')==code and f.get('ownership_proof') in ('unique_source_detail_sheet','native_part_identity') and
              len(f['refs'])==1 and all(ref in records for ref in f['refs']) and len(f['dimensions'])==2 and near(sorted(d['measurement'] for d in f['dimensions']),sorted([w,depth]),TOL)]
    result=[]
    for dim in records.values():
        parsed=label(dim.get('geometry',{}).get('text'))
        if dim['type']!='DIMENSION' or dim.get('review_only') or dim.get('dimension_type')!=0 or not parsed or not near(parsed[0],length,TOL):continue
        sids=sheets.intersection(dim.get('source_sheet_ids',[]))
        owned=[f for f in sections if sids.intersection(f['sheet_ids'])]
        if len(owned)!=1:continue
        section=rect(records[owned[0]['refs'][0]])
        if not section:continue
        # The hollow section must actually exist; stock text alone cannot
        # authorize changing an unseen tube or a solid rectangular bar.
        holes=[e for e in records.values() if e['ref']!=section['ref'] and sids.intersection(e.get('source_sheet_ids',[])) and rect(e) and
               near(rect(e)['low'],[v+gauge for v in section['low']],TOL) and near(rect(e)['high'],[v-gauge for v in section['high']],TOL)]
        if len(holes)!=1:continue
        d=world(dim);g=d['geometry'];angle=math.radians(g['angle']);axis=[math.cos(angle),math.sin(angle)];normal=[-axis[1],axis[0]]
        project=lambda p,v:sum(a*b for a,b in zip(p[:2],v))
        ends=sorted(project(g[k],axis) for k in ('defpoint2','defpoint3'));measured=ends[1]-ends[0]
        if not 0<measured<length/2:continue
        items=[]
        for e in records.values():
            if not sids.intersection(e.get('source_sheet_ids',[])) or e.get('review_only') or not e.get('geometry'):continue
            try:items.append(world(e))
            except ValueError:continue
        caps=[]
        for e in items:
            if e['type']!='LINE':continue
            a,b=e['geometry']['start'],e['geometry']['end'];x=[project(p,axis) for p in (a,b)]
            if not near(x[0],x[1],TOL) or not any(near(x[0],end,TOL) for end in ends):continue
            cross=sorted(project(p,normal) for p in (a,b))
            if any(near(cross[1]-cross[0],v,TOL) for v in (w,depth)):caps.append((e,x[0],cross))
        if len(caps)!=2 or not near(sorted(x for _,x,_ in caps),ends,TOL) or not near(caps[0][2],caps[1][2],TOL):continue
        low,high=caps[0][2];face_width=high-low
        breaks=[]
        for e in items:
            if e['type']!='SPLINE':continue
            cp=e['geometry'].get('control_points',[])
            if len(cp)<4 or e['geometry'].get('weights'):continue
            xs=[project(p,axis) for p in cp];ys=[project(p,normal) for p in cp]
            if min(xs)>ends[0]+measured*.1 and max(xs)<ends[1]-measured*.1 and max(xs)-min(xs)<face_width and min(ys)<low and max(ys)>high:
                breaks.append(e)
        if len(breaks)!=2:continue
        a,b=[e['geometry'] for e in breaks];delta=[y-x for x,y in zip(a['control_points'][0],b['control_points'][0])]
        if not 0<abs(project(delta,axis))<face_width/4 or abs(project(delta,normal))>TOL:continue
        if any(a.get(k)!=b.get(k) for k in ('degree','flags','knots','weights')):continue
        if any(not near([[v+t for v,t in zip(p,delta)] for p in a.get(k,[])],b.get(k,[]),TOL) for k in ('control_points','fit_points')):continue
        # Both outside edges must terminate at each end cap and the central
        # break region. This rejects a decorative pair of remote splines.
        joined=[]
        bounds=[project(p,axis) for e in breaks for p in e['geometry']['control_points']]
        for end in ends:
            for cross in (low,high):
                hits=[]
                for e in items:
                    if e['type']!='LINE':continue
                    p,q=e['geometry']['start'],e['geometry']['end']
                    for p,q in ((p,q),(q,p)):
                        if near([project(p,axis),project(p,normal)],[end,cross],TOL) and near(project(q,normal),cross,TOL) and min(bounds)-TOL<=project(q,axis)<=max(bounds)+TOL:
                            hits.append(e['ref'])
                if len(set(hits))!=1:break
                joined.append(hits[0])
        if len(joined)!=4:continue
        result.append(dict(dimension_ref=dim['ref'],part_code=code,source_nominal_mm=length,native_measured_span_mm=measured,
            suffix=parsed[1],section_refs=[section['ref'],holes[0]['ref']],break_refs=[e['ref'] for e in breaks],end_cap_refs=[e['ref'] for e,_,_ in caps],
            joined_edge_refs=joined,sheet_ids=sorted(sids),representation='cropped_nominal_tube_view',geometry_is_full_length=False))
    return result

def valid_binding(binding, ref, before, after, source_hash):
    if not binding or binding.get('source_hash')!=source_hash or binding.get('dimension_ref')!=ref or binding.get('status')!='confirmed_cropped_tube_cut':return False
    if not near(binding.get('before'),before) or not near(binding.get('after'),after):return False
    if not near({k:v for k,v in before.items() if k!='text'},{k:v for k,v in after.items() if k!='text'}):return False
    old,new=label(before.get('text')),label(after.get('text'))
    return bool(old and new and old[1]==new[1] and near(old[0],binding.get('source_nominal_mm'),TOL) and near(new[0],binding.get('target_nominal_mm'),TOL) and
                min(old[0],new[0])>binding.get('native_measured_span_mm',float('inf')) and binding.get('geometry_is_full_length') is False and len(binding.get('break_refs',[]))==2)
