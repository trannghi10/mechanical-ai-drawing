import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
from backend.services import document_atlas_service as atlas
from backend.services.document_request_service import resolve

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
job = atlas.submit(doc_id)
rep = atlas.read(doc_id, job['id'])
if rep['status'] == 'ready':
    data = atlas.report(doc_id, job['id'])
    for req in [
        "đổi chi tiết số 6 481.5mm thành 480mm",
        "đổi chi tiết số 5 956mm thành 950mm",
        "đổi chi tiết số 4 thành 300mm",
        "sửa độ dày thép tấm 1.5mm thành 1mm"
    ]:
        res = resolve(data, job['id'], req)
        print(f"Req: '{req}'")
        print(f"  Status: {res.get('status')}")
        print(f"  Message: {res.get('message')}")
        print(f"  Candidates: {len(res.get('candidates', []))}")
        if res.get('candidates'):
            c = res['candidates'][0]
            print(f"  First candidate: code={c.get('part_code')}, desc={c.get('descriptions')}")
