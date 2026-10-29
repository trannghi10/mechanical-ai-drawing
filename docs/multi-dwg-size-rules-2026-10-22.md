# Mở rộng sửa kích thước trên nhiều DWG — 22/10/2026

Cập nhật tiếp: [đã hỗ trợ thành hộp trong block lồng và kiểm một chi tiết Dauphine thật qua DWG đầy đủ](dauphine-nested-wall-2026-10-22.md). Bốn chi tiết Dauphine còn bị chặn. Các kết quả 873 bài và corpus năm chi tiết bị chặn dưới đây là mốc trước cập nhật này.

Ưu tiên người dùng: đổi chiều dài/rộng/dày và đồng bộ chi tiết liên quan. Đợt này mở rộng bộ sửa độ dày hộp theo hình học nguồn, để nhận thêm cách vẽ và cách ghi BOM. Các bộ sửa dài/rộng, mặt lắp và lỗ đã có tiếp tục được kiểm hồi quy; không tuyên bố đã hiểu mọi DWG.

## Thay đổi đã chạy trên máy chủ

- Đọc được cả quy cách `dày × rộng × cao × dài` và `rộng × cao × dày × dài`; chỉ chọn trường dày khi giá trị cũ và tiết diện vật lý phân biệt duy nhất. Giữ các trường còn lại và cách phân cách nguồn.
- Lấy hướng dọc từ DIM linear/aligned đo thật, đưa hình về hệ tọa độ cục bộ rồi trả kết quả về đúng tọa độ bản vẽ. Hỗ trợ hình xoay trong XY; không giả định chiều dài luôn thẳng đứng. DIM aligned dùng hai điểm đo, không dựa vào góc hiển thị có thể cũ.
- Thêm mặt cắt hộp bằng hai LWPOLYLINE chữ nhật kín, đồng tâm, không bulge/độ rộng nét: giữ ngoài, dịch bốn đỉnh trong theo độ dày. Đường thành trong hình chiếu dọc và DIM phải có binding hình học nguồn.
- Nối polyline vào bước chọn hình học của compiler; kế hoạch tiếp tục qua kiểm scope, liên kết native, revision, xuất DWG và đo kiểm sau mở lại.
- Không dùng tên file, mã LEG6949 hoặc một kích thước cố định để cấp phép bộ sửa chung. Các mapping hình chiếu riêng của LEG6949 vẫn chỉ có hiệu lực trên đúng nguồn đã kiểm.

## Kiểm end-to-end bằng AutoCAD local 2027

Hai nguồn dưới đây là **DWG hồi quy tổng hợp riêng**, có kích thước/góc xoay/BOM khác nhau, chưa phải thêm hai hồ sơ công ty được nghiệm thu. Cả hai chạy qua HTTP thật: tải DWG → nhận khung từ hình nguồn → lập kế hoạch `checked_tube_wall` → apply preview tạo revision → xuất toàn document → tải DWG → nhập lại thành document độc lập. Đo hình học dựa trên đáp án tọa độ đã tác giả hóa, không lấy số mới trong BOM thay cho đo hình.

| Ca | Sửa thực tế | Sau nhập lại độc lập |
|---|---|---|
| Hộp chữ nhật 40×80, dài 215 mm, xoay 37° | Thành 3 → 2 mm; BOM `40x80x3x215` → `40x80x2x215` | Biên trong `[2,2]–[38,78]`; DIM thành 2; DIM dài 215; biên ngoài và hình ngoài vùng sửa giữ nguyên |
| Hộp vuông 14×14, dài 321 mm, xoay 90° | Thành 1,2 → 1 mm; BOM `1.2x14x14x321` → `1x14x14x321` | Biên trong `[1,1]–[13,13]`; DIM thành 1; DIM dài 321; biên ngoài và hình ngoài vùng sửa giữ nguyên |

[Receipt, revision ID, hash và kết quả đo](../storage/validation-fixtures/multi-dwg-native-24853b0b0ba5/receipt.json). Bản nguồn DXF/DWG và bản nhập nguồn đều giữ SHA. Hai DWG kết quả: [hộp chữ nhật xoay](../storage/validation-fixtures/multi-dwg-native-24853b0b0ba5/rectangular-rotated-37/after.dwg), [hộp vuông ngang](../storage/validation-fixtures/multi-dwg-native-24853b0b0ba5/square-horizontal/after.dwg). `production_release=false`, `engineer_accepted=false`.

Lặp kiểm native bằng `python scripts/verify_multi_dwg_tube_rules.py`. Script chỉ dùng AutoCAD/AI cục bộ và tạo bản thử mới; không gửi CAD lên cloud.

## Đối chiếu hồ sơ công ty

[Corpus đọc và lập kế hoạch](../storage/validation-fixtures/multi-dwg-size-rules-2026-10-22/tube-corpus.json) dùng ba DWG gốc khác nhau: Dauphine, MR-106 và LEG6949, giữ nguồn/hash/atlas. Đây là audit **chỉ đọc và lập kế hoạch**, không tự xác nhận yêu cầu kỹ sư hoặc ghi DWG theo mức giảm thử 20%.

- LEG6949: một bản chi tiết hộp đạt bộ sửa hình học. Phép quay 0/37/90° trên hình nguồn cũng nhất quán; chúng là biến thể tọa độ, không được đếm thành ba file công ty. Bản sửa thực có đồng bộ bas/hình chiếu đã [nhập lại độc lập](company-dwg-validation-2026-10-22.md).
- Dauphine: năm bản chi tiết hộp vẫn bị chặn. Hai bản dùng DIM ghi số cố định; ba bản còn lại chưa chứng minh đủ thành trong hình chiếu dọc. Nhận quy cách mới không tự tạo các liên kết thiếu.
- MR-106: không có chi tiết hộp phù hợp cho ca này. Luồng sửa tấm 15×15 mm đã kiểm riêng, xuất toàn hồ sơ và lưu/mở thêm một lượt, giữ OLE/BOM.

## Phạm vi chưa được mở

Bộ sửa hộp này cần đơn vị mm, tiết diện và DIM thật nhất quán, một cặp mặt cắt duy nhất, đủ đường thành trong với đối tác ngoài, DIM độ dày gắn được vào cạnh sửa. Hiện nhận chiều dài/hình chiếu dọc từ 100 mm theo giới hạn rule cũ (DIM dài phải lớn hơn 100 mm). Không hỗ trợ mới bulge, mặt phẳng OCS nghiêng, block động phức tạp, XREF/proxy hoặc tự suy luận mọi chi tiết lắp từ khoảng cách gần. Các phần thiếu bằng chứng tiếp tục chặn đồng bộ toàn yêu cầu.

Kiểm Python liên quan sau tích hợp: **873 bài đạt** trên tube stock/section, planning, dependencies, assembly, geometry, parametric và review. Không phải toàn bộ suite. Các kiểm có cả BOM thứ tự khác nhưng vẫn đồng bộ hai bas/bản cắt, hình xoay, DIM aligned góc cũ, góc mâu thuẫn, hai tiết diện nhập nhằng, bulge/bowtie và độ dày làm mất lòng hộp.

Trên website, tải DWG và yêu cầu theo mã hoặc STT có phạm vi rõ, ví dụ `Mã <mã chi tiết> hộp dày 3 thành 2 mm, giữ kích thước ngoài và chiều dài`. Hệ thống chỉ cho thực thi phần đã đủ bằng chứng; kết quả thử này không cấp chứng nhận tự phát hành toàn công ty.
