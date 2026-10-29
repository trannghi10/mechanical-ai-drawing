import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad.catalog import discover

docs_dir = Path('storage/documents')
for doc_dir in docs_dir.iterdir():
    if not doc_dir.is_dir():
        continue
    status_file = doc_dir / 'status.json'
    if not status_file.is_file():
        continue
    try:
        status = json.loads(status_file.read_text(encoding='utf-8'))
        dxf_rel = status.get('dxf')
        if not dxf_rel:
            continue
        dxf_path = doc_dir / dxf_rel
        if not dxf_path.is_file():
            continue
        cat_file = doc_dir / 'catalog.json'
        # Check if already has category
        needs_regen = True
        if cat_file.is_file():
            try:
                data = json.loads(cat_file.read_text(encoding='utf-8'))
                if any(i.get('category') == 'mechanical_part' for i in data.get('items', [])):
                    needs_regen = False
                    print(f"Doc {doc_dir.name[:8]}: already up to date with {len(data['items'])} items.")
            except Exception:
                pass
        
        if needs_regen:
            print(f"Regenerating catalog for {doc_dir.name[:8]} ({status.get('filename')})...")
            cat = discover(str(dxf_path))
            cat_file.write_text(json.dumps(cat, ensure_ascii=False), encoding='utf-8')
            mech_count = sum(1 for i in cat['items'] if i.get('category') == 'mechanical_part')
            print(f"Done {doc_dir.name[:8]}: total {len(cat['items'])}, mechanical_part: {mech_count}")
    except Exception as e:
        print(f"Error on {doc_dir.name[:8]}: {e}")

print("All catalogs checked.")
