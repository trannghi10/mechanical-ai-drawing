# Kiểm thử stretch polyline tám đỉnh và sáu DIM, 21/10/2026

Cập nhật tiếp theo: [bằng chứng native vertex và thử tự cập nhật đầu DIM](native-vertex-binding-proof-2026-10-21.md) đã nâng số đầu có bằng chứng nguồn từ 6 lên 8/12; bốn đầu còn thiếu vẫn chưa được tự xác nhận.

Đã nối solver điểm với native writer trên bản sao DWG Dauphine: giữ bốn đỉnh bên trái, dịch cùng một lượng X cho bốn đỉnh bên phải, giữ chiều cao và các đoạn vát. Đây là probe cục bộ có phạm vi giới hạn, chưa phải adapter sửa sản phẩm hoặc quyền sửa nhóm cơ khí hoàn chỉnh.

## Phạm vi và bằng chứng

- Nguồn: document `51ec94944c4443b19fb8d5bd7930a6dd`, polyline `3DFA1C`, inspection `ea4b1d186ca4453e9db9cd06c55ef263`.
- Source SHA-256 vẫn là `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.
- Solver affine dùng 16 biến, rank 16, không còn bậc tự do; giải trong hệ tọa độ cục bộ để tránh sai số do tọa độ bản vẽ lớn.
- Ràng buộc: bốn đỉnh trái cố định, bốn đỉnh phải giữ Y và cùng dịch X, chiều rộng mục tiêu; kiểm polygon hợp lệ, không tự cắt hoặc sập phần giữa.
- Đối chiếu 4 DIMASSOC và 2 native action; điểm bắt vuông góc được tính bằng phép chiếu thực, không thay bằng đỉnh gần nhất.
- Ghi tám vertex và hai điểm đo của từng DIM; chạy native action, tái tạo DIM block, lưu/mở lại, kiểm trạng thái lưu trước và sau lần evaluate tiếp theo.
- Kiểm độc lập bằng ezdxf: polygon, điểm đo, số đo, nhãn chữ và liên kết. Native inventory đối chiếu 39.856 mục ngoài nhóm.

| Kiểm thử | Kết quả | Thư mục bằng chứng dưới `storage/validation-fixtures/` |
|---|---|---|
| Rộng 905 → 925 mm; cạnh phẳng 625 → 645 mm | Đạt, cả sáu DIM | `native-poly-dim-probe-9d111fa3` |
| Rộng 905 → 885 mm; cạnh phẳng 625 → 605 mm | Đạt, cả sáu DIM | `native-poly-dim-probe-7c9ac65d` |
| Hồi quy dịch X=3, Y=2 mm | Đạt, cả sáu DIM | `native-poly-dim-probe-9c2732a3` |
| Cố ý bỏ một native action | Từ chối đúng; không tạo DWG | `native-poly-dim-probe-f96663db` |

DWG 925 mm có SHA-256 `f1d42671b4c1c404cbfcaff8a287a3e23a6d096e904fc7fd22bbddddd4b6d35d`; DWG 885 mm có SHA-256 `3dc7564765eaaaad9ba634ff10979b105b9481cf4003888c30c27aa901706a29`. Mỗi thư mục thành công có `stretch-plan.json` (nếu stretch), `poly-dim-receipt.json`, DWG và DXF. Ảnh `native-poly-dim-probe-9d111fa3/group-preview.png` đã được xem: hình kín, nhãn và đường kích thước đúng như bảng.

## Kiểm chữ DIM sau khi tái tạo

Probe ban đầu chặn đúng tại vị trí chữ `3DFA20`: nguồn có chiều cao chữ thực 27 mm; AutoCAD tái tạo nhãn 925 với chiều cao thực 27,018365654 mm. Tâm chữ tăng theo phương vuông góc 0,009182827 mm. Không nới sai số: bộ kiểm dùng một MTEXT có attachment MiddleCenter, dịch tâm theo nửa chênh lệch chiều cao thực, giữ nguyên phía và khoảng hở chữ–đường DIM, đồng thời kiểm tâm dọc trục, đường DIM, style, góc, normal và text override. Log lỗi ban đầu được giữ ở `native-poly-dim-probe-54704dbc` và `native-poly-dim-probe-a7b958c9`.

Ở lượt probe đầu, bốn DIM không đổi số đo được kiểm toàn bộ primitive như phép dịch; hai DIM đổi số đo mới kiểm số lượng/type/style primitive và nhãn riêng. Các receipt cũ vẫn ghi `full_primitive_geometry_verified=false`. Bộ kiểm đã được mở rộng ở lượt tiếp theo bên dưới; không sửa lại bằng chứng cũ.

## Bổ sung: kiểm từng primitive và hồ sơ đầu DIM

Bộ `verify_horizontal_stretch` đối chiếu chính xác từng tọa độ trong cấu trúc đã giới hạn: 3 LINE, 2 SOLID, 1 MTEXT và 3 POINT cho mỗi DIM nằm ngang thay đổi số đo. Graphics ở mỗi đầu dịch cứng theo đúng đầu đo; đường DIM kéo giữa hai đầu; chữ dịch theo trung điểm và nửa thay đổi chiều cao glyph native. So sánh đầy đủ thuộc tính còn lại, kiểm nhãn số riêng. Cấu trúc khác, chữ wrap hoặc attachment khác MiddleCenter, đồ họa ở vùng giữa chưa có quy tắc, chiều kéo sập hai đầu đều bị từ chối.

| Kiểm mới | Thư mục bằng chứng dưới `storage/validation-fixtures/` | Kết quả |
|---|---|---|
| 905→925 mm | `native-poly-dim-probe-faabc0fd` | 54/54 primitive của 6 DIM được đối chiếu tọa độ/style/chữ sau save/reopen |
| 905→885 mm | `native-poly-dim-probe-22bece9f` | 54/54 primitive của 6 DIM được đối chiếu tọa độ/style/chữ sau save/reopen |

SHA-256 DWG mới: 925 mm `9fe7fd8f42b944d38fea0005e285687e9ca17c56c883dbcca068c2d0af6663ed`; 885 mm `0045f6a4803a1616dd97311a0f3c8881b3792dcd625acf992141a3a28c23297a`. Hai DIM thay đổi có `full_primitive_geometry_verified=true`; bốn DIM còn lại tiếp tục dùng bộ đối chiếu phép dịch. Đây là kiểm tọa độ primitive DXF, không phải kiểm pixel AutoCAD hoặc bằng chứng quan hệ toàn sản phẩm.

`binding_review` trong plan/receipt ghi 12 đầu DIM: 6 `source_bound`, 4 `native_dependency_vertex_candidate`, 2 `unbound_vertex_candidate`. Native dependency vào đối tượng không được đánh đồng với ánh xạ đầu DIM vào vertex đã chứng minh. `scope_sha256` gắn hash nguồn, handle, hình trước/sau, ý đồ và bằng chứng từng đầu; đổi nguồn hoặc phương án kéo sẽ đổi fingerprint. Fingerprint không phải chữ ký hay giấy phép sửa. `release_gate.allowed=false` và các trạng thái chưa xác nhận vẫn được giữ.

Kiểm bổ sung: 11 test DIM visuals đạt (có cố ý sửa tọa độ LINE/SOLID/MTEXT/POINT, chiều cao glyph sai và nhãn số sai); 25 test octagon/native topology đạt, gồm phân loại bằng chứng và fingerprint. Tổng 36 test trong hai lượt tập trung, không chạy lại toàn suite. Plugin local build/check đạt, runtime key `469b0f6cff374a10e43f5a94cf2e25e267fd13316af298ee1de278789c2dc96e`.

## Giới hạn còn giữ

Hai đầu DIM của `3DFA25` và `3DFA2A` thiếu liên kết; probe chỉ cho phép giả định trùng đúng vertex khi có cờ `--allow-unbound-test-assumptions`. Mặc định planner từ chối. Các giả định được lưu trong receipt, không nâng thành liên kết đã xác nhận; `edit_authorization=false`, `mechanical_group_complete=false`, `customer_revision_created=false`.

Chưa mở API/UI stretch nhóm này, chưa đồng bộ BOM/hình chiếu khác, chưa xác minh quan hệ lắp ghép hoặc toàn sản phẩm. Không upload bản vẽ khách hàng lên APS. Đề xuất xốp 3.8.01312 vẫn chưa xác nhận.

Kiểm tự động liên quan: `tests/test_octagon_width.py`, `tests/test_native_polyline_dimensions.py`, `tests/test_dimension_visuals.py`: **27 passed, 7 warnings**. Plugin local build và `setup_autocad.py check` đạt; runtime key `eb4f186872ce4b1692385ea77ff38b605544ab04427a929e0cf7e19a90fd8e5a`. Đây là kiểm tập trung cho phần mới, không phải lần chạy lại toàn bộ suite.

## Chạy lại

```powershell
python scripts/probe_native_polyline_dimensions.py 51ec94944c4443b19fb8d5bd7930a6dd 3DFA1C --inspection-job ea4b1d186ca4453e9db9cd06c55ef263 --stretch-width 925 --allow-unbound-test-assumptions
```

Bước tiếp theo: mở rộng đọc bằng chứng subentity/đầu DIM native và đưa phương án thử vào revision/preview có trạng thái giả định rõ ràng; chưa mở phát hành bản sửa khi còn thiếu quan hệ cần giữ.
