# Adapter POLYLINE và kiểm tra FreeCAD — 13/10/2026

Đã bổ sung khả năng sửa cho cấu trúc CAD dùng chung, không tra mã sản phẩm hay handle của các file mẫu. Đây là mở rộng engine, chưa hoàn tất tự sửa mọi DWG hoặc backup toàn sản phẩm Dauphine.

## Chức năng mới

- **POLYLINE 2D kiểu cũ:** sửa XY trực tiếp trên chuỗi POLYLINE/VERTEX/SEQEND. Giữ loại entity, handle, flags, Z, width/bulge, metadata và dữ liệu ngoài phạm vi. Không chuyển sang LWPOLYLINE. Profile thẳng và cung tròn dùng chung bộ stretch theo DIM nguồn, đồng bộ lỗ, DIM, BOM và cô lập instance của block dùng chung.
- **Bảng kê vẽ bằng POLYLINE:** nhận lưới thẳng không width/bulge; truy vết BOM trong block lồng quá 6 cấp. Việc tìm chủ sở hữu chi tiết cũng không còn âm thầm dừng tại cấp 6. Kiểm thử 10 cấp cho ownership và 11 cấp cho bảng kê; vòng tham chiếu hoặc quá giới hạn 128 cấp báo lỗi rõ. Không thay thuật toán tìm khung hiện tại.
- **Bản cắt:** adapter profile bo góc và bộ xếp phôi hiện có chấp nhận classic POLYLINE; giữ các giới hạn kiểm chứng về stock, góc/lỗ, khoảng cách và số lượng.
- **FreeCAD/OpenCASCADE:** mọi kế hoạch có `resize_recipes` được kiểm tra mặt 2D trước khi apply. Dựng LINE và cung tròn thật, kể cả bán nguyệt hoặc bulge âm; kiểm tra mặt kín hợp lệ, số biên/lỗ và lỗ không chạm/cắt biên hay lỗ khác. Dùng tỷ lệ DIM nguồn để báo diện tích mm²; không tự suy ra chiều dày hoặc độ bền từ một mặt 2D.
- **Thao tác cuối cùng:** FreeCAD nhận hình học sau khi ghép các trục và lan truyền dependency; không chỉ kiểm tra recipe đầu tiên. Revision lưu policy 2; duyệt/xuất hoàn chỉnh kiểm tra phiên bản này. Giao diện phân biệt kiểm tra đường bao 2D với kiểm tra solid.
- **Ngữ cảnh AI:** classic POLYLINE được nén thành số đỉnh, closed/bulge và vùng tọa độ; lấy snapshot chính xác khi truy xuất. Prompt và `/cad/capabilities` được cập nhật đúng loại adapter.
- Các file `synthetic-general-<8 ký tự hex>.dwg` của script kiểm chứng được xếp vào nhóm file thử; không làm rối danh sách bản vẽ chính. Kiểm tra riêng phân loại gallery đạt 3 ca sau bộ kiểm thử đầy đủ.

Mã chính: `cad/legacy_polyline.py`, `cad/planar_profiles.py`, `cad/freecad_worker.py`, `cad/native_parts.py`, `cad/graphic_tables.py`, `backend/services/solid_validation_service.py`.

## Công cụ trên máy

Đã xác định ODA File Converter 27.1, FreeCAD 1.1 và DWG TrueView 2025. ODA chuyển DWG/DXF; FreeCAD kiểm tra hình học độc lập, chạy Python cục bộ với dữ liệu số. TrueView phục vụ xem/chuyển đổi; chưa tìm thấy AutoCAD/BricsCAD/ZWCAD/GstarCAD đầy đủ trong các vị trí/registry đã kiểm tra. Không cài dịch vụ trả phí hoặc gửi CAD khách hàng ra cloud cho các kiểm chứng này.

## DWG thật qua API

**Classic POLYLINE có hai cung bán nguyệt, hai lỗ, DIM aligned, block lồng 10 cấp:**

