"""Reuse measured features only across complete, identical source definitions.

This is correspondence between views of one verified part, not a contact rule
between different parts or a reconstruction of a perspective projection.
"""
import math
import json
from ezdxf.math import Vec3
from cad.frame_geometry import world, matrix, similarity
from cad.geometry import near
from cad.measured_features import index
from graph.native_instances import equivalent_flat_refs

OWNED_PROOFS = {'native_part_identity', 'unique_source_detail_sheet', 'local_bom_leader_profile'}


def coalesce_equivalent_recipes(recipes, context):
    """Collapse redundant DIM drivers only after checking their full motion.

    Equal numbers/axes alone cannot prove a common anchor. Each driver is
    compiled independently against the unchanged source, including all bound
    DIMs, holes and leaders. Different or unsupported results stay separate.
    """
    from cad.parametric import resize
    result=[];groups={};snapshots={}
    def snapshot(recipe):
        key=(recipe.part_code,recipe.dimension_ref,recipe.anchor,recipe.new_measurement,
             tuple(sorted(recipe.outline_refs)),tuple(sorted(recipe.hole_refs)),tuple(sorted(recipe.evidence_refs)))
        if key not in snapshots:
            try:
                operations=resize(recipe,context,recipe.new_measurement)
                snapshots[key]={op.ref:(op.action,op.before,op.after) for op in operations}
            except ValueError:snapshots[key]=None
        return snapshots[key]
    def same(a,b):
        return a is not None and b is not None and a.keys()==b.keys() and all(
            a[ref][0]==b[ref][0] and near(json.loads(a[ref][1]),json.loads(b[ref][1]),1e-6)
            and near(json.loads(a[ref][2]),json.loads(b[ref][2]),1e-6) for ref in a)
    for recipe in recipes:
        if recipe.new_measurement is None:result.append(recipe);continue
        key=(recipe.part_code,tuple(sorted(recipe.outline_refs)),tuple(sorted(recipe.hole_refs)),recipe.new_measurement)
        alternatives=groups.setdefault(key,[])
        if any(same(snapshot(previous),snapshot(recipe)) for previous in alternatives):continue
        alternatives.append(recipe);result.append(recipe)
    return result


