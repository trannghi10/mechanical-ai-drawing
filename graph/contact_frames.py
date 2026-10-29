"""Rigid analysis bases for measured native 2D assemblies.

Only the inspection matrices/world feature index change. Native geometry,
handles, positions, BOM values and every output operation retain source space.
The common rotation cancels from source-to-target dependency transforms.
"""
import copy
import math
from ezdxf.math import Matrix44, Vec3
from cad.frame_geometry import matrix


def angles(plan, context):
    from cad.measured_features import index
    report=context.get('source_features') or index(context,context.get('part_graph'));features=report['features']
    driven={op.ref for op in plan.operations if op.action=='replace_geometry'}
    from graph.native_instances import inventory
    _,identities,_=inventory(dict(context,source_features=report))
    found=[]
    for f in features:
        if identities.get(f.get('instance_ref'))!=f.get('part_code') or not f.get('instance_ref') or not driven.intersection(f['refs']):
            continue
        for d in f.get('dimensions',[]):
            if d['ref'] not in driven:continue
            a=d['axis']
            if abs(a[2])>1e-7:continue
            angle=math.atan2(a[1],a[0]) % (math.pi/2)
            if min(angle,math.pi/2-angle)<1e-7:continue
            if not any(abs(angle-other)<1e-7 for other in found):found.append(angle)
    return sorted(found)


def rotated(context, angle):
    rotation=Matrix44.z_rotate(-angle)
    result=dict(context,entities=[],contact_analysis_angle=angle)
    for e in context['entities']:
        placed=dict(e)
        frame=matrix(e) @ rotation
        placed['frame_to_layout']=[list(frame.get_row(i)) for i in range(4)]
        result['entities'].append(placed)
    from cad.measured_features import index
    features=copy.deepcopy(context.get('source_features') or index(context,context.get('part_graph')))
    for f in features['features']:
        f['points']=[list(rotation.transform(Vec3(p))) for p in f['points']]
        for d in f.get('dimensions',[]):d['axis']=list(rotation.transform_direction(Vec3(d['axis'])))
    for binding in features.get('leader_profile_bindings',[]):
        for endpoint in binding.get('leader_endpoints',[]):endpoint['point']=list(rotation.transform(Vec3(endpoint['point'])))
        for candidate in binding.get('candidates',[]):
            if candidate.get('endpoint'):candidate['endpoint']=list(rotation.transform(Vec3(candidate['endpoint'])))
    result['source_features']=features
    return result
