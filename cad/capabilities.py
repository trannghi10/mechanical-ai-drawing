"""Source-bound inventory, not a certificate that a design can be edited.

Definitions are counted once. Scope paths retain their native INSERT ancestry.
External resource names are reported as data and are never opened/resolved.
"""
from collections import Counter
from pathlib import Path
from functools import lru_cache
import copy,json
from cad.edit_engine import digest
from cad.catalog import load_document,CAD_LOCK

VERSION=2
CLONE_TYPES={'LINE','LWPOLYLINE','POLYLINE','VERTEX','SEQEND','CIRCLE','ARC','ELLIPSE','SPLINE','TEXT','MTEXT','ATTDEF','ATTRIB','INSERT','SOLID','TRACE','3DFACE','POINT','DIMENSION','HATCH','LEADER','WIPEOUT','TOLERANCE','MLINE','VIEWPORT','IMAGE','RASTERIMAGE','OLE2FRAME','REGION','3DSOLID','BODY','MESH'}
REASONS={
 'dynamic_block':'Block động: hình học và vị trí được bảo toàn; sửa tham số động cần CAD host.',
 'external_reference':'XREF/phần phụ thuộc ngoài file chưa được nạp vào giao dịch sửa.',
 'missing_block':'Không có định nghĩa block được tham chiếu.',
 'block_dictionary':'Block có dữ liệu mở rộng chưa có adapter bảo toàn.',
 'opaque_block_members':'Block chứa đối tượng chưa thể clone bảo toàn.',
 'proxy_entity':'Proxy/custom entity cần ứng dụng tạo hoặc Object Enabler phù hợp.',
 'native_association':'Reactor/association này chưa có adapter sửa được kiểm chứng.',
 'recursive_block_reference':'Block tham chiếu vòng; không thể sửa một phạm vi đầy đủ.',
 'unsupported_entity':'Loại đối tượng chỉ được kiểm kê; chưa có adapter sửa.',
 'unsupported_polyline':'POLYLINE fit/mesh/3D chưa có adapter sửa.',
 'unsupported_dimension':'Loại DIM này chưa có adapter sửa.',
 'unsupported_hatch':'HATCH này chưa có binding đường bao được hỗ trợ.',
}


def attr(e,key,default=None):
    try:return e.dxf.get(key,default)
    except AttributeError:return default


def dictionary_keys(e):
    if not e.has_extension_dict:return []
    try:return sorted(e.get_extension_dict().keys())
    except (AttributeError,KeyError,ValueError):return ['<unreadable>']


def classify(e,blocks):
    kind=e.dxftype();reasons=[];actions=[];status='conditional'
    if kind in ('LINE','LWPOLYLINE','ARC','CIRCLE','ELLIPSE','SPLINE','LEADER','POLYLINE'):
        actions=['replace_geometry']
        if kind=='LINE':actions.append('line_end')
        if kind=='LWPOLYLINE':actions.append('append_geometry')
        if kind=='POLYLINE':
            from cad.legacy_polyline import supported
            if not supported(e):status='read_only';actions=[];reasons.append('unsupported_polyline')
    elif kind in ('TEXT','MTEXT','ATTRIB'):actions=['replace_text']+(['move_text'] if kind!='ATTRIB' else [])
    elif kind=='ACAD_TABLE':actions=['table_cell']
    elif kind=='DIMENSION':
        if attr(e,'dimtype',0)&15 in (0,1,2,3,4):actions=['replace_geometry']
        else:status='read_only';reasons.append('unsupported_dimension')
    elif kind=='INSERT':
        actions=['move_insert']
        info=blocks.get(attr(e,'name',''))
        if info is None:reasons.append('missing_block')
        else:reasons.extend(info['effective_reasons'])
    elif kind=='HATCH':
        from cad.hatch_translation import snapshot
        try:snapshot(e);actions=['replace_geometry']
        except ValueError:status='read_only';reasons.append('unsupported_hatch')
    elif kind=='ACAD_PROXY_ENTITY':reasons.append('proxy_entity')
    else:status='read_only';reasons.append('unsupported_entity')
    keys=dictionary_keys(e);reactors=e.get_reactors()
    geometry_dimassoc=kind in ('LINE','LWPOLYLINE','CIRCLE','ARC') and not keys and bool(reactors) and all(e.doc.entitydb.get(h) is not None and e.doc.entitydb[h].dxftype()=='DIMASSOC' for h in reactors)
    dimassoc=kind=='DIMENSION' and set(keys)=={'ACAD_DIMASSOC'}
    if dimassoc:
        assoc=e.get_extension_dict()['ACAD_DIMASSOC']
        dimassoc=assoc.dxftype()=='DIMASSOC' and set(reactors)=={assoc.dxf.handle} and attr(e,'dimtype',0)&15 in (0,1,2)
    roundtrip=kind in ('ACAD_TABLE','TEXT','MTEXT','ATTRIB') and keys==['ACAD_XREC_ROUNDTRIP'] and not reactors and e.get_extension_dict()['ACAD_XREC_ROUNDTRIP'].dxftype()=='XRECORD'
    if (keys or reactors) and not dimassoc and not geometry_dimassoc and not roundtrip:reasons.append('native_association')
    reasons=sorted(set(reasons))
    if any(r in reasons for r in ('dynamic_block','external_reference','missing_block','block_dictionary','opaque_block_members','proxy_entity','native_association','recursive_block_reference')):
        if kind=='INSERT' and set(reasons) <= {'dynamic_block','block_dictionary'}:
            status='conditional';actions=['move_insert']
        else:
            status='native_required';actions=[]
    conditional_actions=['move_insert'] if kind=='INSERT' and set(reasons) <= {'dynamic_block','block_dictionary'} else []
    return dict(status=status,actions=actions,conditional_actions=conditional_actions,reasons=reasons,association='conditional_dimassoc' if dimassoc or geometry_dimassoc else 'preserved_roundtrip_metadata' if roundtrip else 'native_or_opaque' if keys or reactors else 'none')


