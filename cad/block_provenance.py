"""Explicit origin metadata for isolated static block definitions."""
APPID='MECHANICAL_AI'
MARKER='SOURCE_BLOCK'


def source_name(document,name):
    if document is None or name not in document.blocks:return None
    record=document.blocks[name].block_record
    if not record.has_xdata(APPID):return None
    tags=list(record.get_xdata(APPID))
    if len(tags)==2 and tags[0].code==1000 and tags[0].value==MARKER and tags[1].code==1000:
        value=tags[1].value
        if value and len(value)<=255 and '\n' not in value and '\r' not in value:return value
    return None
