"""Analyze/propose an explicit affine XY model; never writes CAD."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from graph.linear_point_constraints import analyze


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("model",type=Path);p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    if args.output.resolve()==args.model.resolve():raise ValueError("Keep input model unchanged")
    model=json.loads(args.model.read_text(encoding="utf-8-sig"))
    if model.get("schema_version")!=1 or model.get("units")!="mm":raise ValueError("Version 1 explicit millimeter model required")
    result=analyze(model["points"],model["constraints"])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding="utf8")
    print(json.dumps({k:result[k] for k in ("status","rank","degrees_of_freedom","max_residual_mm")}))
    return 2 if result["status"]=="inconsistent" else 0


if __name__=="__main__":raise SystemExit(main())
