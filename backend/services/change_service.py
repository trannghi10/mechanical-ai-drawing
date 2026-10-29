"""Selection-scoped AI planning. Plans are proposals, never CAD instructions."""
import hashlib
import json
import uuid
import base64
import sys
import importlib
for _mod in ['backend.services.document_request_service', 'backend.services.ai_provider', 'backend.services.gemini_service']:
    if _mod in sys.modules:
        try: importlib.reload(sys.modules[_mod])
        except Exception: pass
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from cad.catalog import load_document, text_of, CAD_LOCK
from cad.sheets import geometry_index, overlaps
from backend.services import catalog_service as storage
from cad.edit_engine import Operation
from graph.change_dependencies import CoordinateRule
from graph.native_span_fits import NativeSpanFit
from graph.fit_constraints import FitRule
from graph.measurement_rules import MeasurementEquation
from cad.parametric import LinearResize
from cad.curved_wall import CurvedWallResize
from cad.hole_resize import HoleResize
from cad.rectangular_nesting import CutPacking
from cad.profile_nesting import ProfilePacking
from graph.process_validation import ProcessAssessment,validate_process_review
from backend.services.geometry_retrieval import GeometryQuery
from backend.services.cpu_planning_pages import MetadataRequest
from rules.mechanical_bom import TEACHING_PROMPT,reading_brief


class EditProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entity_ref: str
    part_number: str
    purpose: Literal['geometry', 'annotation', 'bom']
    before: str
    after: str
    reason: str


class DependencyProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_part: str
    target_part: str
    relationship: str
    evidence_refs: list[str]
    required_change: str
    needs_confirmation: bool
    coordinate_rule: CoordinateRule | None = None
    fit_rule: FitRule | None = None
    equation_rule: MeasurementEquation | None = None


class DrawingChangePlan(BaseModel):
    model_config = ConfigDict(extra='ignore')
    summary: str = Field(default='Kế hoạch chỉnh sửa bản vẽ theo yêu cầu')
    target_part: str = Field(default='')
    edits: list[EditProposal] = Field(default_factory=list)
    dependencies: list[DependencyProposal] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    operations: list[Operation] = Field(default_factory=list)
    geometry_requests: list[str] = Field(default_factory=list)
    context_requests: list[str] = Field(default_factory=list)
    geometry_queries: list[GeometryQuery] = Field(default_factory=list,max_length=4)
    metadata_requests: list[MetadataRequest] = Field(default_factory=list,max_length=4)
    resize_recipes: list[LinearResize] = Field(default_factory=list)
    curved_wall_recipes: list[CurvedWallResize] = Field(default_factory=list,max_length=16)
    hole_recipes: list[HoleResize] = Field(default_factory=list,max_length=16)
    cut_recipes: list[CutPacking] = Field(default_factory=list)
    profile_cut_recipes: list[ProfilePacking] = Field(default_factory=list)
    process_assessments: list[ProcessAssessment] = Field(default_factory=list)
    requires_complete_product_review: bool = False
    native_span_fits: list[NativeSpanFit] = Field(default_factory=list,max_length=32)


def planning_context(context,expanded=(),hierarchical=False,opened_blocks=(),located_refs=()):
    """Retain semantics and make every deferred source entity discoverable."""
    result=dict(context);result['entities']=[];result['coordinate_frames']={}
    result['reading_profile']=reading_brief(context)
    if context.get('confirmed_parameter_links'):
        result['confirmed_parameter_links']=dict(count=len(context['confirmed_parameter_links']),policy='Source-bound confirmed numeric rules are compiled and validated server-side; no inferred 3D contact.')
    if context.get('design_model'):
        from graph.design_model import summary
        result['design_model']=summary(context['design_model'])
    expanded=set(expanded);opened_blocks=set(opened_blocks);located_refs=set(located_refs)
    evidence_refs=set()
    if hierarchical:
        for link in context.get('drawing_evidence',{}).get('bom_links',[]):
            evidence_refs.update(link.get('code_evidence_refs',[]))
            for marker in link.get('number_markers',[]):
                evidence_refs.update(marker.get('leader_refs',[]))
                evidence_refs.update(marker[k] for k in ('circle_ref','number_text_ref') if marker.get(k))
    semantic_kinds={'DIMENSION','ARC_DIMENSION','TOLERANCE','INSERT','ACAD_TABLE','GRAPHIC_TABLE','LEADER','MLEADER','MULTILEADER','VIEWPORT','WIPEOUT','MLINE'}
    tables={e['ref'] for e in context['entities'] if e['type']=='ACAD_TABLE' and e.get('bom',{}).get('status')=='verified_template'}
    focus=set(context.get('root_target_ids',[])) if hierarchical and len(context.get('targets',[]))>4 and len(context['entities'])>2000 else set()
    focus_tables=set(context.get('root_bom_refs',[]))
    geom_budget=0 if focus else 30;deferred=[]
    for entity in context['entities']:
        ref=entity['ref'];kind=entity['type']
        has_text=bool(entity.get('text') or entity.get('raw_text'))
        full=ref in expanded or ref in opened_blocks or any(ref.startswith(b+'/') for b in opened_blocks)
        is_semantic=has_text or kind in semantic_kinds
        keep=full or ref in located_refs or ref in evidence_refs
        if focus and not full and ref not in located_refs and ref not in focus_tables and not focus.intersection(entity.get('source_sheet_ids',[])) and ref.split('/')[0] not in focus:
            deferred.append(entity);continue
        # Verified native cells already contain every display text and its
        # exact binding. Avoid sending a second copy of the entire BOM.
        if hierarchical and not keep and any(ref.startswith(t+'/') for t in tables):
            deferred.append(entity);continue
        if hierarchical and len(context['entities'])>300 and not is_semantic:
            if not keep:
                if kind in ('SPLINE','ELLIPSE','HATCH') or geom_budget<=0:
                    deferred.append(entity);continue
                geom_budget-=1
        if hierarchical and '/' in ref and not is_semantic and not keep:
            deferred.append(entity);continue
        record=dict(entity)
        if focus and not keep and record.get('raw_text'):
            record.pop('raw_text');record['raw_text_deferred']=True
        if hierarchical and not full and record.get('bom',{}).get('status')=='verified_template':
            record.pop('cells',None);record.pop('cell_bindings',None);record.pop('source_refs',None)
            if focus:
                from backend.services.planning_view import bom_view
                record['bom']=bom_view(record['bom'],set(context.get('part_graph',{}).get('seed_codes',[])))
        if hierarchical and record['type'] in ('INSERT','ACAD_TABLE'):
            children=[child for child in context['entities'] if child['ref'].startswith(record['ref']+'/')]
            from collections import Counter
            record['child_inventory']={'count':len(children),'types':dict(Counter(child['type'] for child in children)),
                                       'expanded':record['ref'] in opened_blocks}
        frame=record.get('coordinate_frame');matrix=record.pop('frame_to_layout',None)
        if frame and matrix:result['coordinate_frames'][frame]=matrix
        geometry=record.get('geometry')
        if record.get('read_only_geometry') and record['ref'] not in expanded and record['ref'] not in opened_blocks and not any(record['ref'].startswith(ref+'/') for ref in opened_blocks):
            shape=record.pop('read_only_geometry')
            record['read_only_summary']={k:v for k,v in shape.items() if k not in ('points','boundary_paths','leader_lines')}
            if 'points' in shape:record['read_only_summary']['vertex_count']=len(shape['points'])
            record['read_only_summary']['retrieval']='context_requests retrieves source details; editing this entity type is unsupported'
        if geometry:
            for key in ('start','end','center','radius'):
                if key in geometry:record.pop(key,None)
        if geometry and record['type']!='DIMENSION' and record['ref'] not in expanded:
            record.pop('geometry');kind=record['type'];summary={}
            points=[]
            if kind=='LINE':points=[geometry['start'],geometry['end']]
            elif kind=='LEADER':points=geometry['vertices']
            elif kind in ('LWPOLYLINE','POLYLINE'):
                points=[[p[0],p[1],geometry['elevation']] for p in geometry['points']]
                summary={'vertex_count':len(points),'closed':geometry['closed'],'has_bulge':any(p[4] for p in geometry['points'])}
            elif kind in ('CIRCLE','ARC'):
                center=geometry['center'];radius=geometry['radius']
                points=[[center[0]-radius,center[1]-radius,center[2]],[center[0]+radius,center[1]+radius,center[2]]]
                summary={'radius':radius,'extrusion':geometry['extrusion']}
                if kind=='ARC':summary.update(start_angle=geometry['start_angle'],end_angle=geometry['end_angle'])
            elif kind=='ELLIPSE':
                from backend.services.geometry_retrieval import local_bounds
                points=local_bounds({'type':'ELLIPSE','geometry':geometry})
                summary={'ratio':geometry['ratio'],'extrusion':geometry.get('extrusion',[0,0,1])}
            elif kind=='SPLINE':
                points=geometry['control_points']+geometry['fit_points']
                summary={'degree':geometry['degree'],'flags':geometry['flags'],'control_point_count':len(geometry['control_points']),'fit_point_count':len(geometry['fit_points']),'knot_count':len(geometry['knots']),'weight_count':len(geometry['weights'])}
            summary['local_bbox']=[[round(min(p[i] for p in points),4) for i in range(3)],[round(max(p[i] for p in points),4) for i in range(3)]] if points else None
            summary['bounds_only']=True
            record['geometry_summary']=summary
        result['entities'].append(record)
    if hierarchical:
        if context.get('source_features'):
            from cad.measured_features import model_view
            result['source_features']=model_view(context['source_features'],[e['ref'] for e in result['entities']])
        result['full_parsed_entity_count']=len(context['entities'])
        result['inventory_mode']='hierarchical: technical semantics retained; verified table display text is represented by bound BOM cells. Other geometry deferred in the source store. geometry_queries discovers source refs; context_requests fetches exact placement/children; geometry_requests fetches exact geometry. Deferred entities have not been sent to the model.'
        if deferred:
            from backend.services.geometry_retrieval import discovery_index
            result['deferred_geometry_summary']=dict(__import__('collections').Counter(e['type'] for e in deferred))
            result['geometry_discovery']=discovery_index(deferred,context.get('targets',[]),focus or None)
        if focus:
            result['focused_scope_ids']=sorted(focus)
            result['inventory_mode']+=' Related scopes are deferred, including their text/dimensions; their complete typed inventories are in geometry_discovery.scopes. Query each needed target; do not claim it was inspected before retrieving it.'
            result['targets']=[{k:t[k] for k in ('id','kind','layout','bbox','name') if k in t} for t in context['targets']]
            result['scope_links']=[{k:s[k] for k in ('sheet_id','part_codes') if k in s} for s in context.get('scope_links',[])]
            from backend.services.planning_view import impact_view,evidence_view
            result['drawing_evidence']=evidence_view(context.get('drawing_evidence',{}),{e['ref'] for e in result['entities']},focus_tables)
            graph=context.get('part_graph')
            if graph:
                result['part_graph']=impact_view(graph,defer_specs=True)
    capabilities=context.get('cad_capabilities')
    if capabilities:
        shown={e['ref'] for e in result['entities']}
        relevant=[e for e in capabilities['entities'] if e['ref'] in shown and e['status']!='conditional']
        result['cad_capabilities']={k:capabilities[k] for k in ('version','source_hash','capability_counts','policy')}
        result['cad_capabilities'].update(issue_count_in_shown_scope=len(relevant),issue_examples=relevant[:8],
            retrieval='Full capability inventory remains server-side; examples do not authorize edits or represent deferred scope coverage.')
    return result


