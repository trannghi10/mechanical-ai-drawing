import sys
sys.path.insert(0, ".")
import json
from pathlib import Path
from backend.services.change_service import context_for
from cad.frame_geometry import world
from cad.closed_profiles import contours
from cad.measured_features import binds

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
folder = Path(f"storage/documents/{doc_id}")
source = folder / "converted" / "original.dxf"

with open(folder / "sheets-v3.json", "r", encoding="utf-8") as f:
    sheets = json.load(f)["items"]

target_sheets = [s for s in sheets if s["id"] == "404032"]
ctx = context_for(source, target_sheets)

records = [world(e) for e in ctx["entities"] if e.get("geometry")]
dim_468 = next((e for e in records if e["ref"] == "3E3F60"), None)
print("DIM 3E3F60 found:", dim_468 is not None)
if dim_468:
    print("dim text:", ascii(dim_468.get("text", "")))
    print("dim meas:", dim_468.get("scaled_measurement"))
    print("defpoints:", dim_468["geometry"].get("defpoint2"), dim_468["geometry"].get("defpoint3"))

profiles = contours(records)
print(f"Total contours on 404032: {len(profiles)}")
for i, p in enumerate(profiles):
    pts = p["points"]
    print(f"Profile {i}: {len(pts)} points, refs: {p['refs']}")
    if dim_468:
        binding = binds(dim_468, p)
        print(f"  binds with DIM 3E3F60? {binding}")
