"""Explicit 2D affine point constraints; analysis/proposals only, no CAD mutation."""
import math
import numpy as np


def analyze(points, constraints, *, residual_mm=1e-7, rank_rcond=1e-12):
    if not points or len(points)>64 or len(constraints)>256:
        raise ValueError("Bounded point model required")
    if not math.isfinite(residual_mm) or residual_mm<=0 or not 0<rank_rcond<1:
        raise ValueError("Invalid numerical tolerance")
    names=list(points); index={name:2*i for i,name in enumerate(names)}
    initial=np.asarray([points[name] for name in names],dtype=float)
    if initial.shape!=(len(names),2) or not np.isfinite(initial).all():
        raise ValueError("Finite XY points required")
    initial=initial.ravel(); n=len(initial); rows=[]; rhs=[]; labels=[]; ids=set()
    def equation(terms,value,label):
        row=np.zeros(n)
        for name,axis,coefficient in terms:
            if name not in index:raise ValueError("Unknown point reference")
            row[index[name]+axis]+=coefficient
        if not math.isfinite(value):raise ValueError("Finite constraint value required")
        rows.append(row);rhs.append(value);labels.append(label)
    for c in constraints:
        cid=c['id']
        if not isinstance(cid,str) or not cid or cid in ids:raise ValueError("Unique constraint IDs required")
        ids.add(cid)
        if c.get('status') not in ('explicit','confirmed','native'):
            raise ValueError("Geometric candidates cannot become solver constraints automatically")
        kind=c['type']; refs=c['points']
        if kind=='fixed':
            if len(refs)!=1 or len(c['value'])!=2:raise ValueError("Fixed point needs XY")
            for axis in range(2):equation([(refs[0],axis,1)],float(c['value'][axis]),cid)
        elif kind in ('horizontal','vertical','dx','dy','coincident'):
            if len(refs)!=2 or refs[0]==refs[1]:raise ValueError("Two distinct points required")
            axes=(0,1) if kind=='coincident' else (1,) if kind in ('horizontal','dy') else (0,)
            for axis in axes:
                value=float(c['value']) if kind in ('dx','dy') else 0.
                equation([(refs[1],axis,1),(refs[0],axis,-1)],value,cid)
        else:raise ValueError("Unsupported affine constraint type: "+str(kind))
    a=np.asarray(rows,dtype=float).reshape((-1,n));b=np.asarray(rhs)
    # Solve for the minimum correction to the source, rather than an absolute minimum-norm position.
    correction,_,rank,singular=np.linalg.lstsq(a,b-a@initial,rcond=rank_rcond)
    proposed=initial+correction; residual=a@proposed-b
    worst=float(np.max(np.abs(residual))) if len(residual) else 0.
    consistent=worst<=residual_mm
    dof=n-int(rank)
    status='inconsistent' if not consistent else 'underconstrained' if dof else 'fully_constrained'
    return dict(status=status,variable_count=n,equation_count=len(rows),rank=int(rank),
                degrees_of_freedom=dof,redundant_equation_count=len(rows)-int(rank),
                singular_values=singular.tolist(),rank_rcond=rank_rcond,residual_tolerance_mm=residual_mm,
                max_residual_mm=worst,
                equation_residuals=[dict(constraint_id=label,residual_mm=float(r)) for label,r in zip(labels,residual)],
                proposed_points={name:proposed[i*2:i*2+2].tolist() for i,name in enumerate(names)} if consistent and dof==0 else None,
                edit_authorization=False,
                scope='Explicit affine XY point model in millimeters only. DOF is nullity, even for inconsistent equations; inconsistency means no feasible state. Redundancy count is equation dependence, not a removable constraint list.')
