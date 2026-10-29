"""Placed, circled row labels outside frames: source identity, never a fit rule."""
import hashlib
import math
import re
from collections import Counter
from ezdxf.math import Matrix44,Vec3
from cad.catalog import text_of
from bom.reader import normalized,plain

VERSION=3
LABEL=re.compile(r'(?:[A-Za-z]\d{0,4}|\d{1,4})')
NOTE=re.compile(r'\b(?:yckt|hdcv|han|lap|gan|cum|cong doan|cat|chan|uon|nham|kiem tra|assembly|weld|bend|cut|grind)\b')


def contains(box,point):
    return box[0]-1e-6<=point[0]<=box[2]+1e-6 and box[1]-1e-6<=point[1]<=box[3]+1e-6


def products(sheet):
    values={str(sheet['product_code']).strip()} if sheet.get('product_code') else set()
    values.update(t.split(':',1)[1].strip() for t in sheet.get('texts',[]) if ':' in t and
                  normalized(t.split(':',1)[0]) in ('ma tp','ma san pham','product code','product id') and t.split(':',1)[1].strip())
    return values


def identity_groups(rows):
    """Local frame callouts do not require a separate external row label."""
    return rows.get('groups',[])+rows.get('frame_groups',[])


def annotations(document):
    """Visit all placed INSERT levels; unused definitions are inventoried only."""
    texts=[];circles=[];leaders=[];types=Counter();warnings=[];placed=set();instances=0;hidden=0
    def visit(container,matrix,layout,prefix='',ancestry=(),visible=True):
        nonlocal instances,hidden
        for entity in container:
            kind=entity.dxftype();types[kind]+=1;ref=prefix+entity.dxf.handle
            layer=document.layers.get(entity.dxf.layer)
            shown=visible and not (entity.dxf.get('invisible',0) or layer.is_off() or layer.is_frozen())
            if not shown:hidden+=1
            if kind=='INSERT':
                instances+=1;name=entity.dxf.name;placed.add(name)
                if name in ancestry or len(ancestry)>=128:
                    warnings.append(dict(ref=ref,reason='recursive_or_excessive_block_depth'));continue
                block=document.blocks.get(name)
                if block is None:
                    warnings.append(dict(ref=ref,reason='missing_block'));continue
                # ATTRIB positions are in the INSERT's containing coordinate system.
                visit(entity.attribs,matrix,layout,ref+'/',ancestry,shown)
                visit(block,entity.matrix44()*matrix,layout,ref+'/',ancestry+(name,),shown)
            elif not shown:continue
            elif kind=='ACAD_PROXY_ENTITY':
                warnings.append(dict(ref=ref,reason='opaque_or_unsupported_annotation_payload'))
            elif kind=='MULTILEADER':
                context=entity.context;mtext=context.mtext
                if mtext is not None:
                    texts.append(dict(ref=ref,label=plain(mtext.default_content),layout=layout,source_type=kind,
                        anchor=list(matrix.transform(mtext.insert)),height=context.char_height*matrix.transform_direction(Vec3(0,1,0)).magnitude))
                elif context.block is not None:warnings.append(dict(ref=ref,reason='multileader_block_content_requires_binding'))
                for leader in context.leaders:
                    for line in leader.lines:
                        points=list(line.vertices)+[leader.last_leader_point]
                        if points:leaders.append(dict(ref=ref,layout=layout,points=[list(matrix.transform(v)) for v in (points[0],points[-1])]))
            elif kind in ('TEXT','MTEXT','ATTRIB'):
                value=text_of(entity)
                if not value:continue
                point=matrix.transform(entity.dxf.insert)
                height=entity.dxf.get('char_height',1) if kind=='MTEXT' else entity.dxf.get('height',1)
                scale=matrix.transform_direction(Vec3(0,1,0)).magnitude
                record=dict(ref=ref,label=plain(value),layout=layout,anchor=list(point),height=height*scale,source_type=kind)
                if LABEL.fullmatch(record['label']):
                    from ezdxf import bbox
                    bounds=bbox.extents([entity],fast=True)
                    if bounds.has_data:record['label_center']=list(matrix.transform((bounds.extmin+bounds.extmax)/2))
                texts.append(record)
            elif kind=='CIRCLE':
                axes=[matrix.transform_direction(Vec3(v)) for v in ((1,0,0),(0,1,0))]
                if list(entity.dxf.extrusion)!=[0,0,1] or abs(axes[0].magnitude-axes[1].magnitude)>1e-6 or abs(axes[0].dot(axes[1]))>1e-6:continue
                circles.append(dict(ref=ref,layout=layout,center=list(matrix.transform(entity.dxf.center)),radius=entity.dxf.radius*axes[0].magnitude))
            elif kind in ('LINE','LEADER'):
                points=[entity.dxf.start,entity.dxf.end] if kind=='LINE' else list(entity.vertices)
                if points:leaders.append(dict(ref=ref,layout=layout,points=[list(matrix.transform(v)) for v in (points[0],points[-1])]))
    for layout in document.layouts:visit(layout,Matrix44(),layout.name)
    definitions={b.name:len(b) for b in document.blocks}
    return texts,circles,leaders,dict(placed_entity_count=sum(types.values()),placed_entity_types=dict(types),
        layout_count=len(document.layouts),block_definition_count=len(definitions),definition_entity_count=sum(definitions.values()),
        placed_block_instance_count=instances,unplaced_definition_count=len(set(definitions)-placed),
        hidden_placed_entity_count=hidden,
        annotation_scan_complete=not warnings,warnings=warnings,coverage='all_layouts_and_placed_block_annotations',
        complete_design_understanding=False)


