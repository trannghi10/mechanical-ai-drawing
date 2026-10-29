"""Exact visible/full cuboid wire graphs with a metric orthographic camera.

No hidden edge is invented. Nine visible edges (seven vertices) or all twelve
edges (eight vertices) must already exist as native LINEs. A general affine
parallelepiped is not enough: BOM lengths must give orthogonal equal-scale
camera rows. Geometry evidence does not establish a part code or fixed end.
"""
import copy
import itertools
from collections import defaultdict

import networkx as nx
import numpy as np
from cad.geometry import near

TOL=1e-5
BITS=list(itertools.product((0,1),repeat=3))


def components(records):
    groups=defaultdict(list)
    for e in records:
        if e.get('type')=='LINE' and e.get('geometry') and not e.get('review_only'):
            groups[(e.get('layout'),e.get('coordinate_frame'))].append(e)
    result=[]
    for (layout,frame),lines in groups.items():
        graph=nx.Graph();edges=defaultdict(list);points={}
        for e in lines:
            g=e['geometry'];a,b=[tuple(round(float(x),5) for x in g[k]) for k in ('start','end')]
            if not np.isfinite([*a,*b]).all() or near(list(a),list(b),TOL):continue
            pair=tuple(sorted((a,b)));edges[pair].append(e);graph.add_edge(a,b)
            for k,p in zip(('start','end'),(a,b)):points.setdefault(p,g[k])
        for vertices in nx.connected_components(graph):
            sub=graph.subgraph(vertices)
            if (len(vertices),sub.number_of_edges()) not in ((7,9),(8,12)):continue
            native=[edges[tuple(sorted((a,b)))] for a,b in sub.edges]
            if any(len(es)!=1 for es in native):continue
            refs=sorted(es[0]['ref'] for es in native)
            actual={p:np.asarray(points[p],dtype=float) for p in vertices}
            if np.ptp([p[2] for p in actual.values()])>TOL:continue
            maps=[]
            for corner in sorted(vertices):
                neighbors=sorted(sub.neighbors(corner))
                if len(neighbors)!=3:continue
                origin=actual[corner];vectors=np.column_stack([actual[n]-origin for n in neighbors])
                if np.linalg.matrix_rank(vectors[:2],tol=TOL)!=2:continue
                bits=BITS if len(vertices)==8 else [b for b in BITS if b!=(1,1,1)]
                mapping={};valid=True
                for b in bits:
                    p=origin+vectors@b
                    matches=[v for v in vertices if near(actual[v].tolist(),p.tolist(),TOL)]
                    if len(matches)!=1 or matches[0] in mapping:valid=False;break
                    mapping[matches[0]]=b
                if not valid or set(mapping)!=vertices:continue
                expected={tuple(sorted((a,b))) for a,b in itertools.combinations(vertices,2)
                          if sum(abs(x-y) for x,y in zip(mapping[a],mapping[b]))==1}
                if expected!={tuple(sorted(pair)) for pair in sub.edges}:continue
                maps.append(dict(origin=origin.tolist(),vectors=vectors.tolist(),
                                 vertices=[dict(point=actual[v].tolist(),bits=mapping[v]) for v in sorted(vertices)]))
            if maps:
                result.append(dict(refs=refs,layout=layout,coordinate_frame=frame,wire_kind='visible_three_faces' if len(vertices)==7 else 'complete_wire',
                    sheet_ids=sorted({sid for es in native for sid in es[0].get('source_sheet_ids',[])}),maps=maps))
    return result


def cameras(body,dimensions):
    sizes=np.asarray(dimensions,dtype=float)
    if sizes.shape!=(3,) or not np.isfinite(sizes).all() or min(sizes)<=TOL:return []
    result=[]
    for mapping in body['maps']:
        vectors=np.asarray(mapping['vectors'])[:2]
        for order in itertools.permutations(range(3)):
            camera=vectors/sizes[list(order)]
            metric=camera@camera.T;scale2=float(np.trace(metric)/2)
            # Source export noise is bounded relatively; this is a camera
            # metric check, never a confidence score or a fitted skew map.
            if scale2<=TOL*TOL or np.max(abs(metric-np.eye(2)*scale2))>1e-7*scale2:continue
            result.append(dict(mapping=mapping,dimension_order=list(order),camera=camera.tolist(),scale=scale2**.5,
                               relative_metric_error=float(np.max(abs(metric-np.eye(2)*scale2))/scale2)))
    return result


def resize(body,records,before,after,anchor='center',fixed_point=None):
    """Return only a unique native result under every valid camera labelling.

    Center is an explicit depiction datum. A fixed source vertex may instead
    be supplied; reversing a hidden physical axis may not change the result.
    Distinct results for equal BOM axes remain ambiguous and are rejected.
    """
    new=np.asarray(after,dtype=float);old=np.asarray(before,dtype=float)
    if new.shape!=(3,) or not np.isfinite(new).all() or min(new)<=TOL:raise ValueError('Kích thước hộp sau sửa không hợp lệ')
    if anchor not in ('center','vertex') or (anchor=='vertex')!=(fixed_point is not None):raise ValueError('Thiếu mốc giữ hình hộp chiếu')
    candidates=[]
    for fit in cameras(body,before):
        mapping=fit['mapping'];vectors=np.asarray(mapping['vectors']);order=fit['dimension_order']
        scaled=vectors*(new[list(order)]/old[list(order)])
        fixed=np.array([.5,.5,.5])
        if anchor=='vertex':
            matches=[v for v in mapping['vertices'] if near(v['point'],fixed_point,TOL)]
            if len(matches)!=1:continue
            fixed=np.asarray(matches[0]['bits'])
        changed={};valid=True
        for ref in body['refs']:
            e=records[ref];g=copy.deepcopy(e['geometry'])
            for key in ('start','end'):
                vertices=[v for v in mapping['vertices'] if near(v['point'],g[key],TOL)]
                if len(vertices)!=1:valid=False;break
                delta=(scaled-vectors)@(np.asarray(vertices[0]['bits'])-fixed)
                g[key]=(np.asarray(g[key])+delta).tolist()
            if not valid:break
            changed[ref]=g
        if not valid:continue
        # Reconstruct the original exact edge graph after the change. Every
        # edge must survive and retain the same metric camera and new sizes.
        updated=[dict(records[r],geometry=g) for r,g in changed.items()]
        rebuilt=components(updated)
        if len(rebuilt)!=1 or not cameras(rebuilt[0],after):continue
        if not any(all(near(g,other[r],TOL) for r,g in changed.items()) for other in candidates):candidates.append(changed)
    if len(candidates)!=1:raise ValueError('Hình hộp chưa có phép chiếu/mốc giữ cho kết quả duy nhất')
    return candidates[0]
