import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import ezdxf

doc_id = '8565af68196b40a6acc853d9d9eead87'
p = Path(f'storage/documents/{doc_id}/converted/original.dxf')
doc = ezdxf.readfile(str(p))

nested_count = 0
for b in doc.blocks:
    for e in b:
        if e.dxftype() == 'INSERT':
            nested_count += 1

print(f'Total nested INSERTs inside blocks: {nested_count}')

# Check which blocks have nested inserts
blocks_with_inserts = []
for b in doc.blocks:
    ins = [e.dxf.name for e in b if e.dxftype() == 'INSERT']
    if ins:
        blocks_with_inserts.append((b.name, len(ins), ins[:5]))

print(f'Blocks containing INSERTs ({len(blocks_with_inserts)}):')
for bname, count, sample in blocks_with_inserts[:15]:
    print(f'  Block {bname}: {count} inserts -> {sample}')
