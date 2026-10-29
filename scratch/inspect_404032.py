import json

doc_id = "5a1955b75d4345b69d19d38b7cfaf75c"
storage_dir = f"storage/documents/{doc_id}"

with open(f"{storage_dir}/sheets-v3.json", "r", encoding="utf-8") as f:
    sheets_data = json.load(f)

for s in sheets_data.get("items", []):
    if s.get("id") == "404032":
        print("=== SHEET 404032 ===")
        print("name:", ascii(s.get("name", "")))
        print("texts:")
        for t in s.get("texts", []):
            print("  ", ascii(t))
