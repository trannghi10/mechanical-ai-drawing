"""Narrow source evidence for stationary drafting centerlines, not cut edges."""
import math


def annotate(document, record):
    if record.get('type') != 'LINE':
        return
    entity = document.entitydb.get(record['ref'].split('/')[-1])
    if entity is None:
        return
    name = entity.dxf.get('linetype', 'BYLAYER')
    if name.upper() == 'BYLAYER':
        layer = document.layers.get(entity.dxf.layer)
        name = layer.dxf.linetype if layer else 'CONTINUOUS'
    if name.upper() not in ('CENTER', 'CENTER2', 'CENTERX2') or name not in document.linetypes:
        return
    tags = document.linetypes.get(name).pattern_tags.tags
    pattern = [t.value for t in tags if t.code == 49]
    simple = all(t.value == 0 for t in tags if t.code == 74)
    if simple and len(pattern) == 4 and pattern[0] > pattern[2] > 0 and pattern[1] < 0 and pattern[3] < 0:
        record['reference_line'] = dict(kind='centerline', linetype=name, pattern=pattern, simple=True)


def stationary_cross_axis(record, axis, low, high, bottom, top, z):
    """Only a proven centerline parallel to the resized dimension stays put.

    Its infinite reference axis and cross-coordinate are unchanged. The source
    graphic overruns remain intact. Oblique/longitudinal axes still need their
    own attachment and motion rule; a layer name alone is never sufficient.
    """
    proof = record.get('reference_line', {})
    p = proof.get('pattern', [])
    if record.get('type') != 'LINE' or proof.get('kind') != 'centerline' or not proof.get('simple') or len(p) != 4:
        return False
    if not (p[0] > p[2] > 0 and p[1] < 0 and p[3] < 0):
        return False
    g = record.get('geometry', {})
    if not g or any(abs(g[k][2]-z) > 1e-6 for k in ('start', 'end')):
        return False
    direction = [g['end'][i]-g['start'][i] for i in range(3)]
    length = math.dist(g['start'], g['end'])
    if length <= 1e-6 or abs(abs(sum(a*b for a, b in zip(direction, axis)))/length-1) > 1e-7:
        return False
    normal = [-axis[1], axis[0], 0]
    us = sorted(sum(g[k][i]*axis[i] for i in range(3)) for k in ('start', 'end'))
    vs = [sum(g[k][i]*normal[i] for i in range(3)) for k in ('start', 'end')]
    return us[0] < low-1e-6 and us[1] > high+1e-6 and all(bottom-1e-6 <= v <= top+1e-6 for v in vs)


def stationary_hole_marks(records,holes,transform):
    """Accept a symmetric native cross fully inside a stationary source hole.

    Neither block names nor layer names establish ownership. Require a cross
    at the actual circle center, paired segments, and verified center linetypes
    on any disconnected arms. These marks need no geometric edit.
    """
    from cad.geometry import near
    result=set()
    for parent in records.values():
        if parent['type']!='INSERT' or parent.get('attributes'):continue
        center=parent.get('position')
        matching=[g for g in holes if center and near(center,g['center'],1e-6) and near(center,transform(center),1e-6)]
        if not matching:continue
        children=[e for e in records.values() if e['ref'].startswith(parent['ref']+'/')]
        if not 2<=len(children)<=6 or any(e['type']!='LINE' or not e.get('geometry') for e in children):continue
        radius=max(g['radius']-math.dist(center,g['center']) for g in holes);segments=[];axes=[];valid=True
        for e in children:
            a,b=[e['geometry'][k] for k in ('start','end')]
            if e.get('layout')!=parent.get('layout') or any(math.dist(p,center)>=radius-1e-6 for p in (a,b)):valid=False;break
            v=[b[i]-a[i] for i in range(3)];length=math.dist(a,b)
            if length<=1e-6:valid=False;break
            unit=[x/length for x in v]
            if math.dist(a,[center[i]+sum((a[j]-center[j])*unit[j] for j in range(3))*unit[i] for i in range(3)])>1e-6:valid=False;break
            midpoint=[(p+q)/2 for p,q in zip(a,b)]
            if near(midpoint,center,1e-6):axes.append(unit)
            elif e.get('reference_line',{}).get('kind')!='centerline' or not e.get('reference_line',{}).get('simple'):valid=False;break
            segments.append((a,b))
        if not valid or len(axes)!=2 or abs(sum(a*b for a,b in zip(*axes)))>1e-7:continue
        if any(not any(near([2*c-v for c,v in zip(center,a)],p,1e-6) and near([2*c-v for c,v in zip(center,b)],q,1e-6) for p,q in segments for p,q in [(p,q),(q,p)]) for a,b in segments):continue
        result.update([parent['ref']]+[e['ref'] for e in children])
    return result
