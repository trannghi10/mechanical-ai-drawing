import sys, os
sys.path.insert(0, os.path.abspath('.'))
from backend.services import catalog_service as storage

doc = storage.get_document('5a1955b75d4345b69d19d38b7cfaf75c')
boms = [e for e in doc['entities'] if e.get('bom')]
for b in boms:
    for r in b['bom']['rows']:
        print(f"STT {r.get('part_number')}: {r.get('part_code')} - {r.get('description')}")
