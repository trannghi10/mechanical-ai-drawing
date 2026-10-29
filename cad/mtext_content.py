"""Replace only native AcDbMText content tags; preserve every other raw tag."""
from ezdxf.tools.text import split_mtext_string


def patch(raw, text):
    if '\n' in text or '\r' in text:
        raise ValueError('Dùng mã MTEXT \\P thay newline')
    markers = [i for i in range(0, len(raw), 2) if raw[i].strip() == b'100' and raw[i+1].strip() == b'AcDbMText']
    if len(markers) != 1:
        raise ValueError('MTEXT chưa có subclass nội dung duy nhất')
    start = markers[0]+2
    end = next((i for i in range(start, len(raw), 2) if raw[i].strip() in (b'100', b'101', b'1001')), len(raw))
    positions = [i for i in range(start, end, 2) if raw[i].strip() in (b'1', b'3')]
    if sum(raw[i].strip() == b'1' for i in positions) != 1:
        raise ValueError('MTEXT chưa có group 1 kết thúc nội dung duy nhất')
    # DXF defines 250 CHARACTER chunks, not 250 UTF-8 bytes. Use ezdxf's
    # native splitter so caret escapes are not split across chunks either.
    chunks = split_mtext_string(text, size=250) or ['']
    newline = b'\r\n' if raw[positions[0]+1].endswith(b'\r\n') else b'\n'
    replacement = []
    for i, chunk in enumerate(chunks):
        replacement.extend([f'{3 if i < len(chunks)-1 else 1:3d}'.encode('ascii')+newline, chunk.encode('utf8')+newline])
    slots = set(positions)
    result = []
    for i in range(0, len(raw), 2):
        if i == positions[0]:
            result.extend(replacement)
        if i not in slots:
            result.extend(raw[i:i+2])
    return result
