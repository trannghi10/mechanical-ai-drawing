import sys
sys.path.insert(0, '.')
from pathlib import Path
from cad.sheets import render_sheet, discover_sheets
from cad.svg_comparison import overlay

source = 'storage/documents/5a1955b75d4345b69d19d38b7cfaf75c/converted/original.dxf'
modified = 'scratch/test_revision_apply.dxf'
sheets = discover_sheets(source)

for sid in ['3E4E7A', '404033']:
    s = next(x for x in sheets if x['id'] == sid)
    b = render_sheet(source, s)
    a = render_sheet(modified, s)
    marked, stats = overlay(b, a)
    print(f"Sheet {sid}: removed={stats['old_paths']} added={stats['new_paths']}")
    Path(f'scratch/overlay_{sid}.svg').write_text(marked, encoding='utf8')
