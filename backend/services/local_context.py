"""Image-relative locators for overview; retrieve exact CAD values before editing."""
from itertools import product
from ezdxf.math import Matrix44


def overview(context,opened=(),expanded_geometry=(),defer_frames=False):
    result=dict(context);result['entities']=[];definitions={}
    opened=set(opened);expanded_geometry=set(expanded_geometry)
    for original in context['entities']:
        record=dict(original)
        full=record['ref'] in opened or record['ref'] in expanded_geometry or any(record['ref'].startswith(ref+'/') for ref in opened)
        inventory=record.get('child_inventory')
        if inventory and record.get('name'):
            definitions[record['name']]={'count':inventory['count'],'types':inventory['types']}
            record['child_inventory']={'definition':record['name'],'expanded':inventory['expanded']}
        if full:
            result['entities'].append(record);continue
        if record['type']=='DIMENSION' and record.get('geometry'):
            geometry=record.pop('geometry')
            record['geometry_deferred']=True
            record['geometry_summary']={'local_bbox':[
                [min(geometry['defpoint2'][i],geometry['defpoint3'][i]) for i in range(3)],
                [max(geometry['defpoint2'][i],geometry['defpoint3'][i]) for i in range(3)]],
                'bounds_only':True}
        frame=context.get('coordinate_frames',{}).get(record.get('coordinate_frame'))
        matrix=Matrix44([v for row in frame for v in row]) if frame else Matrix44()
        summary=record.get('geometry_summary',{})
        bbox=summary.get('local_bbox')
        anchor=record.get('position') or record.get('text_placement',{}).get('anchor')
        points=[matrix.transform(point) for point in product(*zip(*bbox))] if bbox else [matrix.transform(anchor)] if anchor else []
        if points:
            extent=[min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points)]
            locations=[]
            for target in context['targets']:
                bounds=target.get('bbox')
                if not bounds or target.get('layout')!=record.get('layout'):continue
                if extent[2]<bounds[0] or extent[0]>bounds[2] or extent[3]<bounds[1] or extent[1]>bounds[3]:continue
                width,height=bounds[2]-bounds[0],bounds[3]-bounds[1]
                if width<=0 or height<=0:continue
                locations.append([target['id'],round(1000*(extent[0]-bounds[0])/width),round(1000*(bounds[3]-extent[3])/height),
                                  round(1000*(extent[2]-bounds[0])/width),round(1000*(bounds[3]-extent[1])/height)])
            record['preview_locations']=locations
        if bbox:
            record['geometry_summary']={k:v for k,v in summary.items() if k!='local_bbox'}
        for key in ('position','scale','rotation','text_placement','leader_vertices'):
            record.pop(key,None)
        result['entities'].append(record)
    result['block_definitions']=definitions
    if defer_frames:
        used={e.get('coordinate_frame') for e in result['entities'] if e.get('geometry') or e.get('radial_geometry') or e.get('position')}
        frames=context.get('coordinate_frames',{})
        result['coordinate_frames']={k:v for k,v in frames.items() if k in used}
        result['deferred_frame_count']=len(frames)-len(result['coordinate_frames'])
        result['frame_retrieval']='context_requests / geometry_requests returns exact source frames with expanded records; overview locators are not CAD coordinates.'
    result['locator_coordinates']='Approximate image coordinates 0..1000, origin top-left of each target. NOT CAD coordinates or manufacturing measurements. Request context_requests=[ref] for exact placement/block children and geometry_requests=[ref] for exact geometry before editing.'
    return result
