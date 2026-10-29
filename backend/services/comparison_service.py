"""Material review and CAD differences bound to the immutable revision hashes."""
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from ezdxf import bbox
from cad.catalog import load_document
from cad.edit_engine import digest
from cad.sheets import render_sheet, inside
from cad.svg_comparison import overlay
from cad.renderer_patch import RENDER_VERSION
from cad.table_data import table_cells
from backend.services import catalog_service as storage
from backend.services.revision_service import read_revision, safe_id


def plain(value):
    return re.sub(r'\s+', ' ', re.sub(r'\\[A-Za-z][^;]*;', '', str(value).replace('\\P', ' ')).replace('{', '').replace('}', '')).strip()


def natural(value):
    return tuple((0, int(p)) if p.isdigit() else (1, p.casefold()) for p in re.split(r'(\d+)', str(value)))


def applied_material_plan(proposal,revision):
    """A partial revision uses its executable snapshot, not the blocked full plan."""
    if proposal['plan'].get('operations'):return proposal
    preview=proposal.get('checked_preview_plan')
    if not preview or revision.get('complete_product_backup') is not False:return proposal
    if proposal.get('source_hash')!=revision['validation'].get('source_hash'):
        raise ValueError('Kế hoạch xem trước thuộc nguồn CAD khác.')
    return dict(proposal,plan=preview)


def revision_inputs(document_id, revision_id):
    path, revision = read_revision(document_id, revision_id)
    base = storage.folder(document_id)
    proposal = json.loads((base / 'change-plans' / (safe_id(revision['plan_id']) + '.json')).read_text(encoding='utf8'))
    source = base / storage.read_status(document_id)['dxf']
    modified = path / 'modified.dxf'
    if digest(source) != revision['validation']['source_hash'] or digest(modified) != revision['validation']['output_hash']:
        raise ValueError('CAD đã thay đổi sau validation; cần tạo lại bản sửa để đối chiếu')
    return path, revision, proposal, source, modified


def material_rows(proposal, root_id, cells, text_values=None):
    edits = proposal['plan']['edits']
    ops = proposal['plan']['operations']
    rows = []
    for node in proposal.get('impact_graph', {}).get('nodes', []):
        occurrences = [o for o in node['bom_occurrences'] if root_id in o.get('sheet_ids', [])]
        # A selected detail sheet may not have its own BOM.
        if not occurrences and root_id in node.get('detail_sheets', []):
            occurrences = node['bom_occurrences'][:1]
        seen = set()
        for occurrence in occurrences:
            number = str(occurrence['part_number'])
            if number in seen:
                continue
            seen.add(number)
            graphic=occurrence.get('source_kind')=='graphic_grid'
            cell=occurrence.get('description_cell',{})
            matches = [e for e in edits if e['purpose'] == 'bom' and str(e['part_number']) in (number,node['code'])
                       and (e['entity_ref']==cell.get('mirror_ref') if graphic else e['entity_ref'].split('/')[0] == occurrence['table_ref'])]
            values = {(plain(e['before']), plain(e['after'])) for e in matches}
            if len(values) > 1:
                raise ValueError(f'Chi tiết {number} có nhiều quy cách đề xuất khác nhau')
            before, after = next(iter(values), (occurrence['description'], occurrence['description']))
            bound = [op for op in ops if (op['action']=='replace_text' and op['ref']==cell.get('mirror_ref') if graphic
                     else op['action'] == 'table_cell' and op['ref'] == occurrence['table_ref'])
                     and plain(op['after']) == after] if before != after else []
            if before != after and not bound:
                raise ValueError(f'Chưa có ô bảng kê native đã sửa cho chi tiết {number}')
            for op in bound:
                actual = (text_values or {}).get(op['ref']) if graphic else next((c['raw_text'] for c in cells.get(op['ref'], []) if c['index'] == op['cell_index']), None)
                if actual is None or plain(actual) != after:
                    raise ValueError(f'Bảng kê CAD của chi tiết {number} chưa khớp bản sửa')
            rows.append(dict(part_number=number, code=node['code'], before=before, after=after,
                             changed=before != after, material=occurrence.get('material', ''),
                             detail_ids=node.get('detail_sheets', [])))
    return sorted(rows, key=lambda r: (natural(r['part_number']), natural(r['code'])))


