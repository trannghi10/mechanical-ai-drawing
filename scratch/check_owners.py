import json

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
storage_dir = f"storage/documents/{doc_id}"

with open(f"{storage_dir}/part-graph-v1.json", "r", encoding="utf-8") as f:
    graph = json.load(f)

parts = {n.get("code") or n.get("id"): n for n in graph.get("nodes", [])}

with open(f"{storage_dir}/sheets-v3.json", "r", encoding="utf-8") as f:
    sheets_data = json.load(f)

for s in sheets_data.get("items", []):
    sid = s.get("id") or s.get("handle")
    owners = {code for code, node in parts.items() if sid in node.get("detail_sheets", [])}
    if "404030" in str(sid) or "40402D" in str(sid) or "404032" in str(sid):
        print(f"Sheet {sid}: owners={owners}")
