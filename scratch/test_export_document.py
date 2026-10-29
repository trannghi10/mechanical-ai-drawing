import sys
sys.path.insert(0, '.')
from pathlib import Path
from backend.services.revision_service import export_dwg

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
rev_id = '5f87b84ede6345c88ccf3596bfe75ac7'

print("Exporting full document DWG (scope='document')...")
try:
    dwg_path = export_dwg(doc_id, rev_id, require_approval=False, scope='document')
    print("SUCCESS! Exported DWG:", dwg_path)
    print("File size:", dwg_path.stat().st_size, "bytes")
except Exception as e:
    print("FAILED with error:", type(e), e)
    import traceback
    traceback.print_exc()
