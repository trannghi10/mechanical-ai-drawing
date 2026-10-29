"""Build explicit solver input from native rectangle point bindings."""
import numpy as np
from graph.linear_point_constraints import analyze


def solve_binding(binding, target_width):
    if binding.get('schema_version')!=1 or binding.get('units')!='mm':raise ValueError('Expected millimeter binding')
    vertices=binding['vertices']
    if len(vertices)!=4 or [v['index'] for v in vertices]!=[0,1,2,3] or [v['point_id'] for v in vertices]!=['v0','v1','v2','v3']:
        raise ValueError('Invalid vertex mapping')
    p=np.asarray([v['xyz'] for v in vertices],dtype=float)
    if p.shape!=(4,3) or not np.isfinite(p).all() or not np.isfinite(target_width) or target_width<=0:
        raise ValueError('Invalid target or coordinates')
    if binding['fixed_vertex_indices']!=[0,3] or binding['moving_vertex_indices']!=[1,2] or binding['dimension']['vertex_indices']!=[0,1]:
        raise ValueError('Unexpected explicit intent or DIM mapping')
    width=p[1,0]-p[0,0];height=p[3,1]-p[0,1]
    expected=np.array([[p[0,0],p[0,1],p[0,2]],[p[0,0]+width,p[0,1],p[0,2]],
                       [p[0,0]+width,p[0,1]+height,p[0,2]],[p[0,0],p[0,1]+height,p[0,2]]])
    if width<=0 or height<=0 or not np.allclose(p,expected,atol=1e-7,rtol=0):raise ValueError('Expected axis-aligned rectangle')
    d=binding['dimension']
    if abs(d['measurement_mm']-width)>1e-7 or not np.allclose(d['defpoint2'],p[0],atol=1e-7,rtol=0) or not np.allclose(d['defpoint3'],p[1],atol=1e-7,rtol=0):
        raise ValueError('DIM binding does not match geometry')
    def c(i,t,refs,value=None):
        row=dict(id=i,type=t,points=refs,status='explicit')
        if value is not None:row['value']=value
        return row
    constraints=[c('left0','fixed',['v0'],p[0,:2].tolist()),c('left3','fixed',['v3'],p[3,:2].tolist()),
                 c('bottom','horizontal',['v0','v1']),c('top','horizontal',['v3','v2']),
                 c('right','vertical',['v1','v2']),c('width','dx',['v0','v1'],float(target_width))]
    result=analyze({v['point_id']:v['xyz'][:2] for v in vertices},constraints)
    if result['status']!='fully_constrained':raise ValueError('Solver failed to constrain rectangle')
    pts=[result['proposed_points'][v['point_id']]+[v['xyz'][2]] for v in vertices]
    return dict(points=pts,solver=result,constraints=constraints)
