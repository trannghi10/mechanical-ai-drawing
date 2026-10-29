"""Plan one explicit local/cloud rectangle edit from immutable inspection artifacts."""
import json
from backend.services import aps_jobs,catalog_service as storage
from cad.edit_engine import digest
from cad.point_binding import solve_binding
from cad.dimension_associations import source_binding


def _load(document_id,inspection_id,source_hash,provider,*,allow_edit=False):
    import ezdxf
    job=aps_jobs.read(document_id,inspection_id)
    source=storage.folder(document_id)/'original.dwg'
    if provider not in ('autocad','aps') or job.get('provider')!=provider or job['mode'] not in (('inspect','edit') if allow_edit else ('inspect',)) or job['status']!='ready' or job['source_hash']!=source_hash or digest(source)!=source_hash:
        raise ValueError('Completed matching-provider inspection of the current source DWG required')
    inventory=json.loads(aps_jobs.artifact(document_id,inspection_id,'inventory.json').read_text(encoding='utf-8-sig'))
    d=ezdxf.readfile(aps_jobs.artifact(document_id,inspection_id,'roundtrip.dxf'))
    return job,inventory,d


def _pair(d,inventory,polyline_handle,dimension_handle,rows=None):
    if rows is None:rows={r['handle']:r for r in inventory['entities']}
    if polyline_handle not in rows or dimension_handle not in rows:raise ValueError('Selected handles missing from native inventory')
    row=rows[polyline_handle];poly=d.entitydb.get(polyline_handle);dim=d.entitydb.get(dimension_handle)
    if poly is None or dim is None or poly.dxftype()!='LWPOLYLINE' or dim.dxftype()!='DIMENSION' or not row.get('is_layout') or rows[dimension_handle].get('native_class')!='AcDbRotatedDimension' or poly.dxf.owner!=dim.dxf.owner or poly.dxf.owner!=row['owner_handle'] or d.units!=4 or not poly.closed or len(poly)!=4 or tuple(poly.dxf.extrusion)!=(0,0,1) or any(any(abs(v)>1e-10 for v in p[2:]) for p in poly.get_points()) or abs(poly.dxf.const_width)>1e-10:
        raise ValueError('Only a plain layout rectangle and rotated DIM in millimeters are supported')
    if dim.dxf.dimtype&15!=0 or dim.dxf.get('text','') not in ('','<>') or abs(dim.dxf.get('angle',0))>1e-10:raise ValueError('Unmodified horizontal linear DIM required')
    association=source_binding(dim)
    if not isinstance(association,dict) or association.get('status')!='verified_source_points' or association.get('source_refs')!=[polyline_handle] or [p.get('vertex_index') for p in association['points']]!=[0,1]:raise ValueError('DIM must bind vertices 0 and 1')
    points=[[p[0],p[1],poly.dxf.elevation] for p in poly.get_points()]
    binding=dict(schema_version=1,units='mm',vertices=[dict(index=i,point_id='v'+str(i),xyz=p) for i,p in enumerate(points)],fixed_vertex_indices=[0,3],moving_vertex_indices=[1,2],dimension=dict(vertex_indices=[0,1],measurement_mm=dim.get_measurement(),defpoint2=list(dim.dxf.defpoint2),defpoint3=list(dim.dxf.defpoint3)))
    assoc=association['association_ref']
    if poly.has_extension_dict or set(poly.get_reactors())!={assoc} or set(dim.get_reactors())!={assoc} or set(dim.get_extension_dict().keys())!={'ACAD_DIMASSOC'}:
        raise ValueError('Rectangle supports only this single DIM association')
    return binding,row,association,points


def start(document_id, inspection_id, polyline_handle, dimension_handle, target_width_mm, source_hash, *, provider='autocad'):
    _,inventory,d=_load(document_id,inspection_id,source_hash,provider)
    binding,row,association,points=_pair(d,inventory,polyline_handle,dimension_handle)
    solved=solve_binding(binding,target_width_mm)
    op=dict(action='stretch_rectangle',handle=polyline_handle,owner_handle=row['owner_handle'],expected_type='LWPOLYLINE',dimension_handle=dimension_handle,association_handle=association['association_ref'],before=json.dumps(points),after=json.dumps(solved['points']))
    result=aps_jobs.start(document_id,provider=provider,mode='edit',operations=[op],scope_handles=[polyline_handle,dimension_handle],expected_source_hash=source_hash)
    result['solver_summary']={k:solved['solver'][k] for k in ('status','rank','degrees_of_freedom','max_residual_mm')}
    return result


def candidates(document_id,inspection_id,*,provider='autocad'):
    job=aps_jobs.read(document_id,inspection_id)
    _,inventory,d=_load(document_id,inspection_id,job['source_hash'],provider)
    result=[];scanned=0;unsupported=0;truncated=False
    rows={r['handle']:r for r in inventory['entities']}
    for layout in d.layouts:
        for dim in layout.query('DIMENSION'):
            scanned+=1
            if scanned>20000:truncated=True;break
            try:
                association=source_binding(dim)
                if not isinstance(association,dict) or association.get('status')!='verified_source_points' or len(association.get('source_refs',[]))!=1:raise ValueError('Unsupported DIM source')
                polyline=association['source_refs'][0]
                binding,row,assoc,points=_pair(d,inventory,polyline,dim.dxf.handle,rows)
                width=binding['dimension']['measurement_mm'];solve_binding(binding,width)
                result.append(dict(polyline_handle=polyline,dimension_handle=dim.dxf.handle,association_handle=assoc['association_ref'],layout=layout.name,
                    width_mm=width,height_mm=points[3][1]-points[0][1],fixed_edge='left',fixed_vertex_indices=[0,3],moving_vertex_indices=[1,2],
                    edit_authorization=False,requires_explicit_target=True))
                if len(result)>=100:truncated=True;break
            except (ValueError,KeyError,TypeError):unsupported+=1
        if truncated:break
    return dict(inspection_id=inspection_id,source_hash=job['source_hash'],provider=provider,items=result,scanned_dimensions=scanned,
                unsupported_dimensions=unsupported,truncated=truncated,scope='Entire inspected file; only the selected polyline and DIM will be edited.')


def preview(document_id,job_id,polyline_handle,dimension_handle,*,provider='autocad'):
    job=aps_jobs.read(document_id,job_id)
    _,inventory,d=_load(document_id,job_id,job['source_hash'],provider,allow_edit=True)
    binding,_,_,_=_pair(d,inventory,polyline_handle,dimension_handle);solve_binding(binding,binding['dimension']['measurement_mm'])
    from ezdxf.addons.drawing import RenderContext,Frontend,svg,layout
    from ezdxf.addons.drawing.config import Configuration,ColorPolicy,BackgroundPolicy
    from cad.catalog import CAD_LOCK
    with CAD_LOCK:
        backend=svg.SVGBackend()
        frontend=Frontend(RenderContext(d),backend,config=Configuration(color_policy=ColorPolicy.BLACK,background_policy=BackgroundPolicy.WHITE))
        frontend.set_background('#ffffff');frontend.draw_entities([d.entitydb[polyline_handle],d.entitydb[dimension_handle]]);backend.finalize()
        return backend.get_string(layout.Page(180,110))
