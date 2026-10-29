"""Read-only evidence for unsupported company tube details; never edits CAD."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from cad.catalog import load_document
    from cad.edit_engine import digest
    from cad.geometry import snapshot
    from cad.sheets import render_sheet
    from cad.vision import rasterize_svg
    from backend.services.change_service import context_for
    from backend.services import catalog_service as storage
    folder=storage.folder('51ec94944c4443b19fb8d5bd7930a6dd')
    state=storage.read_status(folder.name);source=folder/state['dxf'];before=digest(source)
    atlas=json.loads((folder/'document-atlas/c756444e398e47c8a0085c205a56b730/report.json').read_text(encoding='utf8'))
    if atlas['source_hash']!=before:raise ValueError('Stale source atlas')
    wanted={'3A1D79','3A0878','3A0B2C','3A10ED','3A1991'}
    targets=[f for f in atlas['frames'] if f['id'] in wanted]
    base=ROOT/'storage/validation-fixtures/dauphine-wall-evidence-2026-10-22';base.mkdir(exist_ok=True)
    report=dict(source_hash=before,read_only=True,engineering_intent_confirmed=False,cases=[])
    for target in targets:
        context=context_for(source,[target]);rows=[]
        for e in context['entities']:
            if e['type'] in ('LINE','LWPOLYLINE','ARC','CIRCLE','DIMENSION','INSERT','TEXT','MTEXT','LEADER'):
                rows.append(e)
        report['cases'].append(dict(sheet_id=target['id'],bbox=target['bbox'],entities=rows))
        svg=render_sheet(source,target)
        (base/(target['id']+'.svg')).write_text(svg,encoding='utf8')
        (base/(target['id']+'.png')).write_bytes(rasterize_svg(svg,width=1600))
        print(json.dumps(dict(sheet_id=target['id'],entities=len(rows))),flush=True)
    report['source_unchanged']=digest(source)==before
    (base/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
