"""Evidence-derived scope for the bounded eight-vertex, six-DIM adapter."""
import math
import re
from cad.geometry import near,snapshot
from cad.dimension_associations import source_binding
from cad.dimensions import dimension_snapshot
from cad.native_head_repairs import propose,hybrid_binding


def validate_scope(scope):
    handle=lambda s:isinstance(s,str) and re.fullmatch('[A-F0-9]{1,16}',s)
    if scope.get('schema_version')!=1 or not handle(scope.get('polyline_handle')):raise ValueError('Invalid native scope root/schema')
    dims=scope.get('dimension_handles',[]);targets=scope.get('repairs',[]);legacy=scope.get('legacy_handles',[])
    if len(dims)!=6 or len(set(dims))!=6 or not all(map(handle,dims)) or len(targets)!=2 or len(legacy)!=4 or len(set(legacy))!=4 or scope['polyline_handle'] in dims:
        raise ValueError('Unsupported native scope cardinality')
    if set(legacy)&{t['dimension_handle'] for t in targets} or set(legacy)|{t['dimension_handle'] for t in targets}!=set(dims):
        raise ValueError('Native/legacy scope overlap or missing dimensions')
    ids=[]
    for t in targets:
        for k in ['dimension_handle','action_handle','body_handle','geometry_dependency','dimension_dependency']:
            if not handle(t.get(k)):raise ValueError('Invalid native target identity')
            ids.append(t[k])
        if any(type(t.get(k))!=int or not 0<=t[k]<8 for k in ['a_vertex','b_vertex']) or t['a_vertex']==t['b_vertex']:
            raise ValueError('Invalid native endpoint indices')
        if t.get('design_intent_confirmed') is not False:raise ValueError('Unconfirmed intent must remain explicit')
        for k in ['a','b']:
            if len(t.get(k,[]))!=3 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in t[k]):raise ValueError('Invalid native endpoint coordinates')
    if len(set(ids))!=len(ids):raise ValueError('Duplicate native ownership identity')
    return scope


def build_scope(original,base,group,report):
    plan=propose(original,group,report)
    root=group['polyline_handle'];native={t['dimension_handle'] for t in plan['repairs']}
    for t in plan['repairs']:
        angle=math.radians(dimension_snapshot(original.entitydb[t['dimension_handle']])['angle'])
        span=[t['b'][i]-t['a'][i] for i in [0,1]]
        if math.hypot(*span)<=20 or abs(span[0]*math.sin(angle)-span[1]*math.cos(angle))>1e-6:
            raise ValueError('Native scope requires a measurable span parallel to DIM axis')
    if not near(snapshot(original.entitydb[root]),snapshot(base.entitydb[root]),1e-8):raise ValueError('Base polyline geometry changed')
    for h in group['dimension_handles']:
        # Repairing references must not change any DIM measuring point or style.
        if not near(dimension_snapshot(original.entitydb[h]),dimension_snapshot(base.entitydb[h]),1e-8):raise ValueError('Base DIM geometry/style changed')
        if h in native:
            x,y=original.entitydb[h],base.entitydb[h]
            if y.has_extension_dict or set(x.get_reactors())!=set(y.get_reactors()):raise ValueError('Base native DIM topology changed')
        else:
            binding=source_binding(base.entitydb[h])
            if not binding or binding['status']!='verified_source_points' or binding['source_refs']!=[root] or len(binding['points'])!=2:
                raise ValueError('Base legacy DIM must retain two verified endpoints')
    scope=dict(schema_version=1,polyline_handle=root,dimension_handles=group['dimension_handles'],repairs=plan['repairs'],
               legacy_handles=[h for h in group['dimension_handles'] if h not in native])
    return validate_scope(scope)


def result_bindings(doc,scope):
    validate_scope(scope);result={}
    for t in scope['repairs']:
        binding=hybrid_binding(doc.entitydb[t['dimension_handle']],t['dimension_dependency'])
        expected={'defpoint2':t['a_vertex'],'defpoint3':t['b_vertex']}
        if not binding or binding['status']!='verified_source_points' or binding['source_refs']!=[scope['polyline_handle']] or {p['dimension_field']:p['vertex_index'] for p in binding['points']}!=expected:
            raise ValueError('Native result endpoint bindings do not match scope')
        result[t['dimension_handle']]=binding
    return result


def challenge_target(scope,dimension,endpoint,step):
    validate_scope(scope)
    if endpoint not in ('A','B') or abs(step)!=10:raise ValueError('Unsupported endpoint challenge')
    matches=[t for t in scope['repairs'] if t['dimension_handle']==dimension]
    if len(matches)!=1:raise ValueError('DIM outside native repair scope')
    t=matches[0];a,b=t['a'],t['b'];length=math.hypot(b[0]-a[0],b[1]-a[1])
    if length<=20 or abs(a[2]-b[2])>1e-6:raise ValueError('Unsupported short/nonplanar endpoint challenge')
    # Move along the measuring span; A outward and B outward increase length.
    sign=-1 if endpoint=='A' else 1
    delta=[sign*step*(b[i]-a[i])/length for i in [0,1]]+[0]
    return t,t['a_vertex' if endpoint=='A' else 'b_vertex'],delta


def outside_content_handles(inventory,scope):
    """Verify every OLE/tolerance object present, rather than fixture handles."""
    selected={scope['polyline_handle'],*scope['dimension_handles']}
    return sorted(r['handle'] for r in inventory['entities'] if r['handle'] not in selected and r['type'] in ('OLE2FRAME','TOLERANCE'))
