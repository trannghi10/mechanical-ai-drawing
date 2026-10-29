"""Local-only native DXF import control; never modifies source or releases CAD."""
import argparse
import json
from pathlib import Path
import sys
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('document_id')
    parser.add_argument('source', help='DXF path relative to the document directory')
    parser.add_argument('report', type=Path)
    parser.add_argument('--normalize-index', action='store_true')
    parser.add_argument('--via-oda', action='store_true')
    parser.add_argument('--guarded', action='store_true')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    from backend.services import catalog_service as storage, aps_jobs
    from cad.edit_engine import digest
    from scripts.verify_company_whole_file import require_local
    require_local()
    folder = storage.folder(args.document_id).resolve()
    source = (folder / args.source).resolve()
    if not source.is_relative_to(folder) or source.suffix.lower() != '.dxf':
        raise ValueError('Control must use an existing document DXF')
    before = digest(source)
    report = dict(document_id=args.document_id, source=str(source.relative_to(folder)),
                  source_sha256=before, cloud_used=False, production_release=False)
    original = source
    if args.guarded:
        from backend.services.autocad_dxf_input import conversion_input
        from cad.catalog import load_document
        from cad.table_data import table_cells
        from cad.empty_ole import verify
        from scripts.verify_company_whole_file import audit_outside
        directory=folder/'diagnostics'/('guarded-repeat-'+before[:16]);output=directory/'output';check=directory/'check'
        output.mkdir(parents=True,exist_ok=True);check.mkdir(exist_ok=True)
        job_id=aps_jobs.convert_revision(args.document_id,None,source,output,check,provider='autocad')
        a=load_document(str(source));b=load_document(str(check/'modified.dxf'))
        _,normalization=conversion_input(args.document_id,source)
        outside=audit_outside(a,b,[])
        if not outside['passed'] or table_cells(source)!=table_cells(check/'modified.dxf'):raise ValueError('Repeated native readback changed geometry or BOM')
        report.update(status='passed',job_id=job_id,source_unchanged=digest(source)==before,normalization=normalization,
                      ole_integrity=verify(a,b,normalization),outside_checked_count=outside['checked_count'],output_sha256=digest(output/'modified.dwg'))
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(dict(status=report['status'],job_id=job_id,source_unchanged=report['source_unchanged'],outside_checked_count=report['outside_checked_count'])),flush=True)
        return
    if args.normalize_index:
        from cad.catalog import load_document
        from cad.scoped_export import select_entities
        drawing = load_document(str(source))
        keep = {e.dxf.handle for layout in drawing.layouts for e in layout}
        source = folder / 'diagnostics' / ('full-index-' + before[:16]) / 'normalized.dxf'
        normalization = select_entities(original, source, keep)
        assert normalization['removed_entity_count'] == 0
        report.update(normalization=normalization,normalized_sha256=digest(source))
    mode='convert'
    if args.via_oda:
        from cad.converter import converter_path
        converter=converter_path()
        if not converter:raise ValueError('Local ODA converter unavailable')
        bridge=folder/'diagnostics'/('oda-bridge-'+digest(source)[:16]);inputs=bridge/'input';outputs=bridge/'output'
        inputs.mkdir(parents=True,exist_ok=True);outputs.mkdir(exist_ok=True)
        shutil.copyfile(source,inputs/'source.dxf')
        result=subprocess.run([converter,str(inputs),str(outputs),'ACAD2018','DWG','0','0','source.dxf'],capture_output=True,timeout=180,
                              creationflags=getattr(__import__('os'),'CREATE_NO_WINDOW',0))
        if result.returncode or not (outputs/'source.dwg').is_file():raise ValueError('ODA bridge failed')
        source=outputs/'source.dwg';mode='inspect'
        report.update(intermediate_converter='ODA File Converter',intermediate_sha256=digest(source))
    job = aps_jobs.start(args.document_id, mode=mode, source=source,
                         expected_source_hash=digest(source), provider='autocad')
    report['job_id'] = job['id']
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report), flush=True)
    try:
        job = aps_jobs.wait(args.document_id, job['id'])
        report.update(status=job['status'], message=job['message'])
    except ValueError as error:
        report.update(status='failed', message=str(error))
    finally:
        report['source_unchanged'] = digest(original) == before
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=True), flush=True)
    if not report['source_unchanged']:
        raise ValueError('Source changed during native control')


if __name__ == '__main__':
    main()
