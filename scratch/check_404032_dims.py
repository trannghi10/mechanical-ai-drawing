import sys
sys.path.insert(0, ".")
import json
from pathlib import Path
from backend.services.change_service import context_for

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
folder = Path(f"storage/documents/{doc_id}")
source = folder / "converted" / "original.dxf"

with open(folder / "sheets-v3.json", "r", encoding="utf-8") as f:
    sheets = json.load(f)["items"]

target_sheets = [s for s in sheets if s["id"] == "404032"]
ctx = context_for(source, target_sheets)

dims = [e for e in ctx["entities"] if e["type"] == "DIMENSION"]
print(f"Sheet 404032 dimensions count: {len(dims)}")
for d in dims:
    meas = d.get("scaled_measurement") or d.get("measurement")
    text = d.get("text", "") or d.get("geometry", {}).get("text", "")
    print(f"  DIM #{d['ref']}: meas={meas}, text={ascii(text)}")
