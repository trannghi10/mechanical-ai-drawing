"""Source-bound rectangular foam pads around one planar product envelope."""
import json
import numpy as np
from ezdxf.math import Vec3
from cad.frame_geometry import matrix,world
from cad.geometry import near
from cad.edit_engine import Operation
from cad.parametric import LinearResize
from graph.change_dependencies import CoordinateRule
from graph.measurement_rules import MeasurementEquation,MeasurementTerm

TOL=1e-5


def rules(proof,pads,records,ops):
    from graph.native_contacts import bounds
    product=proof['product'];axis=proof['axis'];other=1-axis
    p0=bounds(product['points']);b0=bounds(proof['box']['points']);delta=proof['expected_bounds']-b0
    pd=proof['product_recipe'].dimension_ref
    physical=[p0]+[bounds(p['points']) for p in pads]
    for i,a in enumerate(physical):
        if np.any(a[0,:2]<b0[0,:2]-TOL) or np.any(a[1,:2]>b0[1,:2]+TOL) or abs(a[0,2]-b0[0,2])>TOL:return None
        for b in physical[i+1:]:
            if np.all(np.minimum(a[1,:2],b[1,:2])-np.maximum(a[0,:2],b[0,:2])>TOL):return None
    resized=[];moved=[];expectations=[]
    for pad in pads:
        a=bounds(pad['points']);after=a.copy();mode=None
        if a[0,axis]>=p0[1,axis]-TOL:mode='top';after[:,axis]+=delta[1,axis]
        elif a[1,axis]<=p0[0,axis]+TOL:mode='bottom';after[:,axis]+=delta[0,axis]
        elif (a[1,other]<=p0[0,other]+TOL or a[0,other]>=p0[1,other]-TOL) and (
                near(a[:,axis].tolist(),p0[:,axis].tolist(),TOL) or near(a[:,axis].tolist(),b0[:,axis].tolist(),TOL)):
            mode='side';after[:,axis]+=delta[:,axis]
        if mode is None or np.any(after[0,:2]<proof['expected_bounds'][0,:2]-TOL) or np.any(after[1,:2]>proof['expected_bounds'][1,:2]+TOL):return None
        expectations.append((pad,after))
        if near(a.tolist(),after.tolist(),TOL):continue
        evidence=sorted(set(product['evidence_refs']+pad['evidence_refs']))
        if mode=='side':
            dims=[d for d in pad['dimensions'] if abs(abs(d['axis'][axis])-1)<TOL and abs(d['linear_factor']-1)<TOL]
            if len(dims)!=1:return None
            d=dims[0];g=world(records[d['ref']])['geometry'];dl,dh=delta[:,axis]
            anchor='center' if abs(dl+dh)<TOL and abs(dl)>TOL else 'first' if (abs(dl)<TOL)==(g['defpoint2'][axis]<g['defpoint3'][axis]) else 'second'
            recipe=LinearResize(part_code=pad['part_code'],dimension_ref=d['ref'],new_measurement=float(d['measurement']+dh-dl),
                outline_refs=pad['refs'],hole_refs=[],anchor=anchor,evidence_refs=evidence)
            equation=MeasurementEquation(terms=[MeasurementTerm(dimension_ref=pd,coefficient=-1),MeasurementTerm(dimension_ref=d['ref'],coefficient=1)],evidence_refs=evidence)
            resized.append(dict(proof,box=pad,recipe=recipe,equation=equation,role='side_pad',
                before_mm=d['measurement'],after_mm=recipe.new_measurement,expected_bounds=after,pad_motions=[],pad_expectations=[]))
        else:
            shift=after[0]-a[0];driver=records[pd];dg0=driver['geometry'];dg1=json.loads(ops[pd].after);source=None
            for key in ('defpoint2','defpoint3'):
                vector=np.asarray(dg1[key])-dg0[key];nz=np.flatnonzero(abs(vector)>TOL)
                w=np.asarray(matrix(driver).transform_direction(Vec3(vector)))
                if len(nz)==1 and abs(w[axis])>TOL and np.linalg.norm(np.delete(w,axis))<TOL:
                    source=(key,int(nz[0]),float(w[axis]));break
            if source is None:return None
            key,k,driver_delta=source;ref=pad['instance_ref'];native=records[ref]
            inv=matrix(native);inv.inverse();local=list(inv.transform_direction(Vec3(shift)))
            xyz=(np.asarray(native['position'])+local).tolist()
            op=Operation(ref=ref,action='move_insert',before=json.dumps(native['position']),after='',xyz=xyz,reason='Dịch lớp đệm theo đầu sản phẩm; giữ độ dày và khe hở nguồn')
            rule=CoordinateRule(source_ref=pd,source_field=key,target_ref=ref,target_action='move_insert',axis='xyz'[k],multiplier=float(shift[axis]/driver_delta))
            moved.append(dict(operation=op,rule=rule,evidence_refs=evidence,part_code=pad['part_code'],source_part=product['part_code']))
    after_pieces=[p0+delta]+[a for _,a in expectations]
    for i,a in enumerate(after_pieces):
        for b in after_pieces[i+1:]:
            if np.all(np.minimum(a[1,:2],b[1,:2])-np.maximum(a[0,:2],b[0,:2])>TOL):return None
    return resized,moved,expectations
