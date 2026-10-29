"""Persist reviewable, source-bound relationship proposals; never execute repairs."""
import json,re,uuid,hashlib
from backend.services import aps_jobs,catalog_service as storage
from cad.edit_engine import digest
from cad.native_polyline_dimensions import discover
from cad.relationship_repairs import legacy_endpoint_proposals


def _id(value):
    if not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('Invalid proposal/inspection ID')
    return value


def _load(document_id,inspection_id,source_hash):
    import ezdxf
    _id(inspection_id)
    job=aps_jobs.read(document_id,inspection_id)
    source=storage.folder(document_id)/'original.dwg'
    if job.get('provider')!='autocad' or job.get('mode')!='inspect' or job.get('status')!='ready' or job.get('source_hash')!=source_hash or digest(source)!=source_hash:
        raise ValueError('Completed local inspection of the current source DWG required')
    inventory_path=aps_jobs.artifact(document_id,inspection_id,'inventory.json')
    dxf_path=aps_jobs.artifact(document_id,inspection_id,'roundtrip.dxf')
    hashes=dict(inventory_sha256=digest(inventory_path),dxf_sha256=digest(dxf_path))
    return json.loads(inventory_path.read_text(encoding='utf-8-sig')),ezdxf.readfile(dxf_path),hashes


def _native_base(document_id,revision_id,source_hash):
    from backend.services import relationship_revision_service as revisions
    r=revisions.read(document_id,_id(revision_id))
    if r['status']!='ready' or r['source_hash']!=source_hash or r.get('adapter','legacy')!='legacy' or r.get('validation',{}).get('status')!='validated_relationship_repair_proposal':
        raise ValueError('Native reference adapter requires a verified ready legacy revision of this source')
    folder=storage.folder(document_id)/'revisions'/revision_id
    report=folder/'evidence/native-subentities.json'
    if r['artifact_hashes'].get('evidence/native-subentities.json')!=digest(report):raise ValueError('Base native evidence not protected by revision artifact hashes')
    bridge=storage.ROOT.parent.parent/'autodesk/NativePointReference/build/MechanicalPointReference.dll'
    if not bridge.is_file():raise ValueError('Build the native point-reference adapter first')
    return folder,dict(revision_id=revision_id,dwg_sha256=digest(folder/'modified.dwg'),dxf_sha256=digest(folder/'modified.dxf'),
                       native_evidence_sha256=digest(report),bridge_sha256=digest(bridge))


def create(document_id,inspection_id,polyline_handle,source_hash,adapter='legacy',base_revision_id=None):
    if not re.fullmatch('[A-Fa-f0-9]{1,16}',polyline_handle):raise ValueError('Invalid polyline handle')
    inventory,doc,hashes=_load(document_id,inspection_id,source_hash)
    group=discover(inventory,doc,polyline_handle.upper())
    if adapter not in ('legacy','native_pointrefs'):raise ValueError('Unsupported relationship adapter')
    base=None
    if adapter=='native_pointrefs':
        if not base_revision_id:raise ValueError('Native reference repair requires a ready base revision')
        folder,base=_native_base(document_id,base_revision_id,source_hash)
        from cad.native_head_repairs import propose
        group['source_sha256']=source_hash
        plan=propose(doc,group,json.loads((folder/'evidence/native-subentities.json').read_text(encoding='utf8')))
        import ezdxf
        from cad.native_point_reference_scope import build_scope
        plan['execution_scope']=build_scope(doc,ezdxf.readfile(folder/'modified.dxf'),group,json.loads((folder/'evidence/native-subentities.json').read_text(encoding='utf8')))
    else:
        if base_revision_id:raise ValueError('Legacy repair does not accept a base revision')
        plan=legacy_endpoint_proposals(doc,group)
    plan=json.loads(json.dumps(plan,allow_nan=False))
    content=dict(schema_version=1,document_id=document_id,inspection_id=inspection_id,source_sha256=source_hash,
                 artifact_hashes=hashes,plan=plan)
    if base:content.update(schema_version=3,adapter=adapter,base=base)
    fingerprint=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    proposal_id=uuid.uuid4().hex
    result=dict(**content,id=proposal_id,scope_sha256=fingerprint,status='proposed_relationship_repair',
                release_gate=dict(allowed=False,reasons=['Cần kiểm native trên bản sao và đối chứng ngoài nhóm.',
                    'Chưa xác nhận đầy đủ ý đồ cơ khí và hình thức hiển thị dung sai/OLE.']),
                edit_authorization=False,source_unchanged=True,
                next_step='Kiểm chứng bản sao; đề xuất này không tự sửa hoặc phát hành DWG.')
    folder=storage.folder(document_id)/'relationship-proposals';folder.mkdir(exist_ok=True)
    storage.write_json(folder/(proposal_id+'.json'),result)
    return result


