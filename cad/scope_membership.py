"""Assign source scopes to children of an INSERT spanning several drawings.

The detected frames are inputs, never changed here. Unknown extents remain in
the enclosing scope; they must not disappear from subsequent coverage checks.
"""
from itertools import product
import math
from ezdxf import bbox

TOL=1e-5


def assign(records,targets,membership,placements,doc,review_only_ids=(),part_codes=()):
    from cad.sheets import overlaps
    sheets={t['id']:t for t in targets if t['kind']=='sheet'}
    review=set(review_only_ids);cache=bbox.Cache();local={};result=[]
    from cad.part_identity import entity_identity
    # A verified native part is indivisible. Keep all its source holes/DIMs,
    # including ones beyond the frame edge, whenever the part intersects it.
    # Only the drawing container is partitioned, not the physical part itself.
    codes=set(part_codes)
    parts={ref for ref,(entity,_) in placements.items() if entity.dxftype()=='INSERT' and entity_identity(entity,codes)}
    def bound_owner(ref):
        current=ref;owner=ref
        while current:
            if current in parts:owner=current
            current=current.rsplit('/',1)[0] if '/' in current else None
        return owner

    def extent(ref):
        entity,matrix=placements[ref];handle=entity.dxf.handle
        if handle not in local:
            try:
                bound=bbox.extents([entity],fast=True,cache=cache)
                local[handle]=(list(bound.extmin),list(bound.extmax)) if bound.has_data else None
            except (ValueError,TypeError,AttributeError,NotImplementedError,OverflowError):local[handle]=None
        bound=local[handle]
        if bound is None:return None
        points=list(matrix.transform_vertices(product(*zip(*bound))))
        if not all(math.isfinite(v) for p in points for v in p):return None
        return [min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points)]

    # Most part INSERTs fit entirely in a frame. Only split containers need
    # per-child extents; native handles cache definition-local bounds across
    # repeated instances, while each placement uses its own parent matrix.
    split={}
    for root,ids in membership.items():
        if root not in placements or doc.entitydb[root].dxftype()!='INSERT':continue
        candidates=[sid for sid in ids if sid in sheets]
        if not candidates:continue
        outer=extent(root)
        if outer is None:continue
        for sid in candidates:
            box=sheets[sid]['bbox']
            if not (box[0]-TOL<=outer[0] and box[1]-TOL<=outer[1] and outer[2]<=box[2]+TOL and outer[3]<=box[3]+TOL):
                split.setdefault(root,set()).add(sid)
    for record in records:
        ref=record['ref'];root=ref.split('/')[0];ids=set(membership.get(root,()))
        if '/' in ref and root in split:
            bound=extent(bound_owner(ref))
            if bound is not None:
                ids-={sid for sid in split[root] if not overlaps(bound,sheets[sid]['bbox'])}
        if not ids:continue
        record['source_sheet_ids']=sorted(ids)
        if ids<=review:record['review_only']=True
        else:record.pop('review_only',None)
        result.append(record)
    return result
