"""Numerical, source-checked 2D projections of an explicitly bound 3D point.

This operates on DWG geometry, never image pixels. A camera alone cannot infer
depth: each point must already have an unambiguous part/plane binding.
"""
import copy
import math
import numpy as np
from cad.geometry import near


class Projection:
    def __init__(self,matrix,origin,scale=1):
        self.matrix=np.asarray(matrix,dtype=float)
        self.origin=np.asarray(origin,dtype=float)
        if self.matrix.shape!=(2,3) or self.origin.shape!=(2,) or not np.isfinite(self.matrix).all() or not np.isfinite(self.origin).all():
            raise ValueError('Hệ chiếu cần ma trận hữu hạn 2×3 và gốc 2D')
        if scale<=0 or not np.allclose(self.matrix@self.matrix.T,np.eye(2)*scale**2,atol=1e-8,rtol=0):
            raise ValueError('Hệ chiếu chưa chứng minh đúng tỉ lệ trực giao')

    def point(self,point):
        value=self.matrix@np.asarray(point,dtype=float)+self.origin
        if value.shape!=(2,) or not np.isfinite(value).all():raise ValueError('Điểm chiếu không hợp lệ')
        return value.tolist()

    def move_bound_point(self,actual,before,after,tolerance=2e-4):
        old=self.point(before)
        if len(actual)!=3 or math.dist(actual[:2],old)>tolerance:
            raise ValueError('Điểm nguồn không khớp binding hình chiếu đã đo')
        delta=np.asarray(self.point(after))-old
        # Preserve the original drafting residual and Z/extrusion coordinates.
        return [actual[0]+float(delta[0]),actual[1]+float(delta[1]),actual[2]]

    def line(self,geometry,before,after):
        result=copy.deepcopy(geometry)
        for k,old,new in zip(('start','end'),before,after):
            result[k]=self.move_bound_point(geometry[k],old,new)
        if near(result['start'],result['end']):raise ValueError('Đường chiếu bị co về 0')
        return result

    def concentric_arc(self,geometry,center,old_radius,new_radius,axes=(0,1),tolerance=2e-4):
        if old_radius<=0 or new_radius<=0:raise ValueError('Bán kính chiếu phải dương')
        if math.dist(geometry['center'][:2],self.point(center))>tolerance:
            raise ValueError('Tâm cung chiếu không khớp binding')
        a=np.asarray(geometry['major_axis'][:2]);b=np.array([-a[1],a[0]])*geometry['ratio']
        basis=self.matrix[:,list(axes)]*old_radius
        # A rotated ellipse parameterization has the same conic metric.
        if not np.allclose(np.outer(a,a)+np.outer(b,b),basis@basis.T,atol=1e-7,rtol=0):
            raise ValueError('Cung elip không cùng mặt phẳng/bán kính với chi tiết')
        result=copy.deepcopy(geometry)
        result['major_axis']=[v*new_radius/old_radius for v in geometry['major_axis']]
        return result
