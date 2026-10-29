"""Evidence-based links between native cell slots and rendered table text."""


def bind_cells(table,cells,doc):
    geometry=doc.blocks.get(table.dxf.get('geometry',''))
    if geometry is None:return []
    text_entities=[e for e in geometry if e.dxftype() in ('MTEXT','TEXT')]
    result=[]
    for cell in cells:
        before=cell['raw_text']
        if not before:continue
        matches=[e for e in text_entities if (e.text if e.dxftype()=='MTEXT' else e.dxf.text)==before]
        native=[c for c in cells if c['raw_text']==before]
        matched=None;method=None
        if len(matches)==1 and len(native)==1:
            matched=matches[0];method='unique_exact_text'
        elif len(matches)==len(native) and len(matches)>1:
            indices=[c['index'] for c in native];steps={b-a for a,b in zip(indices,indices[1:])}
            x_values=[e.dxf.insert.x for e in matches]
            y_values=[e.dxf.insert.y for e in matches]
            # Only accept repeated values in one vertical column, with regular
            # native cell-slot spacing and distinct row positions. Do not guess
            # between duplicate values spread over multiple columns or merges.
            if len(steps)==1 and max(x_values)-min(x_values)<1e-6 and len(set(round(y,6) for y in y_values))==len(matches):
                ordered=sorted(matches,key=lambda e:e.dxf.insert.y,reverse=True)
                matched=ordered[indices.index(cell['index'])];method='same_column_row_order'
        if matched is not None:
            result.append({'cell_index':cell['index'],'mirror_handle':matched.dxf.handle,
                           'mirror_ref':table.dxf.handle+'/'+matched.dxf.handle,'method':method})
    return result
