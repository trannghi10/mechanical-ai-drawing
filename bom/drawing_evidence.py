"""Expose source-backed BOM/code/balloon evidence, without guessing part geometry."""
import math
import re
from bom.reader import plain


def drawing_evidence(entities):
    cell_refs={cell.get('mirror_ref') for entity in entities for row in entity.get('bom',{}).get('rows',[]) for cell in row.get('cells',{}).values()}
    rows = [(entity['ref'], row) for entity in entities
            if entity.get('bom', {}).get('status') == 'verified_template'
            for row in entity['bom']['rows']]
    texts = [entity for entity in entities if entity.get('text')]
    circles = [entity for entity in entities if entity['type'] == 'CIRCLE' and entity.get('geometry')]
    leaders = [entity for entity in entities if entity.get('leader_vertices')
               or entity['type'] == 'LINE' and entity.get('geometry')]
    tables={e['ref']:e for e in entities if e.get('bom',{}).get('status')=='verified_template'}
    def score(table,entity):
        if table.get('layout') and entity.get('layout') and table['layout']!=entity['layout']:return None
        a=set(table.get('source_sheet_ids',[]));b=set(entity.get('source_sheet_ids',[]))
        if a and b and not a.intersection(b):return None
        left=table.get('coordinate_frame','');right=entity.get('coordinate_frame','')
        common=0;depth=len(left[9:].split('/')) if left.startswith('instance:') else 0
        if left.startswith('instance:') and right.startswith('instance:'):
            for x,y in zip(left[9:].split('/'),right[9:].split('/')):
                if x!=y:break
                common+=1
            if not common and not (a and b):return None
        return common,common-depth
    # A number may repeat in every assembly. Assign it only to one local BOM,
    # using scope and placed instance ancestry, never a document-wide STT map.
    marker_tables={};unresolved=[]
    for text in texts:
        if text['ref'] in cell_refs:continue
        number=plain(text['text']);choices=[]
        for ref,table in tables.items():
            if text['ref'].startswith(ref+'/'):continue
            if not any(plain(r['part_number'])==number for r in table['bom']['rows']):continue
            rank=score(table,text)
            if rank is not None:choices.append((rank,ref))
        if not choices:continue
        best=max(rank for rank,_ in choices);refs=[ref for rank,ref in choices if rank==best]
        if len(refs)==1 and sum(plain(r['part_number'])==number for r in tables[refs[0]]['bom']['rows'])==1:marker_tables[text['ref']]=refs[0]
        else:unresolved.append(dict(number_text_ref=text['ref'],part_number=number,table_refs=sorted(refs),status='ambiguous_local_bom'))
    links = []
    for table_ref, row in rows:
        code = row['part_code'].strip()
        pattern = re.compile(r'(?<![\w.])' + re.escape(code) + r'(?![\w.])')
        code_refs = [entity['ref'] for entity in texts
                     if not entity['ref'].startswith(table_ref + '/')
                     and entity['ref'] not in cell_refs
                     and pattern.search(plain(entity['text']))]
        markers = []
        for text in texts:
            if plain(text['text']) != row['part_number'] or not text.get('text_placement'):
                continue
            if marker_tables.get(text['ref'])!=table_ref:continue
            if text['ref'].startswith(table_ref + '/') or text['ref'] in cell_refs:
                continue
            anchor = text['text_placement']['anchor']
            for circle in circles:
                if circle.get('coordinate_frame') != text.get('coordinate_frame'):
                    continue
                if score(tables[table_ref],circle) is None:continue
                if circle.get('layout')!=text.get('layout'):continue
                geometry = circle['geometry']; center = geometry['center']; radius = geometry['radius']
                if geometry['extrusion'] != [0, 0, 1] or radius <= 0:
                    continue
                if math.dist(anchor, center) > radius * .85:
                    continue
                if text['text_placement']['height'] > radius * 1.5:
                    continue
                leader_refs = []
                for leader in leaders:
                    if leader.get('coordinate_frame') != circle.get('coordinate_frame'):
                        continue
                    if score(tables[table_ref],leader) is None or leader.get('layout')!=circle.get('layout'):continue
                    points = leader.get('leader_vertices')
                    if points is None:
                        points = [leader['geometry']['start'], leader['geometry']['end']]
                    if points and any(abs(math.dist(point, center)-radius) <= max(1e-5, radius*.02)
                                      for point in (points[0], points[-1])):
                        leader_refs.append(leader['ref'])
                markers.append({'number_text_ref': text['ref'], 'circle_ref': circle['ref'],
                                'leader_refs': leader_refs, 'status': 'number_marker_candidate'})
        links.append({'table_ref': table_ref, 'part_number': row['part_number'], 'part_code': code,
                      'scope_ids':tables[table_ref].get('source_sheet_ids',[]),
                      'code_evidence_refs': code_refs, 'number_markers': markers,
                      'status': 'source_evidence_only'})
    return {'bom_links': links,'unresolved_number_markers':unresolved,
            'instruction': 'Code text and number markers are evidence candidates, not verified geometry ownership. '
                           'Trace leader endpoints and compare drawing images before assigning part geometry. '
                           'Do not treat revision numbers, nearby geometry or matching sizes as a proven assembly link.'}
