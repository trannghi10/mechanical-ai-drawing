"""Read placed CAD across every layout, independently of selected edit scopes.

Coordinates stay in their native frame. A complete traversal is an inventory,
not proof that assembly contacts, design intent, or edit adapters are complete.
"""
from collections import Counter
from ezdxf.math import Matrix44, Vec2, Vec3
from cad.entities import extract_entities
from cad.geometry import snapshot
from cad.part_identity import entity_identity

VERSION = 2
EXACT = {'LINE', 'LWPOLYLINE', 'POLYLINE', 'CIRCLE', 'ARC', 'ELLIPSE', 'SPLINE', 'DIMENSION', 'LEADER'}


def native_attributes(entity):
    """Lossless reading attributes, including dimensions without edit recipes."""
    def plain(value):
        if isinstance(value, (Vec2, Vec3)): return list(value)
        if isinstance(value, (tuple, list)): return [plain(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)): return value
        raise TypeError('Thuộc tính CAD chưa có bộ đọc: '+type(value).__name__)
    return {key: plain(value) for key, value in entity.dxf.all_existing_dxf_attribs().items()}


def scan(doc, emit, *, codes=(), progress=None, max_records=250000, max_depth=128):
    """Stream all placed instance paths; report every traversal limitation.

    DIM/table render blocks are marked annotation graphics, so their lines and
    text cannot be mistaken for additional mechanical components.
    """
    counts = Counter(); metadata = Counter(); failures = Counter(); gaps = []
    layouts = []; used = set(); total = 0; gap_count = 0

    def gap(ref, reason, **details):
        nonlocal gap_count
        gap_count += 1
        if len(gaps) < 100: gaps.append(dict(ref=ref, reason=reason, **details))

    def visit(entity, ref, frame, layout_name, trail=(), role='drawing', owner=None):
        nonlocal total
        if total >= max_records:
            gap(ref, 'record_budget'); return
        total += 1; kind = entity.dxftype(); counts[kind] += 1
        detail = extract_entities([entity])[0]
        record = dict(ref=ref, handle=entity.dxf.handle, type=kind, layout=layout_name,
                      role=role, frame_to_layout=[list(frame.get_row(i)) for i in range(4)],
                      facts=detail, edit_authorized=False)
        if owner: record['container_part_code'] = owner
        if kind in EXACT:
            try: record['geometry'] = snapshot(entity)
            except (ValueError, TypeError, AttributeError, NotImplementedError) as error:
                if kind in ('DIMENSION', 'POLYLINE'):
                    try:
                        record['geometry'] = dict(read_only_native_attributes=native_attributes(entity))
                        if kind == 'POLYLINE': record['geometry']['vertices'] = [native_attributes(v) for v in entity.vertices]
                    except (TypeError, AttributeError) as read_error: record['geometry_error'] = str(read_error)
                else: record['geometry_error'] = str(error)
        if kind == 'INSERT':
            identity = entity_identity(entity, codes)
            if identity:
                owner = identity
                record['native_part_code'] = identity
            if entity.mcount > 1:
                gap(ref, 'multiple_insert_array', instance_count=entity.mcount)
        # An extraction failure or metadata-only record remains visible in the
        # report; never relabel it as fully understood because it was visited.
        if detail.get('parse_error') or record.get('geometry_error'):
            record['read_status'] = 'partial'; failures[kind] += 1
        elif detail.get('data_status') == 'metadata_only':
            record['read_status'] = 'metadata_only'; metadata[kind] += 1
        else: record['read_status'] = 'read'
        emit(record)
        if progress and total % 500 == 0: progress(total, layout_name)
        name = (entity.dxf.name if kind == 'INSERT' else
                entity.dxf.get('geometry', '') if kind in ('ACAD_TABLE', 'DIMENSION', 'ARC_DIMENSION') else '')
        if name:
            used.add(name)
            block = doc.blocks.get(name)
            if block is None: gap(ref, 'missing_block', block=name)
            elif name in trail: gap(ref, 'recursive_block', block=name)
            elif len(trail) >= max_depth: gap(ref, 'depth_budget', block=name)
            elif block.block.dxf.get('flags', 0) & (4 | 8):
                gap(ref, 'external_reference', block=name)
            else:
                try: child_frame = entity.matrix44() * frame if kind == 'INSERT' else frame
                except (ValueError, TypeError, ZeroDivisionError) as error:
                    gap(ref, 'invalid_transform', message=str(error)); child_frame = None
                if child_frame is not None:
                    child_role = role if kind == 'INSERT' else 'annotation_graphics'
                    for child in block:
                        visit(child, ref+'/'+child.dxf.handle, child_frame, layout_name,
                              trail+(name,), child_role, owner)
        if kind == 'INSERT':
            # ATTRIB locations already live in the INSERT's parent coordinates.
            for attribute in entity.attribs:
                visit(attribute, ref+'/'+attribute.dxf.handle, frame, layout_name, trail, role, owner)

    for layout in doc.layouts:
        before = total; types = dict(Counter(e.dxftype() for e in layout))
        for entity in layout: visit(entity, entity.dxf.handle, Matrix44(), layout.name)
        layouts.append(dict(name=layout.name, root_count=len(layout), root_types=types, visited_count=total-before))
        if progress: progress(total, layout.name)
    layout_blocks = {layout.block_record_handle for layout in doc.layouts}
    definitions = [dict(name=b.name, entity_count=len(b), placed=b.name in used,
                        flags=b.block.dxf.get('flags', 0)) for b in doc.blocks
                   if b.block_record_handle not in layout_blocks]
    return dict(version=VERSION, units=doc.units, layouts=layouts, definitions=definitions,
                placed_record_count=total, entity_types=dict(counts),
                traversal_complete=gap_count == 0, gap_count=gap_count, gaps=gaps,
                gaps_omitted=max(0, gap_count-len(gaps)), metadata_only_types=dict(metadata),
                partial_types=dict(failures), all_placed_data_read=not (gap_count or metadata or failures),
                limits=dict(max_records=max_records, max_depth=max_depth),
                unused_definition_count=sum(not d['placed'] for d in definitions),
                complete_design_understanding=False, edit_authorized=False)


def parts_directory(graph, sheets):
    """Keep BOM membership distinct from geometry ownership and contact proof."""
    available = {s['id']: s for s in sheets}
    parts = []
    for node in graph.get('nodes', []):
        occurrences = node.get('bom_occurrences', [])
        ids = set(node.get('detail_sheets', []))
        ids.update(s for o in occurrences for s in o.get('sheet_ids', []))
        ids.update(s for i in node.get('native_instances', []) for s in i.get('sheet_ids', []))
        parts.append(dict(part_code=node['code'], definition_conflict=node.get('definition_conflict', False),
                          descriptions=sorted({o['description'] for o in occurrences if o.get('description')}),
                          materials=sorted({o['material'] for o in occurrences if o.get('material')}),
                          bom_occurrences=occurrences, native_instances=node.get('native_instances', []),
                          detail_sheet_ids=node.get('detail_sheets', []),
                          frames=[dict(id=sid, name=available[sid].get('name', ''), layout=available[sid]['layout'],
                                       bbox=available[sid].get('bbox'), kind='sheet') for sid in sorted(ids) if sid in available],
                          unavailable_sheet_ids=sorted(ids-available.keys()),
                          geometry_ownership=node.get('geometry_ownership', 'unverified'), edit_authorized=False))
    return sorted(parts, key=lambda p: p['part_code'])
