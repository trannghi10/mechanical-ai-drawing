import json

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
storage_dir = f"storage/documents/{doc_id}"

with open(f"{storage_dir}/catalog.json", "r", encoding="utf-8") as f:
    cat = json.load(f)

print(f"Entities in catalog: {len(cat.get('entities', []))}")

# Check entities belonging to sheet 404032 and 404030
for sid in ["404032", "404030"]:
    sheet_entities = [e for e in cat.get("entities", []) if sid in e.get("source_sheet_ids", [])]
    print(f"\n=== SHEET {sid}: {len(sheet_entities)} entities ===")
    types = {}
    for e in sheet_entities:
        t = e.get("type")
        types[t] = types.get(t, 0) + 1
    print("Types:", types)
    dims = [e for e in sheet_entities if e.get("type") == "DIMENSION"]
    print(f"Dimensions ({len(dims)}):")
    for d in dims:
        meas = d.get("measurement") or d.get("scaled_measurement")
        g = d.get("geometry", {})
        text = d.get("text", "") or g.get("text", "")
        print(f"  DIM #{d.get('ref')}: meas={meas}, text={ascii(text)}, layer={d.get('layer')}")