_CONTEXT_CACHE = {}


def _context_for(source, targets, review_only_ids=()):
    source_path = Path(source).resolve()
    try:
        st = source_path.stat()
        cache_key = (
            str(source_path),
            st.st_mtime_ns,
            st.st_size,
            tuple(sorted((t['id'], t.get('kind', ''), t.get('layout', ''), tuple(t.get('bbox') or ())) for t in targets)),
            tuple(sorted(review_only_ids)),
        )
    except OSError:
        cache_key = None

    if cache_key and cache_key in _CONTEXT_CACHE:
        cached = _CONTEXT_CACHE[cache_key]
        return {
            k: [dict(e) for e in v] if k == 'entities' else dict(v) if isinstance(v, dict) else v
            for k, v in cached.items()
        }

    doc=load_document(str(source))
    from cad.table_data import table_cells
    cells=table_cells(source)
    records=[]
    visited=set(); sheet_membership={};placements={}
    from ezdxf.math import Matrix44
    def append(entity, reference, parent_matrix=None, layout_name=None,review_only=False,block_path=()):
        if reference in visited:return
        visited.add(reference)
        parent_matrix=parent_matrix if parent_matrix is not None else Matrix44()
        placements[reference]=(entity,parent_matrix)
        layout_name=layout_name or next((layout.name for layout in doc.layouts if layout.block_record_handle==entity.dxf.get('owner')),None)
        if layout_name is None:raise ValueError('Không xác định được layout của entity trong phạm vi')
        data={'ref':reference,'type':entity.dxftype(),'layer':entity.dxf.get('layer','')}
        if review_only:data['review_only']=True
        data['coordinate_frame']='instance:'+reference.rsplit('/',1)[0] if '/' in reference else 'layout:'+layout_name
        data['frame_to_layout']=[list(parent_matrix.get_row(i)) for i in range(4)]
        data['layout']=layout_name
        text=text_of(entity)
        if text is not None:data['text']=text
        if entity.dxftype()=='MTEXT':data['raw_text']=entity.text
        kind=entity.dxftype()
        if kind=='LWPOLYLINE':data['constant_width']=entity.dxf.const_width
        if kind=='TOLERANCE':data['text']=entity.dxf.content
        from cad.legacy_polyline import supported as supported_polyline
        legacy_polyline=kind=='POLYLINE' and supported_polyline(entity)
        if kind in ('HATCH','SOLID','3DFACE','POINT','MULTILEADER','TOLERANCE','ARC_DIMENSION','XLINE','RAY','VIEWPORT','WIPEOUT','MLINE','IMAGE','RASTERIMAGE','OLE2FRAME','REGION','3DSOLID','BODY','MESH','TRACE') or kind=='POLYLINE' and not legacy_polyline:
            from cad.entities import extract_entities
            extracted=extract_entities([entity])
            if extracted:
                data['read_only_geometry']=extracted[0]
            data['edit_support']='read_only: entity type has no checked editing adapter'
        if kind=='HATCH':
            from cad.hatch_translation import snapshot as hatch_snapshot
            try:
                data['hatch_translation_geometry']=hatch_snapshot(entity)
                data['edit_support']='checked rigid translation or rectangular resize; source boundary binding required'
            except ValueError:
                pass
        if kind in ('TEXT','MTEXT','ATTRIB'):
            anchor=entity.dxf.get('insert')
            if kind in ('TEXT','ATTRIB') and (entity.dxf.get('halign',0) or entity.dxf.get('valign',0)):
                anchor=entity.dxf.get('align_point',anchor)
            if anchor is not None:
                data['text_placement']={'anchor':list(anchor),
                    'height':entity.dxf.get('char_height',0) if kind=='MTEXT' else entity.dxf.get('height',0),
                    'extrusion':list(entity.dxf.get('extrusion',(0,0,1))),
                    'direction':list(entity.dxf.get('text_direction',(1,0,0))) if kind=='MTEXT' else [1,0,0],
                    'rotation':entity.dxf.get('rotation',0)}
                from cad.row_groups import LABEL
                from bom.reader import plain
                if LABEL.fullmatch(plain(text or '')):
                    from ezdxf import bbox
                    bounds=bbox.extents([entity],fast=True)
                    if bounds.has_data:data['text_placement']['label_center']=list((bounds.extmin+bounds.extmax)/2)
        if kind=='LEADER':
            data['leader_vertices']=[list(point) for point in entity.vertices]
        if legacy_polyline or kind in ('LINE','LWPOLYLINE','CIRCLE','ARC','ELLIPSE','SPLINE','LEADER') or (kind=='DIMENSION' and entity.dxf.dimtype & 15 in (0,1,2)):
            from cad.geometry import snapshot
            data['geometry']=snapshot(entity)
        if kind=='DIMENSION' and entity.dxf.dimtype & 15 in (3,4):
            from cad.geometry import snapshot
            data['radial_geometry']=snapshot(entity)
        if kind=='ACAD_TABLE':
            data['cells']=cells.get(entity.dxf.handle,[])
            data['rows']=entity.dxf.get('n_rows')
            data['columns']=entity.dxf.get('n_cols')
            from cad.table_bindings import bind_cells
            data['cell_bindings']=bind_cells(entity,data['cells'],doc)
            from bom.reader import read_bom
            data['bom']=read_bom(data['cells'],data['cell_bindings'])
        if kind=='LINE':
            data.update(start=list(entity.dxf.start),end=list(entity.dxf.end))
            from cad.reference_geometry import annotate as annotate_reference
            annotate_reference(doc,data)
        elif kind in ('CIRCLE','ARC'):
            data.update(center=list(entity.dxf.center),radius=entity.dxf.radius)
        elif kind=='DIMENSION':
            data.update(text=entity.dxf.get('text',''),measurement=entity.dxf.get('actual_measurement'))
            data['dimension_type']=entity.dxf.dimtype & 15
            if entity.dxf.hasattr('defpoint'):
                data['defpoint']=[round(float(entity.dxf.defpoint.x),4),round(float(entity.dxf.defpoint.y),4)]
            for dp_key in ('defpoint2','defpoint3','defpoint4','defpoint5','text_midpoint'):
                if entity.dxf.hasattr(dp_key):
                    pt=entity.dxf.get(dp_key)
                    data[dp_key]=[round(float(pt.x),4),round(float(pt.y),4),round(float(pt.z),4)]
            data['dimstyle']=entity.dxf.dimstyle
            data['geometry_block']=entity.dxf.get('geometry','')
            if entity.dxf.hasattr('angle'):
                data['angle']=round(float(entity.dxf.angle),4)
            if '/' not in reference:
                from cad.dimension_associations import source_binding
                association=source_binding(entity)
                if association:data['dimension_association']=association
            from cad.dimensions import native_tolerance
            data['dimension_tolerance']=native_tolerance(entity)
            data['dimension_rounding']=entity.override().get('dimrnd',0.)
            if entity.dxf.dimtype & 15 in (0,1,3,4):
                measured=entity.get_measurement()
                if entity.dxf.dimtype & 15==1:
                    import math
                    measured=math.dist(entity.dxf.defpoint2,entity.dxf.defpoint3)
                factor=entity.override().get('dimlfac',1)
                data['linear_factor']=factor
                if isinstance(measured,(int,float)):
                    data['geometric_measurement']=measured
                    data['scaled_measurement']=abs(measured*factor)
        elif kind=='INSERT':
            data.update(name=entity.dxf.name,position=list(entity.dxf.insert),
                        attributes=[(a.dxf.tag,a.dxf.text) for a in entity.attribs],
                        scale=[entity.dxf.xscale,entity.dxf.yscale,entity.dxf.zscale],rotation=entity.dxf.rotation)
            from cad.block_provenance import source_name
            origin=source_name(doc,entity.dxf.name)
            if origin:data['source_block_name']=origin
        records.append(data)
        name=entity.dxf.get('geometry','') if kind=='ACAD_TABLE' else entity.dxf.name if kind=='INSERT' else None
        if name and name in doc.blocks:
            # Instance path identifies shared definitions; coordinates remain local.
            if name in block_path:
                raise ValueError('Block tham chiếu vòng; không thể lập phạm vi sửa đầy đủ: '+' → '.join((*block_path,name)))
            if len(block_path)>=128:
                raise ValueError('Block lồng quá 128 cấp; cần tách phạm vi trước khi sửa')
            child_matrix=entity.matrix44()*parent_matrix if kind=='INSERT' else parent_matrix
            children=list(doc.blocks.get(name))
            if review_only and kind=='INSERT':
                from collections import Counter
                data['review_block_inventory']={'definition_count':len(children),'types':dict(Counter(c.dxftype() for c in children)),
                                                 'geometry_unexpanded':True}
                children=[c for c in children if c.dxftype() in ('TEXT','MTEXT','ATTRIB','INSERT','DIMENSION','ARC_DIMENSION','TOLERANCE')]
            for child in children:append(child,reference+'/'+child.dxf.handle,child_matrix,layout_name,review_only,(*block_path,name))
        if kind=='INSERT':
            for child in entity.attribs:append(child,reference+'/'+child.dxf.handle,parent_matrix,layout_name,review_only)
    # Proven editing scopes are expanded first. Co-process candidates retain
    # text, true dimensions and explicit block inventories, without copying
    # tens of thousands of repeated cut outlines into an editing transaction.
    from collections import defaultdict
    sheets_by_layout = defaultdict(list)
    for target in sorted(targets,key=lambda t:t['id'] in review_only_ids):
        if target['kind']=='sheet':
            sheets_by_layout[target['layout']].append(target)
        else:
            entity=doc.entitydb.get(target['id'])
            name=target.get('name') if target.get('name') in doc.blocks else target['id'] if target['id'] in doc.blocks else None
            if entity is not None and entity.dxftype() not in ('BLOCK_RECORD','BLOCK'):
                sheet_membership.setdefault(entity.dxf.handle,set()).add(target['id'])
                append(entity,entity.dxf.handle,layout_name=target.get('layout'),review_only=target['id'] in review_only_ids)
            elif name and name in doc.blocks:
                block=doc.blocks.get(name)
                sheet_membership.setdefault(target['id'],set()).add(target['id'])
                for child in block:
                    append(child,target['id']+'/'+child.dxf.handle,layout_name=target.get('layout','BlockTable'),review_only=target['id'] in review_only_ids)
            elif entity is not None:
                sheet_membership.setdefault(entity.dxf.handle,set()).add(target['id'])
                append(entity,entity.dxf.handle,layout_name=target.get('layout'),review_only=target['id'] in review_only_ids)

    for layout_name, sheet_group in sheets_by_layout.items():
        bounds=geometry_index(str(source),layout_name)
        layout=doc.layouts.get(layout_name)
        if not layout:continue
        for entity in layout:
            extent=bounds.get(entity.dxf.handle)
            if not extent:continue
            for target in sheet_group:
                if overlaps(extent,target['bbox']):
                    sheet_membership.setdefault(entity.dxf.handle,set()).add(target['id'])
                    append(entity,entity.dxf.handle,layout_name=layout_name,review_only=target['id'] in review_only_ids)

    from cad.graphic_tables import discover
    # Source BOM identity makes a native part indivisible when a frame edge
    # crosses it. These unscoped tables supply identities only, never editing
    # scopes; scoped tables/cell memberships are reconstructed below.
    unscoped_tables=discover(records) if any(t['kind']=='sheet' for t in targets) else []
    part_codes={r['part_code'] for e in [*records,*unscoped_tables] if e.get('bom',{}).get('status')=='verified_template' for r in e['bom']['rows']}
    from cad.scope_membership import assign as assign_source_scopes
    records=assign_source_scopes(records,targets,sheet_membership,placements,doc,review_only_ids,part_codes)
    records.extend(discover(records))
    # Never silently truncate and pretend the context was complete.
    if len(records)>64000:
        raise ValueError(f'Nhóm công đoạn có {len(records)} đối tượng, vượt giới hạn parser 64000; cần chia nhóm ràng buộc trước khi sửa.')
    result={'units':doc.units,'targets':targets,'entities':records,'source_hash':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'table_status':'TABLE native dùng CELL_VALUE và mirror đã kiểm tra; GRAPHIC_TABLE dùng ô khép kín và ref TEXT/MTEXT chính xác. Bảng unsupported không đủ dữ liệu sửa. BOM không tự chứng minh liên kết cơ khí.',
            'coordinates':'Block child coordinates are local to its instance path.'}
    if review_only_ids:
        result['review_only_ids']=sorted(review_only_ids)
        result['review_inventory_note']='Co-process candidates: text/dimensions and block inventory for review. Repeated block geometry is unexpanded; these refs cannot authorize geometry operations.'
    from bom.drawing_evidence import drawing_evidence
    result['drawing_evidence']=drawing_evidence(records)
    from cad.capabilities import report as capability_report,scope as capability_scope
    result['cad_capabilities']=capability_scope(capability_report(source),records)
    # Parsing/edit validation has a different budget from model inference.
    # A source-proven cut grid and repeated assembly BOMs must fit the checked
    # compiler together; the model adapter applies its own token budget later.
    if len(json.dumps(result,ensure_ascii=False))>128000000:
        raise ValueError('Dữ liệu CAD liên quan vượt giới hạn 128 MB của engine; cần chia nhóm ràng buộc.')
    if cache_key:
        if len(_CONTEXT_CACHE) > 16:
            _CONTEXT_CACHE.clear()
        _CONTEXT_CACHE[cache_key] = result
    return {
        k: [dict(e) for e in v] if k == 'entities' else dict(v) if isinstance(v, dict) else v
        for k, v in result.items()
    }


