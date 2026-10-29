"""Read typed native values, independently of optional formatted display text."""
from cad.edit_engine import chunks


def cell_value(lines,start,end):
    """Return source text and writable tag slots for one bounded ACVALUE.

    Code 302 is an optional formatted representation. Older tables leave it
    empty while storing the real string in code 1 or integer in code 91.
    Conflicting representations and unknown types are never editable.
    """
    stop=next((j for j in range(start,end,2) if lines[j].strip()==b'304'
               and lines[j+1].strip()==b'ACVALUE_END'),end)
    tags=[(j,int(lines[j]),lines[j+1].strip().decode('utf8')) for j in range(start,stop,2)]
    types=[v for _,c,v in tags if c==90]
    display=[(j,v) for j,c,v in tags if c==302]
    if len(display)!=1:return None,[],None
    shown=display[0][1]
    kind=types[0] if len(types)==1 else None
    field=1 if kind=='4' else 91 if kind=='1' else None
    values=[(j,v) for j,c,v in tags if c==field] if field else []
    if len(values)==1:
        value=values[0][1]
        if kind=='1':
            try:value=str(int(value))
            except ValueError:return None,[],None
        if shown and shown!=value:return shown,[],None
        return value,[values[0][0]]+([display[0][0]] if shown else []),kind
    if kind=='0' and not shown:return '',[],None
    return shown,[],None


from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=16)
def _table_cells(path_str, mtime_ns, size):
    path = Path(path_str)
    lines = path.read_bytes().splitlines(keepends=True)
    result = {}
    for handle, a, b in chunks(lines):
        if lines[a+1].strip() != b'ACAD_TABLE': continue
        starts = [j for j in range(a, b, 2) if lines[j].strip() == b'301' and lines[j+1].strip() == b'CELL_VALUE']
        cells = []
        for index, start in enumerate(starts):
            end = starts[index+1] if index+1 < len(starts) else b
            value, _, _ = cell_value(lines, start, end)
            if value is not None: cells.append({'index': index, 'raw_text': value})
        result[handle] = cells
    return result


def table_cells(path):
    source = Path(path).resolve()
    stat = source.stat()
    return _table_cells(str(source), stat.st_mtime_ns, stat.st_size)


table_cells.cache_clear = _table_cells.cache_clear
