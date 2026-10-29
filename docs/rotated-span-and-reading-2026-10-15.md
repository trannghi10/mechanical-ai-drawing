# Co/giãn cụm xoay và đọc CAD — 15/10/2026

Đã mở rộng engine dùng chung cho chi tiết 2D nằm giữa hai mặt lắp của cụm xoay. Bản sửa toàn Dauphine và khả năng sửa đúng mọi DWG vẫn chưa hoàn thành; các kết quả bên dưới không thay thế nghiệm thu toàn sản phẩm.

## Thay đổi chức năng

- Suy ra hệ trục phân tích từ DIM và hình học nguồn của các chi tiết được sửa. Co/giãn chi tiết nhận để giữ hai mốc ngoài và khe hở đo thật, rồi tính vị trí/DIM cụm trong hệ trục đó. Không quay hoặc đổi tọa độ native của file để thực hiện sửa.
- Ràng buộc lưu thêm `analysis_angle`; khi tạo/duyệt bản sửa, engine dựng lại góc từ nguồn. Kế hoạch cũ theo X/Y có giá trị mặc định 0. Góc, DIM, BOM, hình hoặc thao tác dịch chuyển bị thay đổi/thiếu đều không được coi là đạt.
- Đọc nội dung `TOLERANCE`, hình học `XLINE`/`RAY` và các điểm định nghĩa/ghi chú `ARC_DIMENSION`. Số đo cung được ghi rõ là giá trị lưu trong nguồn; không tự coi là số đo đã tái tính hoặc đã sửa.
- Ghi JSON trạng thái bằng file tạm riêng, thử lại lỗi khóa file Windows trong thời gian giới hạn. Lỗi tác vụ đọc nền được trả về qua trạng thái tài liệu thay vì để giao diện chờ vô hạn.
- Kết quả phân tích hiện ngay “Phần chưa hoàn tất”, kèm mã/STT chi tiết, nguyên nhân hoặc DIM chưa đạt; không chỉ hiện thông báo xem trước chung.

## DWG mới đã kiểm chứng

Ba file tổng hợp riêng đã chạy qua API thật: upload DWG → chọn phạm vi → yêu cầu nhiều mệnh đề → tự tìm chi tiết nhận → tạo bản sửa → xem trước → duyệt → tải DWG → ODA mở lại.

| Trường hợp | Chi tiết nhận sau sửa | Khe hở giữ lại | Thời gian đầu cuối |
| --- | --- | --- | --- |
| Cụm lồng xoay 30° | 110 mm | 0 mm | 4,318 giây |
| POLYLINE có rãnh, cụm xoay −35° | 90 mm | 0 mm | 3,686 giây |
| Cụm có rãnh xoay 73°, khe hở DIM thật | 110 mm | 2 mm | 3,821 giây |

Đã đối chiếu đường bao native của các hình chi tiết nhận, số đo DIM, vị trí lắp, BOM và kích thước ngoài cụm. Hash nguồn giữ nguyên. Không cung cấp mapping riêng hoặc liên kết tham số thủ công cho engine.

Bằng chứng: `storage/validation-fixtures/native-span-dwg-dd3dc39a/receipts.json`. Chạy lại bằng `python scripts/verify_native_span_dwg.py --rotated`. Các upload thử đã được đánh dấu để không lẫn với tài liệu khách hàng trong danh mục mặc định.

## Đọc các file thực tế

Đã kiểm kê Model/Layout và mọi block definition, kể cả anonymous/system blocks, trên Dauphine, MR-106, Sample_recover và LEG6949. Báo cáo phân biệt số bản ghi ở các vùng với số handle duy nhất, lỗi phân tích và đối tượng chỉ đọc được metadata.

| File | Định nghĩa block, gồm block hệ thống | Entity duy nhất | Lỗi phân tích | Chỉ có metadata |
| --- | --- | --- | --- | --- |
| Dauphine | 1.457 | 39.917 | 0 | 6 OLE2FRAME |
| MR-106 | 469 | 10.067 | 0 | 13 OLE2FRAME |
| Sample_recover | 1.044 | 13.105 | 0 | 2 OLE2FRAME |
| LEG6949 | 1.468 | 118.746 | 0 | 4 OLE2FRAME |

Bằng chứng: `storage/validation-fixtures/read-audit-2026-10-15.json`. Việc kiểm kê được entity không có nghĩa đã hiểu quan hệ lắp ghép hoặc có adapter sửa đối tượng đó. OLE nhúng vẫn chưa được đọc nội dung.

## Kiểm thử và dịch vụ

- **926/926 kiểm thử Python đạt** trong 123,27 giây trên bản mã cuối; log `storage/validation-fixtures/pytest-reading-span-ready-2026-10-15.txt`.
- Toàn bộ 11 script xác minh JavaScript đạt, gồm tải/xuất, lựa chọn tài liệu, đề xuất vật tư, liên kết tham số và trạng thái phân tích.
- Backend đã nạp mã mới ở cổng 8765, `/health` trả 200. Ba bản DWG kiểm chứng đã duyệt vẫn tải lại được sau restart, hash khớp biên nhận.
- File thử từng kẹt trạng thái đọc đã được xử lý lại thành công. Bằng chứng dịch vụ: `storage/validation-fixtures/reading-span-live-2026-10-15.json`.

## Phần chưa hoàn thành

- Kế hoạch Dauphine gần nhất vẫn thiếu kiểm chứng liên kết công đoạn cho các mã `8.1.05060.013`, `8.1.05190.002`, `8.1.05191.002`, `8.1.05192.002`; hình cụm và đóng gói chưa được chứng nhận đồng bộ toàn bộ.
- Block động, proxy association, XREF thiếu dữ liệu, phối cảnh không có mapping và quan hệ thiết kế chưa được xác định vẫn cần adapter/bằng chứng tương ứng.
- Bộ giải mới dành cho hình native 2D có profile, danh tính, DIM và mặt lắp được chứng minh. Không suy ra tiếp xúc 3D ẩn, độ bền, hoặc thông số uốn của xưởng.

Không đổi model/API, không thêm công cụ trả phí, không sửa file gốc của khách hàng và không thay bộ nhận diện/chọn khung.