- Tạo DWG độc lập bằng ODA; upload qua HTTP, chọn block và yêu cầu 140 → 123 mm, giữ tâm.
- Planner nguồn tạo thao tác, apply/preview HTTP 200; FreeCAD kiểm tra hợp lệ. Diện tích trước/sau 3981,725606 → 3471,725606 mm²; còn hai lỗ và ba biên.
- Xuất/tải DWG rồi mở chính file tải xuống qua ODA: DIM đo 123 mm, hai lỗ vẫn R2, classic POLYLINE và bulge được giữ; hash nguồn không đổi.
- Biên nhận: `storage/validation-fixtures/general-workflow-85014bc9/report.json`.
- DWG: `storage/validation-fixtures/general-workflow-85014bc9/download/checked-preview.dwg`.
- Document `b429d53a5c3d43b4b7450b0de7217785`, revision `cf1215b5f9a14fb7b84a64f2ac436ad5`.

**Profile có rãnh, block lồng 8 cấp:** đã chạy thêm luồng xem trước → duyệt → xuất backup được duyệt → tải → mở lại đo 123 mm và kiểm tra lỗ. Việc duyệt tự động chỉ áp dụng cho dữ liệu tổng hợp của script kiểm thử này.

- Biên nhận: `storage/validation-fixtures/general-workflow-bbf92ef2/report.json`.
- DWG: `storage/validation-fixtures/general-workflow-bbf92ef2/download/checked-preview.dwg`.
- Document `58e5fffd8105418f98b5b8522834c368`, revision `64668c4b7ddb4313a2b7d0de706ff2fe`.

Hai file trên là bằng chứng cấu trúc mới, không thay thế backup sản phẩm khách hàng. Một lần dựng fixture đầu tiên đặt điểm DIM ngoài đường bao đã không qua matcher và hết thời gian chờ AI; fixture được sửa cho DIM bám đúng biên, đồng thời script có bước kiểm tra matcher trước khi gọi API. Không tính lần thất bại đó là kết quả đạt.

## Kiểm thử

Toàn bộ **519 kiểm thử Python đạt**, 271 cảnh báo deprecation của thư viện, 41,29 giây. Hai script `verify_frontend.js` và `verify_frontend_downloads.js` đạt. Log Python tại `storage/validation-fixtures/pytest-polyline-kernel-20261013.txt`. Các ca mới kiểm tra classic POLYLINE thẳng/cong, quay/tỷ lệ, lỗ/DIM/BOM, hai trục ghép, giữ nguồn và instance ngoài phạm vi, raw bytes/metadata, topology không hỗ trợ, association không được tách bỏ, ownership/BOM lồng sâu, xếp phôi và FreeCAD phát hiện mặt/lỗ lỗi. Backend đã nạp mã mới; `/health` trả 200 và `/cad/capabilities` báo FreeCAD/DWG sẵn sàng.

## Phần chưa hoàn tất

- POLYLINE curve-fit/spline-fit, mesh/3D, thay số đỉnh/bulge/width và association native chưa có adapter vẫn bị từ chối.
- Dynamic block, deformation SPLINE/ELLIPSE tổng quát, association/proxy nhị phân và XREF chưa được sửa tổng quát bằng các công cụ hiện tại.
- Trên MR-106, INSERT đường tâm `4074FD` liên kết reactor `407817`. Object đó là `ACAD_PROXY_OBJECT` có payload nhị phân; không thể coi như LINE tĩnh rồi xóa liên kết để cho phép backup. Yêu cầu ống 478 → 460 mm vẫn chưa có backup đã kiểm chứng.
- Liên kết tiếp xúc giữa những chi tiết khác nhau, mốc giữ, phôi uốn, phối cảnh và thùng/xốp vẫn phải có bằng chứng thiết kế nguồn. Mặt CAD hợp lệ không chứng minh đủ lắp ghép, sức bền hoặc chất lượng sản xuất.
- Dauphine chưa có backup toàn sản phẩm/đóng gói hoàn chỉnh. Không có cam kết tự sửa mọi DWG bất kỳ.

## Chạy lại

```powershell
Set-Location D:\mechanical-ai-drawing
python -m pytest -q
python scripts/verify_general_dwg_workflow.py --legacy --depth 10
python scripts/verify_general_dwg_workflow.py --approve
```

Hai lệnh cuối cần backend cổng 8765, ODA và FreeCAD đã cài; mỗi lần tạo một tài liệu kiểm thử độc lập mới.
