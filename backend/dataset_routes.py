"""Read-only dataset registry. No approval, training, upload or CAD edits here."""
import json
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from cad_dataset import store

router=APIRouter()


@router.get('/dataset',include_in_schema=False)
def page():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/dataset.html')


@router.get('/dataset.js',include_in_schema=False)
def script():
    return FileResponse(Path(__file__).resolve().parents[1]/'frontend/dataset.js',media_type='application/javascript')


@router.get('/dataset/status')
def status():
    try:
        result=store.status(verify=True)
        source=store.ROOT/'sources.json'
        result['sources']=json.loads(source.read_text(encoding='utf8')) if source.is_file() else {'public_sources':[]}
        return result
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@router.get('/dataset/records')
def records(offset:int=0,limit:int=50,query:str=''):
    if offset<0 or not 1<=limit<=100:raise HTTPException(422,'Trang dữ liệu không hợp lệ.')
    try:
        values=[];text=query.casefold().strip()
        for record in store.read_all():
            if text and text not in ' '.join([record.id,record.title,record.group,record.source_id]).casefold():continue
            values.append(dict(id=record.id,title=record.title,source_id=record.source_id,origin=record.origin,group=record.group,
                group_review=record.group_review.status,rights=record.rights.model_dump(),split=record.split,
                cad_formats=sorted({a.format for a in record.assets if a.role=='original'}),
                native_opened=any(a.role=='original' and a.validation in ('native_opened','native_roundtrip') for a in record.assets),
                label_count=len(record.labels),relationship_count=len(record.relationships),edit_case_count=len(record.edit_cases),
                dossier_review=record.dossier_review.status,notes=record.notes))
        return dict(items=values[offset:offset+limit],count=len(values),next_offset=offset+limit if offset+limit<len(values) else None)
    except (ValueError,FileNotFoundError) as error:raise HTTPException(422,str(error))


@router.get('/dataset/starter.zip')
def starter():
    path=store.ROOT/'mechanical-dwg-v1-starter.zip';receipt=store.ROOT/'package-receipt.json'
    if not path.is_file() or not receipt.is_file():raise HTTPException(404,'Chưa tạo gói starter.')
    if store.sha256(path)!=json.loads(receipt.read_text(encoding='utf8'))['sha256']:raise HTTPException(422,'Gói dữ liệu không khớp hash đã kiểm tra.')
    return FileResponse(path,media_type='application/zip',filename=path.name)
