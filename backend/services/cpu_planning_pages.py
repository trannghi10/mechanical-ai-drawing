"""Budgeted source pages for the offline planner; complete CAD stays on server."""
import copy
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field


class MetadataRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['targets','entities','bom_rows','features','parts','relations','processes','choices','detail','chunks','query_results','requested_records',
                 'assemblies','assembly_members','assembly_chunks','products','balloons','row_groups','row_frames','row_markers','row_chunks','row_bindings','leader_profiles',
                 'part_views','view_matches','part_view_chunks']
    target_id:str=''
    part_code:str=''
    ref:str=''
    field:str=''
    assembly_id:str=Field(default='',max_length=256)
    part_number:str=Field(default='',max_length=64)
    row_group_id:str=Field(default='',max_length=64)
    view_id:str=Field(default='',max_length=64)
    offset:int=Field(default=0,ge=0)
    limit:int=Field(default=4,ge=1,le=12)


def size(value):return len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf8'))


class PlanningPages:
    def __init__(self,context,max_bytes=6000):
        self.source=context;self.max_bytes=max_bytes;self.requests=[];self.query_results=[];self.requested_refs=[]
        self.by={e['ref']:e for e in context['entities']}
        self.targets={t['id']:t for t in context.get('targets',[])}
        self.roots=set(context.get('root_target_ids',[]))
        self.features=context.get('source_features',{}).get('features',[])
        self.graph=context.get('part_graph',{})
        self.structure=self.graph.get('assembly_structure',{})
        self.assemblies={g['id']:g for g in self.structure.get('assemblies',[])}
        from cad.row_groups import identity_groups
        self.row_groups={g['id']:g for g in identity_groups(self.graph.get('drawing_rows',{}))}
        self.part_map=context.get('design_model',{}).get('part_map',{})
        if self.part_map and self.part_map.get('source_hash')!=context.get('source_hash'):
            raise ValueError('Part Map và trang AI phải cùng nguồn CAD')
        self.part_views={v['id']:v for v in self.part_map.get('views',[])}
        self.defaults=[MetadataRequest(kind='choices',limit=4),MetadataRequest(kind='bom_rows',limit=3),
                       MetadataRequest(kind='features',limit=3),MetadataRequest(kind='entities',limit=3)]
        if self.assemblies:self.defaults[-1]=MetadataRequest(kind='assemblies',limit=1)
        if self.row_groups:self.defaults.append(MetadataRequest(kind='row_groups',limit=1))
        if context.get('design_model',{}).get('loose_planar_relationships',{}).get('contacts'):
            self.defaults.append(MetadataRequest(kind='relations',limit=2))

    def validate(self,request):
        if request.target_id and request.target_id not in self.targets:raise ValueError('AI yêu cầu trang ngoài khung CAD đã mở')
        if request.ref and request.ref not in self.by:raise ValueError('AI yêu cầu nội dung CAD không tồn tại trong phạm vi')
        if request.kind in ('detail','chunks') and not request.ref:raise ValueError('Trang chi tiết cần ref CAD nguồn')
        if request.kind=='chunks' and request.field not in self.by[request.ref]:raise ValueError('AI yêu cầu trường CAD không có trong nguồn')
        if request.assembly_id and request.assembly_id not in self.assemblies:raise ValueError('AI yêu cầu cụm ngoài đồ thị nguồn đã mở')
        if request.row_group_id and request.row_group_id not in self.row_groups:raise ValueError('AI yêu cầu nhóm hàng không có trong nguồn')
        if request.view_id and request.view_id not in self.part_views:raise ValueError('AI yêu cầu hình ngoài Part Map nguồn')
        if request.kind=='part_view_chunks':
            if not request.view_id or request.field not in self.part_views[request.view_id]:raise ValueError('Trang hình cần view_id và trường Part Map nguồn')
        if request.kind in ('row_frames','row_markers','row_chunks','row_bindings') and not request.row_group_id:raise ValueError('Cần row_group_id để đọc khung/ký hiệu cùng hàng')
        if request.kind=='row_chunks' and request.field not in self.row_groups[request.row_group_id]:raise ValueError('Trường nhóm hàng không có trong nguồn')
        if request.kind=='assembly_chunks':
            if not request.assembly_id:raise ValueError('Trang cụm cần assembly_id nguồn')
            if request.field not in self.assemblies[request.assembly_id]:raise ValueError('Trường cụm không có trong nguồn')

    def set_requests(self,requests):
        for request in requests:self.validate(request)
        self.requests=list(requests)

    def _scope(self,record,request):
        return not request.target_id or request.target_id in record.get('source_sheet_ids',record.get('sheet_ids',[]))

    def _rows(self,request):
        c=self.source;kind=request.kind
        if kind in ('part_views','view_matches','part_view_chunks'):
            views=[v for v in self.part_views.values() if self._scope(v,request) and
                   (not request.view_id or v['id']==request.view_id) and
                   (not request.ref or request.ref in v['geometry_refs']+v.get('circle_refs',[])) and
                   (not request.part_code or request.part_code in v['part_codes']+v.get('candidate_part_codes',[]))]
            views.sort(key=lambda v:(not bool(self.roots.intersection(v['sheet_ids'])),v['id']))
            if kind=='part_views':return [dict(v,view_id=v['id'],executable=False) for v in views]
            if kind=='part_view_chunks':
                if not views:return []
                raw=json.dumps(views[0][request.field],ensure_ascii=False,separators=(',',':'))
                return [dict(view_id=request.view_id,field=request.field,index=i//200,json_fragment=raw[i:i+200]) for i in range(0,len(raw),200)]
            ids={v['id'] for v in views}
            return [dict(r,executable=False) for r in self.part_map.get('correspondences',[]) if ids.intersection([r['source_view_id'],r['target_view_id']])]
        if kind=='leader_profiles':
            return [b for b in c.get('source_features',{}).get('leader_profile_bindings',[]) if self._scope(b,request) and
                    (not request.part_code or request.part_code in b['part_codes']) and
                    (not request.part_number or request.part_number==b['part_number']) and
                    (not request.row_group_id or request.row_group_id==b['row_group_id'])]
        if kind in ('row_groups','row_frames','row_markers','row_chunks','row_bindings'):
            rows=[g for g in self.row_groups.values() if (not request.row_group_id or g['id']==request.row_group_id) and
                  (not request.target_id or request.target_id in g['sheet_ids']) and
                  (not request.part_code or request.part_code in g.get('part_codes',[]))]
            rows.sort(key=lambda g:(not bool(self.roots.intersection(g['sheet_ids'])),g['id']))
            if kind=='row_chunks':
                if not rows:return []
                raw=json.dumps(rows[0][request.field],ensure_ascii=False,separators=(',',':'))
                return [dict(row_group_id=request.row_group_id,field=request.field,index=i//200,json_fragment=raw[i:i+200]) for i in range(0,len(raw),200)]
            if kind=='row_groups':return [dict(row_group_id=g['id'],label=g['label'],kind=g['kind'],sheet_ids=g['sheet_ids'],
                part_codes=g.get('part_codes',[]),status=g['status'],label_ref=g['label_ref'],circle_ref=g['circle_ref'],
                frame_count=len(g['frames']),marker_count=len(g['markers']),executable=False) for g in rows]
            field={'row_frames':'frames','row_markers':'markers','row_bindings':'marker_bindings'}[kind]
            return [dict(row_group_id=g['id'],**item) for g in rows for item in g[field]
                    if kind=='row_frames' or not request.part_number or item.get('label',item.get('part_number'))==request.part_number]
        groups=[g for g in self.assemblies.values() if
                (not request.assembly_id or request.assembly_id==g['id']) and
                (not request.target_id or request.target_id in g.get('scope_ids',[])) and
                (not request.part_code or request.part_code==g.get('owner_code') or
                 request.part_code in g.get('descendant_part_codes',[]) or
                 any(m['part_code']==request.part_code for m in g['members']))]
        groups.sort(key=lambda g:(not bool(self.roots.intersection(g.get('scope_ids',[])) or g['table_ref'] in c.get('root_bom_refs',[])),g['id']))
        if kind=='assemblies':
            return [dict(assembly_id=g['id'],table_ref=g['table_ref'],scope_ids=g.get('scope_ids',[]),
                         owner_code=g.get('owner_code'),kind=g['kind'],member_count=len(g['members']),
                         parent_ids=g.get('parent_ids',[]),child_ids=g.get('child_ids',[]),
                         covered_assembly_ids=g.get('covered_assembly_ids',[]),status=g.get('status'),executable=False) for g in groups]
        if kind=='assembly_members':
            return [dict(assembly_id=g['id'],table_ref=g['table_ref'],scope_ids=g.get('scope_ids',[]),**m) for g in groups for m in g['members']
                    if (not request.part_number or request.part_number==m['part_number']) and (not request.part_code or request.part_code==m['part_code'])]
        if kind=='assembly_chunks':
            if not groups:return []
            raw=json.dumps(groups[0][request.field],ensure_ascii=False,separators=(',',':'))
            return [dict(assembly_id=request.assembly_id,field=request.field,index=i//200,json_fragment=raw[i:i+200]) for i in range(0,len(raw),200)]
        if kind=='products':
            ids={g['id'] for g in groups}
            return [dict(product_code=p.get('product_code'),domain=p['domain'],status=p['status'],
                         assembly_count=len(p['assembly_ids']),leaf_part_count=len(p['leaf_part_codes']),
                         main_candidate_count=len(p['main_drawing_candidates']),main_assembly_id=main)
                    for p in self.structure.get('products',[]) if ids.intersection(p['assembly_ids'])
                    for main in (p['main_drawing_candidates'] or [None])]
        if kind=='balloons':
            refs={g['table_ref'] for g in groups}
            links=[l for l in c.get('drawing_evidence',{}).get('bom_links',[]) if l['table_ref'] in refs and
                   (not request.part_code or request.part_code==l['part_code']) and (not request.part_number or request.part_number==l['part_number'])]
            return [dict(table_ref=l['table_ref'],part_number=l['part_number'],part_code=l['part_code'],
                         status='source_marker_candidate' if marker else 'marker_not_bound',**marker)
                    for l in links for marker in (l.get('number_markers') or [{}])]
        if kind=='requested_records':return [self.by[r] for r in self.requested_refs]
        if kind=='query_results':
            return [dict(query=p['query'],ref=r,match_count=p['match_count'],next_geometry_offset=p.get('next_offset'))
                    for p in self.query_results for r in p['refs']]
        if kind=='targets':
            return [{k:t[k] for k in ('id','kind','layout','name') if k in t} for t in c.get('targets',[])]
        if kind in ('detail','chunks'):
            record=self.by[request.ref]
            if kind=='detail':return [record]
            raw=json.dumps(record[request.field],ensure_ascii=False,separators=(',',':'))
            return [dict(ref=request.ref,field=request.field,index=i//200,json_fragment=raw[i:i+200]) for i in range(0,len(raw),200)]
        if kind=='choices':return c.get('design_choices',{}).get('confirmed_choices',[])
        if kind=='features':
            return [{k:v for k,v in f.items() if k!='points'} for f in self.features if self._scope(f,request) and
                    (not request.part_code or f.get('part_code')==request.part_code)]
        if kind=='parts':return [n for n in self.graph.get('nodes',[]) if not request.part_code or n['code']==request.part_code]
        if kind=='relations':
            contacts=[e for e in c.get('design_model',{}).get('relationship_observations',[]) if e.get('kind') in ('planar_end_face_contact','planar_measured_clearance')]
            return [e for e in self.graph.get('edges',[])+contacts if (not request.part_code or request.part_code in (e['source'],e['target'])) and
                    (not request.target_id or request.target_id in e.get('sheet_ids',[]) or any(p.get('sheet_id')==request.target_id for p in e.get('evidence',[])))]
        if kind=='processes':return [g for g in self.graph.get('process_groups',[]) if not request.part_code or any(m['part_code']==request.part_code for m in g.get('members',[]))]
        if kind=='bom_rows':
            tables=[e for e in c['entities'] if e.get('bom') and self._scope(e,request)]
            tables.sort(key=lambda e:(e['ref'] not in c.get('root_bom_refs',[]),e['ref']))
            return [dict(table_ref=e['ref'],status=e['bom'].get('status'),source_sheet_ids=e.get('source_sheet_ids',[]),**row)
                for e in tables for row in e['bom'].get('rows',[]) if not request.part_code or row.get('part_code')==request.part_code]
        entities=[e for e in c['entities'] if self._scope(e,request)]
        # Every entity remains accessible; only ordering prioritizes the selected
        # drawing's semantic records. No entity is dropped by this catalogue.
        entities.sort(key=lambda e:(not bool(self.roots.intersection(e.get('source_sheet_ids',[])) or e['ref'].split('/')[0] in self.roots),
                                   e['type'] not in ('DIMENSION','ACAD_TABLE','GRAPHIC_TABLE','TEXT','MTEXT','INSERT'),e['ref']))
        return [{k:e[k] for k in ('ref','type','source_sheet_ids','text','name','dimension_type','scaled_measurement','coordinate_frame') if k in e}
                for e in entities]

    def _brief(self,row,available):
        # A chunk is already a bounded exact fragment. Summarizing it again
        # loses its payload while advancing the cursor, so it must stay intact.
        if 'json_fragment' in row:return copy.deepcopy(row)
        if size(row)<=available:return copy.deepcopy(row)
        identity={k:row[k] for k in ('ref','table_ref','part_code','part_number','code','kind','source_hash','dimension_ref','index','assembly_id','row_group_id','sheet_id','label','view_id','identity_status','part_codes','candidate_part_codes','executable','source_view_id','target_view_id','status','proof') if k in row}
        identity['fields_deferred']={k:size(v) for k,v in row.items() if k not in identity}
        identity['retrieval']=('part_view_chunks(view_id,field) retrieves exact source view fields; then detail(ref) retrieves geometry. Reading correspondence never grants edit permission.' if 'view_id' in row else
                               'assembly_members(assembly_id) or assembly_chunks(assembly_id,field) retrieves exact group fields; BOM cells/geometry require source CAD refs.' if 'assembly_id' in row else
                               'row_frames/row_markers(row_group_id), or row_chunks(row_group_id,field) retrieves exact source row fields; then retrieve frame CAD before any edit.' if 'row_group_id' in row else
                               'detail(ref) retrieves a CAD record; chunks(ref,field) gives ordered JSON fragments. Other metadata pages expose the exact source rows when requested alone.')
        return identity

    def view(self):
        c=self.source
        result=dict(encoding='source_pages_v1',source_hash=c.get('source_hash'),units=c.get('units'),
            root_target_ids=c.get('root_target_ids',[]),full_parsed_entity_count=len(c['entities']),
            design_choices_source_hash=c.get('design_choices',{}).get('source_hash'),
            resource_counts=dict(targets=len(self.targets),entities=len(self.by),features=len(self.features),parts=len(self.graph.get('nodes',[])),
                                 assemblies=len(self.assemblies),assembly_members=sum(len(g['members']) for g in self.assemblies.values()),row_groups=len(self.row_groups),
                                 part_views=len(self.part_views),view_matches=len(self.part_map.get('correspondences',[]))),
            policy='Only page rows supplied in this turn have been inspected. All source CAD remains stored. Request metadata_requests for another page or exact detail/chunks. Counts and deferred fields are not geometry/ownership proof. No editing until exact evidence is supplied.',pages=[])
        from rules.mechanical_bom import PROFILE_ID
        result['reading_profile_id']=PROFILE_ID
        requests=self.requests or self.defaults
        allowance=max(256,(self.max_bytes-size(result)-600)//max(1,len(requests)))
        for request in requests:
            self.validate(request);rows=self._rows(request);selected=[];used=0
            for row in rows[request.offset:request.offset+request.limit]:
                if selected and used+size(row)>allowance:break
                item=self._brief(row,max(250,allowance-used-200))
                if used+size(item)>allowance and selected:break
                selected.append(item);used+=size(item)
            end=request.offset+len(selected)
            result['pages'].append(dict(request=request.model_dump(),match_count=len(rows),rows=selected,
                next_offset=end if end<len(rows) else None,page_complete=end>=len(rows)))
        if size(result)>self.max_bytes:
            # This is a view budget, never a source-data truncation. Reducing
            # page rows leaves a cursor so the planner can fetch them later.
            for page in reversed(result['pages']):
                while page['rows'] and size(result)>self.max_bytes:
                    page['rows'].pop();page['next_offset']=page['request']['offset']+len(page['rows']);page['page_complete']=False
        return result
