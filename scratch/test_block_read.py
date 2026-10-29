import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import ezdxf

dxf_path = Path("storage/documents/8565af68196b40a6acc853d9d9eead87/converted/original.dxf")
if not dxf_path.exists():
    print(f"DXF not found at {dxf_path}")
    sys.exit(1)

doc = ezdxf.readfile(dxf_path)
print(f"Total blocks in doc: {len(doc.blocks)}")
user_blocks = [b.name for b in doc.blocks if not b.name.startswith('*')]
print(f"User blocks ({len(user_blocks)}): {user_blocks[:10]}")

# Check what happens when inspecting a block definition
for b_name in user_blocks[:5]:
    b = doc.blocks.get(b_name)
    rec_handle = getattr(getattr(b, 'block_record', None), 'dxf', None)
    h = getattr(rec_handle, 'handle', None)
    ents = list(b)
    types = [e.dxftype() for e in ents]
    print(f"Block '{b_name}' handle={h}: {len(ents)} entities: {types[:8]}")
