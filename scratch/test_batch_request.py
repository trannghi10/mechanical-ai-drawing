import sys
import json
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from backend.services.document_request_service import resolve_request
from backend.services.change_service import plan_change

doc_id = '34ee84f35e1a44fb81c56044397a0fff'
req = "Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm"

print("1. Resolving request...")
res = resolve_request(doc_id, req)
print(f"Status: {res.get('status')}")
print(f"Message: {res.get('message')}")
print(f"Target count: {len(res.get('targets', []))}")
print(f"Part codes: {res.get('part_codes')}")

if res.get('status') == 'resolved':
    print("2. Planning change...")
    try:
        plan = plan_change(doc_id, res['targets'], req, document_reading=res['evidence'])
        print(f"Plan ID: {plan.get('id')}")
        print(f"Execution available: {plan.get('execution_available')}")
        print(f"Questions: {plan.get('plan', {}).get('questions')}")
        print(f"Operations count: {len(plan.get('plan', {}).get('operations', []))}")
        print(f"Summary: {plan.get('plan', {}).get('summary')}")
        with open(ROOT / 'scratch' / 'plan_result.json', 'w', encoding='utf-8') as f:
            json.dump({
                'id': plan.get('id'),
                'execution_available': plan.get('execution_available'),
                'questions': plan.get('plan', {}).get('questions'),
                'op_count': len(plan.get('plan', {}).get('operations', [])),
                'summary': plan.get('plan', {}).get('summary'),
            }, f, indent=2, ensure_ascii=False)
        print("Success! Result saved to scratch/plan_result.json")
    except Exception as e:
        import traceback
        traceback.print_exc()
