# Adapter tham chiếu DIM trực tiếp — 22/10/2026

**Cập nhật tích hợp:** adapter đã vào proposal/revision/undo, PostgreSQL đã phục hồi và luồng HTTP + restart đạt. Xem [báo cáo tích hợp revision](native-revision-release-2026-10-22.md). Bản revision đang chọn là `f1e25b7472f64ce2b64571d5687909df`; các trạng thái “chưa tích hợp” bên dưới ghi lại thời điểm kiểm adapter độc lập trước đó.

**Bản giao cuối tích lũy:** `storage/validation-fixtures/native-point-reference-validated-613ecb2c/native-dim-links-verified.dwg`. Bản này dùng revision legacy `fc3037b7d2bc4588ad3c0df9b15e2494` đã `ready` làm đầu vào (hash `11f2808eea82975c8aa3e67553276e67a25b56cc5ed45f017b251bb710be4342`), giữ nguyên đủ hai tham chiếu của cả bốn DIM legacy và bổ sung hai DIM native. Hash DWG đầu ra: `500417e9ce9cd167b3f19c8c615e901af4b3324bd26f5df0f02d5e7f12e9d921`.

Bản tích lũy đạt lại 8/8 phép kéo A/B ±10 mm, kiểm inventory 39.896 đối tượng, đồ họa 54 thành phần và 15 đối tượng ngoài nhóm. Thêm 4/4 phép kéo B độc lập: trên bản thử riêng, adapter tạm xóa tham chiếu B DIMASSOC mới, chỉ giữ A DIMASSOC và action native B gốc; DIM vẫn theo B ±10 mm, giữ A, đúng sau lưu/mở lại, DXF xác nhận không còn tham chiếu legacy B. Bằng chứng ở `native-b-isolation.json`, cùng thư mục với `verification.json`. Bản giao cuối vẫn giữ đủ cả A/B, không áp dụng thao tác xóa B của phép thử.

Bridge dùng cho phép thử tách B được build thêm export `MechanicalDisableSecondPointReference`, hash DLL `2e542e39ffe40a642eda53bec72f0b4b4de6566ea8dbc6694394c66febc7c4ca`. Hàm writer tạo tham chiếu giữ nguyên; các bản sửa đã kiểm trước đó dùng DLL hash `536117...`. Kết quả bên dưới mô tả cả phép thử ban đầu trên nguồn và phạm vi phát hành.

Đã sửa tham chiếu của `3DFA24` và `3DFA29` trên bản sao nguồn có SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`. File gốc giữ nguyên. Kết quả nằm tại `storage/validation-fixtures/native-point-reference-validated-edafbefa/native-dim-links-verified.dwg`; báo cáo có hash artifact tại `verification.json` cùng thư mục.

## Cách sửa

Bridge C++ dùng ObjectARX 2027, `AcDbDimAssoc::setDimObjId`, `setPointRef`, `post`, `addToPointRefReactor` và `updateDimension`. Nó thêm DIMASSOC đủ hai tham chiếu A/B, đồng thời giữ nguyên action native B cũ. Không sửa field nội bộ của `AcDbAssocRotatedDimActionBody`, không gọi DIMREASSOCIATE, không tháo native B, không vá DXF rồi nhập toàn file.

| DIM | Tham chiếu A | Tham chiếu B | Action B / geometry dependency / DIM dependency |
|---|---|---|---|
| 3DFA24 | Polyline 3DFA1C, vertex 1 | vertex 2 | 3E0329 / 3E032B / 3E032C |
| 3DFA29 | Polyline 3DFA1C, vertex 0 | vertex 7 | 3E032F / 3E0331 / 3E0332 |

Native getter checks trước/sau sửa và sau mở lại xác nhận ownership, reactor và cây tham số B không đổi. DXF được đọc độc lập để kiểm đủ hai vertex reference. Geometry nguồn giữ nguyên; các phép kéo thử được lưu ở các bản sao riêng.

## Kiểm chứng

- Mẫu hình chữ nhật: tạo hai tham chiếu, lưu/mở lại và đọc DXF độc lập đạt (`point-reference-0b132ec4`).
- DWG thực: tạo tham chiếu và lưu/mở lại đạt (`point-reference-edafbefa`). Output SHA-256 `247869669d7e52372c5decd00756706ee556b5f098462955924875576227b4f1`.
- 8/8 phép kéo độc lập: A/B của từng DIM, ±10 mm. DIM24 đo khoảng 625 → 635/615 mm (sai khác nguồn khoảng 0,0000282 mm được giữ); DIM29 đo 625 → 635/615 mm. Chỉ sửa vertex, gọi DIMREGEN; không gán tọa độ DIM. Sau lưu/mở lại, điểm đo, số đo, style và native B ownership/reactor/vertex đều đạt. Tham chiếu DXF và nhãn MTEXT kiểm độc lập cũng đạt.
- 54/54 thành phần đồ họa của sáu DIM giữ nguyên ở bản sửa liên kết, kiểm tọa độ/style/text.
- 39.896 đối tượng inventory ngoài phạm vi sửa đạt kiểm trong dung sai số học `1e-8`. Hai block đồ họa DIM được tái tạo 18 entity; ba block vô danh được AutoCAD đánh lại tên. Handle/ownership/membership được kiểm, không bỏ qua đổi block tùy ý.
- 15 đối tượng ngoài nhóm từng có chênh lệch bbox được kiểm DXF thô; tất cả đạt bộ so sánh nội dung, chỉ cho phép đúng trường modified FILETIME của CFB root khi có chênh lệch OLE. Không khẳng định đã kiểm hình ảnh OLE bằng mắt.
- 21 test tập trung đạt, 7 cảnh báo pyparsing; không chạy lại toàn bộ suite.

## Build và giới hạn phát hành

SDK đã giải nén trong workspace. Bộ cài Visual Studio hệ thống chưa hoàn tất; compiler MSVC 14.44.35207, thư viện runtime và Windows SDK từ gói Microsoft chính thức được chuẩn bị cục bộ, có đối chiếu hash compiler theo catalog. Build bằng `scripts/build_native_point_reference.py`. DLL SHA-256 `536117f27842c6199bdb8f019965a86e042f49f864d43b94a6363ad1fb1b2d41`.

Mã managed mới đã build và được thực thi trong AutoCAD ở các probe/challenge. `setup_autocad.py check` mới nhất dừng trước bước CAD vì PostgreSQL trả `the database system is in recovery mode`; không ghi nhận check tiêu chuẩn đó là đạt.

Đây là artifact sửa liên kết đã kiểm chứng, chưa nối bridge mới vào API revision/undo và chưa tạo revision khách hàng mới. Các cờ thử nghiệm managed cũ vẫn bị khóa. Không nâng ứng viên hình học thành ý đồ cơ khí đã xác nhận, không thay xác nhận còn thiếu của chi tiết xốp 745 → 718, không khẳng định hỗ trợ mọi DWG.
