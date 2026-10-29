"""Export read-only geometric candidates for explicitly selected DXF handles."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ezdxf
from graph.geometric_candidates import candidates


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("dxf",type=Path);p.add_argument("handles",nargs="+")
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--distance-mm",type=float,default=.01)
    p.add_argument("--angle-degrees",type=float,default=.5)
    args=p.parse_args()
    if args.output.resolve()==args.dxf.resolve():raise ValueError("Keep source DXF unchanged")
    before=hashlib.sha256(args.dxf.read_bytes()).hexdigest()
    report=candidates(ezdxf.readfile(args.dxf),args.handles,distance_mm=args.distance_mm,angle_degrees=args.angle_degrees)
    if hashlib.sha256(args.dxf.read_bytes()).hexdigest()!=before:raise ValueError("Source changed during scan")
    report.update(source_sha256=before,source_unchanged=True,customer_revision_created=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps(dict(status=report["status"],nodes=len(report["nodes"]),edges=len(report["edges"]),output=str(args.output))))


if __name__=="__main__":main()
