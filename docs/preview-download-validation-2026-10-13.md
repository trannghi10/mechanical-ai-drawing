# Sửa luồng xem trước và tải DWG — 13/10/2026

## Thay đổi

- Xuất CAD chạy trong hàng đợi trên server; trả ID ngay, có trạng thái queued/running/ready/failed. Đóng trang không hủy lượt xuất. Lượt trùng dùng chung công việc/file đã kiểm chứng.
- Đường dẫn tải GET được lưu theo bản sửa, khôi phục khi mở lại bản sửa, không phụ thuộc blob URL của trang cũ. Tải file kiểm tra hash bản sửa, nguồn và file xuất; file lỗi hoặc thất lạc có thể xuất lại.
- Lượt đang chạy khi server khởi động lại được đánh dấu thất bại với hướng dẫn thử lại. Không báo sẵn sàng cho file chưa hoàn tất.
- Thêm lựa chọn **Tạo xem trước phần đã kiểm chứng** cho planner đã có thao tác CAD hợp lệ nhưng chưa đủ bao phủ liên kết/công đoạn. Giữ riêng snapshot đã kiểm chứng trước kiểm tra độ bao phủ; không xóa câu hỏi hay mở khóa kế hoạch đầy đủ. API tạo preview kiểm tra lại nguồn, recipe, ràng buộc, liên kết native và hình học.
- Yêu cầu nhiều mệnh đề chưa đủ dữ liệu không được lấy riêng ý đầu để tạo preview bằng luồng này. Phần hình học chưa có quy tắc không có snapshot xem trước.
- Bản sửa một phần có nhãn rõ trong giao diện/lịch sử; backend chặn duyệt và xuất dưới tên backup hoàn chỉnh, kể cả gọi API trực tiếp.

## Kiểm chứng thực tế

Nguồn Dauphine: document `34ee84f35e1a44fb81c56044397a0fff`, SHA256 `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

1. Đưa thí nghiệm tấm ốp đã kiểm chứng vào lịch sử bản sửa bằng `scripts/publish_checked_preview.py`. Script kiểm tra biên nhận/hash nguồn và DWG, kiểm tra lại kế hoạch và áp dụng lại thao tác vào bản sao nguồn, không sửa kế hoạch khách đang bị chặn.
   - Revision `2e4fa4b071f64eeeb42054de88ebf544`, nhãn sửa một phần.
   - Tấm ốp cao 697 mm, dày 1 mm; chi tiết kiểm chứng ở [biên nhận tấm ốp](dauphine-height-wall-validation.md).
   - Xuất selection qua API, kiểm tra DWG → DXF bằng dịch vụ xuất và tải GET HTTP 200: **1.347.463 byte**, chữ ký DWG `AC1032`.
   - SHA256 DWG tải: `397bf458552257be66487efb1fbd47e66ec9520052ab4b1c9d5a59c853b80322`.
   - Bản tải lưu tại `storage/backups/Dauphine-PREVIEW-trinh-duyet-cao697-day1.dwg`.
2. Nhập yêu cầu qua API của giao diện: **Mã 8.1.05417.258 chiều cao từ 724 mm thành 697 mm, giữ đáy**, chọn khung `3B8A74`.
   - Planner `checked_measured_profile_resize`, plan `b7930a99b0fb4cedb2c7b550fc637a87`, không có câu hỏi cho thao tác trực tiếp này.
   - Apply preview HTTP 200, revision `d57235035d084d7ab3fc9362fea7a440`, **22 thay đổi**. Đây là yêu cầu riêng về chiều cao tấm ốp, không bao gồm đổi độ dày và toàn bộ sản phẩm.
   - Xuất DWG selection, kiểm chứng chuyển đổi và tải GET HTTP 200: **1.749.050 byte**, chữ ký `AC1032`.
   - Bản tải: `storage/backups/Dauphine-PREVIEW-yeu-cau-cao697.dwg`.
   - Các phản hồi thật lưu trong `storage/validation-fixtures/live-user-request-*.json`.
3. LEG6949: nhập **thay đổi chi tiết số 6 hộp 30x60 dày 2 mm thành dày 1.2 mm**, chọn khung `43C372`.
   - Kế hoạch đầy đủ vẫn bị chặn bởi các liên kết của `3.1.00766`, `8.1.07013.121`, `9.1.05415`; có snapshot preview đã kiểm chứng cho hộp và bốn bas liên quan.
   - API `apply-checked-preview` HTTP 200, revision `d757f79077e741d5b66b0c9dd394005b`, 18 khung trong phạm vi, **16.025 thay đổi ghi nhận**, `complete_product_backup=false`.
   - Xuất/đọc lại/tải DWG HTTP 200, **2.942.830 byte**, SHA256 `0b064da7c3a38762ca1134a45deba34353f6f92a220a01059eca5adb78e43bd5`.
   - File `storage/backups/LEG6949-PREVIEW-hop1.2-bas-lien-quan.dwg`; phản hồi thật `storage/validation-fixtures/live-leg-checked-preview-*.json`.
   - Không tuyên bố đã đồng bộ các liên kết còn thiếu. Kế hoạch đầy đủ và trạng thái chặn vẫn được giữ nguyên.

## Kiểm thử và giới hạn

- 453 kiểm thử Python đạt; log `storage/validation-fixtures/pytest-download-jobs-20261013.txt`.
- 7 script JavaScript đạt, gồm hàng đợi xuất/tải, khôi phục liên kết khi mở lại trang, điều hướng CAD, chuyển tài liệu, danh sách tài liệu, BOM và đóng gói.
- Đã mở Explorer, thấy nhãn sửa một phần và đường dẫn tải đã lưu; tải trực tiếp bằng liên kết trên giao diện thành công vào `C:\Users\nghi.tran\Downloads\PREVIEW-backup-2e4fa4b0.dwg`. Lần mở đầu công cụ trình duyệt bị timeout, lần kiểm tra lại thành công.
- **Chưa phải backup Dauphine đầy đủ**: còn các thanh/tấm khác, hình cụm/phối cảnh, phôi triển khai sau uốn và toàn bộ thùng/xốp. Chưa chứng minh khả năng tự sửa mọi DWG bất kỳ.