def expand(recipes, context):
    recipes=coalesce_equivalent_recipes(recipes,context)
    records = {e['ref']: e for e in context['entities']}
    report = context.get('source_features') or index(context, context.get('part_graph'))
    features = report['features']
    result = list(recipes)
    by_dim = {r.dimension_ref: r for r in result}
    mappings = {}

    def feature_for(recipe):
        matches = [f for f in features if f.get('part_code') == recipe.part_code
                   and f.get('ownership_proof') in OWNED_PROOFS
                   and set(f['refs']) == set(recipe.outline_refs)
                   and any(d['ref'] == recipe.dimension_ref for d in f['dimensions'])]
        return matches[0] if len(matches) == 1 else None

    def frame(feature):
        name = feature.get('coordinate_frame', '') or ''
        root = name.removeprefix('instance:') if name.startswith('instance:') else None
        if not root or records.get(root, {}).get('type') != 'INSERT': return None
        if not all(ref.startswith(root + '/') for ref in feature['refs']): return None
        return root

    def local_dim(ref, feature):
        record = world(records[ref]); geometry = record['geometry']
        m = matrix(records[feature['refs'][0]]); similarity(m); m.inverse()
        from cad.dimensions import linear_axis
        axis = m.transform_direction(Vec3(linear_axis(record))).normalize()
        return ([list(m.transform(Vec3(geometry[k]))) for k in ('defpoint2', 'defpoint3')], list(axis))

    for recipe in recipes:
        if recipe.new_measurement is None:continue
        source = feature_for(recipe)
        source_root = frame(source) if source else None
        if not source_root: continue
        if not all(ref.startswith(source_root + '/') for ref in recipe.hole_refs): continue
        try: source_points, source_axis = local_dim(recipe.dimension_ref, source)
        except ValueError: continue
        source_binding = next(d for d in source['dimensions'] if d['ref'] == recipe.dimension_ref)
        for target in features:
            if target.get('part_code') != recipe.part_code or target.get('ownership_proof') not in OWNED_PROOFS: continue
            target_root = frame(target)
            if not target_root or target_root == source_root: continue
            pair = (source_root, target_root)
            if pair not in mappings: mappings[pair] = equivalent_flat_refs(records, *pair)
            mapping = mappings[pair]
            if not mapping or {mapping.get(ref) for ref in recipe.outline_refs} != set(target['refs']): continue
            refs = [mapping.get(ref) for ref in recipe.outline_refs + recipe.hole_refs]
            if not all(ref in records and not records[ref].get('review_only') for ref in refs): continue
            matches = []
            for binding in target['dimensions']:
                if not near(binding['measurement'], source_binding['measurement'], 1e-5): continue
                try: points, axis = local_dim(binding['ref'], target)
                except ValueError: continue
                if abs(abs(sum(a*b for a,b in zip(axis,source_axis)))-1) > 1e-7: continue
                if near(points, source_points, 1e-5): reverse = False
                elif near(points, source_points[::-1], 1e-5): reverse = True
                else: continue
                anchor = recipe.anchor
                if reverse and anchor != 'center': anchor = 'second' if anchor == 'first' else 'first'
                matches.append((binding['ref'], anchor))
            # Redundant DIMs are acceptable only when every independently
            # compiled driver produces the exact same complete CAD edits.
            if len(matches)>1:
                options=[recipe.model_copy(update=dict(dimension_ref=ref,anchor=anchor,
                    outline_refs=[mapping[r] for r in recipe.outline_refs],hole_refs=[mapping[r] for r in recipe.hole_refs],
                    evidence_refs=sorted(set(refs+[ref,source_root,target_root]+recipe.evidence_refs)))) for ref,anchor in matches]
                unique=coalesce_equivalent_recipes(options,context)
                if len(unique)==1:matches=[(unique[0].dimension_ref,unique[0].anchor)]
            if len(matches) != 1: continue
            dimension, anchor = matches[0]
            copied = recipe.model_copy(update=dict(dimension_ref=dimension, anchor=anchor,
                outline_refs=[mapping[r] for r in recipe.outline_refs],
                hole_refs=[mapping[r] for r in recipe.hole_refs],
                evidence_refs=sorted(set(refs + [dimension, source_root, target_root] + recipe.evidence_refs))))
            previous = by_dim.get(dimension)
            if previous:
                if (previous.part_code != copied.part_code or previous.anchor != copied.anchor
                    or not near(previous.new_measurement, copied.new_measurement)
                    or set(previous.outline_refs) != set(copied.outline_refs)
                    or set(previous.hole_refs) != set(copied.hole_refs)):
                    raise ValueError('Các hình chiếu cùng định nghĩa có recipe xung đột: ' + dimension)
                continue
            result.append(copied); by_dim[dimension] = copied
    return expand_exploded_views(result,context,report)


