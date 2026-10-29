"""Explicit left-fixed octagon width experiment; never design authorization."""
import copy,math,hashlib,json
from shapely.geometry import Polygon
from cad.geometry import snapshot,near
from cad.dimensions import dimension_snapshot
from cad.dimension_associations import bound_point
from graph.linear_point_constraints import analyze


def solve_points(geometry,target_width):
    pts=geometry['points']
    if len(pts)!=8 or not geometry['closed'] or not near(geometry['extrusion'],[0,0,1]) or any(any(abs(v)>1e-10 for v in p[2:]) for p in pts):
        raise ValueError('Plain closed eight-vertex XY polyline required')
    if not math.isfinite(target_width) or target_width<=0:raise ValueError('Positive finite target width required')
    old_width=max(p[0] for p in pts)-min(p[0] for p in pts)
    if abs(target_width-old_width)<=1e-7:raise ValueError('Width must change')
    xs=[p[0] for p in pts];ys=[p[1] for p in pts]
    if not (max(xs[:4])<min(xs[4:]) and near([xs[1],xs[2]],[min(xs)]*2,1e-6) and near([xs[5],xs[6]],[max(xs)]*2,1e-6)
            and near([ys[0],ys[7]],[max(ys)]*2,1e-6) and near([ys[3],ys[4]],[min(ys)]*2,1e-6)):
        raise ValueError('Explicit canonical left/right partition not satisfied')
    origin=pts[0][:2];local={f'v{i}':[p[0]-origin[0],p[1]-origin[1]] for i,p in enumerate(pts)}
    constraints=[]
    def add(cid,kind,refs,value):constraints.append(dict(id=cid,type=kind,points=refs,value=value,status='explicit'))
    for i in range(4):add(f'left{i}','fixed',[f'v{i}'],local[f'v{i}'])
    for i in range(4,8):add(f'y{i}','dy',['v3',f'v{i}'],local[f'v{i}'][1]-local['v3'][1])
    for i in range(5,8):add(f'right-offset{i}','dx',['v4',f'v{i}'],local[f'v{i}'][0]-local['v4'][0])
    add('target-width','dx',['v1','v5'],target_width)
    result=analyze(local,constraints)
    if result['status']!='fully_constrained':raise ValueError('Octagon model not fully constrained')
    after=copy.deepcopy(geometry)
    for i,p in enumerate(after['points']):p[:2]=[result['proposed_points'][f'v{i}'][j]+origin[j] for j in range(2)]
    before_polygon=Polygon([p[:2] for p in pts]);after_polygon=Polygon([p[:2] for p in after['points']])
    if not before_polygon.is_valid or not after_polygon.is_valid or after_polygon.area<=1e-6 or max(p[0] for p in after['points'][:4])>=min(p[0] for p in after['points'][4:]):
        raise ValueError('Target width collapses or crosses the profile')
    return dict(before=geometry,after=after,source_width_mm=old_width,target_width_mm=target_width,solver=result,constraints=constraints,origin_xy=origin,
                intent=dict(fixed_vertex_indices=list(range(4)),moving_vertex_indices=list(range(4,8)),preserve_height=True,preserve_chamfers=True),edit_authorization=False)


