import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
from backend.services.document_atlas_service import report, submit

doc_id = sys.argv[1] if len(sys.argv) > 1 else 'baf461e9c2764a5ba9000a48772f846c'
job = submit(doc_id)
data = report(doc_id, job['id'])
print(f'Total parts in {doc_id}: {len(data["parts"])}')
for p in data['parts']:
    descs = p.get('descriptions', [])
    nums = [o.get('part_number') for o in p.get('bom_occurrences', [])]
    print(f"{p['part_code']} (STT {nums}): {descs}")
