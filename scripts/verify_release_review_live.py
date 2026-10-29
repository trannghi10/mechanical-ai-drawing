"""Read-only HTTP checks on the existing authorized company revisions."""
import hashlib
import json
from pathlib import Path
import sys
import httpx

ROOT=Path(__file__).resolve().parents[1]
CASES=[
    ('Dauphine previous','51ec94944c4443b19fb8d5bd7930a6dd','cea85585ac9240eaab6ec1ceb7e1ed0e',True),
    ('Dauphine source guard','51ec94944c4443b19fb8d5bd7930a6dd','68a4f91c2fda4155928f8d83b596993d',True),
    ('MR-106','adca0491043c4105aeced9b94ca779be','fefe2e74f4a947a591ad90bb212b6095',True),
    ('LEG6949 selection','349a82dab3824d2b8b8082eae9ee9af0','56fb8ab223f449b19436d0647539ea9a',False),
]


def main():
    rows=[]
    with httpx.Client(base_url='http://127.0.0.1:8765',timeout=180) as client:
        assert client.get('/health').status_code==200
        assert client.get('/documents',headers={'Origin':'https://foreign.example'}).status_code==403
        assert client.get('/documents',headers={'Host':'foreign.example'}).status_code==403
        for name,did,rid,full_native in CASES:
            source=ROOT/'storage/documents'/did/'original.dwg'
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            response=client.get(f'/documents/{did}/revisions/{rid}/release-review');response.raise_for_status()
            report=response.json();checks={c['id']:c['status'] for c in report['checks']}
            assert not report['auto_release_allowed'] and not report['production_release']
            assert checks['certification']=='blocked' and checks['coverage']=='blocked'
            assert checks['geometry']=='passed'
            assert (checks['native_reopen']=='passed')==full_native
            if name=='Dauphine source guard':assert checks['source_preservation']=='passed'
            assert hashlib.sha256(source.read_bytes()).hexdigest()==before
            rows.append(dict(name=name,source_unchanged=True,report=report))
    output=ROOT/'storage/validation-fixtures/release-review-2026-10-23';output.mkdir(exist_ok=True)
    (output/'company-checks.json').write_text(json.dumps(dict(status='passed',cases=rows),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status='passed',cases=len(rows),no_production_release=True,source_unchanged=True)))


if __name__=='__main__':main()
