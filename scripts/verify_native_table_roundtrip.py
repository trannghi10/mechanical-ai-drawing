"""Verify the older native TABLE encoding using a real uploaded source copy.

This is an adapter regression artifact: it changes BOM text only, not the
product geometry, and is deliberately outside the user's revision history.
"""
import json
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cad.catalog import load_document
from cad.table_data import table_cells
from cad.table_bindings import bind_cells
from bom.reader import read_bom
from cad.edit_engine import Operation,apply_patch,digest
from cad.converter import DWGConverter,converter_path


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'storage/documents/34ee84f35e1a44fb81c56044397a0fff/converted/original.dxf'
    out=root/'storage/validation-fixtures/native-table-roundtrip'/uuid.uuid4().hex
    authored=out/'modified';authored.mkdir(parents=True)
    original_hash=digest(source);doc=load_document(str(source));all_cells=table_cells(source)
    operations=[];updated=[]
    for handle,cells in all_cells.items():
        table=doc.entitydb[handle];bom=read_bom(cells,bind_cells(table,cells,doc))
        for row in bom['rows']:
            before=row['cells']['description']['raw_text']
            if 'Sắt tấm 1.5x' not in before:continue
            cell=row['cells']['description'];ref=cell['mirror_ref']
            if not ref:raise RuntimeError('No proven native display binding for '+handle)
            after=before.replace('Sắt tấm 1.5x','Sắt tấm 1x')
            operations.extend([Operation(ref=handle,action='table_cell',cell_index=cell['index'],before=before,after=after,mirror_ref=ref,xyz=[],reason='Adapter regression only'),
                               Operation(ref=ref,action='replace_text',before=before,after=after,xyz=[],reason='Adapter regression only')])
            updated.append(dict(table_ref=handle,cell_index=cell['index'],part_code=row['part_code'],before=before,after=after))
    if not operations:raise RuntimeError('No test cells found')
    destination=authored/'modified.dxf'
    validation=apply_patch(source,destination,operations,{o.ref for o in operations},original_hash)
    print(json.dumps(dict(stage='native_edit_validated',cells=len(updated)),ensure_ascii=False),flush=True)
    converter=DWGConverter(converter_path());converter.convert_dxf_to_dwg(str(authored),str(out/'dwg'))
    converter.convert_dwg_to_dxf(str(out/'dwg'),str(out/'reopened'))
    reopened=out/'reopened/modified.dxf'
    expected,actual=table_cells(destination),table_cells(reopened)
    if expected!=actual:raise RuntimeError('ODA roundtrip changed native table values')
    actual_doc=load_document(str(reopened));display_checks=[]
    for change in validation['changes']:
        if change['action']!='replace_text':continue
        entity=actual_doc.entitydb[change['ref'].split('/')[-1]]
        if entity.text!=change['after']:raise RuntimeError('ODA roundtrip lost updated display text')
        display_checks.append(change['ref'])
    assert digest(source)==original_hash
    dwg=out/'dwg/modified.dwg'
    receipt=dict(status='passed',adapter_regression_only=True,complete_product_backup=False,
                 source_unchanged=True,source_hash=original_hash,native_tables=len(actual),
                 changed_cells=len(updated),display_checks=len(display_checks),changes=updated,
                 dwg=str(dwg),dwg_hash=digest(dwg),bytes=dwg.stat().st_size)
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='changes'},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
