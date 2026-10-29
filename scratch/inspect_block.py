import ezdxf

doc = ezdxf.readfile('storage/documents/5a1955b75d4345b69d19d38b7cfaf75c/converted/original.dxf')
target_bname = None
for b in doc.blocks:
    if '58bdaf5a' in b.name.lower():
        target_bname = b.name
        break

print('Target block name:', target_bname)
inserts = [e for e in doc.modelspace() if e.dxftype() == 'INSERT' and e.dxf.name == target_bname]
print(f'Total inserts of {target_bname} in modelspace: {len(inserts)}')
for ins in inserts[:10]:
    print('  handle:', ins.dxf.handle, 'insert:', ins.dxf.insert, 'scale:', (ins.dxf.xscale, ins.dxf.yscale, ins.dxf.zscale), 'rotation:', ins.dxf.rotation)

b = doc.blocks[target_bname]
for e in b:
    print('Entity in block:', e.dxf.handle, e.dxftype())
    if e.dxftype() == 'LWPOLYLINE':
        pts = list(e.get_points())
        print('  LWPOLYLINE points:', pts)
    elif e.dxftype() == 'CIRCLE':
        print('  CIRCLE center:', e.dxf.center, 'radius:', e.dxf.radius)
