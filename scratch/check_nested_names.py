import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import ezdxf
from collections import Counter

dxf_path = Path("storage/documents/8565af68196b40a6acc853d9d9eead87/converted/original.dxf")
doc = ezdxf.readfile(dxf_path)

nested_block_names = Counter()
for b in doc.blocks:
    for e in b:
        if e.dxftype() == 'INSERT':
            nested_block_names[e.dxf.name] += 1

print("Top 15 nested block names:")
for name, cnt in nested_block_names.most_common(15):
    print(f"  {name}: {cnt}")
