"""Bounded, source-scoped discovery of geometry omitted from model context.

Image bounds locate candidates only. An edit still needs the exact source
snapshot through geometry_requests and the normal checked CAD transaction.
"""
import math
from itertools import product
from collections import Counter
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ezdxf.math import Matrix44
from cad.geometry import near


class GeometryQuery(BaseModel):
    model_config=ConfigDict(extra='forbid')
    target_id:str
    region:list[float]=Field(default_factory=list,max_length=4)
    types:list[str]=Field(default_factory=list,max_length=12)
    layer:str=''
    offset:int=Field(default=0,ge=0)
    limit:int=Field(default=40,ge=1,le=80)

    @model_validator(mode='after')
    def valid_region(self):
        if self.region and (len(self.region)!=4 or not all(math.isfinite(x) and 0<=x<=1000 for x in self.region)
                or self.region[0]>=self.region[2] or self.region[1]>=self.region[3]):
            raise ValueError('region phải là [left,top,right,bottom] trong ảnh 0..1000')
        return self


def local_bounds(entity):
    g=entity.get('geometry') or entity.get('radial_geometry') or {}
    points=[]
    kind=entity['type']
    if kind=='LINE':points=[g.get('start'),g.get('end')]
    elif kind in ('LWPOLYLINE','POLYLINE'):points=[[p[0],p[1],g.get('elevation',0)] for p in g.get('points',[])]
    elif kind in ('CIRCLE','ARC') and g:
        c=g['center'];r=g['radius'];points=[[c[0]-r,c[1]-r,c[2]],[c[0]+r,c[1]+r,c[2]]]
    elif kind=='ELLIPSE' and g:
        c=g['center'];r=math.sqrt(sum(v*v for v in g['major_axis']))
        if abs(g['major_axis'][2])<1e-7 and near(g.get('extrusion',[0,0,1]),[0,0,1]):
            x,y=g['major_axis'][:2];ratio=g['ratio']
            # Exact full-ellipse bounds also enclose a partial ellipse. The
            # major-axis endpoints alone omit the entire minor-axis extent.
            dx,dy=math.hypot(x,y*ratio),math.hypot(y,x*ratio)
            points=[[c[0]-dx,c[1]-dy,c[2]],[c[0]+dx,c[1]+dy,c[2]]]
        else:
            points=[[c[0]-r,c[1]-r,c[2]-r],[c[0]+r,c[1]+r,c[2]+r]]
    elif kind=='SPLINE':points=g.get('control_points',[])+g.get('fit_points',[])
    elif kind=='LEADER':points=g.get('vertices',entity.get('leader_vertices',[]))
    elif kind=='DIMENSION':points=[g.get(k) for k in ('defpoint','defpoint2','defpoint3','defpoint4')]
    if not any(p is not None for p in points):
        points=[entity.get('position') or entity.get('text_placement',{}).get('anchor')]
    points=[p for p in points if p is not None and len(p)>=3 and all(math.isfinite(x) for x in p[:3])]
    return [[min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)]] if points else None


def locations(entity,targets):
    bounds=local_bounds(entity)
    if not bounds:return []
    rows=entity.get('frame_to_layout')
    matrix=Matrix44([v for row in rows for v in row]) if rows else Matrix44()
    points=[matrix.transform(p) for p in product(*zip(*bounds))]
    extent=[min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points)]
    result=[]
    for t in targets:
        b=t.get('bbox')
        if not b or t.get('layout')!=entity.get('layout'):continue
        w,h=b[2]-b[0],b[3]-b[1]
        if w<=0 or h<=0 or extent[2]<b[0] or extent[0]>b[2] or extent[3]<b[1] or extent[1]>b[3]:continue
        result.append([t['id'],round(1000*(extent[0]-b[0])/w,2),round(1000*(b[3]-extent[3])/h,2),
                       round(1000*(extent[2]-b[0])/w,2),round(1000*(b[3]-extent[1])/h,2)])
    return result


def discovery_index(entities,targets,tile_target_ids=None):
    """A fixed 4x4 tile index; no enormous list of decorative source refs."""
    counts=Counter();unlocated=Counter();scopes={}
    for e in entities:
        for sid in e.get('source_sheet_ids',[]):
            scopes.setdefault(sid,Counter())[e['type']]+=1
        locs=locations(e,targets)
        if not locs:unlocated[e['type']]+=1
        for tid,x0,y0,x1,y1 in locs:
            if tile_target_ids is not None and tid not in tile_target_ids:continue
            # Each entity belongs to the tile containing its bounds center.
            col=min(3,max(0,int((x0+x1)/500)));row=min(3,max(0,int((y0+y1)/500)))
            counts[(tid,col,row,e['type'])]+=1
    tiles={}
    for (tid,col,row,kind),count in sorted(counts.items()):
        tiles.setdefault((tid,col,row),{})[kind]=count
    return dict(deferred_count=len(entities),types=dict(Counter(e['type'] for e in entities)),
                tiles=[dict(target_id=tid,region=[col*250,row*250,(col+1)*250,(row+1)*250],types=kinds)
                       for (tid,col,row),kinds in tiles.items()],unlocated_types=dict(unlocated),
                scopes=[dict(target_id=sid,types=dict(types)) for sid,types in sorted(scopes.items())],
                retrieval='geometry_queries selects a source-bound page by target_id, region (image 0..1000), types, layer, offset, limit. Empty region searches the whole target, including unlocated entities. Use returned refs with geometry_requests for exact CAD snapshots; image coordinates never authorize edits.')


def resolve_queries(context,queries):
    targets={t['id']:t for t in context['targets']};refs=set();pages=[]
    for query in queries:
        if query.target_id not in targets:raise ValueError('AI yêu cầu vùng ngoài bản vẽ đã chọn/liên quan')
        matches=[]
        for e in context['entities']:
            if query.types and e['type'] not in query.types:continue
            if query.layer and e.get('layer')!=query.layer:continue
            locs=locations(e,[targets[query.target_id]])
            membership=e.get('source_sheet_ids',[])
            in_scope=query.target_id in membership or bool(locs) or (len(targets)==1 and not membership)
            if not in_scope:continue
            if query.region:
                a=query.region
                if not any(not (b[3]<a[0] or b[1]>a[2] or b[4]<a[1] or b[2]>a[3]) for b in locs):continue
            matches.append(e['ref'])
        matches.sort();selected=matches[query.offset:query.offset+query.limit];refs.update(selected)
        end=query.offset+len(selected)
        pages.append(dict(query=query.model_dump(),match_count=len(matches),refs=selected,
                          next_offset=end if end<len(matches) else None))
    return refs,pages
