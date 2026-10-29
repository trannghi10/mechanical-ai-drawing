"""Hash-bound local DXF compatibility copies; original CAD stays immutable."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from filelock import FileLock
from backend.services import catalog_service as storage
from cad.edit_engine import digest
from cad.empty_ole import normalize, POLICY_VERSION


def prepare(document_id,source):
    source=Path(source).resolve();folder=storage.folder(document_id).resolve()
    if not source.is_relative_to(folder):raise ValueError('Normalization source outside document')
    if source.suffix.lower()!='.dxf':return source,None
    source_hash=digest(source)
    directory=folder/'autocad-inputs'/(str(POLICY_VERSION)+'-'+source_hash)
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/'normalized.dxf';receipt=directory/'normalization.json'
    with FileLock(str(receipt)+'.lock',timeout=120):
        if receipt.is_file():
            proof=json.loads(receipt.read_text(encoding='utf8'))
            if proof.get('policy_version')!=POLICY_VERSION or proof.get('source_hash')!=source_hash:
                raise ValueError('Invalid normalization receipt')
            if not proof.get('empty_ole'):return source,proof if proof.get('ole_count',0)>0 else None
            if not target.is_file() or digest(target)!=proof['output_hash']:raise ValueError('Normalized DXF changed')
            return target,proof
        proof=normalize(source,target)
        if proof is None:
            from cad.catalog import load_document
            ole_count=sum(e.dxftype()=='OLE2FRAME' for e in load_document(str(source)).entitydb.values())
            if ole_count:proof=dict(policy_version=POLICY_VERSION,source_hash=source_hash,output_hash=source_hash,empty_ole=[],ole_count=ole_count,appearance_verified=False)
        storage.write_json(receipt,proof or dict(policy_version=POLICY_VERSION,source_hash=source_hash,empty_ole=[]))
        return (target if proof.get('empty_ole') else source,proof) if proof else (source,None)


def conversion_input(document_id,source):
    """Read OLE-bearing DXF through local ODA; AutoCAD must save/reopen DWG.

    Feeding a placeholder-normalized DXF directly to DxfIn can discard other
    OLE contents. The DWG bridge is accepted only after all opaque payloads,
    metadata and XDATA are compared by the caller against the original DXF.
    """
    source=Path(source).resolve();_,normalization=prepare(document_id,source)
    if normalization is None:return source,None
    from cad.converter import converter_path
    converter=converter_path()
    if not converter:raise ValueError('DXF chứa OLE cần ODA cục bộ trước bước lưu/mở AutoCAD; chưa tạo DWG tải xuống.')
    converter_hash=digest(converter)
    directory=storage.folder(document_id)/'autocad-inputs'/(str(POLICY_VERSION)+'-'+digest(source))/'bridge'/converter_hash[:16]
    directory.mkdir(parents=True,exist_ok=True);receipt=directory/'bridge.json';target=directory/'output'/'input.dwg'
    with FileLock(str(receipt)+'.lock',timeout=240):
        if receipt.is_file():
            bridge=json.loads(receipt.read_text(encoding='utf8'))
            if bridge.get('source_hash')!=digest(source) or bridge.get('converter_hash')!=converter_hash or not target.is_file() or digest(target)!=bridge['dwg_hash']:
                raise ValueError('Local CAD bridge changed after conversion')
        else:
            inputs=directory/'input';outputs=directory/'output';inputs.mkdir(exist_ok=True);outputs.mkdir(exist_ok=True)
            shutil.copyfile(source,inputs/'input.dxf')
            result=subprocess.run([converter,str(inputs),str(outputs),'ACAD2018','DWG','0','0','input.dxf'],
                                  capture_output=True,timeout=180,creationflags=getattr(os,'CREATE_NO_WINDOW',0))
            if result.returncode or not target.is_file() or target.read_bytes()[:6]!=b'AC1032':raise ValueError('Local ODA bridge did not create a valid DWG')
            if digest(source)!=normalization['source_hash'] or digest(inputs/'input.dxf')!=normalization['source_hash']:raise ValueError('CAD bridge source changed')
            bridge=dict(source_hash=digest(source),converter_hash=converter_hash,dwg_hash=digest(target),
                        method='ODA File Converter -> AutoCAD Core Console',local_only=True,audit_repair=False)
            storage.write_json(receipt,bridge)
    return target,dict(normalization,reference_only=True,conversion_bridge=bridge)


def valid_receipt(validation):
    normalization=validation.get('input_normalization')
    if not normalization:return True
    bridge=normalization.get('conversion_bridge',{})
    return (normalization.get('policy_version') in (2,POLICY_VERSION)
            and bridge.get('local_only') is True and bridge.get('audit_repair') is False
            and bridge.get('source_hash')==normalization.get('source_hash')
            and validation.get('ole_integrity',{}).get('status')=='passed')