def build(texts,circles,sheets,regions=(),leaders=()):
    frames=[s for s in sheets if s.get('bbox') and s.get('read_status')!='layout_extent']
    def cancelled(layout,point):return any(r['layout']==layout and contains(r['bbox'],point) for r in regions)
    frames=[s for s in frames if not cancelled(s['layout'],[(s['bbox'][0]+s['bbox'][2])/2,(s['bbox'][1]+s['bbox'][3])/2,0])]
    markers=[];warnings=[]
    for text in texts:
        if not LABEL.fullmatch(text['label']) or cancelled(text['layout'],text['anchor']):continue
        choices=[c for c in circles if c['layout']==text['layout'] and c['radius']>0 and
                 text['height']<=1.5*c['radius'] and math.dist(c['center'],text.get('label_center',text['anchor']))<=.85*c['radius']]
        if len(choices)!=1:continue
        c=choices[0];point=c['center']
        parents=[s['id'] for s in frames if s['layout']==text['layout'] and contains(s['bbox'],point)]
        touching=[l for l in leaders if l['layout']==text['layout'] and any(abs(math.dist(p,point)-c['radius'])<=max(1e-5,.02*c['radius']) for p in l['points'])]
        markers.append(dict(label=text['label'].upper(),text_ref=text['ref'],circle_ref=c['ref'],layout=text['layout'],
                            center=point,radius=c['radius'],sheet_ids=parents,leader_refs=[l['ref'] for l in touching],
                            leader_endpoints=[p for l in touching for p in l['points'] if abs(math.dist(p,point)-c['radius'])>max(1e-5,.02*c['radius'])]))
    outside=[m for m in markers if not m['sheet_ids']];groups=[]
    for marker in outside:
        x,y,_=marker['center'];r=marker['radius'];layout=marker['layout']
        # Labels starting a second horizontal group bound the first group.
        stops=[m['center'][0]-m['radius'] for m in outside if m is not marker and m['layout']==layout and
               m['center'][0]>x and abs(m['center'][1]-y)<=max(r,m['radius'])]
        stop=min(stops) if stops else math.inf
        right=sorted((s for s in frames if s['layout']==layout and x+r<s['bbox'][0]<stop and s['bbox'][1]<=y<=s['bbox'][3]),key=lambda s:s['bbox'][0])
        chosen=[];product_codes=set()
        for s in right:
            box=s['bbox'];width=box[2]-box[0]
            current_products=products(s)
            if product_codes and current_products and not product_codes.intersection(current_products):break
            gap=box[0]-(chosen[-1]['bbox'][2] if chosen else x+r)
            previous=chosen[-1]['bbox'][2]-chosen[-1]['bbox'][0] if chosen else width
            if gap>2*max(width,previous):break
            if chosen and box[0]<chosen[-1]['bbox'][2]-1e-6:
                warnings.append(dict(label_ref=marker['text_ref'],reason='overlapping_row_frames',sheet_ids=[chosen[-1]['id'],s['id']]))
                chosen=[];break
            chosen.append(s);product_codes.update(current_products)
        if not chosen:continue
        key=layout+'|'+marker['text_ref']+'|'+marker['circle_ref']
        group=dict(id='row-'+hashlib.sha256(key.encode()).hexdigest()[:20],label=marker['label'],
            kind='assembly_row' if marker['label'][0].isalpha() else 'part_row',layout=layout,
            label_ref=marker['text_ref'],circle_ref=marker['circle_ref'],center=marker['center'],
            product_codes=sorted(product_codes),
            sheet_ids=[s['id'] for s in chosen],evidence_refs=[marker['text_ref'],marker['circle_ref']],
            frames=[dict(sheet_id=s['id'],name=s.get('name',''),bbox=s['bbox'],
                         source_texts=list(dict.fromkeys(s.get('texts',[])+[t['label'] for t in texts if t['layout']==layout and contains(s['bbox'],t['anchor'])])),
                         notes=list(dict.fromkeys([t for t in s.get('texts',[]) if NOTE.search(normalized(t))]+[t['label'] for t in texts if t['layout']==layout and contains(s['bbox'],t['anchor']) and NOTE.search(normalized(t['label']))])),
                         source_note_refs=[t['ref'] for t in texts if t['layout']==layout and contains(s['bbox'],t['anchor']) and NOTE.search(normalized(t['label']))]) for s in chosen],
            markers=[m for m in markers if set(m['sheet_ids']).intersection(s['id'] for s in chosen)],
            status='source_row_group',executable=False,
            policy='Circled label and row identify source views; compare BOM/codes/notes before geometry ownership or contact rules.')
        groups.append(group)
    # A frame reached from two different labels cannot be silently assigned.
    for g in groups:
        conflicts={h['id'] for h in groups if h is not g and set(g['sheet_ids']).intersection(h['sheet_ids'])}
        if conflicts:g.update(status='ambiguous_row_group',conflicting_group_ids=sorted(conflicts))
    # Many production DWGs only label parts inside their own assembly frame;
    # requiring an external C1/16 row discarded all of those valid callouts.
    # Keep these scopes separate from horizontal row/group observations.
    covered={sid for g in groups for sid in g['sheet_ids']};frame_groups=[]
    for sheet in frames:
        sid=sheet['id']
        if sid in covered:continue
        local=[m for m in markers if m['sheet_ids']==[sid] and m['leader_refs']]
        if not local:continue
        source_texts=list(dict.fromkeys(sheet.get('texts',[])+[t['label'] for t in texts if t['layout']==sheet['layout'] and contains(sheet['bbox'],t['anchor'])]))
        notes=[t for t in source_texts if NOTE.search(normalized(t))]
        frame_groups.append(dict(id='frame-'+hashlib.sha256((sheet['layout']+'|'+sid).encode()).hexdigest()[:20],
            label=sheet.get('name') or '#'+sid,kind='drawing_frame',layout=sheet['layout'],label_ref=None,circle_ref=None,
            center=[(sheet['bbox'][0]+sheet['bbox'][2])/2,(sheet['bbox'][1]+sheet['bbox'][3])/2,0],
            product_codes=sorted(products(sheet)),sheet_ids=[sid],evidence_refs=sorted({r for m in local for r in [m['text_ref'],m['circle_ref']]}),
            frames=[dict(sheet_id=sid,name=sheet.get('name',''),bbox=sheet['bbox'],source_texts=source_texts,notes=notes,
                source_note_refs=[t['ref'] for t in texts if t['layout']==sheet['layout'] and contains(sheet['bbox'],t['anchor']) and NOTE.search(normalized(t['label']))])],
            markers=local,status='source_row_group',executable=False,
            policy='Frame-local circled STT and native leader; identity requires this frame BOM. No external row, global STT or mechanical fit is inferred.'))
    return dict(version=VERSION,groups=groups,frame_groups=frame_groups,marker_count=len(markers),warnings=warnings)


def document_rows(document,sheets,regions=()):
    texts,circles,leaders,scan=annotations(document)
    result=build(texts,circles,sheets,regions,leaders);result['scan']=scan
    return result
