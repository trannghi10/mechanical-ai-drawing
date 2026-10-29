import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.document_request_service import resolve_request

# Let's check both documents in storage/documents
docs = [p.name for p in Path('storage/documents').iterdir() if p.is_dir() and (p/'status.json').is_file()]
out_lines = []
out_lines.append(f"Available docs: {docs}")
req = "đổi chiều dài từ 1115mm thành 1110mm"

for doc_id in docs[:2]:
    out_lines.append(f"\n--- Testing doc: {doc_id} ---")
    try:
        res = resolve_request(doc_id, req)
        out_lines.append(f"Status: {res.get('status')}")
        out_lines.append(f"Message: {res.get('message')}")
        out_lines.append(f"Part codes: {res.get('part_codes')}")
        out_lines.append(f"Targets count: {len(res.get('targets', []))}")
        if res.get('targets'):
            for t in res.get('targets')[:2]:
                out_lines.append(f" Target: {t.get('id')} {t.get('name')}")
    except Exception as e:
        import traceback
        out_lines.append(traceback.format_exc())

Path('scratch/resolve_result.txt').write_text('\n'.join(out_lines), encoding='utf-8')
print("Finished test_resolve_req")
