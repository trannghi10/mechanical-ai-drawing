import json

rev_path = "storage/documents/5a1955b75d4345b69d19d38b7cfaf75c/revisions/f5a911a0a66f4ea69d104c845bc82e55/revision.json"
with open(rev_path, "r", encoding="utf-8") as f:
    rev = json.load(f)

print("Revision id:", rev.get("id"))
ops = rev.get("operations", [])
print(f"Ops count: {len(ops)}")
for i, op in enumerate(ops):
    print(f"[{i}] action={op.get('action')}, ref={op.get('ref')}, sheet={op.get('sheet_id')}")
    print(f"     reason={ascii(op.get('reason', ''))}")
    if "before" in op or "after" in op:
        print(f"     before={ascii(op.get('before', ''))} -> after={ascii(op.get('after', ''))}")
    if "delta" in op:
        print(f"     delta={op.get('delta')}")
