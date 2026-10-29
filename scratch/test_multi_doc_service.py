import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
from backend.services.multi_document_service import (
    list_project_documents,
    analyze_project,
    plan_project_changes,
    apply_project_changes
)

print("1. Listing project documents...")
docs = list_project_documents()
print(f"Total documents found: {len(docs)}")
for d in docs[:5]:
    print(f"  - [{d['id'][:8]}] {d['filename']} (sheets: {d['sheet_count']}, parts: {d['part_count']})")

req = "đổi chi tiết số 6 481.5mm thành 480mm"
print(f"\n2. Analyzing project request: '{req}'")
analysis = analyze_project([d['id'] for d in docs[:6]], req)
print(f"Summary: {analysis['summary']}")
print(f"Affected count: {analysis['affected_count']}")
for aff in analysis['affected_documents']:
    print(f"  * Affected: {aff['filename']} -> {aff['explanation']}")
    print(f"    Targets: {aff['matched_targets']}")

if analysis['affected_documents']:
    print("\n3. Testing project plan creation...")
    plan_res = plan_project_changes([aff['document_id'] for aff in analysis['affected_documents']], req)
    print(f"Project Plan ID: {plan_res.get('project_plan_id')}")
    for p in plan_res.get('plans', []):
        print(f"  - Document {p['filename']}: status={p['status']}, ops={p.get('operations_count')}")
