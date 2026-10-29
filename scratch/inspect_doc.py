import json

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
storage_dir = f"storage/documents/{doc_id}"

with open(f"{storage_dir}/sheets-v3.json", "r", encoding="utf-8") as f:
    sheets_data = json.load(f)

items = sheets_data.get("items", [])
print(f"Total sheets items: {len(items)}")
for s in items:
    sid = s.get("id") or s.get("handle")
    title = s.get("title") or s.get("name")
    code = s.get("drawing_code") or s.get("code")
    print(f"Sheet {sid}: title={ascii(title)}, code={code}")

print("\n--- Part Graph Keys ---")
with open(f"{storage_dir}/part-graph-v1.json", "r", encoding="utf-8") as f:
    graph = json.load(f)

print("graph keys:", list(graph.keys()))
if "nodes" in graph:
    print(f"nodes count: {len(graph['nodes'])}")
    for n in graph["nodes"][:10]:
        print("  node:", ascii(n.get("code") or n.get("id")), ascii(n.get("name", "")))
if "parts" in graph:
    print("parts type:", type(graph["parts"]), len(graph["parts"]))
    for k, v in list(graph["parts"].items())[:5]:
        print("  part:", ascii(k), v)
