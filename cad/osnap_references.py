"""Bounded structural reader for DIMASSOC hasLastPointRef nesting."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PointReference:
    start:int
    own_end:int
    end:int
    child:object=None


def point_references(pairs):
    starts=[i for i,tag in enumerate(pairs) if tag==(1,'AcDbOsnapPointRef')]
    if len(starts)>64:raise ValueError('DIMASSOC quá nhiều point reference')
    segments=[(start,starts[i+1] if i+1<len(starts) else len(pairs)) for i,start in enumerate(starts)]
    def read(index,depth=0):
        if index>=len(segments):raise ValueError('DIMASSOC thiếu last point reference')
        if depth>4:raise ValueError('DIMASSOC last point reference lồng quá sâu')
        start,end=segments[index];tags=pairs[start:end]
        flags=[v for c,v in tags if c==75]
        if len(flags)!=1 or flags[0] not in ('0','1') or any(c==1 for c,v in tags[1:]):
            raise ValueError('DIMASSOC hasLastPointRef không hợp lệ')
        child=None;next_index=index+1
        if flags[0]=='1':child,next_index=read(next_index,depth+1)
        return PointReference(start,end,child.end if child else end,child),next_index
    roots=[];index=0
    while index<len(segments):
        node,index=read(index);roots.append(node)
    return roots
