import time
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.catalog_service import folder
from backend.services.revision_service import export_dwg, read_revision

doc_id = '34ee84f35e1a44fb81c56044397a0fff'
rev_dir = folder(doc_id) / 'revisions'
rev_files = sorted(rev_dir.glob('*/revision.json'), key=lambda p: p.stat().st_mtime, reverse=True)
if not rev_files:
    print("No revisions found.")
    sys.exit(0)

latest_rev_id = rev_files[0].parent.name
print(f"Testing export on revision {latest_rev_id}...")

t0 = time.time()
try:
    dwg = export_dwg(doc_id, latest_rev_id, require_approval=False, scope='selection')
    print(f"export_dwg (scope=selection) took {time.time() - t0:.2f}s -> {dwg}")
except Exception as e:
    print(f"export_dwg (scope=selection) failed in {time.time() - t0:.2f}s: {e}")

t1 = time.time()
try:
    dwg_doc = export_dwg(doc_id, latest_rev_id, require_approval=False, scope='document')
    print(f"export_dwg (scope=document) took {time.time() - t1:.2f}s -> {dwg_doc}")
except Exception as e:
    print(f"export_dwg (scope=document) failed in {time.time() - t1:.2f}s: {e}")