def inspect_document(doc,source_hash):
    blocks={};resources=[];layouts={};entities={}
    for b in doc.blocks:
        keys=dictionary_keys(b.block_record);flags=attr(b.block,'flags',0);reasons=[]
        if flags&(4|8|16|32|64):reasons.append('external_reference')
        if any('ENHANCEDBLOCK' in k.upper() or 'DYNAMIC' in k.upper() for k in keys):reasons.append('dynamic_block')
        if keys and keys!=['ACAD_SORTENTS']:reasons.append('block_dictionary')
        if any(e.dxftype() not in CLONE_TYPES for e in b):reasons.append('opaque_block_members')
        blocks[b.name]=dict(name=b.name,flags=flags,entity_count=len(b),types=dict(Counter(e.dxftype() for e in b)),dictionary_keys=keys,
            inserts=sorted({e.dxf.name for e in b if e.dxftype()=='INSERT'}),effective_reasons=reasons)
        if flags&(4|8):resources.append(dict(kind='xref',block_name=b.name,path=attr(b.block,'xref_path',''),status='not_loaded',resolution_attempted=False))
    from collections import defaultdict,deque
    parents=defaultdict(set);outdegree={name:len(set(b['inserts'])&blocks.keys()) for name,b in blocks.items()}
    for name,b in blocks.items():
        for child in b['inserts']:
            if child in blocks:parents[child].add(name)
    leaves=deque(n for n,d in outdegree.items() if d==0);acyclic=set()
    while leaves:
        name=leaves.popleft();acyclic.add(name)
        for parent in parents[name]:
            outdegree[parent]-=1
            if outdegree[parent]==0:leaves.append(parent)
    for name in blocks.keys()-acyclic:blocks[name]['effective_reasons'].append('recursive_block_reference')
    # Propagate special definitions through nested inserts. No arbitrary depth
    # cap and no exponential expansion of repeated definitions.
    pending=True
    while pending:
        pending=False
        for b in blocks.values():
            reasons=set(b['effective_reasons'])
            for child in b['inserts']:reasons.update(blocks[child]['effective_reasons'] if child in blocks else ['missing_block'])
            if reasons!=set(b['effective_reasons']):b['effective_reasons']=sorted(reasons);pending=True
    def add(e,location):
        handle=attr(e,'handle')
        if not handle or handle in entities:return
        entities[handle]=dict(handle=handle,type=e.dxftype(),location=location,**classify(e,blocks))
        if e.dxftype()=='INSERT':
            for a in e.attribs:add(a,location)
        if e.dxftype()=='POLYLINE':
            for a in [*e.vertices,e.seqend]:
                if a is not None:add(a,location)
    layout_blocks={s.block_record_handle for s in doc.layouts}
    for s in doc.layouts:
        layouts[s.name]=dict(entity_count=len(s),types=dict(Counter(e.dxftype() for e in s)))
        for e in s:add(e,dict(layout=s.name))
    for b in doc.blocks:
        if b.block_record_handle in layout_blocks:continue
        for e in b:add(e,dict(block=b.name))
    objects=Counter(e.dxftype() for e in doc.objects)
    for e in doc.objects:
        if e.dxftype() in ('IMAGEDEF','PDFDEFINITION','DWFDEFINITION','DGNDEFINITION'):
            resources.append(dict(kind=e.dxftype().lower(),handle=e.dxf.handle,path=attr(e,'filename',''),status='not_loaded',resolution_attempted=False))
    statuses=Counter(e['status'] for e in entities.values())
    classes=[dict(name=attr(e,'name',''),application=attr(e,'app_name',''),cpp_class_name=attr(e,'cpp_class_name','')) for e in doc.classes]
    return dict(version=VERSION,source_hash=source_hash,dxf_version=doc.dxfversion,units=doc.units,
        summary=dict(stored_entity_count=len(entities),layout_count=len(layouts),block_definition_count=len(blocks),entity_types=dict(Counter(e['type'] for e in entities.values())),
                     capability_counts=dict(statuses),object_types=dict(objects),external_resource_count=len(resources)),
        layouts=layouts,blocks=blocks,entities=entities,resources=resources,classes=classes,
        adapters=[dict(id='checked_dxf',available=True,authorization='Source geometry, ownership and constraints must still be validated.')],
        complete_design_understanding=False,policy='Inventory includes definitions once, not expanded instance counts. Conditional means a supported adapter exists, not permission to edit. Untouched data preservation is checked separately on export.')