def expand_exploded_views(recipes,context,report):
    """Turn a unique checked correspondence into independently checked recipes.

    Reading identity alone never authorizes motion. Require one exact transform,
    complete hole sets and a unique real DIM measuring the same source endpoints
    in each view. The normal parametric compiler still validates every receiver.
    """
    from graph.part_map import build as part_map,VERSION
    by_dim={r.dimension_ref:r for r in recipes};measurements={}
    for recipe in recipes:
        for f in report['features']:
            if set(f['refs'])==set(recipe.outline_refs):
                measurements[(recipe.part_code,recipe.dimension_ref)]=next((d['measurement'] for d in f['dimensions'] if d['ref']==recipe.dimension_ref),None)
    if not any(d['ref'] not in by_dim and any(code==f.get('part_code') and value is not None and near(d['measurement'],value,1e-5) for (code,_),value in measurements.items())
               for f in report['features'] for d in f['dimensions']):return recipes
    # Native matches above are sufficient unless a representation actually
    # differs (for example LWPOLYLINE versus four exploded LINE entities).
    stored=context.get('design_model',{}).get('part_map')
    if stored and stored.get('source_hash')!=context.get('source_hash'):
        raise ValueError('Part Map không khớp nguồn CAD của bản sửa')
    if stored and stored.get('version')!=VERSION:stored=None
    mapped=stored or part_map(dict(context,source_features=report))
    views={v['id']:v for v in mapped['views']}
    relations=[r for r in mapped['correspondences'] if r['status']=='verified_source_correspondence' and
        r['proof']=='exact_outline_and_circles' and r.get('transform',{}).get('transform_count')==1]
    if not relations:return recipes
    records={e['ref']:e for e in context['entities']};result=list(recipes);by_dim={r.dimension_ref:r for r in result}
    for recipe in recipes:
        if recipe.new_measurement is None:continue
        sources=[v for v in views.values() if v['identity_status']=='verified_source_identity' and v['part_codes']==[recipe.part_code] and
                 set(v['geometry_refs'])==set(recipe.outline_refs) and set(v['circle_refs'])==set(recipe.hole_refs) and
                 any(d['ref']==recipe.dimension_ref for d in v['dimensions'])]
        if len(sources)!=1:continue
        source=sources[0]
        for relation in relations:
            if source['id'] not in (relation['source_view_id'],relation['target_view_id']):continue
            forward=source['id']==relation['source_view_id'];target=views[relation['target_view_id'] if forward else relation['source_view_id']]
            refs=target['geometry_refs']+target['circle_refs']
            if not refs or any(r not in records or records[r].get('review_only') for r in refs):continue
            transform=relation['transform'];angle=math.radians(transform['rotation_degrees']);cosine,sine=math.cos(angle),math.sin(angle)
            fa,fb=transform['source_mm_per_layout_unit'],transform['target_mm_per_layout_unit']
            origin,destination=transform['source_origin_mm'],transform['target_origin_mm']
            source_dimension=next(d for d in source['dimensions'] if d['ref']==recipe.dimension_ref)
            original=world(records[recipe.dimension_ref])['geometry']
            def mapped_point(point):
                if forward:
                    x,y=point[0]*fa-origin[0],point[1]*fa-origin[1]
                    return [(destination[0]+cosine*x-sine*y)/fb,(destination[1]+sine*x+cosine*y)/fb]
                x,y=point[0]*fb-destination[0],point[1]*fb-destination[1]
                return [(origin[0]+cosine*x+sine*y)/fa,(origin[1]-sine*x+cosine*y)/fa]
            endpoints=[mapped_point(original[k]) for k in ('defpoint2','defpoint3')];matches=[]
            for binding in target['dimensions']:
                ref=binding['ref']
                if ref not in records or records[ref].get('review_only') or not near(binding['measurement'],source_dimension['measurement'],1e-5):continue
                g=world(records[ref])['geometry']
                if g.get('text') not in ('','<>'):continue
                points=[g[k][:2] for k in ('defpoint2','defpoint3')]
                if near(points,endpoints,1e-5):reverse=False
                elif near(points,endpoints[::-1],1e-5):reverse=True
                else:continue
                anchor=recipe.anchor
                if reverse and anchor!='center':anchor='second' if anchor=='first' else 'first'
                matches.append((ref,anchor))
            if len(matches)>1:
                options=[recipe.model_copy(update=dict(dimension_ref=ref,anchor=anchor,outline_refs=list(target['geometry_refs']),
                    hole_refs=list(target['circle_refs']),evidence_refs=sorted(set(refs+[ref]+target['evidence_refs'])))) for ref,anchor in matches]
                unique=coalesce_equivalent_recipes(options,context)
                if len(unique)==1:matches=[(unique[0].dimension_ref,unique[0].anchor)]
            if len(matches)!=1:continue
            ref,anchor=matches[0]
            copied=recipe.model_copy(update=dict(dimension_ref=ref,anchor=anchor,outline_refs=list(target['geometry_refs']),
                hole_refs=list(target['circle_refs']),evidence_refs=sorted(set(refs+[ref]+target['evidence_refs']))))
            previous=by_dim.get(ref)
            if previous:
                if previous.part_code!=copied.part_code or previous.anchor!=copied.anchor or not near(previous.new_measurement,copied.new_measurement) or set(previous.outline_refs)!=set(copied.outline_refs) or set(previous.hole_refs)!=set(copied.hole_refs):
                    raise ValueError('Các hình nét rời có recipe xung đột: '+ref)
                continue
            by_dim[ref]=copied;result.append(copied)
    return result
