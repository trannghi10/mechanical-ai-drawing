import json

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
storage_dir = f"storage/documents/{doc_id}"

with open(f"{storage_dir}/sheets-v3.json", "r", encoding="utf-8") as f:
    sheets_data = json.load(f)

for s in sheets_data.get("items", []):
    if s.get("id") == "404030":
        print("=== SHEET 404030 ===")
        print("name:", ascii(s.get("name", "")))
        print("texts:")
        for t in s.get("texts", []):
            print("  ", ascii(t))
        print("drawing_code:", s.get("drawing_code"))

with open(f"{storage_dir}/part-graph-v1.json", "r", encoding="utf-8") as f:
    graph = json.load(f)

for g in graph.get("assembly_structure", {}).get("assemblies", []):
    if "404030" in g.get("scope_ids", []):
        print("=== ASSEMBLY GROUP ON 404030 ===")
        print("id:", g.get("id"))
        print("kind:", g.get("kind"))
        print("owner_code:", g.get("owner_code"))
        print("owner_candidates:", g.get("owner_candidates"))
        print("members:")
        for m in g.get("members", []):
            print(f"  {m.get('part_number')}: {m.get('part_code')} - {ascii(m.get('description'))}")