def focus_region(proposal, revision, source, row):
    """Use a changed native dimension or rounded section, never guessed block ownership."""
    doc = load_document(str(source))
    refs = {e['entity_ref'] for e in proposal['plan']['edits']
            if e['purpose'] == 'geometry' and str(e['part_number']) in (row['part_number'],row.get('code'))}
    targets = {s['id']: s for s in revision['targets'] if s['kind'] == 'sheet'}
    for detail_id in row['detail_ids']:
        sheet = targets.get(detail_id)
        if sheet is None:
            continue
        # A changed R2 annotation has a smaller picture than the whole part.
        # Focus the audited source contour, not the smallest native DIM arrow.
        recipes=[r for key in ('resize_recipes','hole_recipes','curved_wall_recipes') for r in proposal['plan'].get(key,[])
                 if r.get('part_code')==row.get('code') and r.get('outline_refs')]
        shapes=[];extra=0.
        from ezdxf.math import Matrix44
        from cad.nested_scope_export import path_entity
        for recipe in recipes:
            group=[]
            try:
                for ref in recipe['outline_refs']:
                    parts=ref.split('/');matrix=Matrix44()
                    for i in range(1,len(parts)):
                        parent=path_entity(doc,'/'.join(parts[:i]));matrix=parent.matrix44()*matrix
                    entity=path_entity(doc,ref)
                    if entity.dxftype() not in ('LINE','ARC','CIRCLE','LWPOLYLINE','POLYLINE','ELLIPSE','SPLINE'):raise ValueError('Unsupported focus contour')
                    copy=entity.copy();copy.transform(matrix);group.append(copy)
                bound=bbox.extents(group,fast=True)
                if not bound.has_data or not inside(bound.center,sheet['bbox']):continue
                shapes.extend(group)
                dim=doc.entitydb.get(recipe.get('dimension_ref','').split('/')[-1])
                if dim is not None and recipe.get('new_measurement') is not None:
                    extra=max(extra,abs(recipe['new_measurement']-dim.get_measurement())/max(1e-8,abs(dim.override().get('dimlfac',1))))
            except (ValueError,KeyError,AttributeError,TypeError):continue
        if shapes:
            bounds=bbox.extents(shapes,fast=True);pad=max(3.,max(bounds.size.x,bounds.size.y)*.18,extra+3.)
            return sheet,[bounds.extmin.x-pad,bounds.extmin.y-pad,bounds.extmax.x+pad,bounds.extmax.y+pad]
        entities = []
        for ref in refs:
            entity = doc.entitydb.get(ref) if '/' not in ref else None
            if entity is None or entity.get_layout() != doc.layouts.get(sheet['layout']):
                continue
            bounds = bbox.extents([entity], fast=True)
            if bounds.has_data and inside(bounds.center, sheet['bbox']):
                entities.append(entity)
        arcs = [e for e in entities if e.dxftype() == 'ARC']
        dimensions = [e for e in entities if e.dxftype() == 'DIMENSION']
        chosen = arcs
        if not chosen and dimensions:
            chosen = [min(dimensions, key=lambda e: abs(e.get_measurement()))]
        if not chosen and entities:
            chosen = [min(entities, key=lambda e: bbox.extents([e], fast=True).size.magnitude)]
        if not chosen:
            continue
        bounds = bbox.extents(chosen, fast=True)
        w, h = bounds.size.x, bounds.size.y
        pad = max(3., min(max(w, h) * .18, 12.))
        box = [bounds.extmin.x-pad, bounds.extmin.y-pad, bounds.extmax.x+pad, bounds.extmax.y+pad]
        return sheet, box
    return None, None


