"""Manage the local dataset without executing downloaded programs or using APS."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from cad_dataset import store
from cad_dataset.bootstrap import initialize


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['init','source-audit','collect','register-company','inspect-dwg','audit','pack'])
    parser.add_argument('--cadsy-limit',type=int,default=3)
    args=parser.parse_args()
    if not 0<=args.cadsy_limit<=65:parser.error('--cadsy-limit phải trong 0..65')
    load_dotenv(Path(__file__).resolve().parents[1]/'.env',encoding='utf-8-sig')
    if args.action=='init':result=dict(root=str(initialize()))
    elif args.action=='source-audit':
        from cad_dataset.sources import audit_sources
        result=audit_sources()
    elif args.action=='collect':
        from cad_dataset.collect import collect_cadquarry,collect_engineering,collect_cadsy,collect_autodesk
        from cad_dataset.sources import audit_sources
        needed=('cadquarry-tree','cadquarry-commit','engineering-tree','engineering-commit','cadsy-metadata','cadsy-license','cadsy-upstream','cadquarry-data-license')
        if any(not (store.ROOT/'source-evidence'/(name+'.txt')).is_file() for name in needed):audit_sources()
        initialize();result={};errors={}
        for name,action in [('autodesk',lambda:collect_autodesk()),('cadquarry',lambda:collect_cadquarry()),('engineering',lambda:collect_engineering()),('cadsy',lambda:collect_cadsy(limit=args.cadsy_limit))]:
            try:result[name]=action();print(json.dumps(dict(source=name,downloaded_records=len(result[name]))),flush=True)
            except Exception as error:errors[name]=str(error);print(json.dumps(dict(source=name,status='failed',error=str(error))),flush=True)
        result['errors']=errors;store.write_json(store.ROOT/'collection-report.json',result)
    elif args.action=='register-company':
        from cad_dataset.operations import register_company
        result=dict(registered=register_company())
    elif args.action=='inspect-dwg':
        from cad_dataset.operations import inspect_dwgs
        result=dict(results=inspect_dwgs())
    elif args.action=='pack':
        from cad_dataset.operations import pack
        result=pack();store.write_json(store.ROOT/'package-receipt.json',result)
    else:
        result=store.status(verify=True);store.write_json(store.ROOT/'status.json',result)
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':main()
