# Sửa thử liên kết DIM chưa đầy đủ, 21/10/2026

**Cập nhật:** Đã hoàn tất đối chứng 15 đối tượng và kéo thử hai liên kết mới ở cả hai chiều. Xem phần kiểm chứng bổ sung ở cuối; các bản bị từ chối và kết luận ban đầu vẫn được giữ để truy vết.

Đã triển khai planner, native command và runner cục bộ cho hai DIM chỉ có đầu thứ nhất gắn với polyline. Thử bằng DIMREASSOCIATE trên bản sao DWG, giữ nguyên file nguồn. Đây là sửa thử quan hệ, không thay đổi kích thước hoặc xác nhận ý đồ cơ khí.

## Kết quả đọc lại

Lượt `storage/validation-fixtures/relationship-repair-bc99f837` có báo cáo `diagnostic-bindings.json` được đọc từ DXF sau lưu/mở lại:

| DIM | Association giữ nguyên | Đầu A | Đầu B được bổ sung |
|---|---|---|---|
| `3DFA25` | `3DFA27` | vertex 2 | vertex 3 |
| `3DFA2A` | `3DFA2C` | vertex 7 | vertex 6 |

Cả hai có `verified_source_points`, source duy nhất `3DFA1C`, đủ `defpoint2` và `defpoint3`. Không suy ra ý đồ thiết kế chỉ từ tọa độ trùng nhau; planner vẫn ghi `design_intent_confirmed=false` và `proposal_only=true`.

## Bản thử chưa được chấp nhận

Native kiểm điểm đo, số đo, đường DIM, vị trí chữ, style/góc/normal của cả sáu DIM trước/sau lưu đều qua. Tuy nhiên kiểm ngoài nhóm phát hiện 15 TOLERANCE/OLE2FRAME có bbox khác sau regen/save. Không thêm hoặc xóa entity. Chưa chứng minh đây chỉ là cache hiển thị nên giữ điều kiện từ chối `Repair changed objects outside group`; không bỏ qua bbox. DWG ứng viên chỉ ở thư mục worker riêng, chưa chuyển thành kết quả hợp lệ hoặc customer revision. Chưa kiểm được hai liên kết mới bám theo hình trong lần kéo tiếp theo vì bản sửa chưa qua kiểm toàn vẹn.

Bằng chứng: `relationship-repair-outside-diff.json`, `repair-summary.json`, `diagnostic-bindings.json`, `console.log` trong thư mục trên. DXF chẩn đoán nằm ở `storage/acwork/relationship-repair-bc99f837/relationship-repair-diagnostic.dxf`.