@lru_cache(maxsize=8)
def cached_materials(plan_path, modified_path, output_hash, graph_path, graph_hash, root_id):
    proposal = json.loads(Path(plan_path).read_text(encoding='utf8'))
    proposal['impact_graph'] = json.loads(Path(graph_path).read_text(encoding='utf8'))
    revision=json.loads((Path(modified_path).parent/'revision.json').read_text(encoding='utf8'))
    proposal=applied_material_plan(proposal,revision)
    remap={ref:change['ref'] for change in revision['validation']['changes']
           for ref in change.get('original_refs',[change.get('original_ref',change['ref'])])}
    from cad.catalog import text_of
    doc=load_document(modified_path);texts={}
    for op in proposal['plan']['operations']:
        if op['action']!='replace_text':continue
        entity=doc.entitydb.get(remap.get(op['ref'],op['ref']).split('/')[-1])
        if entity is not None:texts[op['ref']]=entity.text if entity.dxftype()=='MTEXT' else text_of(entity)
    return material_rows(proposal, root_id, table_cells(Path(modified_path)),texts)


def material_review(document_id, revision_id, root_id=None):
    path, revision, proposal, source, modified = revision_inputs(document_id, revision_id)
    root_id = root_id or revision['root_target_ids'][0]
    if root_id not in {t['id'] for t in revision['targets']}:
        raise ValueError('Bản vẽ không thuộc bản sửa đã chọn')
    from backend.services.part_graph_service import document_graph
    document_graph(document_id)
    graph_path = path.parent.parent / 'part-graph-v1.json'
    rows = cached_materials(str(path.parent.parent / 'change-plans' / (revision['plan_id'] + '.json')),
                            str(modified), revision['validation']['output_hash'], str(graph_path), digest(graph_path), root_id)
    return {'root_id': root_id, 'rows': rows, 'changed_count': sum(r['changed'] for r in rows)}


def comparison_preview(document_id, revision_id, sheet_id, part_number=None, mode='overlay', part_code=None):
    if mode not in ('overlay', 'before', 'after'):
        raise ValueError('Chế độ đối chiếu không hợp lệ')
    path, revision, proposal, source, modified = revision_inputs(document_id, revision_id)
    sheet = next((t for t in revision['targets'] if t['id'] == sheet_id and t['kind'] == 'sheet'), None)
    if sheet is None:
        raise ValueError('Khung không thuộc bản sửa đã chọn')
    box = None
    key = digest(source)[:16] + '-' + revision['validation']['output_hash'][:16]
    suffix = re.sub(r'[^A-Za-z0-9_-]', '_', part_number or 'full')
    cache = path / f'compare-v{RENDER_VERSION}-focus2-{key}-{sheet_id}-{suffix}-{mode}.svg'
    if part_number is not None:
        rows = material_review(document_id, revision_id, sheet_id)['rows']
        candidates = [r for r in rows if r['part_number'] == part_number and r['changed']]
        matches = [r for r in candidates if part_code is None or r['code'] == part_code]
        if not matches:
            raise ValueError('Chi tiết không có thay đổi trong bảng kê đang chọn')
        if len(matches) != 1:
            raise ValueError('STT thuộc nhiều mã vật tư; cần chọn đúng mã chi tiết để đối chiếu')
        row = matches[0]
        if len(candidates) > 1:
            suffix += '-' + re.sub(r'[^A-Za-z0-9_-]', '_', row['code'])
            cache = path / f'compare-v{RENDER_VERSION}-focus2-{key}-{sheet_id}-{suffix}-{mode}.svg'
        if cache.exists():
            return cache.read_text(encoding='utf8')
        sheet, box = focus_region(proposal, revision, source, row)
        if sheet is None:
            raise ValueError('Chưa có vùng hình học đã xác định cho chi tiết này')
    # Cache visualization only. It cannot approve a revision or mark an entire sheet reviewed.
    if cache.exists():
        return cache.read_text(encoding='utf8')
    before = render_sheet(source, sheet, render_box=box, include_annotations=box is None)
    after = render_sheet(modified, sheet, render_box=box, include_annotations=box is None)
    marked, _ = overlay(before, after)
    for name, content in [('before', before), ('after', after), ('overlay', marked)]:
        target = path / f'compare-v{RENDER_VERSION}-focus2-{key}-{sheet_id}-{suffix}-{name}.svg'
        temporary = target.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        temporary.write_text(content, encoding='utf8')
        temporary.replace(target)
    return {'before': before, 'after': after, 'overlay': marked}[mode]
