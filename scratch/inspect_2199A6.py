import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

f = Path(r"d:\mechanical-ai-drawing\storage\documents\fdb1918fbce7401aa33c7738c4096b8f")
pg = json.loads((f / "part-graph-v1.json").read_text(encoding="utf-8"))
for n in pg.get("nodes", []):
    if "04121" in n.get("code", "") or "04123" in n.get("code", ""):
        print("Node:", n.get("code"), "name:", n.get("name"), "sheets:", n.get("sheets"), "detail_sheets:", n.get("detail_sheets"))

cat = json.loads((f / "catalog.json").read_text(encoding="utf-8"))
sheets = json.loads((f / "sheets-v3.json").read_text(encoding="utf-8"))["items"]
s_219B0A = [s for s in sheets if s["id"] == "219B0A"]
print("Sheet 219B0A texts:", s_219B0A[0]["texts"] if s_219B0A else None)
