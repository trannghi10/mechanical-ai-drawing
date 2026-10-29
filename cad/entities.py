from typing import Any, Dict, List, Optional
import ezdxf


def extract_entities(container) -> List[Dict[str, Any]]:
    """Trích xuất chi tiết toàn bộ thực thể CAD từ modelspace, layout hoặc block container.
    Hỗ trợ đầy đủ các kiểu hình học cơ khí: LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC,
    ELLIPSE, SPLINE, TEXT, MTEXT, DIMENSION, INSERT, HATCH, SOLID, POINT, LEADER,
    MULTILEADER, VIEWPORT, WIPEOUT, MLINE, IMAGE, TOLERANCE, ARC_DIMENSION...
    """
    result = []

    for entity in container:
        entity_type = entity.dxftype()

        item: Dict[str, Any] = {
            "type": entity_type,
            "handle": getattr(entity.dxf, "handle", ""),
        }

        if hasattr(entity.dxf, "layer"):
            item["layer"] = entity.dxf.layer

        if hasattr(entity.dxf, "color"):
            item["color"] = entity.dxf.color

        try:
            if entity_type == "LINE":
                item["start"] = [round(float(entity.dxf.start.x), 4), round(float(entity.dxf.start.y), 4)]
                item["end"] = [round(float(entity.dxf.end.x), 4), round(float(entity.dxf.end.y), 4)]

            elif entity_type in ('XLINE','RAY'):
                item['start']=list(entity.dxf.start)
                item['unit_vector']=list(entity.dxf.unit_vector)
                item['extent_kind']='infinite' if entity_type=='XLINE' else 'semi_infinite'

            elif entity_type=='TOLERANCE':
                item['text']=entity.dxf.content
                item['position']=list(entity.dxf.insert)
                item['x_axis_vector']=list(entity.dxf.x_axis_vector)
                item['extrusion']=list(entity.dxf.extrusion)
                item['dimstyle']=entity.dxf.dimstyle

            elif entity_type=='ARC_DIMENSION':
                # Preserve native arc-length annotation and definition points.
                # get_measurement() does not support R2018 arc dimensions in
                # this ezdxf runtime; do not reinterpret them as angle DIMs.
                item['text']=entity.dxf.get('text','')
                item['actual_measurement']=entity.dxf.get('actual_measurement',None)
                item['measurement_status']='source_cached_value' if item['actual_measurement'] is not None else 'not_available'
                item['dimtype']=entity.dxf.dimtype
                item['geometry_block']=entity.dxf.get('geometry','')
                item['dimstyle']=entity.dxf.dimstyle
                for key in ('defpoint','defpoint2','defpoint3','defpoint4','text_midpoint','leader_point1','leader_point2'):
                    if entity.dxf.hasattr(key):item[key]=list(entity.dxf.get(key))
                for key in ('start_angle','end_angle','is_partial','has_leader'):
                    item[key]=entity.dxf.get(key)

            elif entity_type == "CIRCLE":
                item["center"] = [round(float(entity.dxf.center.x), 4), round(float(entity.dxf.center.y), 4)]
                item["radius"] = round(float(entity.dxf.radius), 4)

            elif entity_type == "ARC":
                item["center"] = [round(float(entity.dxf.center.x), 4), round(float(entity.dxf.center.y), 4)]
                item["radius"] = round(float(entity.dxf.radius), 4)
                item["start_angle"] = round(float(entity.dxf.start_angle), 4)
                item["end_angle"] = round(float(entity.dxf.end_angle), 4)

            elif entity_type == "LWPOLYLINE":
                points = []
                for p in entity.get_points(format="xy"):
                    points.append([round(float(p[0]), 4), round(float(p[1]), 4)])
                item["points"] = points
                item["is_closed"] = bool(entity.closed)
                item['vertices_xyseb']=[list(map(float,p)) for p in entity.get_points('xyseb')]
                item['elevation']=float(entity.dxf.elevation)
                item['extrusion']=list(entity.dxf.extrusion)

            elif entity_type == "POLYLINE":
                points = []
                if hasattr(entity, "vertices"):
                    for v in entity.vertices:
                        points.append(list(v.dxf.location))
                item["points"] = points
                item["is_closed"] = bool(getattr(entity, "is_closed", False))

            elif entity_type == "ELLIPSE":
                item["center"] = [round(float(entity.dxf.center.x), 4), round(float(entity.dxf.center.y), 4)]
                item["major_axis"] = [round(float(entity.dxf.major_axis.x), 4), round(float(entity.dxf.major_axis.y), 4)]
                item["ratio"] = round(float(entity.dxf.ratio), 4)
                item['start_param']=float(entity.dxf.start_param)
                item['end_param']=float(entity.dxf.end_param)

            elif entity_type == "SPLINE":
                cps = []
                if hasattr(entity, "control_points"):
                    for cp in entity.control_points:
                        cps.append([round(float(cp[0]), 4), round(float(cp[1]), 4)])
                item["control_points"] = cps
                item["closed"] = bool(getattr(entity, "closed", False))
                item['fit_points']=[list(p) for p in entity.fit_points]
                item['knots']=list(entity.knots);item['weights']=list(entity.weights)
                item['degree']=entity.dxf.degree;item['flags']=entity.dxf.flags

            elif entity_type in ("TEXT","ATTRIB","ATTDEF"):
                item["text"] = entity.dxf.text
                item["position"] = [round(float(entity.dxf.insert.x), 4), round(float(entity.dxf.insert.y), 4)]
                item["height"] = round(float(getattr(entity.dxf, "height", 2.5)), 4)
                item["rotation"] = round(float(getattr(entity.dxf, "rotation", 0.0)), 4)
                if entity_type in ('ATTRIB','ATTDEF'):item['tag']=entity.dxf.tag

            elif entity_type == "MTEXT":
                plain = entity.plain_text() if hasattr(entity, "plain_text") else entity.text
                item["text"] = plain
                item["position"] = [round(float(entity.dxf.insert.x), 4), round(float(entity.dxf.insert.y), 4)]
                item["height"] = round(float(getattr(entity.dxf, "char_height", 2.5)), 4)
                item["rotation"] = round(float(getattr(entity.dxf, "rotation", 0.0)), 4)

            elif entity_type == "INSERT":
                item["block_name"] = entity.dxf.name
                item["position"] = [round(float(entity.dxf.insert.x), 4), round(float(entity.dxf.insert.y), 4)]
                item["scale"] = [
                    round(float(getattr(entity.dxf, "xscale", 1.0)), 4),
                    round(float(getattr(entity.dxf, "yscale", 1.0)), 4),
                    round(float(getattr(entity.dxf, "zscale", 1.0)), 4),
                ]
                item["rotation"] = round(float(getattr(entity.dxf, "rotation", 0.0)), 4)
                attribs = {}
                for att in getattr(entity, "attribs", []):
                    attribs[att.dxf.tag] = att.dxf.text
                item["attributes"] = attribs

            elif entity_type=='ACAD_TABLE':
                item['geometry_block']=entity.dxf.get('geometry','')
                item['rows']=entity.dxf.get('n_rows',0)
                item['columns']=entity.dxf.get('n_cols',0)
                item['cell_status']='requires_source_cell_values'

            elif entity_type == "DIMENSION":
                val = None
                cached_measurement = entity.dxf.get('actual_measurement')
                if cached_measurement is not None:
                    val = round(float(cached_measurement), 4)
                text = getattr(entity.dxf, "text", "")
                item["text"] = text or (str(val) if val is not None else "")
                item["actual_measurement"] = val
                measured=entity.get_measurement()
                if entity.dxf.dimtype & 15==1:
                    import math
                    measured=math.dist(entity.dxf.defpoint2,entity.dxf.defpoint3)
                if isinstance(measured,(int,float)):
                    item['geometric_measurement']=float(measured)
                    item['linear_factor']=float(entity.override().get('dimlfac',1))
                    item['scaled_measurement']=abs(measured*item['linear_factor'])
                item["dimtype"] = getattr(entity, "dimtype", None)
                if hasattr(entity.dxf, "defpoint"):
                    item["defpoint"] = [round(float(entity.dxf.defpoint.x), 4), round(float(entity.dxf.defpoint.y), 4)]
                for dp_key in ('defpoint2', 'defpoint3', 'defpoint4', 'defpoint5', 'text_midpoint'):
                    if entity.dxf.hasattr(dp_key):
                        pt = entity.dxf.get(dp_key)
                        item[dp_key] = [round(float(pt.x), 4), round(float(pt.y), 4), round(float(pt.z), 4)]
                item['dimstyle'] = entity.dxf.dimstyle
                item['geometry_block'] = entity.dxf.get('geometry', '')
                if entity.dxf.hasattr('angle'):
                    item['angle'] = round(float(entity.dxf.angle), 4)
                dim_override = entity.override()
                item['dimension_rounding'] = float(dim_override.get('dimrnd', 0))
                item['dimension_tolerance'] = {
                    'dimtol': int(dim_override.get('dimtol', 0)),
                    'dimlim': int(dim_override.get('dimlim', 0)),
                    'dimtp': float(dim_override.get('dimtp', 0)),
                    'dimtm': float(dim_override.get('dimtm', 0)),
                    'dimdec': int(dim_override.get('dimdec', 2)),
                    'dimtdec': int(dim_override.get('dimtdec', 2)),
                }

            elif entity_type == "HATCH":
                item['extrusion']=list(entity.dxf.extrusion)
                item['elevation']=list(entity.dxf.elevation)
                item["pattern_name"] = getattr(entity.dxf, "pattern_name", "")
                item["solid_fill"] = bool(getattr(entity.dxf, "solid_fill", False))
                item['boundary_path_count']=len(entity.paths)
                item['boundary_paths']=[{'path_type_flags':p.path_type_flags,
                    'vertices':[list(v) for v in getattr(p,'vertices',[])],
                    'edge_count':len(getattr(p,'edges',[]))} for p in entity.paths]
                try:
                    from cad.hatch_translation import preserved_paths
                    if any(not hasattr(p,'vertices') for p in entity.paths):
                        item['analytic_boundary_paths']=preserved_paths(entity,allow_boundary_refs=True)
                except (ValueError,TypeError,AttributeError,ZeroDivisionError):pass
                item['pattern_scale'] = round(float(getattr(entity.dxf, 'pattern_scale', 1.0)), 4)
                item['pattern_angle'] = round(float(getattr(entity.dxf, 'pattern_angle', 0.0)), 4)
                item['associative'] = bool(getattr(entity.dxf, 'associative', 0))
                gradient = getattr(entity, 'gradient', None)
                if gradient is not None:
                    item['gradient'] = {'name': getattr(gradient, 'name', ''), 'one_color': getattr(gradient, 'one_color', 0)}

            elif entity_type == "POINT":
                item["position"] = [round(float(entity.dxf.location.x), 4), round(float(entity.dxf.location.y), 4)]

            elif entity_type in ("SOLID", "3DFACE", "TRACE"):
                pts = []
                for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
                    if hasattr(entity.dxf, attr):
                        pt = getattr(entity.dxf, attr)
                        pts.append([round(float(pt.x), 4), round(float(pt.y), 4)])
                item["points"] = pts

            elif entity_type == "LEADER":
                item['vertices']=[list(p) for p in entity.vertices]
            elif entity_type == "MULTILEADER":
                context=getattr(entity,'context',None);mtext=getattr(context,'mtext',None)
                item['text']=getattr(mtext,'default_content','') if mtext else ''
                item['leader_lines']=[{'vertices':[list(v) for v in line.vertices]} for leader in getattr(context,'leaders',[]) for line in leader.lines]
                block_data=getattr(context,'block',None)
                if block_data and getattr(block_data,'block_record_handle',None):
                    item['block_record_handle']=str(block_data.block_record_handle)
                    item['content_type']='block'
                elif mtext and getattr(mtext,'default_content',''):
                    item['content_type']='mtext'
                else:
                    item['content_type']='none'
                if mtext:
                    try:
                        item['text_position']=list(mtext.insert)
                        item['text_height']=float(getattr(mtext,'char_height',2.5))
                    except (AttributeError,TypeError):pass

            elif entity_type == "VIEWPORT":
                item['center']=[round(float(entity.dxf.center.x),4),round(float(entity.dxf.center.y),4)]
                item['width']=round(float(entity.dxf.width),4)
                item['height']=round(float(entity.dxf.height),4)
                status=entity.dxf.get('status',0);item['status']=status
                if status>0:
                    if entity.dxf.hasattr('view_center_point'):
                        vcp=entity.dxf.view_center_point
                        item['view_center']=[round(float(vcp.x),4),round(float(vcp.y),4)]
                    if entity.dxf.hasattr('view_height'):
                        vh=float(entity.dxf.view_height);item['view_height']=round(vh,4)
                        if vh>0 and item['height']>0:item['scale']=round(item['height']/vh,6)
                    if entity.dxf.hasattr('view_direction_vector'):
                        item['view_direction']=list(entity.dxf.view_direction_vector)
                    try:
                        frozen=list(entity.frozen_layers)
                        if frozen:item['frozen_layers']=frozen
                    except (AttributeError,TypeError):pass

            elif entity_type == "WIPEOUT":
                if entity.dxf.hasattr('insert'):
                    item['position']=list(entity.dxf.insert)
                if entity.dxf.hasattr('u_pixel'):
                    item['u_vector']=list(entity.dxf.u_pixel)
                if entity.dxf.hasattr('v_pixel'):
                    item['v_vector']=list(entity.dxf.v_pixel)
                if entity.dxf.hasattr('image_size'):
                    item['image_size']=list(entity.dxf.image_size)
                try:
                    bp=entity.boundary_path
                    if bp:item['boundary_vertices']=[[round(float(p[0]),4),round(float(p[1]),4)] for p in bp]
                except (AttributeError,TypeError):pass

            elif entity_type == "MLINE":
                verts=[]
                try:
                    for v in entity.vertices:verts.append(list(v.location))
                except (AttributeError,TypeError):pass
                item['vertices']=verts
                item['style_name']=entity.dxf.get('style_name','')
                item['scale_factor']=float(entity.dxf.get('scale_factor',1.0))
                item['justification']=entity.dxf.get('justification',0)
                item['is_closed']=bool(entity.dxf.get('flags',0)&2)

            elif entity_type in ("IMAGE","RASTERIMAGE"):
                if entity.dxf.hasattr('insert'):
                    item['position']=[round(float(entity.dxf.insert.x),4),round(float(entity.dxf.insert.y),4)]
                if entity.dxf.hasattr('image_size'):
                    sz=entity.dxf.image_size;item['image_size']=[round(float(sz.x),4),round(float(sz.y),4)]
                try:
                    bp=entity.boundary_path
                    if bp:item['boundary_path']=[[round(float(p[0]),4),round(float(p[1]),4)] for p in bp]
                except (AttributeError,TypeError):pass

            elif entity_type == "OLE2FRAME":
                item['ole_version']=entity.dxf.get('version_number',0)

            elif entity_type in ("REGION","3DSOLID","BODY"):
                item['acis_data_present']=bool(getattr(entity,'acis_data',None))

        except Exception as err:
            item["parse_error"] = str(err)

        if not (set(item)-{'type','handle','layer','color'}):
            item['data_status']='metadata_only'
        result.append(item)

    return result


def extract_all_blocks(document, include_system: bool = False) -> Dict[str, Dict[str, Any]]:
    """Trích xuất toàn bộ block definitions trong tài liệu CAD và các thực thể bên trong mỗi block."""
    blocks_data = {}
    for block in document.blocks:
        name = block.name
        if not include_system and name.startswith("*"):
            continue
        entities = extract_entities(block)
        texts = []
        for ent in entities:
            if ent.get("text"):
                texts.append(ent["text"])
        blocks_data[name] = {
            "name": name,
            "base_point": [round(float(block.base_point.x), 4), round(float(block.base_point.y), 4)],
            "entity_count": len(entities),
            "entities": entities,
            "texts": texts,
            "description": getattr(block, "description", "") or "",
        }
    return blocks_data
