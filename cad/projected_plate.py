"""Rebuild a bound exploded plate projection from authoritative detail sizes.

The source may be a simplified illustration. Its visible edge graph and camera
are checked first; the new nominal geometry is generated from the detail/BOM.
"""
import copy,math
import numpy as np
from cad.projection_mapping import Projection


def rebuild(descriptor,records,new_size,new_radius,hole_radius=None):
    matrix=np.asarray(descriptor['matrix']);origin=np.asarray(descriptor['origin'])
    projection=Projection(matrix,origin,descriptor.get('scale',1))
    old_size=descriptor['size'];old_r=descriptor['radius'];gauge=descriptor['gauge']
    if min(new_size)<=0 or new_radius<=0 or 2*new_radius>=min(new_size):raise ValueError('Bas chiếu không đủ cạnh thẳng cho bán kính mới')
    # Keep the exploded view centered; this is display placement, not a mate.
    new_origin=origin+matrix[:,:2]@((np.asarray(old_size)-new_size)/2)
    by={e['ref']:e for e in records};outputs={}
    def coordinate(value,axis):
        old=old_size[axis];new=new_size[axis]
        options=[(0,0),(old_r,new_radius),(old-old_r,new-new_radius),(old,new)]
        matches=[b for a,b in options if abs(value-a)<1e-6]
        if len(matches)!=1:raise ValueError('Tọa độ bas chưa gắn góc/biên duy nhất')
        return matches[0]
    def center(point):return [coordinate(point[0],0),coordinate(point[1],1),point[2]]
    new_points=[];conics=[]
    for binding in descriptor['curves']:
        e=by[binding['ref']];g=e['geometry'];old_center=binding['center'];new_center=center(old_center)
        projection.concentric_arc(g,old_center,old_r,new_radius)
        result=copy.deepcopy(g);result['center']=[*(matrix@new_center+new_origin).tolist(),g['center'][2]]
        result['major_axis']=[a*new_radius/old_r for a in g['major_axis']]
        outputs[e['ref']]=result
        a=np.array(g['major_axis'][:2]);b=np.array([-a[1],a[0]])*g['ratio']
        conics.append((np.array(g['center'][:2]),a,b,np.array(result['center'][:2])))
        for parameter in (g['start_param'],g['end_param']):
            old_xy=np.array(g['center'][:2])+a*math.cos(parameter)+b*math.sin(parameter)
            new_xy=np.array(result['center'][:2])+(a*math.cos(parameter)+b*math.sin(parameter))*new_radius/old_r
            new_points.append((old_xy,new_xy))
    for binding in descriptor['lines']:
        e=by[binding['ref']];g=e['geometry'];after=copy.deepcopy(g)
        for key,p in zip(('start','end'),(binding['start'],binding['end'])):
            actual=np.array(g[key][:2]);matches=[b for a,b in new_points if np.linalg.norm(a-actual)<1e-4]
            # A cylindrical silhouette can touch the interior of a corner arc,
            # rather than its trimmed endpoint. Retain that exact tangent angle.
            for old_c,a,b,new_c in conics:
                coefficients=np.linalg.solve(np.column_stack((a,b)),actual-old_c)
                if abs(np.linalg.norm(coefficients)-1)<1e-5:
                    matches.append(new_c+(a*coefficients[0]+b*coefficients[1])*new_radius/old_r)
            if matches:
                if any(np.linalg.norm(m-matches[0])>2e-4 for m in matches):raise ValueError('Điểm bas chiếu khớp nhiều góc khác nhau: '+e['ref']+' '+key)
                xy=matches[0]
            else:
                if math.dist(projection.point(p),actual)>descriptor.get('tolerance',.05):raise ValueError('Biên nguồn bas không khớp mapping chiếu')
                xy=matrix@center(p)+new_origin
            after[key]=[float(xy[0]),float(xy[1]),g[key][2]]
        outputs[e['ref']]=after
    for binding in descriptor.get('holes',[]):
        e=by[binding['ref']];g=e['geometry']
        projection.concentric_arc(g,binding['center'],binding['radius'],hole_radius)
        after=copy.deepcopy(g);after['major_axis']=[a*hole_radius/binding['radius'] for a in g['major_axis']]
        outputs[e['ref']]=after
    # Check every mapped visible endpoint of the two plate faces against its
    # intended tangent/edge. A changed hole stays at its original center.
    return outputs
