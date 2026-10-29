"""Reproducible source audit. TLS errors remain errors; never disable verify."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import requests
from cad_dataset import store


def audit_sources(root=store.ROOT):
    root=Path(root);folder=root/'source-evidence';folder.mkdir(parents=True,exist_ok=True)
    urls={
        'autodesk-mechanical':'https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/5FT67coP41xn6vjfEgyGQo.html',
        'autodesk-autocad':'https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/6XGQklp3ZcBFqljLPjrnQ9.html',
        'engineering-repo':'https://api.github.com/repos/david1203d/EngineeringCADDrawings',
        'engineering-tree':'https://api.github.com/repos/david1203d/EngineeringCADDrawings/git/trees/main?recursive=1',
        'engineering-commit':'https://api.github.com/repos/david1203d/EngineeringCADDrawings/commits/main',
        'forge-repo':'https://api.github.com/repos/Autodesk-Forge/learn.forge.designautomation',
        'ldm-metadata':'https://ldm.kisski.de/api/3/action/package_show?id=example-cad',
        'ldm-current-metadata':'https://service.tib.eu/ldmservice/api/3/action/package_show?id=example-cad',
        'cadquarry-tree':'https://api.github.com/repos/jacobjennings/CadQuarry/git/trees/main?recursive=1',
        'cadquarry-commit':'https://api.github.com/repos/jacobjennings/CadQuarry/commits/main',
        'cadsy-metadata':'https://huggingface.co/api/datasets/cadsy/cad-technical-drawings',
        'cadsy-upstream':'https://huggingface.co/datasets/ADSKAILab/Zero-To-CAD-100k/raw/main/README.md',
    }
    def fetch(item):
        name,url=item;entry=dict(name=name,url=url,checked_at=datetime.now(timezone.utc).isoformat())
        try:
            with requests.get(url,timeout=(15,30),allow_redirects=False,stream=True,headers={'User-Agent':'MechanicalDWGDatasetV1/1.0'}) as response:
                entry['http_status']=response.status_code
                if response.ok:
                    data=bytearray()
                    for chunk in response.iter_content(128*1024):
                        data.extend(chunk)
                        if len(data)>12*1024*1024:raise ValueError('Source metadata exceeds 12 MB')
                    path=folder/(name+'.txt')
                    # Preserve snapshots already referenced by dataset manifests.
                    # A changed upstream file becomes a new content-addressed
                    # snapshot, not an overwrite of license/provenance evidence.
                    import hashlib
                    checksum=hashlib.sha256(data).hexdigest()
                    if path.exists() and store.sha256(path)!=checksum:path=folder/(name+'-'+checksum[:12]+'.txt')
                    path.write_bytes(data);entry.update(path=path.relative_to(root).as_posix(),sha256=checksum,bytes=len(data))
        except requests.exceptions.SSLError:entry['error']='certificate_verification_failed'
        except (requests.RequestException,ValueError) as error:entry['error']=type(error).__name__
        cached=folder/(name+'.txt')
        if not entry.get('path') and cached.is_file():
            entry['previous_snapshot']=dict(path=cached.relative_to(root).as_posix(),sha256=store.sha256(cached),bytes=cached.stat().st_size,
                                           note='Cached evidence only; this attempt did not verify a new download.')
        return entry
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(fetch,urls.items()))
    # Licenses are fetched from exactly the revisions captured above.
    for name,commit_name,metadata_name in [('cadquarry','cadquarry-commit',None),('cadsy',None,'cadsy-metadata')]:
        source=next((e for e in results if e['name']==(commit_name or metadata_name) and e.get('path')),None)
        if not source:continue
        value=json.loads((root/source['path']).read_text(encoding='utf8'));revision=value['sha']
        extra=({'cadquarry-data-license':f'https://raw.githubusercontent.com/jacobjennings/CadQuarry/{revision}/DATA_LICENSE'} if name=='cadquarry' else
               {'cadsy-card':f'https://huggingface.co/datasets/cadsy/cad-technical-drawings/raw/{revision}/README.md','cadsy-license':f'https://huggingface.co/datasets/cadsy/cad-technical-drawings/raw/{revision}/LICENSE'})
        results.extend(fetch(item) for item in extra.items())
    report=dict(sources=results,tls_verification_disabled=False,customer_files_uploaded=False)
    store.write_json(root/'source-audit.json',report);return report
