import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import ezdxf
from collections import Counter

dxf_path = Path("storage/documents/8565af68196b40a6acc853d9d9eead87/converted/original.dxf")
doc = ezdxf.readfile(dxf_path)

top_inserts = [e for space in doc.layouts for e in space if e.dxftype() == 'INSERT']
print(f"Top-level INSERTs in layouts: {len(top_inserts)}")

nested_inserts = 0
for b in doc.blocks:
    for e in b:
        if e.dxftype() == 'INSERT':
            nested_inserts += 1

print(f"Nested INSERTs inside doc.blocks: {nested_inserts}")