def plan(doc,group,target_width,*,allow_unbound_test_assumptions=False,subentity_evidence=None):
    if doc.units!=4:raise ValueError('Millimeter source required')
    poly=doc.entitydb[group['polyline_handle']];result=solve_points(snapshot(poly),target_width)
    legacy={row['dimension_handle']:row['binding'] for row in group['legacy_associations']}
    native={row['dimension_handle'] for row in group['native_actions']}
    native_vertices={};native_report_hash=None
    if subentity_evidence is not None:
        from cad.native_subentity_bindings import vertex_bindings
        native_vertices,native_report_hash=vertex_bindings(doc,group,subentity_evidence)
    dimensions=[];assumptions=[]
    for handle in group['dimension_handles']:
        dim=doc.entitydb[handle];before=dimension_snapshot(dim)
        if before['text'] not in ('','<>'):raise ValueError('Overridden DIM text is unsupported')
        bindings={p['dimension_field']:p for p in legacy.get(handle,{}).get('points',[])}
        expected={};evidence=[]
        for field in ('defpoint2','defpoint3'):
            old=before[field]
            if field in bindings:
                binding=bindings[field]
                expected[field]=bound_point('LWPOLYLINE',result['after'],binding)
                evidence.append(dict(field=field,kind='verified_dimassoc',binding=binding))
            elif (handle,field) in native_vertices:
                entry=native_vertices[(handle,field)];p=result['after']['points'][entry['vertex_index']]
                expected[field]=[p[0],p[1],old[2]];evidence.append(copy.deepcopy(entry))
            else:
                matches=[i for i,p in enumerate(result['before']['points']) if near([p[0],p[1],result['before']['elevation']],old,1e-6)]
                if len(matches)!=1:raise ValueError('DIM point does not uniquely match a source vertex')
                i=matches[0];new=result['after']['points'][i]
                expected[field]=[new[0],new[1],old[2]]
                entry=dict(dimension_handle=handle,field=field,vertex_index=i,kind='native_dependency_and_exact_vertex' if handle in native else 'unbound_exact_vertex_test_assumption')
                evidence.append(entry)
                if handle not in native:assumptions.append(entry)
        angle=math.radians(before['angle']);a=expected['defpoint2'];b=expected['defpoint3']
        measure=abs((b[0]-a[0])*math.cos(angle)+(b[1]-a[1])*math.sin(angle))
        dimensions.append(dict(handle=handle,before_a=before['defpoint2'],before_b=before['defpoint3'],a=a,b=b,measurement=measure,evidence=evidence))
    if assumptions and not allow_unbound_test_assumptions:raise ValueError('Unbound DIM points require explicit test assumptions; no production authorization')
    # A repeatable review artifact, never a transferable confirmation or permission.
    # Keep native object dependency evidence separate from exact endpoint binding.
    endpoint_review=[]
    for dim in dimensions:
        for item in dim['evidence']:
            field=item['field']
            endpoint_review.append(dict(dimension_handle=dim['handle'],field=field,
                before=dim['before_a' if field=='defpoint2' else 'before_b'],
                proposed=dim['a' if field=='defpoint2' else 'b'],
                status={'verified_dimassoc':'source_bound','verified_native_vertex':'source_bound_native_vertex','native_dependency_and_exact_vertex':'native_dependency_vertex_candidate',
                        'unbound_exact_vertex_test_assumption':'unbound_vertex_candidate'}[item['kind']],
                evidence=copy.deepcopy(item)))
    scope=dict(source_sha256=group.get('source_sha256'),polyline_handle=group['polyline_handle'],
               source_geometry=result['before'],proposed_geometry=result['after'],intent=result['intent'],
               native_subentity_report_sha256=native_report_hash,endpoints=sorted(endpoint_review,key=lambda r:(r['dimension_handle'],r['field'])))
    fingerprint=hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    review=dict(schema_version=1,scope_sha256=fingerprint,source_sha256=group.get('source_sha256'),
                polyline_handle=group['polyline_handle'],endpoints=endpoint_review,
                native_subentity_report_sha256=native_report_hash,
                unresolved_endpoint_count=sum(r['status'] not in ('source_bound','source_bound_native_vertex') for r in endpoint_review),
                release_gate=dict(allowed=False,reasons=['Endpoint candidates are not persistent source bindings.',
                    'Complete mechanical intent and downstream product relationships are not established.']),
                policy='Private experiment only. Fingerprint identifies this source geometry, intent and proposal; it grants no edit authorization.')
    result.update(dimensions=dimensions,test_assumptions=assumptions,mechanical_group_complete=False,binding_review=review)
    return result
