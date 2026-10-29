"""The checked write path for native TABLE cells or source-bound graphic cells."""
from cad.edit_engine import Operation


def cell_operations(table, cell, after, records, reason):
    before=cell['raw_text'];ref=cell.get('mirror_ref');record=records.get(ref,{})
    raw=record.get('raw_text',record.get('text'))
    if not ref or raw!=before or record.get('type') not in ('TEXT','MTEXT'):
        raise ValueError('Ô bảng kê chưa liên kết duy nhất với chữ CAD nguồn')
    if before==after:return []
    text=Operation(ref=ref,action='replace_text',before=before,after=after,xyz=[],reason=reason)
    if cell.get('storage')=='text':
        if table.get('type')!='GRAPHIC_TABLE' or ref not in table.get('source_refs',[]):
            raise ValueError('Ô bảng LINE/TEXT chưa có bằng chứng nguồn')
        return [text]
    return [Operation(ref=table['ref'],action='table_cell',before=before,after=after,
                      cell_index=cell['index'],mirror_ref=ref,xyz=[],reason=reason),text]


def has_cell_change(table,cell,operations):
    if cell.get('storage')=='text':
        return any(op.action=='replace_text' and op.ref==cell.get('mirror_ref') and op.before==cell.get('raw_text') and op.before!=op.after for op in operations)
    return any(op.action=='table_cell' and op.ref==table['ref'] and op.cell_index==cell.get('index') and op.before!=op.after for op in operations)
