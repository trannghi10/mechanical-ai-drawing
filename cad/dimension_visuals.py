"""Check visible DIM primitives separately from its measured definition points."""
import copy
import math
from cad.geometry import near

_POINTS={'LINE':('start','end'),'SOLID':('vtx0','vtx1','vtx2','vtx3'),'TRACE':('vtx0','vtx1','vtx2','vtx3'),
         'TEXT':('insert','align_point'),'MTEXT':('insert',),'INSERT':('insert',),'CIRCLE':('center',),'ARC':('center',),'POINT':('location',)}


def records(dimension,delta=(0,0,0)):
    result=[]
    def plain(value):
        if value is None or isinstance(value,(str,int,float,bool)):return value
        return [plain(v) for v in value]
    for entity in dimension.virtual_entities():
        kind=entity.dxftype()
        if kind not in _POINTS:raise ValueError('DIM visual primitive chưa có bộ đối chiếu: '+kind)
        data={key:plain(value) for key,value in entity.dxfattribs().items() if key not in ('handle','owner','paperspace')}
        # Compare resolved opacity, preserving differences in visible output.
        # AutoCAD regen can switch DIM primitives from BYLAYER to BYBLOCK.
        def opacity(item,layer_name):
            if item.is_transparency_by_layer:return item.doc.layers.get(layer_name).transparency
            return item.transparency
        layer_name=dimension.dxf.layer if entity.dxf.layer=='0' else entity.dxf.layer
        if entity.is_transparency_by_block:
            transparency=opacity(dimension,dimension.dxf.layer)
        elif entity.is_transparency_by_layer:
            transparency=dimension.doc.layers.get(layer_name).transparency
        else:transparency=entity.transparency
        data.pop('transparency',None);data['effective_transparency']=transparency
        if kind=='MTEXT':data['content']=entity.text
        if kind=='TEXT' and not entity.dxf.halign and not entity.dxf.valign:data.pop('align_point',None)
        for key in _POINTS[kind]:
            if key in data:data[key]=[v-d for v,d in zip(data[key],delta)]
        result.append(dict(type=kind,attributes=data))
    return result


def verify_translation(before,after,delta,tolerance=1e-6):
    expected=records(before);remaining=records(after,delta)
    if len(expected)!=len(remaining):raise ValueError('DIM visual primitive count changed')
    for item in expected:
        index=next((i for i,value in enumerate(remaining) if near(item,value,tolerance)),None)
        if index is None:raise ValueError('DIM visual geometry/style/text did not translate exactly')
        remaining.pop(index)
    return dict(status='verified_translated_dimension_visuals',primitive_count=len(expected))


def verify_regenerated_appearance(before,after,tolerance=1e-6):
    """Style/count check only; caller must separately verify measured geometry/text."""
    def appearance(dim):
        result=[]
        for item in records(dim):
            attrs=dict(item['attributes'])
            for key in _POINTS[item['type']]:attrs.pop(key,None)
            if item['type']=='MTEXT':attrs.pop('content',None)
            if item['type']=='TEXT':attrs.pop('text',None)
            result.append(dict(type=item['type'],attributes=attrs))
        return result
    remaining=appearance(after);expected=appearance(before)
    if len(remaining)!=len(expected):raise ValueError('Regenerated DIM primitive count differs')
    for item in expected:
        index=next((i for i,value in enumerate(remaining) if near(item,value,tolerance)),None)
        if index is None:raise ValueError('Regenerated DIM primitive style/type differs')
        remaining.pop(index)
    return dict(status='verified_regenerated_dimension_appearance',primitive_count=len(expected),
                full_primitive_geometry_verified=False,policy='Counts and style only; measured endpoints and numeric labels require separate checks.')


def verify_horizontal_stretch(before,after,*,before_text_height,after_text_height,tolerance=1e-6):
    """Bounded 9-primitive horizontal DIM: rigid end graphics, stretched baseline.

    Native MText heights are required because regenerated glyph metrics can change.
    This does not infer endpoint bindings or authorize a mechanical edit.
    """
    from cad.dimensions import dimension_snapshot
    a=dimension_snapshot(before);b=dimension_snapshot(after)
    if (abs(a['angle'])>1e-10 or abs(b['angle'])>1e-10
            or not all(math.isfinite(h) and h>0 for h in (before_text_height,after_text_height))):
        raise ValueError('Horizontal DIM and finite native text heights required')
    left,right=a['defpoint2'][0],a['defpoint3'][0]
    new_left,new_right=b['defpoint2'][0],b['defpoint3'][0]
    if right-left<=tolerance or new_right-new_left<=tolerance:
        raise ValueError('Ordered noncollapsed DIM endpoints required')
    if not near(a['defpoint2'][1:],b['defpoint2'][1:],tolerance) or not near(a['defpoint3'][1:],b['defpoint3'][1:],tolerance) or not near(a['defpoint'][1:],b['defpoint'][1:],tolerance):
        raise ValueError('Only horizontal endpoint stretch is supported')
    expected=copy.deepcopy(records(before));remaining=records(after)
    kinds=[r['type'] for r in expected]
    if sorted(kinds)!=sorted(['LINE']*3+['SOLID']*2+['MTEXT']+['POINT']*3):
        raise ValueError('Unsupported horizontal DIM primitive structure')
    old_text=next(r['attributes'] for r in expected if r['type']=='MTEXT')
    new_text=next((r['attributes'] for r in remaining if r['type']=='MTEXT'),{})
    if old_text.get('attachment_point')!=5 or old_text.get('width')!=0 or new_text.get('width')!=0:
        raise ValueError('Unwrapped middle-center DIM text required')
    # The verified native profile uses one default numeric MText with this prefix.
    if old_text['content']!='\\A1;'+str(round(before.get_measurement())) or new_text.get('content')!='\\A1;'+str(round(after.get_measurement())):
        raise ValueError('Unexpected regenerated DIM numeric label')
    old_gap=old_text['insert'][1]-a['defpoint'][1]
    if abs(old_gap)<=tolerance:raise ValueError('DIM text side is undefined')
    for item in expected:
        attrs=item['attributes']
        if item['type']=='MTEXT':
            attrs['insert'][0]+=((new_left-left)+(new_right-right))*.5
            attrs['insert'][1]+=math.copysign(1,old_gap)*(after_text_height-before_text_height)*.5
            attrs['content']='\\A1;'+str(round(after.get_measurement()))
        else:
            for key in _POINTS[item['type']]:
                p=attrs[key]
                distances=[abs(p[0]-left),abs(p[0]-right)]
                # No center graphics/leader/text-break layout is accepted by this adapter.
                if min(distances)>=min(right-left,new_right-new_left)*.25:
                    raise ValueError('Primitive is outside the verified DIM endpoint region')
                p[0]+=(new_left-left) if distances[0]<distances[1] else (new_right-right)
    if len(expected)!=len(remaining):raise ValueError('Stretched DIM primitive count changed')
    for item in expected:
        index=next((i for i,value in enumerate(remaining) if near(item,value,tolerance)),None)
        if index is None:raise ValueError('Stretched DIM primitive geometry/style/text mismatch')
        remaining.pop(index)
    return dict(status='verified_horizontal_stretch_dimension_visuals',primitive_count=len(expected),
                full_primitive_geometry_verified=True,native_glyph_heights=[before_text_height,after_text_height],
                coverage='Bounded horizontal 3 LINE, 2 SOLID, 1 MTEXT, 3 POINT profile only; not mechanical edit authorization.')
