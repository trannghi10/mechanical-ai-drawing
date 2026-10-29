"""Bounded native vertex evidence, scoped to a hash-checked source group."""
import hashlib,json,re
from cad.geometry import near
from cad.dimensions import dimension_snapshot


def vertex_bindings(doc,group,report):
    def require(ok,message):
        if not ok:raise ValueError(message)
    source_hash=group.get('source_sha256','')
    require(bool(re.fullmatch('[a-f0-9]{64}',source_hash)), 'Source SHA-256 is required for native vertex evidence')
    require(report.get('source_sha256')==source_hash and report.get('polyline_handle')==group['polyline_handle']
            and report.get('status')=='inspected_native_subentities','Native vertex evidence source mismatch')
    expected={a['dimension_handle']:a for a in group['native_actions']}
    rows=report.get('dependencies',[])
    require(len(rows)==len(expected) and {r['dimension_handle'] for r in rows}==set(expected),'Incomplete or duplicate native subentity evidence')
    poly=doc.entitydb[group['polyline_handle']];points=[list(p) for p in poly.get_points()]
    # Polyline points include widths/bulge; native vertex geometry is XYZ with elevation.
    points=[[p[0],p[1],poly.dxf.elevation] for p in points]
    result={}
    for row in rows:
        dim=row['dimension_handle'];native=row['geometry'];action=expected[dim]
        require(native.get('source_handle')==group['polyline_handle'] and native.get('action_handle')==action['action_handle']
                and native.get('dependency_handle')==action['geometry_dependency'],'Native subentity topology mismatch')
        require(native.get('errors')==[] and native.get('subentity_type')=='Vertex','Native vertex evidence is partial or unsupported')
        require(native.get('is_caching_geometry') is False,'Cached native vertex geometry is not supported as binding evidence')
        ids=native.get('transient_ids',[]);vertices=native.get('vertices',[])
        require(len(ids)==1 and ids[0].get('type')=='Vertex' and isinstance(ids[0].get('index'),int)
                and len(vertices)==1,'Native vertex reference must be singular')
        p=vertices[0]['point'];indices=[i for i,q in enumerate(points) if near(p,q,1e-6)]
        require(len(indices)==1 and vertices[0].get('matching_polyline_vertices')==indices,'Native vertex geometry mismatch')
        snapshot=dimension_snapshot(doc.entitydb[dim])
        fields=[f for f in ('defpoint2','defpoint3') if near(snapshot[f],p,1e-6)]
        require(len(fields)==1,'Native vertex does not uniquely identify a DIM endpoint')
        result[(dim,fields[0])]=dict(kind='verified_native_vertex',field=fields[0],vertex_index=indices[0],
            geometry_dependency=action['geometry_dependency'],action_handle=action['action_handle'],
            transient_subentity_index=ids[0]['index'],source_point=p)
    fingerprint=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result,fingerprint
