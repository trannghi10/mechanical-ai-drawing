"""Independent OCC closure/face check of the actual exported callout strip.

Run with FreeCAD's Python; input is read back from the DWG conversion.
This proves the 2D strip, not the complete assembly or fabrication strength.
"""
import json,math,sys
import FreeCAD as App
import Part


def vector(p):return App.Vector(*p)


def point(arc,angle):
    a=math.radians(angle);c=arc['center'];r=arc['radius']
    return [c[0]+r*math.cos(a),c[1]+r*math.sin(a),c[2]]


def edge(arc):
    span=(arc['end_angle']-arc['start_angle'])%360
    return Part.Arc(vector(point(arc,arc['start_angle'])),vector(point(arc,arc['start_angle']+span/2)),vector(point(arc,arc['end_angle']))).toShape()


def clip_edge(clip,a,b):
    c=clip['center'];a0=math.degrees(math.atan2(a[1]-c[1],a[0]-c[0]));b0=math.degrees(math.atan2(b[1]-c[1],b[0]-c[0]))
    delta=(b0-a0+180)%360-180
    return Part.Arc(vector(a),vector(point(clip,a0+delta/2)),vector(b)).toShape()


def check(data):
    outer,inner,leg0,leg1,clip=(data[k] for k in ('outer','inner','outer_leg','inner_leg','clip'))
    # Recenter to avoid loss of precision at large modelspace coordinates.
    origin=clip['center'][:]
    for k in ('outer','inner','clip'):
        data[k]['center']=[v-origin[i] for i,v in enumerate(data[k]['center'])]
    for k in ('outer_leg','inner_leg'):
        for key in ('start','end'):data[k][key]=[v-origin[i] for i,v in enumerate(data[k][key])]
    outer_clip=point(outer,outer['end_angle']);inner_clip=point(inner,inner['end_angle'])
    assert min((outer['end_angle']-outer['start_angle'])%360,(inner['end_angle']-inner['start_angle'])%360)>0
    # The supported orientation is supplied and checked by the native adapter.
    assert (vector(point(outer,outer['start_angle']))-vector(leg0['start'])).Length<1e-5
    assert (vector(point(inner,inner['start_angle']))-vector(leg1['start'])).Length<1e-5
    edges=[Part.makeLine(vector(leg0['end']),vector(leg0['start'])),edge(outer),
        clip_edge(clip,outer_clip,inner_clip),edge(inner),
        Part.makeLine(vector(leg1['start']),vector(leg1['end'])),clip_edge(clip,leg1['end'],leg0['end'])]
    wire=Part.Wire(edges);face=Part.Face(wire)
    assert wire.isClosed() and wire.isValid() and face.isValid() and face.Area>0
    return dict(closed=True,valid_face=True,face_area_layout_squared=face.Area,edge_count=len(wire.Edges),
        scope='Exported 2D clipped strip only; not an assembly/strength certification')


if __name__=='__main__':
    result=check(json.load(open(sys.argv[1],encoding='utf8')))
    with open(sys.argv[2],'w',encoding='utf8') as f:json.dump(result,f,indent=2)
