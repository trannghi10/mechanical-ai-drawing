"""Prove circular/straight rational quadratic Bezier spans without flattening.

Some CAD exporters store circles as SPLINEs. Only clamped quadratic spans
whose homogeneous polynomial satisfies the circle equation are accepted.
The native SPLINE, knots, weights and parameterization remain unchanged.
Other NURBS, fit-point splines and periodic definitions require another adapter.
"""
import math
import numpy as np


def _span(points,weights):
    p=np.asarray(points,dtype=float);w=np.asarray(weights,dtype=float)
    if p.shape!=(3,3) or not np.isfinite(p).all() or np.ptp(p[:,2])>1e-7:return None
    scale=float(np.linalg.norm(p[2,:2]-p[0,:2]))
    if scale<=1e-7:return None
    q=(p[:,:2]-p[0,:2])/scale
    cross=float(q[1,0]*q[2,1]-q[1,1]*q[2,0])
    if abs(cross)<=1e-12:
        if abs(cross)*scale>1e-7 or not -1e-12<=float(q[1]@q[2])<=1+1e-12:return None
        return dict(kind='line',start=p[0].tolist(),end=p[2].tolist())
    # Evaluate the actual rational midpoint, then solve a candidate circle.
    mid=(q[0]*w[0]+2*q[1]*w[1]+q[2]*w[2])/(w[0]+2*w[1]+w[2])
    try:c=np.linalg.solve(2*np.asarray([mid,q[2]]),np.asarray([mid@mid,q[2]@q[2]]))
    except np.linalg.LinAlgError:return None
    r=float(np.linalg.norm(c))
    if not math.isfinite(r) or r<=1e-10:return None
    def coefficients(values):return np.asarray([values[0],2*(values[1]-values[0]),values[0]-2*values[1]+values[2]])
    ww=coefficients(w)
    xx=coefficients((q[:,0]-c[0])*w);yy=coefficients((q[:,1]-c[1])*w)
    def square(values):
        product=np.polynomial.polynomial.polymul(values,values)
        return np.pad(product,(0,5-len(product)))
    residual=square(xx)+square(yy)-r*r*square(ww)
    # This checks the entire rational polynomial, not sampled points. A curve
    # passing through three circular points does not by itself prove an arc.
    error_bound=scale*float(np.sum(np.abs(residual)))/(float(min(w))**2*r)
    if not math.isfinite(error_bound) or error_bound>1e-7:return None
    center=(p[0,:2]+scale*c).tolist()+[float(p[0,2])]
    start=math.atan2(-c[1],-c[0]);end=math.atan2(q[2,1]-c[1],q[2,0]-c[0])
    middle=math.atan2(mid[1]-c[1],mid[0]-c[0])
    ccw=(middle-start)%math.tau<(end-start)%math.tau
    sweep=((end-start) if ccw else (start-end))%math.tau
    if not 1e-9<sweep<math.pi-1e-9:return None
    return dict(kind='arc',start=p[0].tolist(),end=p[2].tolist(),center=center,radius=r*scale,ccw=ccw)


def primitives(record):
    g=record.get('geometry',{})
    if record.get('type')!='SPLINE' or g.get('degree')!=2 or g.get('fit_points') or g.get('flags',0)&3:return []
    points=g.get('control_points',[]);knots=g.get('knots',[]);weights=g.get('weights',[])
    count=len(points)
    if count<3 or count%2!=1 or len(knots)!=count+3 or count>513:return []
    if weights and (len(weights)!=count or not g.get('flags',0)&4):return []
    weights=weights or [1.]*count
    if not all(math.isfinite(v) and v>0 for v in weights) or not all(math.isfinite(v) for v in knots):return []
    largest=max(weights);weights=[v/largest for v in weights]
    if min(weights)<1e-12:return []
    groups=[]
    for k in knots:
        if groups and k==groups[-1][0]:groups[-1][1]+=1
        elif groups and k<groups[-1][0]:return []
        else:groups.append([k,1])
    if len(groups)<2 or groups[0][1]!=3 or groups[-1][1]!=3 or any(n!=2 for _,n in groups[1:-1]):return []
    if len(groups)!=((count-1)//2)+1:return []
    result=[]
    for i in range(0,count-2,2):
        edge=_span(points[i:i+3],weights[i:i+3])
        if edge is None:return []
        edge.update(ref=record['ref'],segment_index=i//2,
                    spline_geometry_proof='homogeneous_quadratic_circle_identity' if edge['kind']=='arc' else 'positive_weight_collinear_convex_hull')
        result.append(edge)
    return result
