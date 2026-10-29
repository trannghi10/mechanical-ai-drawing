"""Isolated, offline BRep verification using FreeCAD's bundled Python.

Input is numeric geometry only. Never evaluates model-generated Python.
"""
import json
import math
import sys
import FreeCAD as App
import Part


def face(profile):
    edges=[]
    for segment in profile['segments']:
        kind,a,b,c,r=segment[:5]
        va,vb=App.Vector(*a,0),App.Vector(*b,0)
        if kind=='LINE':edges.append(Part.makeLine(va,vb))
        elif kind=='ARC':
            if len(segment)==6:mid=App.Vector(*segment[5],0)
            else:
                vx,vy=(a[0]+b[0])/2-c[0],(a[1]+b[1])/2-c[1]
                factor=r/math.hypot(vx,vy)
                mid=App.Vector(c[0]+vx*factor,c[1]+vy*factor,0)
            edges.append(Part.Arc(va,mid,vb).toShape())
        elif kind=='NURBS':
            data=segment[5];degree=data['degree'];weights=data['weights']
            poles=[App.Vector(*q,0) for q in data['poles']]
            if len(poles)!=degree+1 or len(weights)!=len(poles) or any(w<=0 for w in weights):
                raise ValueError('Invalid rational Bezier span')
            curve=Part.BSplineCurve()
            curve.buildFromPolesMultsKnots(poles,[degree+1,degree+1],[0.,1.],False,degree,weights)
            edge=curve.toShape()
            if edge.Vertexes[0].Point.distanceToPoint(va)>1e-6 or edge.Vertexes[-1].Point.distanceToPoint(vb)>1e-6:
                raise ValueError('NURBS endpoints do not match source')
            edges.append(edge)
        else:raise ValueError('Unsupported edge')
    wire=Part.Wire(Part.__sortEdges__(edges))
    if not wire.isClosed() or not wire.isValid():raise ValueError('Open or invalid source wire')
    result=Part.Face(wire)
    if any(segment[0]=='NURBS' for segment in profile['segments']):
        # Rebuild the original rational curves, never the locator chords.
        # BOPCheck also rejects self-intersecting exact wires/faces.
        result.check(True)
    raw_holes=profile.get('holes',[])
    holes=[]
    for h in raw_holes:
        dup=None
        for existing in holes:
            if math.hypot(existing['center'][0]-h['center'][0],existing['center'][1]-h['center'][1])<1e-4:
                dup=existing;break
        if dup is not None:
            dup['radius']=max(dup['radius'],h['radius'])
        else:
            holes.append(dict(h))
    for h in holes:
        if h['radius']<=0:raise ValueError('Invalid hole radius')
        hole=Part.Face(Part.Wire([Part.makeCircle(h['radius'],App.Vector(*h['center'],0))]))
        if any(hole.OuterWire.distToShape(wire)[0]<=1e-7 for wire in result.Wires):
            raise ValueError('Hole touches/crosses an existing boundary')
        intersection=result.common(hole)
        if abs(intersection.Area-hole.Area)>1e-7*max(1,hole.Area):raise ValueError('Hole crosses outline or another hole')
        result=result.cut(hole)
    if not result.isValid() or result.Area<=0 or len(result.Faces)!=1:raise ValueError('Invalid plate face')
    return result


def verify(payload):
    checks=[]
    for item in payload['checks']:
        states={}
        for state in ('before','after'):
            p=face(item[state])
            if item.get('mode')=='planar':
                states[state]=dict(valid=True,area_mm2=p.Area,boundary_count=len(p.Wires),
                    hole_count=len(item[state].get('holes',[])))
                if len(p.Wires)!=1+len(item[state].get('holes',[])):raise ValueError('Unexpected planar boundary/hole count')
                continue
            solid=p.extrude(App.Vector(0,0,item['gauge']))
            if not solid.isValid() or len(solid.Solids)!=1:raise ValueError('Invalid plate solid')
            result=dict(valid=True,volume_mm3=solid.Volume)
            cavity=item.get('cavity_'+state)
            if cavity:
                v=solid.cut(face(cavity).extrude(App.Vector(0,0,item['gauge']))).Volume
                result.update(interference_volume_mm3=v,fits=v<=1e-7)
            states[state]=result
        checks.append(dict(part_code=item['part_code'],scope=item['scope'],mode=item.get('mode','solid'),**states))
    return dict(engine='FreeCAD/OpenCASCADE',version=App.Version()[:3],
        status='passed' if checks and all(c[s].get('fits',True) for c in checks for s in ('before','after')) else 'failed',checks=checks,
        limitations=['Planar checks prove closed faces and holes, not stock gauge, strength or assembly contact. Section/part-solid checks apply only where separately supplied; detached assembly projections require geometry bindings.'])


if __name__=='__main__':
    try:print(json.dumps(verify(json.load(sys.stdin)),allow_nan=False))
    except Exception as error:
        print(json.dumps(dict(status='error',error=str(error))));sys.exit(1)
