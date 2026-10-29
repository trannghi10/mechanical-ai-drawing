"""Color an actual, registered CAD render difference; never change drawing data."""
from collections import Counter
from copy import deepcopy
import re
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', NS[1:-1])


def paths(root):
    styles = {}
    for style in root.iter(NS + 'style'):
        for name, body in re.findall(r'\.([\w-]+)\s*\{([^}]+)\}', style.text or ''):
            styles[name] = dict(item.strip().split(':', 1) for item in body.split(';') if ':' in item)
    result = []

    def visit(node, transforms=()):
        transforms = transforms + ((node.get('transform'),) if node.get('transform') else ())
        if node.tag == NS + 'path':
            paint = {k.strip(): v.strip() for k, v in styles.get(node.get('class'), {}).items()}
            paint.update({k.strip(): v.strip() for k, v in
                          (item.split(':', 1) for item in node.get('style', '').split(';') if ':' in item)})
            attrs = tuple(sorted((k, v) for k, v in node.attrib.items() if k not in ('class', 'style', 'transform')))
            result.append((node, paint, (attrs, transforms, tuple(sorted(paint.items())))))
        for child in node:
            visit(child, transforms)

    visit(root)
    return result


def overlay(before_svg, after_svg):
    before, after = ET.fromstring(before_svg), ET.fromstring(after_svg)
    if before.get('viewBox') != after.get('viewBox'):
        raise ValueError('Hai hình CAD chưa cùng hệ tọa độ để đối chiếu')
    old, new = paths(before), paths(after)
    old_counts, new_counts = Counter(p[2] for p in old), Counter(p[2] for p in new)
    removed, added = old_counts - new_counts, new_counts - old_counts
    root = ET.Element(NS + 'svg', dict(after.attrib))
    title = ET.SubElement(root, NS + 'title')
    title.text = f'CAD trước/sau: {sum(removed.values())} nét cũ đỏ; {sum(added.values())} nét mới xanh'
    ET.SubElement(root, NS + 'rect', {'width': '100%', 'height': '100%', 'fill': 'white'})

    def layer(source, records, counts, color, opacity):
        copy = deepcopy(source)
        selected = {id(n): (paint, key) for n, paint, key in records}
        remaining = counts.copy() if counts is not None else None

        def filter_children(original, cloned):
            for a, b in zip(list(original), list(cloned)):
                if a.tag in (NS + 'defs', NS + 'rect', NS + 'title'):
                    cloned.remove(b)
                elif a.tag == NS + 'path':
                    paint, key = selected[id(a)]
                    if remaining is not None and remaining[key] <= 0:
                        cloned.remove(b)
                        continue
                    if remaining is not None:
                        remaining[key] -= 1
                    for prop in ('stroke', 'fill'):
                        if paint.get(prop, 'none') != 'none':
                            paint[prop] = color
                    b.attrib.pop('class', None)
                    b.set('style', ';'.join(f'{k}:{v}' for k, v in paint.items()))
                else:
                    filter_children(a, b)

        filter_children(source, copy)
        group = ET.SubElement(root, NS + 'g', {'opacity': str(opacity)})
        group.extend(list(copy))

    layer(after, new, None, '#8993a2', .32)
    layer(before, old, removed, '#d62839', .9)
    layer(after, new, added, '#0076c8', 1)
    return ET.tostring(root, encoding='unicode'), {'old_paths': sum(removed.values()), 'new_paths': sum(added.values())}
