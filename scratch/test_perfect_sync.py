import sys
sys.path.insert(0, '.')
import json
from pathlib import Path
import ezdxf
from cad.edit_engine import Operation, apply_patch
from cad.geometry import snapshot

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
folder = Path(f'storage/documents/{doc_id}')
source = folder / 'converted' / 'original.dxf'
test_dest = Path('scratch/test_modified.dxf')

doc = ezdxf.readfile(source)

# 1. 3D3A59 on sheet 404033:
e_59 = doc.entitydb.get('3D3A59')
snap_59_before = snapshot(e_59)
snap_59_after = json.loads(json.dumps(snap_59_before))
# Move left points from -88543.9533287975 to -88542.4533287975
snap_59_after['points'][0][0] = -88542.4533287975
snap_59_after['points'][3][0] = -88542.4533287975

# 2. 3D3A66 on sheet 404033:
e_66 = doc.entitydb.get('3D3A66')
snap_66_before = snapshot(e_66)
snap_66_after = json.loads(json.dumps(snap_66_before))
snap_66_after['points'][0][0] = -88542.4533287975
snap_66_after['points'][3][0] = -88542.4533287975

# 3. 3D3A67 (DIM 481.5) on sheet 404033:
e_67 = doc.entitydb.get('3D3A67')
snap_67_before = snapshot(e_67)
snap_67_after = json.loads(json.dumps(snap_67_before))
snap_67_after['defpoint2'][0] = -88542.4533287975

# 4. 3D3A62 (DIM 207.5) on sheet 404033:
e_62 = doc.entitydb.get('3D3A62')
snap_62_before = snapshot(e_62)
snap_62_after = json.loads(json.dumps(snap_62_before))
snap_62_after['defpoint2'][0] = -88542.4533287975

# 5. 3E6CBB (DIM 481.5) on sheet 3E4E7A:
e_cbb = doc.entitydb.get('3E6CBB')
snap_cbb_before = snapshot(e_cbb)
snap_cbb_after = json.loads(json.dumps(snap_cbb_before))
snap_cbb_after['defpoint3'][0] = -89972.74065760689
snap_cbb_after['defpoint'][0] = -89972.74065760689

# 6. 3E6CAE (DIM 207.5) on sheet 3E4E7A:
e_cae = doc.entitydb.get('3E6CAE')
snap_cae_before = snapshot(e_cae)
snap_cae_after = json.loads(json.dumps(snap_cae_before))
snap_cae_after['defpoint3'][0] = -89972.74065760689
snap_cae_after['defpoint'][0] = -89972.74065760689

# 7. 3E6C5F/3E50D9 (Flat bar contour on sheet 3E4E7A):
e_d9 = doc.entitydb.get('3E50D9')
snap_d9_before = snapshot(e_d9)
snap_d9_after = json.loads(json.dumps(snap_d9_before))
snap_d9_after['points'][0][0] = 1.5
snap_d9_after['points'][3][0] = 1.5

operations = [
    Operation(ref='3D3A59', action='replace_geometry', before=json.dumps(snap_59_before), after=json.dumps(snap_59_after), xyz=[], reason='Co ngắn 1.5mm hình chiếu mặt chi tiết 6 trên 404033'),
    Operation(ref='3D3A66', action='replace_geometry', before=json.dumps(snap_66_before), after=json.dumps(snap_66_after), xyz=[], reason='Co ngắn 1.5mm hình chiếu cạnh chi tiết 6 trên 404033'),
    Operation(ref='3D3A67', action='replace_geometry', before=json.dumps(snap_67_before), after=json.dumps(snap_67_after), xyz=[], reason='Đồng bộ DIM tổng (481.5 -> 480 mm) trên 404033'),
    Operation(ref='3D3A62', action='replace_geometry', before=json.dumps(snap_62_before), after=json.dumps(snap_62_after), xyz=[], reason='Đồng bộ DIM đoạn lỗ (207.5 -> 206 mm) trên 404033'),
    Operation(ref='3E6CBB', action='replace_geometry', before=json.dumps(snap_cbb_before), after=json.dumps(snap_cbb_after), xyz=[], reason='Đồng bộ DIM tổng (481.5 -> 480 mm) trên 3E4E7A'),
    Operation(ref='3E6CAE', action='replace_geometry', before=json.dumps(snap_cae_before), after=json.dumps(snap_cae_after), xyz=[], reason='Đồng bộ DIM đoạn lỗ (207.5 -> 206 mm) trên 3E4E7A'),
    Operation(ref='3E6C5F/3E50D9', action='replace_geometry', before=json.dumps(snap_d9_before), after=json.dumps(snap_d9_after), xyz=[], reason='Co ngắn 1.5mm phôi cắt La ngắn trên 3E4E7A'),
]

allowed_refs = {'3D3A59', '3D3A66', '3D3A67', '3D3A62', '3E6CBB', '3E6CAE', '3E6C5F/3E50D9'}
from backend.services.revision_service import digest
source_hash = digest(source)

print('Applying patch...')
report = apply_patch(source, test_dest, operations, allowed_refs, source_hash)
print('Patch applied successfully!')
print('Output hash:', report.get('output_hash'))
print('Changes count:', len(report.get('changes', [])))
for ch in report.get('changes', []):
    print(' ', ch.get('ref'), ch.get('action'), ch.get('reason'))
