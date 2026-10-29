# Xuất các phạm vi khác nhau từ block dùng chung — 15/10/2026

Đã bổ sung khả năng xuất khi nhiều instance dùng chung một definition nhưng cần giữ những phần bản vẽ khác nhau. Engine cô lập các definition tĩnh liên quan trong bản sao tạm dành riêng cho xuất, ánh xạ lại đường dẫn rồi bỏ các member ngoài phạm vi. Bản nguồn, bản sửa làm việc và phần nhận diện/chọn khung giữ nguyên.

Trên giao diện, tiếp tục dùng **Phạm vi tệp tải → Bản vẽ đã chọn và các khung liên quan được sửa**. Việc cô lập diễn ra tự động trong bước tạo file. Có thể tải bản xem trước khi chưa đủ điều kiện duyệt; file này vẫn được ghi rõ là xem trước.

## Chức năng và kiểm tra

- Không còn chặn chỉ vì hai instance cần hai tập member khác nhau. Những trường hợp không xung đột vẫn dùng luồng xuất trực tiếp, tránh clone thừa.
- Giữ tọa độ, tỷ lệ, xoay/phản chiếu, thuộc tính, chuỗi POLYLINE, lỗ, text, DIM và thứ tự vẽ SORTENTS. Dựng lại chỉ mục `BLKREFS` theo các INSERT thực tế, kể cả trong definition không còn được đặt. Chỉ nhận đúng cấu trúc chỉ mục đã hỗ trợ; các pointer native khác vẫn được kiểm tra.
- Ánh xạ kiểm chứng thao tác sửa sang instance sống trong file xuất; không dùng sự tồn tại của definition cũ làm bằng chứng rằng hình đang đặt đã đúng. Kiểm tra binding đường dẫn → definition, danh mục member, thuộc tính đặt block và nội dung clone trước/sau ODA.
- Từ chối cô lập khi có dữ liệu động, reactor, proxy hoặc tham chiếu hình học vượt definition chưa có adapter. Không gỡ association để ép xuất.
- Trong bước mở lại DWG, chấp nhận ODA cấp lại handle đã trống cho tài nguyên `SCALE`; không chấp nhận một hình LINE hoặc đối tượng native tùy ý thay cho hình đã bỏ. Trước chuyển đổi, handle bị bỏ phải vắng mặt. MTEXT không khai báo width được đối chiếu như width 0 (không giới hạn chiều rộng).
- Chính sách xuất tăng lên **4**; yêu cầu mới không dùng lại tác vụ selection của chính sách cũ. Không xóa các link tải cũ vẫn đúng hash. Bản tạm được dọn sau thành công hoặc lỗi.

Tài nguyên và definition không còn được đặt vẫn có thể nằm trong file. Đây không phải chức năng purge dữ liệu bí mật.

## Bằng chứng

**1.043 kiểm thử Python đạt**, 154,93 giây; log `storage/validation-fixtures/pytest-export-isolation-verified-2026-10-15.txt`. Vẫn 19 file test; không xóa kiểm tra chức năng để làm gọn số liệu. Các warning đến từ thư viện đang dùng, không có kiểm thử thất bại trong lượt cuối.

Bốn trường hợp xuất độc lập qua ODA thật: ba DWG (block lồng thường, xoay/tỷ lệ, phản chiếu) và một DXF nguồn. Mỗi file có bốn khung trong hai instance dùng chung; chọn PART-A ở instance đầu và PART-B ở instance sau. DWG mở lại chỉ có hai khung được chọn, số đo/BOM đúng nguồn, giữ SORTENTS; nguồn không đổi. Biên nhận: `storage/validation-fixtures/shared-export-masks-c96ab922/receipts.json`. Đây là kiểm tra exporter, không phải tuyên bố đã tự lập kế hoạch sửa mọi kết cấu.

Ba luồng API upload → chọn khung → sửa 100 → 80 mm → duyệt → tải DWG → ODA mở lại cũng đã chạy hồi quy trên backend mới nhất; hình bên cạnh và bản sao ngoài khung giữ nguyên trong bản làm việc. Biên nhận: `storage/validation-fixtures/source-scopes-dwg-165849f8/receipts.json`. Đã chạy lại kiểm tra JavaScript về hàng đợi xuất, tải, phục hồi sau reload và cô lập tài liệu.

Đã xuất lại và tải HTTP 200 bản **xem trước** Dauphine `c75fb805`, DWG `AC1032`, 2.231.055 byte; hash nguồn và DXF làm việc không đổi. Duyệt toàn sản phẩm vẫn trả 422. Biên nhận: `storage/validation-fixtures/dauphine-export-isolation-preview-2026-10-15.json`. Không chỉnh thêm geometry của Dauphine trong lượt này.

## Phần còn thiếu

**Chưa hoàn thành sửa đúng mọi DWG hoặc backup toàn Dauphine.** Block động/proxy, quan hệ thiết kế thiếu bằng chứng và những hình cụm/lắp bên trong/phối cảnh/uốn/đệm đóng gói chưa được ràng buộc đầy đủ vẫn còn giới hạn. Khả năng cô lập/xuất block không thay thế việc chứng minh các liên kết đó.

Mã chính: `cad/nested_scope_export.py`, `cad/scoped_export.py`, `backend/services/revision_service.py`. Các kiểm tra mới nằm trong những file test hiện có; vẫn giữ 19 file Python.
