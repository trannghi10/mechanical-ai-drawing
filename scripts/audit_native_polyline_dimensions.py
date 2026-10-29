"""Read-only discovery from a retained native inventory and its DXF readback."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ezdxf
from cad.native_polyline_dimensions import discover


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("dxf", type=Path)
    parser.add_argument("polyline_handle")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    result = discover(inventory, ezdxf.readfile(args.dxf), args.polyline_handle)
    result["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for name, path in (("inventory", args.inventory), ("dxf", args.dxf))}
    result["input_policy"] = "Hashes identify supplied inspection files; native edit preflight must revalidate the original DWG."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "dimension_handles": result["dimension_handles"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