def context_for(source,targets,review_only_ids=()):
    result=_context_for(source,targets,review_only_ids)
    from graph.parameter_links import attach
    result=attach(result,source)
    from backend.services.aps_context import attach as attach_native
    return attach_native(result,source)


def validate_plan(plan,context):
    refs={e['ref'] for e in context['entities']}
    records={e['ref']:e for e in context['entities']}
    capability=context.get('cad_capabilities')
    if capability:
        if capability['source_hash']!=context['source_hash']:raise ValueError('Kiểm kê CAD thuộc nguồn cũ')
        by_ref={e['ref']:e for e in capability['entities']}
        blocked=[o.ref for o in plan.operations if by_ref.get(o.ref,{}).get('status')=='native_required' and o.action not in by_ref[o.ref].get('conditional_actions',[]) and not (o.action=='replace_text' and records.get(o.ref,{}).get('type') in ('TEXT','MTEXT','ATTRIB'))]
        if blocked:raise ValueError('Đối tượng XREF/dynamic/proxy/association cần CAD host trước sửa: '+', '.join(blocked[:5]))
    if plan.operations and not plan.questions:
        from graph.parameter_links import validate as validate_parameter_links
        validate_parameter_links(plan,context)
        from backend.services.design_choices import validate as validate_choices
        validate_choices(plan,context)
        from graph.native_instances import validate_sync
        validate_sync(plan,context)
        from graph.native_contacts import validate as validate_contacts
        validate_contacts(plan,context)
        from graph.flat_contacts import validate as validate_flat_contacts
        validate_flat_contacts(plan,context)
        from graph.packaging_fit import validate as validate_packaging
        validate_packaging(plan,context)
    if (plan.resize_recipes or plan.curved_wall_recipes or plan.hole_recipes) and plan.operations and not plan.questions:
        from backend.services.parametric_service import compile_recipes
        checked=compile_recipes(plan.model_copy(deep=True),context)
        if len(checked.operations)!=len(plan.operations):
            raise ValueError('Kế hoạch thiếu thao tác do recipe sinh ra')
        from graph.confirmed_inner_panels import validate as validate_inner_panels
        validate_inner_panels(plan, context)
        from graph.laminar_stage_gauges import validate as validate_stage_gauges
        validate_stage_gauges(plan, context)
        from graph.confirmed_inner_tubes import validate as validate_inner_tubes
        validate_inner_tubes(plan, context)
        from graph.corner_wall_contacts import validate as validate_corner_contacts
        validate_corner_contacts(plan, context)
        from graph.core_stack_views import validate as validate_core_views
        validate_core_views(plan, context)
        from graph.curved_detail_contacts import validate as validate_curved_details
        validate_curved_details(plan, context)
    for edit in plan.edits:
        if edit.entity_ref not in refs:
            raise ValueError('AI đề xuất đối tượng ngoài phạm vi hoặc không tồn tại')
    for dep in plan.dependencies:
        if not set(dep.evidence_refs)<=refs:
            raise ValueError('Bằng chứng quan hệ không thuộc phạm vi chọn')
        # Semantic constraints are not established by an LLM's confidence alone.
        dep.needs_confirmation=True
        if dep.coordinate_rule and not {dep.coordinate_rule.source_ref,dep.coordinate_rule.target_ref}<=refs:
            raise ValueError('Quy tắc lan truyền ngoài phạm vi chọn')
        if dep.coordinate_rule:
            expected={'line_end':('LINE',),'move_insert':('INSERT',),'dimension_point':('DIMENSION',),'geometry_point':('LINE','CIRCLE','ARC','ELLIPSE'),
                      'translate_geometry':('LINE','LWPOLYLINE','POLYLINE','CIRCLE','DIMENSION')}[dep.coordinate_rule.target_action]
            if records[dep.coordinate_rule.target_ref].get('type') not in expected:
                raise ValueError('Quy tắc kéo theo không hỗ trợ loại entity đích')
        if dep.fit_rule:
            fit_refs={dep.fit_rule.thickness_dimension_ref,dep.fit_rule.outside_dimension_ref,dep.fit_rule.mating_dimension_ref}
            if not fit_refs<=set(dep.evidence_refs) or any(records.get(ref,{}).get('type')!='DIMENSION' for ref in fit_refs):
                raise ValueError('Ràng buộc lắp ghép cần ba DIMENSION làm bằng chứng')
        if dep.equation_rule:
            if not set(dep.equation_rule.evidence_refs)<=set(dep.evidence_refs):
                raise ValueError('Phương trình cần bằng chứng trong quan hệ phụ thuộc')
    for op in plan.operations:
        if op.ref not in refs:raise ValueError('Operation ngoài phạm vi chọn')
        if records[op.ref].get('type')=='GRAPHIC_TABLE':raise ValueError('GRAPHIC_TABLE là mô tả bảng; cần sửa đúng TEXT/MTEXT của ô, không sửa ref tổng hợp')
        if records[op.ref].get('review_only'):raise ValueError('Chi tiết cùng công đoạn mới ở bước kiểm tra; cần mở đầy đủ hình học và xác định liên kết trước khi sửa')
        if op.mirror_ref and op.mirror_ref not in refs:raise ValueError('Mirror bảng ngoài phạm vi chọn')
    from cad.hatch_translation import validate_operations as validate_hatches
    validate_hatches(plan, context)
    # Do not expose apply for a plan that explains more edits than it executes.
    if plan.operations and not plan.questions:
        from backend.services.assembly_projection_planner import validate_projections
        validate_projections(plan,context)
        from backend.services.rounded_fit_planner import validate_rounded_fits
        validate_rounded_fits(plan,context)
        from cad.rectangular_nesting import validate_pack
        from cad.profile_nesting import validate_profile_packs
        removable=validate_profile_packs(plan.operations,plan.profile_cut_recipes,context)
        validate_pack(plan.operations,plan.cut_recipes,context,removable)
        if any(dep.coordinate_rule is None and dep.fit_rule is None and dep.equation_rule is None for dep in plan.dependencies):
            raise ValueError('Quan hệ kéo theo chưa có quy tắc thực thi; cần làm rõ trước khi tạo bản sửa')
        coverage={op.ref for op in plan.operations}|{dep.coordinate_rule.target_ref for dep in plan.dependencies if dep.coordinate_rule}
        if any(edit.entity_ref not in coverage for edit in plan.edits):
            raise ValueError('Kế hoạch thiếu thao tác thực thi cho một hoặc nhiều thay đổi đã mô tả')
        manifest={edit.entity_ref for edit in plan.edits}
        mirrors={o.mirror_ref for o in plan.operations if o.mirror_ref}
        for op in plan.operations:
            if op.ref not in manifest and op.ref not in mirrors:
                plan.edits.append(EditProposal(
                    entity_ref=op.ref,
                    part_number='',
                    purpose='geometry' if op.action in ('line_end','move_insert','move_text','replace_geometry','remove_insert','append_geometry') else 'annotation',
                    before=str(op.before) if op.before else '',
                    after=str(op.after) if op.after else '',
                    reason=op.reason or 'Chỉnh sửa theo yêu cầu'
                ))
                manifest.add(op.ref)
        operations_by_ref={}
        for operation in plan.operations:operations_by_ref.setdefault(operation.ref,operation)
        for edit in plan.edits:
            op=operations_by_ref.get(edit.entity_ref)
            if op and edit.purpose=='geometry' and op.action not in ('line_end','move_insert','move_text','replace_geometry','remove_insert','append_geometry'):
                raise ValueError('Thay đổi hình học không thể thực thi bằng thao tác chỉ sửa text')
            if op and edit.purpose=='bom' and '/' in op.ref:
                root=records.get(op.ref.split('/')[0],{})
                if root.get('type')=='ACAD_TABLE' and not any(o.action=='table_cell' and o.mirror_ref==op.ref for o in plan.operations):
                    raise ValueError('Thay BOM thiếu thao tác dữ liệu ô bảng native')
        from graph.fit_constraints import validate_fits
        validate_fits(plan.operations,[dep.fit_rule for dep in plan.dependencies if dep.fit_rule],context)
        from graph.measurement_rules import validate_equations
        validate_equations(plan.operations,[dep.equation_rule for dep in plan.dependencies if dep.equation_rule],context)
    return plan


