"""Positive-weight planar NURBS, with a bounded locator approximation.

Bezier subdivision is only used to locate/measure a source contour. Editing
keeps the original SPLINE poles, knots and weights; the export gate rebuilds
the original curves in OpenCASCADE and checks both exact faces independently.
"""
import copy
import json
import math
from functools import lru_cache
import numpy as np
from ezdxf.math import BSpline

ERROR=1e-6
MAX_POINTS=32768


@lru_cache(maxsize=32)
def _locator(serialized):
    points,weights=json.loads(serialized)
    return _flatten(points,weights)


def locator(edge):
    return _locator(json.dumps([edge['control_points'],edge['weights']],allow_nan=False))


def _flatten(points,weights):
    """Positive rational Bezier curves stay inside their control hull.

    Each accepted hull lies within ERROR of its endpoint segment. Continuity
    and the endpoint projections also bound the reverse chord-to-curve error.
    """
    h=np.column_stack((np.asarray(points)*np.asarray(weights)[:,None],weights))
    result=[list(points[0])];stack=[(h,0)]
    while stack:
        poles,depth=stack.pop();p=poles[:,:3]/poles[:,3,None]
        a,b=p[0],p[-1];v=b-a;den=float(v@v)
        t=np.clip((p-a)@v/den,0,1) if den>1e-24 else np.zeros(len(p))
        error=float(np.max(np.linalg.norm(p-(a+t[:,None]*v),axis=1)))
        if error<=ERROR:
            result.append(b.tolist())
            if len(result)>MAX_POINTS:raise ValueError('NURBS locator subdivision budget exceeded')
            continue
        if depth>=24:raise ValueError('NURBS locator error cannot be bounded')
        left=[poles[0]];right=[poles[-1]];level=poles
        while len(level)>1:
            level=(level[:-1]+level[1:])/2;left.append(level[0]);right.append(level[-1])
        stack.extend([(np.asarray(right[::-1]),depth+1),(np.asarray(left),depth+1)])
    return result


@lru_cache(maxsize=128)
def _spline(serialized):
    g=json.loads(serialized);degree=g['degree'];points=g['control_points']
    count=len(points);knots=g['knots'];weights=g['weights'] or [1.]*count
    if (g.get('fit_points') or g.get('flags',0)&2 or not 1<=degree<=8 or
        not degree+1<=count<=257 or len(knots)!=count+degree+1 or len(weights)!=count):return ()
    p=np.asarray(points,dtype=float)
    if p.shape!=(count,3) or not np.isfinite(p).all() or np.ptp(p[:,2])>1e-7:return ()
    if not all(math.isfinite(w) and w>0 for w in weights) or not all(math.isfinite(k) for k in knots):return ()
    if g['weights'] and not g.get('flags',0)&4:return ()
    weights=[w/max(weights) for w in weights]
    if min(weights)<1e-12 or any(b<a for a,b in zip(knots,knots[1:])):return ()
    groups=[]
    for k in knots:
        if groups and groups[-1][0]==k:groups[-1][1]+=1
        else:groups.append([k,1])
    if len(groups)<2 or groups[0][1]!=degree+1 or groups[-1][1]!=degree+1:return ()
    if any(n>degree for _,n in groups[1:-1]):return ()
    if g.get('flags',0)&1 and math.dist(points[0],points[-1])>1e-7:return ()
    span=knots[-1]-knots[0]
    if span<=0:return ()
    normalized=[(k-knots[0])/span for k in knots]
    curve=BSpline(points,order=degree+1,knots=normalized,weights=weights)
    # Exact knot insertion decomposes arbitrary clamped B-splines into
    # rational Bezier spans; it does not change the native document.
    for k,n in groups[1:-1]:
        t=(k-knots[0])/span
        for _ in range(degree-n):curve=curve.insert_knot(t)
    poles=[list(v) for v in curve.control_points];ws=list(curve.weights())
    edges=[]
    for start in range(0,len(poles)-degree,degree):
        q=poles[start:start+degree+1];w=ws[start:start+degree+1]
        if math.dist(q[0],q[-1])<=1e-8:return ()
        edges.append(dict(kind='nurbs',start=q[0],end=q[-1],degree=degree,
            control_points=q,weights=w,locator_error=ERROR,
            spline_geometry_proof='positive_weight_bezier_convex_hull; exact_OCC_face_required'))
    return tuple(edges)


def primitives(record):
    if record.get('type')!='SPLINE' or not record.get('geometry'):return []
    try:edges=copy.deepcopy(_spline(json.dumps(record['geometry'],sort_keys=True,allow_nan=False)))
    except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError):return []
    for i,edge in enumerate(edges):edge.update(ref=record['ref'],segment_index=i)
    return list(edges)


def ellipse_primitives(record):
    """Convert an ellipse arc exactly to rational quadratic Bezier spans."""
    g=record.get('geometry',{})
    if record.get('type')!='ELLIPSE' or not g:return []
    c=g['center'];a=g['major_axis'];normal=g.get('extrusion',[0,0,1]);ratio=g['ratio']
    if (len(c)!=3 or len(a)!=3 or not all(math.isfinite(v) for v in c+a+normal) or
        abs(a[2])>1e-7 or any(abs(x-y)>1e-7 for x,y in zip(normal,[0,0,1])) or
        not 0<ratio<=1 or math.hypot(*a[:2])<=1e-7):return []
    first,last=g['start_param'],g['end_param']
    if not math.isfinite(first) or not math.isfinite(last):return []
    span=(last-first)%math.tau
    if abs(last-first)>=math.tau-1e-9:span=math.tau
    if span<=1e-9 or abs(last-first)>math.tau+1e-7:return []
    minor=[-a[1]*ratio,a[0]*ratio,0]
    def at(t,factor=1):return [c[i]+factor*(a[i]*math.cos(t)+minor[i]*math.sin(t)) for i in range(3)]
    count=math.ceil(span/(math.pi/2));edges=[]
    for i in range(count):
        t=first+span*i/count;u=first+span*(i+1)/count;w=math.cos((u-t)/2)
        q=[at(t),at((t+u)/2,1/w),at(u)]
        edges.append(dict(kind='nurbs',start=q[0],end=q[-1],degree=2,control_points=q,weights=[1,w,1],
            locator_error=ERROR,ref=record['ref'],segment_index=i,
            spline_geometry_proof='exact_rational_quadratic_ellipse; exact_OCC_face_required'))
    return edges
