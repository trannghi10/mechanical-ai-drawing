"""Local nonlinear XY constraint proposals; no DWG mutation or global proof."""
import math
import numpy as np
from scipy.optimize import least_squares


class DegenerateGeometry(ValueError):
    pass


def solve(points, constraints, *, distance_tolerance_mm=1e-7, angle_tolerance_radians=1e-8,
          rank_rcond=1e-8, max_nfev=200):
    if not points or len(points)>32 or not constraints or len(constraints)>128:
        raise ValueError("Select 1..32 points and 1..128 explicit constraints")
    if not all(math.isfinite(v) and v>0 for v in (distance_tolerance_mm,angle_tolerance_radians,rank_rcond)) or rank_rcond>=1:
        raise ValueError("Invalid numerical tolerance")
    if type(max_nfev) is not int or not 1<=max_nfev<=2000:
        raise ValueError("Invalid evaluation budget")
    names=list(points); lookup={name:i for i,name in enumerate(names)}
    start=np.asarray([points[name] for name in names],dtype=float)
    if start.shape!=(len(names),2) or not np.isfinite(start).all():raise ValueError("Finite XY points required")
    records=[]; ids=set()
    arities=dict(fixed=1,horizontal=2,vertical=2,dx=2,dy=2,coincident=2,distance=2,
                 angle=4,parallel=4,perpendicular=4,tangent_line=3)
    for c in constraints:
        cid=c['id'];kind=c['type'];refs=c['points']
        if not isinstance(cid,str) or not cid or cid in ids:raise ValueError("Unique constraint IDs required")
        ids.add(cid)
        if c.get('status') not in ('explicit','confirmed','native'):raise ValueError("Candidate constraints are not accepted")
        if kind not in arities or len(refs)!=arities[kind] or any(ref not in lookup for ref in refs):
            raise ValueError("Unsupported constraint or invalid point references")
        indices=[lookup[ref] for ref in refs]
        if kind=='fixed':
            value=np.asarray(c['value'],dtype=float)
            if value.shape!=(2,) or not np.isfinite(value).all():raise ValueError("Fixed XY required")
        elif kind in ('dx','dy','distance','angle','tangent_line'):
            value=float(c['value'])
            if not math.isfinite(value):raise ValueError("Finite constraint value required")
            if kind in ('distance','tangent_line') and value<=0:raise ValueError("Positive distance/radius required")
            if kind=='angle' and not -math.pi<=value<=math.pi:raise ValueError("Signed angle must be in radians [-pi,pi]")
        else:value=0.
        if kind=='tangent_line' and c.get('side') not in (-1,1):raise ValueError("Explicit tangent side -1 or +1 required")
        records.append((cid,kind,indices,value,c.get('side')))
    def direction(v):
        length=float(np.linalg.norm(v))
        if length<=1e-9:raise DegenerateGeometry("Zero length direction or distance")
        return v/length
    def evaluate(x,details=False):
        xy=x.reshape((-1,2));rows=[];meta=[]
        def add(cid,value,unit):
            tol=angle_tolerance_radians if unit=='rad' else distance_tolerance_mm
            rows.append(float(value)/tol)
            meta.append(dict(constraint_id=cid,residual=float(value),unit=unit,tolerance=tol))
        for cid,kind,idx,value,side in records:
            p=[xy[i] for i in idx]
            if kind=='fixed':
                for v in p[0]-value:add(cid,v,'mm')
            elif kind=='coincident':
                for v in p[1]-p[0]:add(cid,v,'mm')
            elif kind in ('horizontal','vertical','dx','dy'):
                axis=1 if kind in ('horizontal','dy') else 0
                add(cid,p[1][axis]-p[0][axis]-value,'mm')
            elif kind=='distance':
                delta=p[1]-p[0];direction(delta)
                add(cid,np.linalg.norm(delta)-value,'mm')
            elif kind in ('angle','parallel','perpendicular'):
                u=direction(p[1]-p[0]);v=direction(p[3]-p[2])
                theta=math.atan2(u[0]*v[1]-u[1]*v[0],float(u@v))
                target=value if kind=='angle' else math.pi/2 if kind=='perpendicular' else 0.
                error=theta-target
                # Unoriented parallel/perpendicular use a pi period; angle is oriented.
                period=2 if kind in ('parallel','perpendicular') else 1
                add(cid,math.atan2(math.sin(period*error),math.cos(period*error))/period,'rad')
            elif kind=='tangent_line':
                u=direction(p[1]-p[0]);v=p[2]-p[0]
                add(cid,u[0]*v[1]-u[1]*v[0]-side*value,'mm')
        result=np.asarray(rows)
        if not np.isfinite(result).all():raise ValueError("Nonfinite constraint residual")
        return (result,meta) if details else result
    evaluate(start.ravel())  # Fail fast on undefined initial geometry.
    try:
        result=least_squares(evaluate,start.ravel(),jac='3-point',method='trf',loss='linear',
                             x_scale=1.,ftol=1e-12,xtol=1e-12,gtol=1e-12,max_nfev=max_nfev)
        residual,details=evaluate(result.x,True)
    except DegenerateGeometry as error:
        return dict(status='degenerate_geometry',reason=str(error),proposed_points=None,edit_authorization=False)
    singular=np.linalg.svd(result.jac,compute_uv=False)
    cutoff=rank_rcond*singular[0] if len(singular) else 0.
    rank=int(np.sum(singular>cutoff));dof=len(start.ravel())-rank
    satisfied=bool(np.max(np.abs(residual))<=1.)
    status=('not_converged' if not result.success else 'unsatisfied' if not satisfied
            else 'locally_underconstrained' if dof else 'local_solution')
    return dict(status=status,optimizer_success=bool(result.success),optimizer_message=result.message,
                evaluations=int(result.nfev),variable_count=int(start.size),equation_count=len(residual),
                jacobian_rank=rank,local_linearized_dof=dof,rank_rcond=rank_rcond,
                singular_values=singular.tolist(),max_normalized_residual=float(np.max(np.abs(residual))),
                equation_residuals=details,
                proposed_points={name:result.x.reshape((-1,2))[i].tolist() for i,name in enumerate(names)} if status=='local_solution' else None,
                edit_authorization=False,global_uniqueness_proven=False,
                scope='Local explicit XY model in mm; angles in radians. tangent_line uses a fixed radius and signed side of an infinite line. No automatic branch choice, finite contact validation, bulge, DWG binding, or edit authorization.')
