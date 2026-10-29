"""Lossless column encoding for large CAD inventories sent to the planner."""
from collections import defaultdict
from collections import Counter


SYMBOL_FIELDS = ('type', 'layout', 'layer', 'coordinate_frame', 'text', 'raw_text', 'name')


def pack_context(context):
    result = {k: v for k, v in context.items() if k != 'entities'}
    symbols = {field: [] for field in SYMBOL_FIELDS}
    groups = defaultdict(list)
    for entity in context['entities']:
        flat = dict(entity)
        summary = flat.pop('geometry_summary', None)
        if summary is not None:
            flat.update({'geometry_summary.' + key: value for key, value in summary.items()})
        for field in SYMBOL_FIELDS:
            if field in flat:
                values = symbols[field]
                if flat[field] not in values:
                    values.append(flat[field])
                flat[field] = values.index(flat[field])
        columns = tuple(sorted(flat))
        groups[columns].append([flat[column] for column in columns])
    result['entity_encoding'] = 'columns_v1'
    result['symbols'] = symbols
    result['entity_tables'] = [{'columns': list(columns), 'rows': rows} for columns, rows in groups.items()]
    result['entity_count'] = len(context['entities'])
    if context.get('focused_scope_ids'):
        fields=('part_graph','geometry_discovery','targets')
        counts=Counter()
        def visit(v):
            if isinstance(v,str):counts[v]+=1
            elif isinstance(v,list):
                for x in v:visit(x)
            elif isinstance(v,dict):
                for x in v.values():visit(x)
        for field in fields:visit(result.get(field))
        atoms=[s for s,n in counts.items() if len(s)>=6 and n>1 or s.startswith('~')]
        lookup={s:i for i,s in enumerate(atoms)}
        def encode(v):
            if isinstance(v,str):return '~'+str(lookup[v]) if v in lookup else v
            if isinstance(v,list):return [encode(x) for x in v]
            if isinstance(v,dict):return {k:encode(x) for k,x in v.items()}
            return v
        for field in fields:
            if field in result:result[field]=encode(result[field])
        result['metadata_string_dictionary']=atoms
        result['metadata_string_fields']=[field for field in fields if field in result]
        result['metadata_string_encoding']='In metadata_string_fields ONLY, a string ~N means metadata_string_dictionary[N]. Decode recursively before using any part code, source ref, label or relationship. Dictionary entries are literal and are never decoded. Entity tables/bindings retain literal source refs.'
    return result


def unpack_metadata(context):
    """Exact verification/retrieval decoder; never mutates the source view."""
    atoms=context.get('metadata_string_dictionary',[])
    def decode(v):
        if isinstance(v,str) and v.startswith('~'):return atoms[int(v[1:])]
        if isinstance(v,list):return [decode(x) for x in v]
        if isinstance(v,dict):return {k:decode(x) for k,x in v.items()}
        return v
    return {field:decode(context[field]) for field in context.get('metadata_string_fields',[])}


def unpack_entities(context):
    """Verification helper: preserve every entity and every supplied value."""
    entities = []
    for table in context['entity_tables']:
        for row in table['rows']:
            record = dict(zip(table['columns'], row))
            for field in SYMBOL_FIELDS:
                if field in record:
                    record[field] = context['symbols'][field][record[field]]
            summary = {}
            for field in list(record):
                if field.startswith('geometry_summary.'):
                    summary[field.split('.', 1)[1]] = record.pop(field)
            if summary:
                record['geometry_summary'] = summary
            entities.append(record)
    return entities