Các lượt lỗi trước được giữ: `relationship-repair-6e5b7378` bị khóa luồng đọc hash; `relationship-repair-3a7cf115` không bắt được endpoint; sau zoom object và regen, lệnh hoàn tất nhưng bộ kiểm ngoài nhóm chặn. File nguồn SHA-256 vẫn `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.

## Mã và kiểm tra

- `cad/relationship_repairs.py`: chỉ đề xuất hai DIM partial đã có binding đầu A, kiểm lại snapshot/binding và vertex khớp duy nhất; không nhận text override.
- `autodesk/MechanicalCad/DimensionRelationshipRepair.cs`: native preflight, DIMREASSOCIATE, save/reopen và đối chiếu ngoài phạm vi; không ghi đè nguồn.
- `scripts/repair_native_dimension_relationships.py`: chạy private worker, xác minh hash và DIMASSOC độc lập trước khi nhận kết quả.
- `tests/test_relationship_repairs.py`: 4 passed, 7 warnings. Plugin build/check đạt; runtime key `ec9d692527809536a7a40e53b5836c4d637a70c55f60d6ee9024f67eb60d6fb5`.

Tài liệu Autodesk: [DIMASSOC DXF](https://help.autodesk.com/cloudhelp/2020/ENU/AutoCAD-DXF/files/GUID-C0B96256-A911-4B4D-85E6-EB4AF2C91E27.htm), [DIMREASSOCIATE](https://help.autodesk.com/cloudhelp/2021/ENU/AutoCAD-Core/files/GUID-8CD54B4A-4BA6-40E8-819D-DDBC013114B8.htm).

Bước tiếp theo: chạy no-op control mở/regen/save để đối chiếu 15 đối tượng ngoài nhóm, kiểm dữ liệu gốc của TOLERANCE/OLE trước/sau; chỉ chấp nhận khi chứng minh bảo toàn nội dung và hình thức. Sau đó kéo thử trên bản sửa để xác minh các liên kết mới tự cập nhật. Hai đầu native còn thiếu vẫn chưa được giải quyết; đề xuất xốp chưa xác nhận vẫn giữ nguyên trạng thái.

## Kiểm chứng bổ sung: 15 đối tượng ngoài nhóm

No-op control `storage/validation-fixtures/relationship-repair-cf3a61fb` mở cùng nguồn, zoom cùng vùng, regen, lưu và mở lại; không chạy DIMREASSOCIATE. Control tái hiện đúng 15 thay đổi bbox (9 TOLERANCE, 6 OLE2FRAME), không thêm/xóa entity.

`outside-source-control-audit.json` trong thư mục control đối chiếu nguồn DXF inspection:

- 14/15 đối tượng có toàn bộ tag DXF trùng nguồn, gồm tất cả 9 TOLERANCE và 5 OLE2FRAME.
- OLE `404747` có payload tăng 512 byte khi no-op save, tag 90 đổi tương ứng độ dài payload, các tag khác giữ nguyên. Wrapper khác một byte tại offset 125; không diễn giải byte này thành bảo đảm hình thức hiển thị.
- Bộ đọc CFB giới hạn v3 kiểm FAT, directory tree, mini FAT và hash từng stream: `/\u0001Ole` (20 byte), `/\u0001CompObj` (106 byte), `/CONTENTS` (1.958.934 byte) giữ nguyên nội dung. Root CLSID/state và stream CLSID/state không đổi. Phần allocation/directory và wrapper có thay đổi; không coi payload byte-identical.
- Đây là bằng chứng bảo toàn nội dung lưu và tác động của no-op save; chưa kiểm pixel hiển thị dung sai/OLE hoặc mở embedded OLE bằng ứng dụng host.

Bản sửa `storage/validation-fixtures/relationship-repair-9986462f` đã đạt đối chiếu inventory ngoài nhóm với control, bao gồm bbox sau lưu. Tag DXF ngoài nhóm khớp control; riêng `404747` chỉ khác đúng 8 byte trường root last-modified FILETIME trong CFB, phần metadata và payload còn lại khớp từng byte. Bộ kiểm chỉ cho ngoại lệ ở trường đã parse này, không bỏ qua toàn payload, toàn entity hoặc toàn bbox. Receipt: `repair-receipt.json`, trường `outside_raw_control_checks`.

Hai DIM đã gắn đủ hai đầu, association giữ nguyên, hình đo không đổi; cả 54 primitive của sáu DIM được đối chiếu với nguồn như phép dịch bằng 0. Trạng thái `validated_relationship_repair_proposal` có nghĩa đạt kiểm dữ liệu và đối chứng trong phạm vi thử, không phải xác nhận ý đồ hoặc phát hành bản sửa khách hàng.

## Kéo thử: không gán trực tiếp đầu DIM

Mỗi lần thử bắt đầu từ bản sửa riêng `9986462f`. Native command chỉ `SetPointAt` một vertex của polyline, rồi `DIMREGEN`/regen. Không gọi setter đầu DIM, không gán số đo hoặc text DIM. Kiểm điểm A giữ nguyên, B đi đúng delta, measurement, style, topology polyline, save/reopen; Python độc lập kiểm DIMASSOC và nhãn số trong DXF.

| DIM / đầu mới | Kéo thử | Nhãn sau mở lại | Thư mục dưới `storage/validation-fixtures/` |
|---|---|---|---|
| `3DFA25` / vertex 3 | Y −10 mm | 150 | `relationship-challenge-fdeb296c` |
| `3DFA25` / vertex 3 | Y +10 mm | 130 | `relationship-challenge-ae30a63d` |
| `3DFA2A` / vertex 6 | X +10 mm | 150 | `relationship-challenge-2034c995` |
| `3DFA2A` / vertex 6 | X −10 mm | 130 | `relationship-challenge-62c59906` |

Số đo hình học có sai số sẵn khoảng ±0,000014 mm từ nguồn, bộ kiểm dùng số đo gốc cộng/trừ 10 mm, không ép hình về số nguyên. Nhãn hiển thị tương ứng 130/150.

Đối chứng âm trên DWG control chưa sửa: `relationship-challenge-3e3ad0f1` cho `3DFA25` và `relationship-challenge-292e61c0` cho `3DFA2A`. Cả hai không tự cập nhật đầu B, bị chặn trước save, không tạo DWG đầu ra. Điều này phân biệt tác dụng của liên kết mới với việc chỉ tái tạo chữ DIM.

Phép perturbation còn làm DIM tổng thể liên quan thay đổi tự nhiên: `3DFA1D` khi dịch vertex 3, `3DFA20` khi dịch vertex 6. Danh sách khác biệt được lưu trong `other_changed_inventory_entries`; không tuyên bố đây là sửa hoàn chỉnh toàn nhóm cơ khí hoặc bảo toàn tất cả ý đồ lắp ghép. Các DWG challenge chỉ là bài thử riêng, không dùng làm bản sản xuất.

Kết quả trên bản sửa đề xuất: 10/12 đầu DIM có bằng chứng nguồn/association, còn hai đầu A của native DIM chưa chứng minh. Nguồn khách hàng không bị thay đổi và vẫn chỉ có 8/12 đầu có bằng chứng như trước. `design_intent_confirmed=false`, `mechanical_group_complete=false`, `customer_revision_created=false` tiếp tục giữ.

## Kiểm tra và chạy lại

17 test tập trung đạt, 7 warnings: `test_compound_streams.py`, `test_ole_control.py`, `test_relationship_repairs.py`. Có kiểm CFB lỗi/cycle/truncated, thay nội dung stream, sửa payload ngoài timestamp và metadata không hợp lệ. Plugin build/check đạt, runtime key `124addb5c51e422236c971c3dd8f5aba8413d406d267c87e5dbdb61861ad9e93`. Không chạy lại toàn suite.

```powershell
python scripts/repair_native_dimension_relationships.py 51ec94944c4443b19fb8d5bd7930a6dd 3DFA1C --inspection-job ea4b1d186ca4453e9db9cd06c55ef263 --control-only
python scripts/repair_native_dimension_relationships.py 51ec94944c4443b19fb8d5bd7930a6dd 3DFA1C --inspection-job ea4b1d186ca4453e9db9cd06c55ef263 --control-evidence storage/validation-fixtures/relationship-repair-cf3a61fb
python scripts/challenge_repaired_dimensions.py storage/validation-fixtures/relationship-repair-9986462f --dimension 3DFA25
python scripts/challenge_repaired_dimensions.py storage/validation-fixtures/relationship-repair-9986462f --dimension 3DFA2A --step -10
```

Các runner luôn tạo thư mục UUID mới; dùng đường dẫn evidence mới in ra khi chạy lại. Bước tiếp theo là kiểm hình thức hiển thị TOLERANCE/OLE, xử lý hai đầu native còn thiếu và tích hợp proposal/revision vào workspace; không tự phát hành bản sửa dựa trên các bài thử này.
