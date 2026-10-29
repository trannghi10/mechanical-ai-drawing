import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import ezdxf
from ezdxf import bbox

doc_id = '8565af68196b40a6acc853d9d9eead87'
p = Path(f'storage/documents/{doc_id}/converted/original.dxf')
doc = ezdxf.readfile(str(p))
msp = doc.modelspace()

failed = 0
no_data = 0
success = 0
cache = bbox.Cache()

for e in msp:
    try:
        b = bbox.extents([e], fast=True, cache=cache)
        if b.has_data:
            success += 1
        else:
            no_data += 1
    except Exception as ex:
        failed += 1

print(f'Modelspace extents: success={success}, no_data={no_data}, failed={failed}')
