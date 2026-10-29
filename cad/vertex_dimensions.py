"""Follow actual source vertices with unambiguous geometry displacements."""
import copy
import json
from cad.geometry import near
from cad.frame_geometry import world,local_geometry
from cad.edit_engine import Operation


def synchronize(context,operations,sheet_ids):
    by={o.ref:o for o in operations};vertices=[];result=[]
    for e in context['entities']:
        if not set(sheet_ids).intersection(e.get('source_sheet_ids',[])) or e.get('review_only') or e['type'] not in ('LINE','LWPOLYLINE','POLYLINE') or not e.get('geometry'):continue
        updated=copy.deepcopy(e);op=by.get(e['ref'])
        if op:
            if op.action!='replace_geometry':continue
            updated['geometry']=json.loads(op.after)
        try:a,b=world(e)['geometry'],world(updated)['geometry']
        except ValueError:continue
        def points(g):
            return [g['start'],g['end']] if e['type']=='LINE' else [[p[0],p[1],g['elevation']] for p in g['points']]
        before,after=points(a),points(b)
        if len(before)!=len(after):continue
        vertices.extend((e.get('layout'),set(e.get('source_sheet_ids',[])),p,q) for p,q in zip(before,after))
    for e in context['entities']:
        if e['type']!='DIMENSION' or e['ref'] in by or e.get('review_only') or not e.get('geometry') or not set(sheet_ids).intersection(e.get('source_sheet_ids',[])):continue
        if e.get('dimension_type') not in (0,1):continue
        g=world(e)['geometry'];moves=[]
        for key in ('defpoint2','defpoint3'):
            hits=[q for layout,sids,p,q in vertices if layout==e.get('layout') and sids.intersection(e.get('source_sheet_ids',[])) and near(p,g[key],1e-5)]
            if not hits or any(not near(q,hits[0],1e-5) for q in hits):break
            moves.append(hits[0])
        if len(moves)!=2 or near(moves,[g['defpoint2'],g['defpoint3']],1e-6):continue
        if g.get('text') not in ('','<>'):raise ValueError('DIM theo đỉnh CAD đang ghi đè số: '+e['ref'])
        after=copy.deepcopy(g)
        after['defpoint2'],after['defpoint3']=moves;after['text']='<>'
        result.append(Operation(ref=e['ref'],action='replace_geometry',before=json.dumps(e['geometry']),
            after=json.dumps(local_geometry(e,after)),xyz=[],reason='Đồng bộ DIM theo hai đỉnh CAD nguồn có chuyển động duy nhất'))
    return result
