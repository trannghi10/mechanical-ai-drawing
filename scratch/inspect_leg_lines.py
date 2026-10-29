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

# Print lines on 404032 near Y: 54770 to 55240
lines = [e for e in ctx["entities"] if e["type"] == "LINE"]
print(f"Total lines: {len(lines)}")
for e in lines:
    g = e.get("geometry", {})
    sy, ey = g.get("start", [0, 0])[1], g.get("end", [0, 0])[1]
    if (54760 <= sy <= 55250) or (54760 <= ey <= 55250):
        length = ((g["end"][0]-g["start"][0])**2 + (g["end"][1]-g["start"][1])**2)**0.5
        print(f"  Line #{e['ref']}: length={length:.2f}, start={[round(v,1) for v in g['start']]}, end={[round(v,1) for v in g['end']]}")
