"""Solve a bounded explicit nonlinear XY JSON model without writing CAD."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from graph.nonlinear_point_constraints import solve


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model",type=Path);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    if args.model.resolve()==args.output.resolve():raise ValueError("Keep input model unchanged")
    model=json.loads(args.model.read_text(encoding="utf-8-sig"))
    if model.get("schema_version")!=1 or model.get("units")!="mm":raise ValueError("Version 1 millimeter model required")
    report=solve(model["points"],model["constraints"])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps({k:report.get(k) for k in ("status","jacobian_rank","local_linearized_dof","max_normalized_residual")}))
    return 0 if report["status"]=="local_solution" else 2


if __name__=="__main__":raise SystemExit(main())