@lru_cache(maxsize=8)
def _report(path,mtime_ns,size,version):
    with CAD_LOCK:return inspect_document(load_document(path),digest(path))


def report(source):
    p=Path(source).resolve();stat=p.stat()
    return copy.deepcopy(_report(str(p),stat.st_mtime_ns,stat.st_size,VERSION))


def scope(report,records):
    result=[]
    for e in records:
        ref=e['ref'];parts=ref.split('/');leaf=report['entities'].get(parts[-1])
        # Graphic tables are bound virtual records, not missing native handles.
        if leaf is None and e['type']=='GRAPHIC_TABLE':leaf=dict(status='conditional',actions=['table_cell'],reasons=[],association='none')
        if leaf is None:leaf=dict(status='read_only',actions=[],reasons=['unsupported_entity'],association='none')
        item={k:copy.deepcopy(leaf[k]) for k in ('status','actions','reasons','association')};item['conditional_actions']=leaf.get('conditional_actions',[]);ancestors=[]
        for handle in parts[:-1]:
            parent=report['entities'].get(handle)
            if parent and parent['status']=='native_required':ancestors.append(handle);item['reasons'].extend(parent['reasons'])
        if ancestors:item.update(status='native_required',actions=[],conditional_actions=[])
        item.update(ref=ref,type=e['type'],reasons=sorted(set(item['reasons'])),native_ancestor_handles=ancestors)
        result.append(item)
    return dict(version=VERSION,source_hash=report['source_hash'],capability_counts=dict(Counter(e['status'] for e in result)),entities=result,
                policy='Scope paths include native parent requirements. This does not prove contact, ownership or complete view coverage.')


def validate_operations(report,operations):
    selected=scope(report,[dict(ref=o.ref,type=report['entities'].get(o.ref.split('/')[-1],{}).get('type','unknown')) for o in operations])
    blocked=[e for e,o in zip(selected['entities'],operations) if e['status']=='native_required' and o.action not in e.get('conditional_actions',[])]
    if blocked:
        first=blocked[0]
        raise ValueError('CAD chưa hỗ trợ sửa XREF/dynamic/proxy/association native ở #'+first['ref']+': '+' '.join(REASONS[r] for r in first['reasons']))


def public(report,offset=0,limit=50):
    issues=[e for e in report['entities'].values() if e['status']!='conditional']
    return {k:copy.deepcopy(report[k]) for k in ('version','source_hash','dxf_version','units','summary','layouts','resources','classes','adapters','complete_design_understanding','policy')}|dict(
        issues=issues[offset:offset+limit],issue_count=len(issues),next_offset=offset+limit if offset+limit<len(issues) else None,reasons=REASONS)
