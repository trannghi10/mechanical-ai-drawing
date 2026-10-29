import xml.etree.ElementTree as ET

tree = ET.parse('scratch/rev_overlay_3E4E7A.svg')
root = tree.getroot()
title = root.find('{http://www.w3.org/2000/svg}title')
with open('scratch/svg_info.txt', 'w', encoding='utf8') as f:
    if title is not None:
        f.write(f"Title: {title.text}\n")
    groups = root.findall('{http://www.w3.org/2000/svg}g')
    f.write(f"Groups count: {len(groups)}\n")
    for i, g in enumerate(groups):
        opacity = g.get('opacity')
        paths = g.findall('{http://www.w3.org/2000/svg}path')
        f.write(f"  Group {i+1} (opacity={opacity}): {len(paths)} paths\n")
print("Written to scratch/svg_info.txt")
