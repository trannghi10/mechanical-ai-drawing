import json
from pathlib import Path
import ezdxf
from ezdxf import bbox

doc_id = '8565af68196b40a6acc853d9d9eead87'
folder = Path(f'storage/documents/{doc_id}')
sheets = json.loads((folder / 'sheets-v3.json').read_text(encoding='utf-8'))['items']
f5a0 = next((s for s in sheets if s['id'] == 'F5A0'), None)
import sys
sys.stdout.reconfigure(encoding='utf-8')
print('F5A0 sheet info:', f5a0['name'].encode('ascii', errors='replace').decode(), f5a0['bbox'])

doc = ezdxf.readfile(str(folder / 'converted' / 'original.dxf'))
msp = doc.modelspace()
xmin, ymin, xmax, ymax = f5a0['bbox']

in_frame = []
for e in msp:
    try:
        b = bbox.extents([e], fast=True)
        if b.has_data:
            c = ((b.extmin.x + b.extmax.x)/2, (b.extmin.y + b.extmax.y)/2)
            if xmin <= c[0] <= xmax and ymin <= c[1] <= ymax:
                in_frame.append(e)
    except Exception:
        pass

print(f'Total entities in frame F5A0: {len(in_frame)}')
types = {}
for e in in_frame:
    t = e.dxftype()
    types[t] = types.get(t, 0) + 1
print('Types in frame F5A0:', types)

inserts = [e for e in in_frame if e.dxftype() == 'INSERT']
print(f'Inserts in F5A0 count: {len(inserts)}')
insert_names = set(e.dxf.name for e in inserts)
print(f'Insert block names ({len(insert_names)}): {list(insert_names)[:10]}')

dims = [e for e in in_frame if e.dxftype() == 'DIMENSION']
print(f'Dims in F5A0 count: {len(dims)}')
for d in dims[:10]:
    t = d.dxf.get('text', '')
    m = d.dxf.get('actual_measurement', 0)
    print(f'  DIM #{d.dxf.handle}: text={t}, actual={m}')
