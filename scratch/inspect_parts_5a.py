import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from backend.services.document_request_service import prepare

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
val, job_id = prepare(doc_id)
parts = val.get('parts', [])
print(f"Total parts in 5a1955...: {len(parts)}")
for p in parts:
    print(f"Code: {p.get('part_code')}, desc: {p.get('descriptions')}")
