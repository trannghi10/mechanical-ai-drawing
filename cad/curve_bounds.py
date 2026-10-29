"""When a native SPLINE's control hull is a conservative geometric bound."""
import math


def ellipse_bounds(g):
    """Exact local XYZ extrema of a native elliptical arc, including -Z OCS.

    Bounds are reading evidence only. Accepting a remote arc's conservative
    box does not authorize changing that arc or flattening its native plane.
    """
    from ezdxf.math import Vec3
    try:
        center=Vec3(g['center']);major=Vec3(g['major_axis']);normal=Vec3(g.get('extrusion',[0,0,1]));ratio=float(g['ratio'])
        start=float(g['start_param']);end=float(g['end_param'])
        if not all(math.isfinite(v) for v in (*center,*major,*normal,ratio,start,end)) or not 0<ratio<=1 or min(major.magnitude,normal.magnitude)<=1e-12:return None
        normal=normal.normalize()
        if abs(normal.dot(major))>1e-8*major.magnitude:return None
        minor=normal.cross(major)*ratio;difference=end-start
        if abs(difference)>math.tau+1e-8:return None
        full=abs(abs(difference)-math.tau)<=1e-8;span=difference%math.tau
        if not full and span<=1e-12:return None
        low=[];high=[]
        for i in range(3):
            angles=[start,end];turn=math.atan2(minor[i],major[i])
            angles.extend(t for t in (turn,turn+math.pi) if full or (t-start)%math.tau<=span+1e-12)
            values=[center[i]+major[i]*math.cos(t)+minor[i]*math.sin(t) for t in angles]
            low.append(min(values));high.append(max(values))
        return [low,high]
    except (ValueError,TypeError,KeyError,ZeroDivisionError):return None


def positive_control_hull(g):
    points = g.get('control_points', [])
    degree = g.get('degree', 0)
    knots = g.get('knots', [])
    weights = g.get('weights', [])
    return (isinstance(degree, int) and 1 <= degree < len(points) and not g.get('fit_points') and
        len(knots) == len(points)+degree+1 and
        all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in points) and
        all(math.isfinite(k) for k in knots) and all(a <= b for a, b in zip(knots, knots[1:])) and
        knots[degree] < knots[-degree-1] and
        len(weights) in (0, len(points)) and all(math.isfinite(w) and w > 0 for w in weights))


def projected_simple_bounds(record,axis,normal):
    """Conservative UVZ bounds without primitive decomposition.

    Bulges, tilted OCS and INSERT bounds are deliberately excluded. Endpoint
    bounds do not enclose bulge arcs or the contents of an inserted block.
    """
    g=record.get('geometry',{});kind=record['type'];points=[]
    if kind=='LINE' and g:points=[g['start'],g['end']]
    elif kind in ('LWPOLYLINE','POLYLINE') and g:
        if g.get('extrusion')!=[0,0,1] or any(p[4] for p in g['points']):return None
        points=[[p[0],p[1],g['elevation']] for p in g['points']]
    elif kind in ('ARC','CIRCLE') and g and g.get('extrusion')==[0,0,1] and g.get('radius',0)>0:
        c=g['center'];r=g['radius']
        u=sum(a*b for a,b in zip(c,axis));v=sum(a*b for a,b in zip(c,normal))
        return [u-r,u+r,v-r,v+r,c[2],c[2]] if all(math.isfinite(x) for x in (*c,r)) else None
    if not points or any(len(p)!=3 or not all(math.isfinite(x) for x in p) for p in points):return None
    us=[sum(a*b for a,b in zip(p,axis)) for p in points];vs=[sum(a*b for a,b in zip(p,normal)) for p in points]
    return [min(us),max(us),min(vs),max(vs),min(p[2] for p in points),max(p[2] for p in points)]
