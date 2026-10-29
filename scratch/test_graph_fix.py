import sys
sys.path.insert(0, ".")
import json
import glob

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
storage_dir = f"storage/documents/{doc_id}"

# Let's search all json files in storage_dir for tables or sheet 404030
with open(f"{storage_dir}/sheets-v3.json", "r", encoding="utf-8") as f:
    sheets = json.load(f)["items"]

for s in sheets:
    if s["id"] == "404030":
        print("Sheet 404030 keys:", list(s.keys()))
        print("  tables:", s.get("tables"))
        print("  bbox:", s.get("bbox"))

# Check part-graph-v1.json graphic_table_count or tables
with open(f"{storage_dir}/part-graph-v1.json", "r", encoding="utf-8") as f:
    graph = json.load(f)

print("graph table_count:", graph.get("table_count"))
print("graph graphic_table_count:", graph.get("table_count"))