def cpu_raw_context(context):
    """Raw entities do not require duplicating thousands of locator points."""
    result=planning_context(context,expanded=[e['ref'] for e in context['entities']],hierarchical=False)
    result['inventory_mode']='raw_entities_full: exact source geometry and instance paths; no omitted block children'
    if context.get('source_features'):
        from cad.measured_features import model_view
        result['source_features']=model_view(context['source_features'],[e['ref'] for e in context['entities']])
    return result


def synthesize_linear_change(plan, context, request, clarifications=None):
    from backend.services.size_commands import interpret_linear_request
    from bom.reader import normalized
    import re
    reading = interpret_linear_request(context, request, clarifications) or {}
    old_val_num = reading.get('explicit_before_mm') or reading.get('nominal_before_mm')
    new_val_num = reading.get('target_mm')
    target_code = reading.get('part_code')
    if old_val_num is None or new_val_num is None:
        text = normalized(request + ' ' + ' '.join(c.get('answer', '') for c in clarifications or []))
        m = re.search(r'(?:\btu\s+|(?<![a-zA-Z\d]))(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:->|→)\s*(\d+(?:[.,]\d+)?)', text)
        if not m:
            m = re.search(r'\btu\s*(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:thanh|sang|xuong|len|con)\s*(?:dung\s*)?(\d+(?:[.,]\d+)?)', text)
        if m:
            old_val_num = float(m.group(1).replace(',', '.'))
            new_val_num = float(m.group(2).replace(',', '.'))
        else:
            m2 = re.search(r'(?<![a-zA-Z\d])(\d+(?:[.,]\d+)?)\s*mm\s*(?:thanh|sang|xuong|len|con)\s*(\d+(?:[.,]\d+)?)', text)
            if m2:
                old_val_num = float(m2.group(1).replace(',', '.'))
                new_val_num = float(m2.group(2).replace(',', '.'))
            else:
                m3 = re.search(r'(?:thanh|sang|xuong|len|con|cao|dai|rong)\s*(\d+(?:[.,]\d+)?)', text)
                if m3:
                    new_val_num = float(m3.group(1).replace(',', '.'))
                if not target_code:
                    from graph.part_graph import seed_codes
                    seeds = seed_codes(context, request, context.get('part_graph'))
                    if seeds: target_code = next(iter(seeds))
                if target_code and old_val_num is None and new_val_num is not None:
                    for n in context.get('part_graph', {}).get('nodes', []):
                        if n.get('code') == target_code:
                            from backend.services.size_commands import parse_part_dimensions
                            for o in n.get('bom_occurrences', []):
                                pdims = parse_part_dimensions(o.get('description', ''))
                                cands = [v for k, v in pdims.items() if k in ('dai', 'cao', 'rong') and v > 0]
                                if cands:
                                    if any(w in text for w in ('cao', 'chieu cao', 'dung')) and 'cao' in pdims:
                                        old_val_num = pdims['cao']
                                    elif any(w in text for w in ('rong', 'chieu rong', 'bemat', 'ngang')) and 'rong' in pdims:
                                        old_val_num = pdims['rong']
                                    elif any(w in text for w in ('dai', 'chieu dai')) and 'dai' in pdims:
                                        old_val_num = pdims['dai']
                                    else:
                                        old_val_num = min(cands, key=lambda v: abs(v - new_val_num))
                                    break
                            if old_val_num: break
    if old_val_num is None or new_val_num is None or abs(old_val_num - new_val_num) < 1e-6:
        return plan
    old_str = f'{old_val_num:g}'
    new_str = f'{new_val_num:g}'
    target_codes = set()
    if target_code: target_codes.add(target_code)
    for p in context.get('document_reading', {}).get('selected_parts', []):
        if p.get('part_code'): target_codes.add(p['part_code'])
    for n in context.get('part_graph', {}).get('nodes', []):
        if n.get('code') and (old_str in str(n.get('description', '')) or n.get('code') in target_codes):
            target_codes.add(n['code'])
    existing_refs = {o.ref for o in plan.operations}
    by_ref = {e['ref']: e for e in context.get('entities', [])}
    new_ops = list(plan.operations)
    new_edits = list(plan.edits)
    bom_mirrors = set()
    for e in context.get('entities', []):
        bom = e.get('bom', {})
        for row in bom.get('rows', []):
            row_code = row.get('part_code')
            desc = row.get('description', '')
            if (row_code and row_code in target_codes) or old_str in desc:
                cells = row.get('cells', {})
                desc_cell = cells.get('description', {})
                idx = desc_cell.get('index', -1)
                raw = desc_cell.get('raw_text', '')
                mirror = desc_cell.get('mirror_ref', '')
                if old_str in raw and idx >= 0:
                    new_raw = re.sub(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', new_str, raw)
                    if new_raw == raw:
                        old_comma, new_comma = old_str.replace('.', ','), new_str.replace('.', ',')
                        new_raw = re.sub(r'(?<![\d.,])' + re.escape(old_comma) + r'(?![\d.,])', new_comma, raw)
                    if new_raw != raw and e['ref'] not in existing_refs:
                        if desc_cell.get('storage') != 'text':
                            new_ops.append(Operation(ref=e['ref'], action='table_cell', cell_index=idx,
                                                     mirror_ref=mirror, before=raw, after=new_raw, xyz=[],
                                                     reason=f'Cập nhật kích thước {old_str} -> {new_str} trong BOM'))
                            new_edits.append(EditProposal(entity_ref=e['ref'], part_number=row.get('part_number', ''),
                                                          purpose='bom', before=raw, after=new_raw,
                                                          reason=f'Đổi {old_str} thành {new_str} trong BOM'))
                        if mirror and mirror in by_ref and mirror not in existing_refs:
                            bom_mirrors.add(mirror)
                            m_rec = by_ref[mirror]
                            m_raw = m_rec.get('raw_text', m_rec.get('text', ''))
                            m_after = re.sub(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', new_str, m_raw)
                            if m_after == m_raw:
                                old_comma, new_comma = old_str.replace('.', ','), new_str.replace('.', ',')
                                m_after = re.sub(r'(?<![\d.,])' + re.escape(old_comma) + r'(?![\d.,])', new_comma, m_raw)
                            if m_after != m_raw:
                                new_ops.append(Operation(ref=mirror, action='replace_text',
                                                         before=m_raw, after=m_after, xyz=[],
                                                         reason=f'Đồng bộ text mirror bảng kê {old_str} -> {new_str}'))
                                new_edits.append(EditProposal(entity_ref=mirror, part_number=row.get('part_number', ''),
                                                              purpose='bom', before=m_raw, after=m_after,
                                                              reason=f'Đổi {old_str} thành {new_str} trong BOM'))
    for e in context.get('entities', []):
        ref = e.get('ref', '')
        if ref in bom_mirrors or ref in existing_refs: continue
        t = e.get('text', '') or ''
        raw = e.get('raw_text', t)
        etype = e.get('type')
        if old_str in t and etype in ('TEXT', 'MTEXT', 'ATTRIB', 'DIMENSION'):
            new_t = re.sub(r'(?<![\d.])' + re.escape(old_str) + r'(?![\d.])', new_str, raw)
            if new_t != raw:
                new_ops.append(Operation(ref=ref, action='replace_text',
                                         before=raw, after=new_t, xyz=[],
                                         reason=f'Cập nhật kích thước {old_str} -> {new_str}'))
                p_num = ''
                for n in context.get('part_graph', {}).get('nodes', []):
                    for o in n.get('bom_occurrences', []):
                        d_clean = re.sub(r'[\s:;–-]+$', '', o.get('description', '')).split('(')[0].strip()
                        if d_clean and d_clean.lower() in t.lower():
                            p_num = o.get('part_number', '')
                            break
                    if p_num: break
                purpose = 'annotation'
                new_edits.append(EditProposal(entity_ref=ref, part_number=p_num,
                                              purpose=purpose, before=raw, after=new_t,
                                              reason=f'Đổi {old_str} thành {new_str}'))
    if new_ops and not plan.operations:
        plan.operations = new_ops
        plan.edits = new_edits
        if plan.questions:
            plan.warnings.extend([f'Lưu ý: {q}' for q in plan.questions])
            plan.questions = []
        plan.summary = f'Sửa kích thước từ {old_str}mm thành {new_str}mm trên các bảng kê BOM, khung tên, ghi chú và DIM liên quan.'
        if target_codes: plan.target_part = ', '.join(sorted(target_codes))
    elif new_ops and len(new_ops) > len(plan.operations):
        plan.operations = new_ops
        plan.edits = new_edits
    return plan


def plan_change(document_id,targets,request,clarifications=None,part_selection=None,document_reading=None):
    if not part_selection:
        result=_plan_change(document_id,targets,request,clarifications,**({'document_reading':document_reading} if document_reading else {}))
        if document_reading:
            result['document_reading']=document_reading
            storage.write_json(storage.folder(document_id)/'change-plans'/(result['id']+'.json'),result)
        return result
    from backend.services.design_model_service import resolve_part_selection
    selection=resolve_part_selection(document_id,targets,part_selection,request)
    # Explicit identity enters every existing compiler/scope/impact validator;
    # no geometry refs or edit privileges are granted by the UI selection.
    effective='Mã '+selection['part_code']+': '+request
    result=_plan_change(document_id,targets,effective,clarifications)
    result.update(part_selection=selection,user_request=request)
    storage.write_json(storage.folder(document_id)/'change-plans'/(result['id']+'.json'),result)
    return result


def _plan_change(document_id,targets,request,clarifications=None,document_reading=None):
    from backend.services.planning_control import progress,remaining
    progress('cad','Đang đọc CAD trong bản vẽ được chọn.')
    path=storage.folder(document_id)
    source=path/storage.read_status(document_id)['dxf']
    with CAD_LOCK:
        context=context_for(source,targets)
    if document_reading:
        if document_reading['source_hash']!=context['source_hash']:
            raise ValueError('Hồ sơ toàn file không khớp nguồn đang lập kế hoạch.')
        context['document_reading']=document_reading
    root_targets=list(targets)
    from backend.services.native_parameters import proposal as native_parameter_proposal
    native_proposal=native_parameter_proposal(document_id,source,targets,context,request,clarifications)
    if native_proposal is not None:return native_proposal
    from backend.services.ai_provider import generate_plan,settings
    provider,model=settings()
    if len(root_targets)==1 and root_targets[0].get('kind')=='block':
        capability=next((e for e in context.get('cad_capabilities',{}).get('entities',[]) if e['ref']==root_targets[0]['id']),{})
        if capability.get('status')=='native_required' and not capability.get('conditional_actions'):
            raise ValueError('Block đã chọn cần CAD host/adapter riêng để sửa tham số, proxy hoặc liên kết native. Chưa gọi AI và chưa tạo bản sửa.')
    from backend.services.scope_service import related_scope
    sheet_cache=path/'sheets-v3.json'
    sheets=json.loads(sheet_cache.read_text(encoding='utf8'))['items'] if sheet_cache.exists() else []
    from backend.services.part_graph_service import document_graph
    from graph.part_graph import seed_codes,impact_graph
    graph=document_graph(document_id)
    root_bom_refs={e['ref'] for e in context['entities'] if e.get('bom',{}).get('status')=='verified_template'}
    root_bom_refs.update(ref for t in root_targets for ref in graph.get('bom_continuations',{}).get(t['id'],{}).get('table_refs',[]))
    sheets=sheets+graph.get('linked_details',[])
    from backend.services.compound_planner import request_seeds
    impact=impact_graph(graph,request_seeds(context,request,graph))
    seed_set=set(impact['seed_codes'])
    known_fit_parts={code for edge in impact['edges'] if edge['kind']=='confirmed_parameter' or edge['kind']=='fit' and seed_set.intersection([edge['source'],edge['target']]) for code in (edge['source'],edge['target'])}
    assembly_constituents = {edge['source'] for edge in impact['edges'] if edge.get('kind') == 'assembly_bom' and edge.get('target') in seed_set} | {edge['target'] for edge in impact['edges'] if edge.get('kind') == 'assembly_bom' and edge.get('source') in seed_set}
    candidates=(set(impact.get('process_candidate_codes',[]))|(set(impact.get('assembly_candidate_codes',[]))-set(impact['affected_codes'])))-known_fit_parts-seed_set-assembly_constituents
    review_only_ids=sorted({s for n in impact['nodes'] if n['code'] in candidates for s in n['detail_sheets']}-{t['id'] for t in root_targets})
    edit_sources={s for n in impact['nodes'] if n['code'] not in candidates for s in n['detail_sheets']}
    edit_sources.update(s for link in impact.get('confirmed_representation_links',[]) if link['part_code'] not in candidates for s in link['sheet_ids'])
    edit_sources.update(s for n in impact['nodes'] if n['code'] not in candidates
                        for i in n.get('native_instances',[]) for s in i['sheet_ids'])
    review_only_ids=sorted((set(review_only_ids)|{r['sheet_id'] for g in impact.get('process_groups',[]) for r in g.get('assembly_references',[])})-edit_sources-{t['id'] for t in root_targets})
    with CAD_LOCK:
        targets,scope_links=related_scope(targets,context,sheets,request,graph)
        if scope_links:context=context_for(source,targets,review_only_ids) if review_only_ids else context_for(source,targets)
    context['scope_links']=scope_links
    context['root_target_ids']=[t['id'] for t in root_targets]
    context['root_bom_refs']=sorted(root_bom_refs)
    context['part_graph']=impact
    from backend.services.document_atlas_service import planning_evidence
    context['document_reading']=document_reading or planning_evidence(document_id,context.get('source_hash') or hashlib.sha256(source.read_bytes()).hexdigest())
    progress('features','Đang kiểm tra DIM, chủ sở hữu và các chi tiết liên quan.')
    from cad.measured_features import index as measured_index
    context['source_features']=measured_index(context,graph)
    from graph.design_model import build as build_design_model
    if context.get('source_hash'):context['design_model']=build_design_model(context,graph)
    from backend.services.design_choices import attach as attach_choices
    attach_choices(context,path)
    from backend.services.height_request_service import review as height_review, verify as verify_height
    size_review=height_review(context,request,clarifications)
    from backend.services.size_commands import interpret_linear_request
    linear_reading=interpret_linear_request(context,request,clarifications)
    context['design_policy']='Giữ đường bao ngoài, kích thước ngoài và vị trí lỗ khi chỉ đổi độ dày; thay mặt trong và chi tiết lắp trong nếu có bằng chứng tiếp xúc/khe hở. Không suy giảm độ bền từ hình học.'
    from graph.native_span_fits import attach_envelope_request
    attach_envelope_request(context,request,clarifications)
    from backend.services.compound_planner import compile_bundle,checked_one
    progress('compiler','Đang thử bộ sửa hình học trực tiếp, không gọi AI nếu đã đủ dữ liệu.')
    compiled,request_review=compile_bundle(context,request,clarifications)
    if request_review:context['request_requirements']=request_review
    planner='checked_atomic_compound'
    if request_review is None:
        compiled,planner=checked_one(context,request,clarifications)
    if compiled is not None and not compiled.operations:
        compiled=None
    invalid_sizes=[item['reason'] for item in size_review if item['status']=='unresolved']
    if invalid_sizes and (compiled is None or not compiled.operations):
        context.setdefault('warnings',[]).extend(invalid_sizes)
    interpreted_intent=None
    if compiled is None and request_review is None:
        from backend.services.intent_service import compile_intent
        from backend.services.native_ai_service import ContextBudgetExceeded
        try:compiled,interpreted_intent=compile_intent(context,request,clarifications,root_targets,source)
        except ContextBudgetExceeded:
            compiled=None;interpreted_intent={'status':'deferred_to_source_pages'}
        except Exception as intent_err:
            compiled=None;interpreted_intent={'status':'failed','error':str(intent_err)}
        planner='vision_intent_checked_rectangular_resize'
    if compiled is not None and compiled.operations:
        compiled=synthesize_linear_change(compiled,context,request,clarifications)
        progress('validation','Đang kiểm tra kế hoạch CAD, BOM và các liên kết kéo theo.')
        from graph.impact_validation import validate_impact
        from graph.process_validation import checked_assessments
        from graph.native_instances import synchronize
        try:
            verify_height(compiled,context,request,clarifications)
            compiled=synchronize(compiled,context)
            if review_only_ids:
                from backend.services.native_fit_scope_service import expand as expand_fit_scope
                compiled,context,targets,review_only_ids,scope_links,impact=expand_fit_scope(document_id,source,compiled,context,graph,targets,sheets,request,review_only_ids,scope_links,discover=True)
            from graph.native_contacts import synchronize as sync_contacts
            compiled=sync_contacts(compiled,context)
            from graph.flat_contacts import synchronize as sync_flat_contacts
            compiled=sync_flat_contacts(compiled,context)
            if compiled.native_span_fits:
                from backend.services.native_fit_scope_service import expand as expand_fit_scope
                compiled,context,targets,review_only_ids,scope_links,impact=expand_fit_scope(document_id,source,compiled,context,graph,targets,sheets,request,review_only_ids,scope_links)
            from graph.packaging_fit import synchronize as sync_packaging
            compiled=sync_packaging(compiled,context)
            from backend.services.design_choices import validate as validate_choices
            validate_choices(compiled,context)
            from cad.dimension_associations import synchronize as sync_native_dimensions
            compiled=sync_native_dimensions(compiled,context)
            from rules.dimension_rules import synchronize_assembly_components
            compiled=synchronize_assembly_components(compiled,context,request)
        except ValueError as error:
            compiled.operations=[];compiled.questions.append(str(error))
        compiled.process_assessments=checked_assessments(compiled,impact,context)
        from graph.request_fulfillment import review as fulfillment_review
        fulfillment=fulfillment_review(compiled,context)
        from backend.services.checked_preview_service import candidate
        preview_candidate=candidate(compiled,context,request_review)
        from bom.stage_links import review_material_inputs
        material_reviews=review_material_inputs(compiled,impact,context)
        plan=validate_plan(validate_impact(validate_process_review(compiled,impact,context),impact,context),context)
        plan_id=uuid.uuid4().hex
        result={'id':plan_id,'document_id':document_id,'status':'proposal_only','request':request,
                'target_ids':[t['id'] for t in targets],'targets':targets,
                'root_target_ids':[t['id'] for t in root_targets],'root_bom_refs':sorted(root_bom_refs),'scope_links':scope_links,
                'review_only_ids':review_only_ids,
                'provider':provider,'model':model,'planner':planner,'impact_graph':impact,
                'document_reading':context['document_reading'],
                'reading_profile':reading_brief(context),
                'interpreted_intent':interpreted_intent,'request_review':request_review,
                'size_interpretation':size_review,'clarifications':clarifications or [],
                'request_interpretation':linear_reading,
                'dimension_choices':(linear_reading or {}).get('dimension_choices',[]),
                'fulfillment_review':fulfillment,
                'material_input_review':material_reviews,
                'packaging_review':__import__('graph.packaging_fit',fromlist=['review']).review(plan,context),
                'forming_review':__import__('backend.services.curved_wall_service',fromlist=['review']).review(plan,context),
                'source_hash':hashlib.sha256(source.read_bytes()).hexdigest(),
                'plan':plan.model_dump(),'execution_available':bool(plan.operations),
                'message':'Engine tính hình học theo nguồn và đồng bộ mô tả/BOM; liên kết chưa đủ bằng chứng vẫn chặn thực thi.'}
        if not result['execution_available'] and preview_candidate:
            result['checked_preview_plan']=preview_candidate
            result['preview_execution_available']=True
            from backend.services.checked_preview_service import reviews as preview_reviews
            result['preview_reviews']=preview_reviews(preview_candidate,context)
        if fulfillment:
            result['request_review']=dict(request_review or {},status='partial',reason=fulfillment['reason'])
        from backend.services.revision_service import ensure_changed_targets
        ensure_changed_targets(result, context, targets)
        from backend.services.edit_gate_service import assess_plan
        result['edit_gate']=assess_plan(result,context,preview=bool(result.get('checked_preview_plan')) and not result['execution_available'],validated=True)
        result['relationship_evidence']=result['edit_gate'].get('relationship_evidence',[])
        output=path/'change-plans';output.mkdir(exist_ok=True)
        storage.write_json(output/(plan_id+'.json'),result)
        if result['execution_available'] and planner=='checked_plate_size':
            from backend.services.design_choices import remember_linear
            remember_linear(context,path,request,clarifications,plan_id,**({'separate':True} if document_reading else {}))
        return result
    from backend.services.planner_prompt import HIERARCHICAL_PROMPT,PACKAGING_POLICY,CURVED_WALL_POLICY
    prompt=HIERARCHICAL_PROMPT+'\n'+PACKAGING_POLICY
    if provider in ('native','ollama'):
        from backend.services.planner_prompt import LOCAL_CPU_PROMPT
        prompt=LOCAL_CPU_PROMPT
    if len(root_targets) > 4:
        root_targets = root_targets[:4]
    from cad.sheets import render_sheet
    from cad.catalog import preview
    from cad.vision import rasterize_svg
    from backend.services.context_wire import pack_context
    from backend.services.local_context import overview
    expanded=set();opened_blocks=set();located_refs=set();query_pages=[];hierarchical=provider in ('ollama','native','gemini','openai')
    from backend.services.cpu_planning_pages import PlanningPages
    cpu_pages=PlanningPages(context) if provider in ('native','ollama') else None
    raw_local=(provider in ('native','ollama') and len(context['entities'])<=25
               and len(json.dumps(context['entities'],ensure_ascii=False))<=8000
               and max((e['ref'].count('/') for e in context['entities']),default=0)<=2)
    if raw_local:
        hierarchical=False
        expanded={e['ref'] for e in context['entities'] if e.get('geometry')}
    def model_context():
        if cpu_pages:return cpu_pages.view()
        if raw_local:
            return pack_context(cpu_raw_context(context))
        data=planning_context(context,expanded,hierarchical,opened_blocks,located_refs)
        if query_pages:data['geometry_query_results']=query_pages
        if hierarchical:data=overview(data,opened_blocks,expanded,defer_frames=provider in ('native','ollama'))
        if data.get('focused_scope_ids'):
            from backend.services.planning_view import pack_focused_metadata
            data=pack_focused_metadata(data)
        return pack_context(data)
    if provider in ('native','ollama'):
        from backend.services.planner_prompt import LOCAL_CPU_PROMPT
        prompt=LOCAL_CPU_PROMPT+'\nsource_pages_v1 gives source-bound pages, not the whole CAD. metadata_requests kinds: targets, entities, bom_rows, features, parts, relations, processes, choices, detail, chunks, query_results, requested_records, assemblies, assembly_members, assembly_chunks, products, balloons, row_groups, row_frames, row_markers, row_chunks, row_bindings, leader_profiles, part_views, view_matches, part_view_chunks. part_views/view_matches expose source-bound Part Map reading evidence, not edit permission. A source_sheet_identity_candidate or shape-only candidate is never a verified owner. Filter with view_id, part_code or target_id; part_view_chunks(view_id,field) retrieves exact deferred view fields. leader_profiles checks native leader boundary/interior associations, holes and paper borders. geometry_owner_verified=true requires a unique straight material interior, a re-read local BOM row and real DIM. Other regions remain reading evidence; this never establishes mechanical contact or cross-view motion. Use row_group_id and field for exact source row/frame annotations. Use offset/limit, target_id, part_code, part_number, assembly_id or exact ref. chunks(ref,field) returns ordered JSON fragments of a large field. Geometry/context requests are returned in requested_records pages, including block children. next_offset means more source rows remain. While retrieving, operations=[] and edits=[]; never assume deferred rows were checked. For a source-verified feature, use its complete outline/evidence refs in resize_recipes; the engine rechecks native geometry. Request the exact BOM row before proposing its text edit.'
    prompt+='\n'+TEACHING_PROMPT
    prompt+='\nNếu nét cần xem bị hoãn, không hỏi user nhập lại tọa độ: dùng geometry_queries=[{target_id,region:[left,top,right,bottom],types:["LINE","ARC"],layer:"",offset:0,limit:40}]. region dùng ảnh 0..1000, [] tìm toàn khung. Kết quả có match_count, refs, next_offset: lấy trang tiếp hoặc thu hẹp vùng; không coi một trang là toàn bộ nét. Sau đó geometry_requests=[ref] lấy snapshot thật trước sửa. Nếu còn truy xuất thì operations=[]; geometry_queries=[] khi đủ dữ liệu. Chỉ có ảnh các preview_target_ids trong lượt này; query target khác sẽ lấy thêm ảnh khung đó ở lượt sau.'
    pictures={}
    def model_content(preview_targets):
        ids=list(dict.fromkeys(t['id'] for t in preview_targets))[:1 if provider in ('native','ollama') else 4]
        content=[{'text':json.dumps({'user_request':request,'clarifications':clarifications or [],
                 'preview_target_ids':ids,'cad_context':model_context()},ensure_ascii=False,separators=(',',':'))}]
        for tid in ids:
            target=next(t for t in targets if t['id']==tid)
            if tid not in pictures:
                with CAD_LOCK:
                    picture=render_sheet(source,target) if target['kind']=='sheet' else preview(source,target['id'])
                pictures[tid]=base64.b64encode(rasterize_svg(picture,512 if provider in ('native','ollama') else 800)).decode()
            content.extend([{'text':f"Preview của {target['kind']} #{tid}; dùng hình đối chiếu, không bịa tọa độ/ref từ pixel."},
                            {'inlineData':{'mimeType':'image/png','data':pictures[tid]}}])
        return content
    content=model_content(root_targets)
    progress('model_prepare','Đang chuẩn bị dữ liệu tóm tắt cho AI nội bộ.')
    prompt+='\n'+CURVED_WALL_POLICY
    active_previews=list(root_targets)
    def generate_step(previews):
        nonlocal content
        from backend.services.native_ai_service import ContextBudgetExceeded
        for attempt in range(4):
            content=model_content(previews)
            try:return generate_plan(prompt,content,DrawingChangePlan)
            except ContextBudgetExceeded:
                if not cpu_pages or attempt==3:raise
                cpu_pages.max_bytes=max(2400,cpu_pages.max_bytes//2)
                progress('model_prepare','Đang chia nhỏ trang CAD theo ngân sách model; nguồn vẫn giữ đầy đủ.')
        raise ValueError('Không tạo được trang CAD vừa ngân sách model')
    try:
        plan=generate_step(active_previews)
    except Exception as ai_err:
        plan=DrawingChangePlan(summary='Kế hoạch chỉnh sửa bản vẽ theo yêu cầu',target_part='',
                               edits=[],dependencies=[],questions=[],warnings=[f'AI: {ai_err}'])
    for _ in range(4 if cpu_pages else 6):
        remaining()
        if not plan.geometry_requests and not plan.context_requests and not plan.geometry_queries and not plan.metadata_requests:break
        available={e['ref'] for e in context['entities'] if e.get('geometry') or e.get('radial_geometry')}
        requested=set(plan.geometry_requests) & available
        plan.geometry_requests=list(requested)
        block_refs={e['ref'] for e in context['entities']}
        requested_blocks=set(plan.context_requests)
        if not requested_blocks<=block_refs:raise ValueError('AI yêu cầu block không tồn tại hoặc ngoài phạm vi')
        from backend.services.geometry_retrieval import resolve_queries
        found,pages=resolve_queries(context,plan.geometry_queries)
        if requested<=expanded and requested_blocks<=opened_blocks and found<=located_refs and pages==query_pages and not plan.metadata_requests:break
        expanded|=requested
        opened_blocks|=requested_blocks
        located_refs|=found;query_pages=pages
        if cpu_pages:
            requests=list(plan.metadata_requests)
            wanted=requested|requested_blocks|{e['ref'] for e in context['entities'] if any(e['ref'].startswith(r+'/') for r in requested_blocks)}
            cpu_pages.requested_refs=sorted(wanted)
            if wanted:requests.append(MetadataRequest(kind='requested_records',limit=4))
            cpu_pages.query_results=pages
            if pages:requests.append(MetadataRequest(kind='query_results',limit=4))
            cpu_pages.set_requests(requests)
        requested_targets=[t for t in targets if any(q.target_id==t['id'] for q in plan.geometry_queries)]
        if requested_targets:active_previews=requested_targets+root_targets
        content=model_content(active_previews)
        plan=generate_step(active_previews)
    if plan.geometry_requests or plan.context_requests or plan.geometry_queries or plan.metadata_requests:
        plan.questions.append('Cần thu hẹp nhóm chi tiết hoặc bổ sung bằng chứng liên kết để lấy đủ geometry cho kế hoạch.')
        plan.operations=[]
    records={e['ref']:e for e in context['entities']}
    for dep in plan.dependencies:
        if dep.coordinate_rule:
            expected={'line_end':('LINE',),'move_insert':('INSERT',),'dimension_point':('DIMENSION',),'geometry_point':('LINE','CIRCLE','ARC','ELLIPSE'),
                      'translate_geometry':('LINE','LWPOLYLINE','POLYLINE','CIRCLE','DIMENSION')}[dep.coordinate_rule.target_action]
            if records.get(dep.coordinate_rule.target_ref,{}).get('type') not in expected:
                dep.coordinate_rule=None
    unresolved=[dep for dep in plan.dependencies if dep.coordinate_rule is None and dep.fit_rule is None and dep.equation_rule is None]
    if unresolved:
        for dep in unresolved:
            plan.warnings.append(f'Liên kết {dep.source_part} → {dep.target_part}: {dep.required_change}. Chi tiết chính đã được tạo bản sửa trực tiếp.')
    if request_review is not None:
        from backend.services.compound_planner import verify_bundle
        try:verify_bundle(plan,context,request,clarifications)
        except ValueError as error:
            if not plan.operations:
                plan.questions.append(str(error))
            else:
                plan.warnings.append(str(error))
    from graph.impact_validation import validate_impact
    from backend.services.parametric_service import compile_recipes
    try:
        plan=compile_recipes(plan,context)
        verify_height(plan,context,request,clarifications)
        from graph.native_instances import synchronize
        plan=synchronize(plan,context)
        if review_only_ids:
            from backend.services.native_fit_scope_service import expand as expand_fit_scope
            plan,context,targets,review_only_ids,scope_links,impact=expand_fit_scope(document_id,source,plan,context,graph,targets,sheets,request,review_only_ids,scope_links,discover=True)
        from graph.native_contacts import synchronize as sync_contacts
        plan=sync_contacts(plan,context)
        from graph.flat_contacts import synchronize as sync_flat_contacts
        plan=sync_flat_contacts(plan,context)
        if plan.native_span_fits:
            from backend.services.native_fit_scope_service import expand as expand_fit_scope
            plan,context,targets,review_only_ids,scope_links,impact=expand_fit_scope(document_id,source,plan,context,graph,targets,sheets,request,review_only_ids,scope_links)
        from graph.packaging_fit import synchronize as sync_packaging
        plan=sync_packaging(plan,context)
        from backend.services.design_choices import validate as validate_choices
        validate_choices(plan,context)
        from cad.dimension_associations import synchronize as sync_native_dimensions
        plan=sync_native_dimensions(plan,context)
    except ValueError as error:
        if not plan.operations:
            plan.questions.append('Chưa thể tạo bản sửa theo tham số: '+str(error))
        else:
            plan.warnings.append('Ghi chú tham số: '+str(error))
    from graph.process_validation import complete_checked_assessments
    plan=complete_checked_assessments(plan,impact,context)
    from bom.stage_links import review_material_inputs
    material_reviews=review_material_inputs(plan,impact,context)
    plan=validate_impact(plan,impact,context)
    plan=validate_process_review(plan,impact,context)
    plan=synthesize_linear_change(plan,context,request,clarifications)
    plan=validate_plan(plan,context)
    plan_id=uuid.uuid4().hex
    result={'id':plan_id,'document_id':document_id,'status':'proposal_only','request':request,'target_ids':[i['id'] for i in targets],
            'targets':targets,'root_target_ids':[t['id'] for t in root_targets],'root_bom_refs':sorted(root_bom_refs),'scope_links':scope_links,'impact_graph':impact,'provider':provider,'model':model,
            'packaging_review':__import__('graph.packaging_fit',fromlist=['review']).review(plan,context),
            'forming_review':__import__('backend.services.curved_wall_service',fromlist=['review']).review(plan,context),
            'review_only_ids':review_only_ids,'request_review':request_review,
            'document_reading':context['document_reading'],
            'material_input_review':material_reviews,
            'reading_profile':reading_brief(context),
            'size_interpretation':size_review,'clarifications':clarifications or [],
            'request_interpretation':linear_reading,
            'source_hash':hashlib.sha256(source.read_bytes()).hexdigest(),
            'plan':plan.model_dump(),'execution_available':bool(plan.operations),
            'message':'Kế hoạch đã lập; chỉ thao tác CAD trong whitelist và không còn câu hỏi/quan hệ chưa xác nhận mới được tạo bản sửa.'}
    from backend.services.edit_gate_service import assess_plan
    result['edit_gate']=assess_plan(result,context,validated=True)
    result['relationship_evidence']=result['edit_gate'].get('relationship_evidence',[])
    from backend.services.revision_service import ensure_changed_targets
    ensure_changed_targets(result, context, targets)
    output=path/'change-plans';output.mkdir(exist_ok=True)
    storage.write_json(output/(plan_id+'.json'),result)
    return result


def refine_change(document_id,plan_id,answers):
    from backend.services.revision_service import safe_id
    path=storage.folder(document_id)
    file=path/'change-plans'/(safe_id(plan_id)+'.json')
    if not file.exists():raise ValueError('Kế hoạch không tồn tại')
    previous=json.loads(file.read_text(encoding='utf8'))
    questions=previous['plan']['questions']
    if len(answers)!=len(questions) or not answers or any(not a.strip() or len(a)>2000 for a in answers):
        raise ValueError('Cần trả lời mỗi câu hỏi, tối đa 2000 ký tự mỗi câu')
    source=path/storage.read_status(document_id)['dxf']
    if hashlib.sha256(source.read_bytes()).hexdigest()!=previous['source_hash']:raise ValueError('Nguồn đã thay đổi; lập yêu cầu lại')
    pairs=previous.get('clarifications',[])+[{'question':q,'answer':a.strip()} for q,a in zip(questions,answers)]
    if len(json.dumps(pairs,ensure_ascii=False))>30000:raise ValueError('Thông tin bổ sung quá dài; tạo yêu cầu mới gọn hơn')
    root_ids=set(previous.get('root_target_ids',previous['target_ids']))
    root_targets=[target for target in previous['targets'] if target['id'] in root_ids]
    extra={'part_selection':previous['part_selection']} if previous.get('part_selection') else {}
    if previous.get('whole_document'):
        from backend.services.document_atlas_service import report as atlas_report
        reading=previous['document_reading']
        if atlas_report(document_id,reading['atlas_id'])['source_hash']!=previous['source_hash']:
            raise ValueError('Hồ sơ toàn file đã đổi; cần phân tích lại.')
        extra['document_reading']=reading
    result=plan_change(document_id,root_targets,previous['request'] if previous.get('whole_document') else previous.get('user_request',previous['request']),pairs,**extra)
    if previous.get('whole_document'):
        result.update(whole_document=True,user_request=previous['user_request'],target_resolution=previous['target_resolution'])
    result['clarifications']=pairs;result['previous_plan_id']=plan_id
    storage.write_json(path/'change-plans'/(result['id']+'.json'),result)
    return result
