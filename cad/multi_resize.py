"""Compose orthogonal source-measured changes to the same straight profile.

Each recipe is valid against the unchanged source; the final geometry must be
independent of order. One original snapshot and one final operation are emitted
per entity, including holes and dimensions shared by the two axes.
"""
import copy
import json
import math
from cad.parametric import resize
from cad.geometry import near
from cad.frame_geometry import world
from graph.fit_constraints import measurement


def resize_many(recipes,context,values,owners=None):
    if not context.get('source_features'):
        from cad.measured_features import index
        context=dict(context,source_features=index(context,context.get('part_graph')))
    from graph.orthographic_sections import augment
    additional,context,values,virtuals=augment(recipes,context,values)
    recipes=list(recipes)+additional
    records={e['ref']:e for e in context['entities']};groups=[]
    for recipe in recipes:
        overlap=[g for g in groups if any(set(r.outline_refs)&set(recipe.outline_refs) for r in g)]
        if not overlap:groups.append([recipe])
        else:
            combined=[recipe]+[r for g in overlap for r in g]
            groups=[g for g in groups if g not in overlap]+[combined]
    output={}
    for group in groups:
        source=group[0]
        if len(group)>1:
            if len(group)!=2 or any(r.part_code!=source.part_code or set(r.outline_refs)!=set(source.outline_refs) or set(r.hole_refs)!=set(source.hole_refs) for r in group):
                raise ValueError('Recipe chồng đường bao cần đúng hai trục của cùng chi tiết/profile/lỗ')
            # Exact circular fillets can move rigidly on both axes. Each axis
            # still passes resize's arc/bridge checks, and both execution
            # orders must produce identical final native geometry below.
            if any(records[ref]['type'] not in ('LINE','LWPOLYLINE','POLYLINE','ARC') for ref in source.outline_refs):
                raise ValueError('Co/giãn hai trục cần đường bao thẳng hoặc cung tròn chính xác')
            from cad.dimensions import linear_axis
            axes=[linear_axis(world(records[r.dimension_ref])) for r in group]
            if abs(sum(a*b for a,b in zip(*axes)))>1e-7:
                raise ValueError('Hai kích thước cùng profile phải vuông góc; không cộng lệnh cùng trục')
        if len(group)>1:
            for recipe in group:resize(recipe,context,values[recipe.dimension_ref])

        def run(order):
            current=dict(records);changes={}
            for recipe in order:
                local=dict(context,entities=list(current.values()))
                for op in resize(recipe,local,values[recipe.dimension_ref]):
                    record=copy.deepcopy(current[op.ref]);key='geometry' if record.get('geometry') else 'radial_geometry'
                    record[key]=json.loads(op.after)
                    if record['type']=='DIMENSION' and key=='geometry' and record.get('dimension_type',0) in (0,1):
                        record['scaled_measurement']=measurement(record,record[key])
                    current[op.ref]=record;changes[op.ref]=op
            final={}
            for ref,op in changes.items():
                before=records[ref].get('geometry') or records[ref].get('radial_geometry')
                after=current[ref].get('geometry') or current[ref].get('radial_geometry')
                if near(before,after):continue
                final[ref]=op.model_copy(update=dict(before=json.dumps(before),after=json.dumps(after),
                    reason='Đồng bộ các kích thước vuông góc của cùng profile từ snapshot nguồn' if len(group)>1 else op.reason))
            for recipe in group:
                dim=current[recipe.dimension_ref]
                if not near(measurement(dim,dim['geometry']),values[recipe.dimension_ref],1e-6):
                    raise ValueError('Kích thước cuối không khớp recipe đồng thời')
            return final

        result=run(group)
        if len(group)>1:
            reverse=run(list(reversed(group)))
            if result.keys()!=reverse.keys() or any(not near(json.loads(op.after),json.loads(reverse[ref].after),1e-6) for ref,op in result.items()):
                raise ValueError('Co/giãn hai trục phụ thuộc thứ tự; chưa có nghiệm hình học duy nhất')
        for ref,op in result.items():
            if ref in virtuals:continue
            if ref in output and not near(json.loads(output[ref].after),json.loads(op.after),1e-6):
                raise ValueError('Các profile khác nhau sửa mâu thuẫn cùng đối tượng: '+ref)
            output[ref]=op
            if owners is not None:
                if ref in owners and owners[ref]!=source.part_code:raise ValueError('Đối tượng chung chưa có chủ sở hữu duy nhất: '+ref)
                owners[ref]=source.part_code
    from graph.unmeasured_views import expand
    ownership=owners if owners is not None else {}
    if owners is None:
        for recipe in recipes:
            for ref in recipe.outline_refs+recipe.hole_refs+[recipe.dimension_ref]:ownership[ref]=recipe.part_code
    return [op for op in expand(list(output.values()),recipes,context,ownership) if op.ref not in virtuals]
