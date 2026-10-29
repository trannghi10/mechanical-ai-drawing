import sys
sys.path.insert(0, ".")
import json
import re
from pathlib import Path
from bom.reader import normalized

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
folder = Path(f"storage/documents/{doc_id}")

with open(folder / "sheets-v3.json", "r", encoding="utf-8") as f:
    sheets = json.load(f)["items"]

with open(folder / "part-graph-v1.json", "r", encoding="utf-8") as f:
    graph = json.load(f)

nodes = {n["code"]: n for n in graph["nodes"]}
query = "chi tiết 1 hạ từ 463 xuống 400"
norm_query = normalized(query)

print("=== FINDING PART FOR QUERY ===")
matched_part = None
for n in graph["nodes"]:
    for occ in n.get("bom_occurrences", []):
        if occ.get("part_number") == "1":
            matched_part = n
            print(f"Found STT 1: code={n['code']}, desc={ascii(occ.get('description'))}")
            break
    if matched_part:
        break

# Extract delta
m = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:mm)?\s*(?:xuong|con|thanh|->|→)\s*(\d+(?:[.,]\d+)?)', norm_query)
delta = 0.0
if m:
    old_val, new_val = float(m.group(1)), float(m.group(2))
    delta = new_val - old_val
    print(f"Delta: {old_val} -> {new_val} (delta = {delta:g} mm)")

# 2. Find assembly containing this part
print("\n=== FINDING ASSEMBLY STRUCTURE ===")
assemblies = graph.get("assembly_structure", {}).get("assemblies", [])
containing_assemblies = []
for a in assemblies:
    member_codes = {m["part_code"] for m in a.get("members", [])}
    if matched_part["code"] in member_codes:
        containing_assemblies.append(a)
        print(f"Part {matched_part['code']} is in assembly {a['id']}:")
        print(f"  kind: {a.get('kind')}, owner: {a.get('owner_code')}, scopes: {a.get('scope_ids')}")

# Check mating leg C1
print("\n=== MATING PARTS AND CO-MEMBERS ===")
leg_code = "8.1.00496.003"
leg_node = nodes.get(leg_code)
if leg_node:
    print(f"Frame leg {leg_code}: detail_sheets={leg_node.get('detail_sheets')}")
    leg_old = 468.0
    leg_new = leg_old + delta
    print(f"Synchronized leg dimension: {leg_old} -> {leg_new:g} mm")
