"""Raster previews for AI, retaining the SVG's explicit paint properties."""
import re
import xml.etree.ElementTree as ET
import fitz


def rasterize_svg(content,width=800):
    root=ET.fromstring(content)
    styles={}
    for style in root.iter('{http://www.w3.org/2000/svg}style'):
        for name,body in re.findall(r'\.([\w-]+)\s*\{([^}]+)\}',style.text or ''):
            styles[name]={key.strip():value.strip() for key,value in
                          (piece.split(':',1) for piece in body.split(';') if ':' in piece)}
    # MuPDF SVG rendering does not apply this backend's class-based paint rules.
    for element in root.iter():
        for name in element.get('class','').split():
            for key,value in styles.get(name,{}).items():
                if value!='none' or key in ('stroke','fill'):element.set(key,value)
    with fitz.open(stream=ET.tostring(root),filetype='svg') as doc:
        page=doc[0];scale=width/page.rect.width
        return page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes('png')
