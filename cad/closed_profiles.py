"""Source-closed straight contours, including notches and split edge entities."""
from collections import defaultdict
import networkx as nx
from shapely.geometry import Polygon,Point
from cad.geometry import near


def segments(record):
    g=record.get('geometry',{})
    if record['type']=='LINE' and g:return [(g['start'],g['end'])]
    if record['type'] not in ('LWPOLYLINE','POLYLINE') or not g or not near(g['extrusion'],[0,0,1]) or any(any(p[2:]) for p in g['points']) or any(g.get('default_widths',[])):return []
    points=[[p[0],p[1],g['elevation']] for p in g['points']]
    return list(zip(points,points[1:]+points[:1])) if g['closed'] else list(zip(points,points[1:]))


def contours(records):
    graph=nx.Graph();edges=defaultdict(list);original={}
    result=[]
    def key(p):return tuple(round(float(v),5) for v in p)
    for e in records:
        source_edges=segments(e)
        # A native closed polyline carries its own topological boundary. Two
        # different parts sharing a face must not merge into one branched graph.
        # Loose LINE cycles still require isolated, unambiguous source edges.
        if e['type'] in ('LWPOLYLINE','POLYLINE') and e.get('geometry',{}).get('closed') and len(source_edges) >= 3:
            try:
                points=[a for a,b in source_edges];polygon=Polygon([p[:2] for p in points])
                if polygon.is_valid and polygon.area>1e-8 and max(p[2] for p in points)-min(p[2] for p in points)<=1e-5:
                    result.append(dict(refs=[e['ref']],points=points))
            except Exception:
                pass
            continue
        for a,b in source_edges:
            ka,kb=key(a),key(b)
            if ka==kb:continue
            graph.add_edge(ka,kb);edges[tuple(sorted((ka,kb)))].append(e['ref'])
            original.setdefault(ka,a);original.setdefault(kb,b)
    for component in nx.connected_components(graph):
        if len(component)<4 or any(graph.degree(p)!=2 for p in component):continue
        start=min(component);order=[start];previous=None;current=start
        while len(order)<len(component):
            nxt=next((p for p in sorted(graph.neighbors(current)) if p!=previous and p not in order),None)
            if nxt is None:break
            order.append(nxt);previous,current=current,nxt
        if len(order)!=len(component) or not graph.has_edge(order[-1],start):continue
        refs=[]
        for a,b in zip(order,order[1:]+order[:1]):
            found=edges[tuple(sorted((a,b)))]
            if len(found)!=1:break
            refs.extend(found)
        else:
            points=[original[k] for k in order]
            if max(p[2] for p in points)-min(p[2] for p in points)>1e-5:continue
            try:
                polygon=Polygon([p[:2] for p in points])
                if polygon.is_valid and polygon.area>1e-8:
                    result.append(dict(refs=sorted(set(refs)),points=points))
            except Exception:
                pass
    return result


def polygon_from(records):
    rings=contours(records)
    if len(rings)!=1 or set(rings[0]['refs'])!={e['ref'] for e in records}:raise ValueError('Đường bao chưa khép kín duy nhất hoặc có cạnh trùng/nhánh')
    return rings[0]['points']


def touches(points,point,tolerance=1e-5):
    return Polygon([p[:2] for p in points]).boundary.distance(Point(point[:2]))<=tolerance
