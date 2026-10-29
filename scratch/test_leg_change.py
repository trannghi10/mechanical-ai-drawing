import sys
sys.path.insert(0, ".")
import json
from pathlib import Path
from backend.services.change_service import context_for
from backend.services.measured_profile_planner import compile_plan as measured_plan
from cad.measured_features import index as measured_index

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
folder = Path(f"storage/documents/{doc_id}")
source = folder / "converted" / "original.dxf"

with open(folder / "sheets-v3.json", "r", encoding="utf-8") as f:
    sheets = json.load(f)["items"]

with open(folder / "part-graph-v1.json", "r", encoding="utf-8") as f:
    graph = json.load(f)

# Targets should include sheets with 8.1.00496.003
target_sheets = [s for s in sheets if s["id"] in ("404032", "404031", "404030", "404029")]
ctx = context_for(source, target_sheets)
ctx["part_graph"] = graph
ctx["units"] = 4
ctx["root_target_ids"] = ["404032"]
ctx["source_features"] = measured_index(ctx, graph)

print("Features for 8.1.00496.003:")
features = [f for f in ctx["source_features"]["features"] if f.get("part_code") == "8.1.00496.003"]
print(f"Count: {len(features)}")
for f in features:
    print("  Feature sheet:", f.get("sheet_ids"), "proof:", f.get("ownership_proof"))
    for d in f.get("dimensions", []):
        print("    dim:", d["ref"], "meas:", d["measurement"], "axis:", d["axis"])

cmd = "chieu dai tu 468 thanh 405 mm, giu day"
ctx["part_graph"] = dict(ctx["part_graph"], seed_codes=["8.1.00496.003"])
plan = measured_plan(ctx, cmd)
print("Plan from measured_plan:", plan is not None)
if plan:
    print("Ops count:", len(plan.operations))
    for op in plan.operations[:5]:
        print("  op:", op.action, op.ref, ascii(op.reason[:60]))