def read(document_id,proposal_id):
    path=storage.folder(document_id)/'relationship-proposals'/(_id(proposal_id)+'.json')
    result=json.loads(path.read_text(encoding='utf8'))
    if result['document_id']!=document_id or result['id']!=proposal_id:raise ValueError('Proposal identity mismatch')
    inventory,doc,hashes=_load(document_id,result['inspection_id'],result['source_sha256'])
    if hashes!=result['artifact_hashes']:raise ValueError('Inspection artifacts changed; recreate proposal')
    content={k:result[k] for k in ('schema_version','document_id','inspection_id','source_sha256','artifact_hashes','plan')}
    if result['schema_version'] in (2,3):
        if result.get('adapter')!='native_pointrefs':raise ValueError('Unsupported proposal adapter')
        _,base=_native_base(document_id,result['base']['revision_id'],result['source_sha256'])
        if base!=result['base']:raise ValueError('Native proposal base/adapter changed; recreate proposal')
        content.update(adapter=result['adapter'],base=result['base'])
        if result['schema_version']==3:
            import ezdxf
            from cad.native_point_reference_scope import build_scope
            folder,_=_native_base(document_id,result['base']['revision_id'],result['source_sha256'])
            group=discover(inventory,doc,result['plan']['polyline_handle']);group['source_sha256']=result['source_sha256']
            scope=build_scope(doc,ezdxf.readfile(folder/'modified.dxf'),group,json.loads((folder/'evidence/native-subentities.json').read_text(encoding='utf8')))
            if scope!=result['plan'].get('execution_scope'):raise ValueError('Native execution scope differs from source/base evidence')
    elif result['schema_version']!=1:raise ValueError('Unsupported proposal schema')
    expected=hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if result['scope_sha256']!=expected or result.get('edit_authorization') is not False or result.get('release_gate',{}).get('allowed') is not False:
        raise ValueError('Proposal integrity/release state mismatch')
    return result,doc


def preview(document_id,proposal_id):
    result,doc=read(document_id,proposal_id)
    if result.get('adapter')=='native_pointrefs':
        import ezdxf
        folder,_=_native_base(document_id,result['base']['revision_id'],result['source_sha256'])
        doc=ezdxf.readfile(folder/'modified.dxf')
    return render_group(doc,result['plan'])


def render_group(doc,plan):
    from ezdxf.addons.drawing import RenderContext,Frontend,svg,layout
    from ezdxf.addons.drawing.config import Configuration,ColorPolicy,BackgroundPolicy
    from cad.catalog import CAD_LOCK
    with CAD_LOCK:
        backend=svg.SVGBackend()
        front=Frontend(RenderContext(doc),backend,config=Configuration(color_policy=ColorPolicy.BLACK,background_policy=BackgroundPolicy.WHITE))
        front.set_background('#ffffff')
        front.draw_entities([doc.entitydb[h] for h in [plan['polyline_handle'],*plan['dimension_handles']]])
        backend.finalize();return backend.get_string(layout.Page(180,150))
