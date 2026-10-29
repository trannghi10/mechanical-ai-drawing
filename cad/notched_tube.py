"""Bind a cut offset to a closed six-edge L silhouette and true dimensions."""
import math
from cad.geometry import near
from cad.rounded_profile import TOL


def notched_openings(records,length,outside_sizes):
    lines=[e for e in records if e['type']=='LINE' and '/' not in e['ref']]
    dims=[e for e in records if e['type']=='DIMENSION' and e.get('geometry') and e.get('dimension_type',0)==0 and e.get('linear_factor',1)==1 and e['geometry']['text'] in ('','<>')]
    results=[]
    def ends(e):return [e['geometry']['start'],e['geometry']['end']]
    def touching(point,axis):
        return [e for e in lines if any(near(p,point,TOL) for p in ends(e)) and near(ends(e)[0][1-axis],ends(e)[1][1-axis],TOL)]
    def other(e,point):return next(p for p in ends(e) if not near(p,point,TOL))
    for dim in dims:
        g=dim['geometry'];axis=0 if near(g['angle']%180,0,TOL) else 1 if near(g['angle']%180,90,TOL) else None
        if axis is None:continue
        a,b=g['defpoint2'],g['defpoint3']
        caps=[e for e in lines if (near(ends(e)[0],a,TOL) and near(ends(e)[1],b,TOL)) or (near(ends(e)[1],a,TOL) and near(ends(e)[0],b,TOL))]
        if len(caps)!=1:continue
        for pa,pb in ((a,b),(b,a)):
            full=[e for e in touching(pa,1-axis) if near(math.dist(*ends(e)),length,TOL)]
            short=[e for e in touching(pb,1-axis) if max(outside_sizes)<math.dist(*ends(e))<length-TOL]
            for first in full:
                for second in short:
                    end1,end2=other(first,pa),other(second,pb)
                    lower=[e for e in touching(end1,axis) if any(near(math.dist(*ends(e)),v,TOL) for v in outside_sizes)]
                    steps=touching(end2,axis)
                    for base in lower:
                        for step in steps:
                            front1,front2=other(base,end1),other(step,end2)
                            closing=[e for e in lines if (near(ends(e)[0],front1,TOL) and near(ends(e)[1],front2,TOL)) or (near(ends(e)[1],front1,TOL) and near(ends(e)[0],front2,TOL))]
                            if len(closing)!=1 or not near(front1[axis],front2[axis],TOL):continue
                            if not any(near(d['geometry']['defpoint2'],front1,TOL) and near(d['geometry']['defpoint3'],front2,TOL) or near(d['geometry']['defpoint2'],front2,TOL) and near(d['geometry']['defpoint3'],front1,TOL) for d in dims):continue
                            refs=[caps[0]['ref'],first['ref'],base['ref'],closing[0]['ref'],step['ref'],second['ref']]
                            if len(set(refs))!=6:continue
                            results.append(dict(offset_dimension=dim,opening_length=math.dist(*ends(second)),step_length=math.dist(*ends(step)),evidence_refs=refs))
    return results
