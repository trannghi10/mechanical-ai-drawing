# Bảng đề xuất và báo cáo preview — 15/10/2026

Đã kiểm tra trực tiếp trang của kế hoạch `65f1111cc5344c5c9ddd2d09eee1c0d1`, bản vẽ `3D337A` trong Dauphine. Dữ liệu đề xuất không rỗng: có 400 edit, gồm 265 hình học, 72 annotation và 63 BOM; kế hoạch đầy đủ đã bị chặn, snapshot preview riêng vẫn có 400 thao tác.

## Đã sửa

- Bảng đề xuất mở sẵn, gồm STT nguồn, mã chi tiết, hiện tại và đề xuất. STT được lấy từ BOM của khung đã chọn, không lấy mã vật tư làm STT. Những vật tư chỉ có ở khung liên quan có nhãn riêng; thiếu binding STT thì hiển thị rõ.
- Ghép các mirror/bảng/annotation trùng; giữ binding bằng ref ô nguồn. Các snapshot JSON DIM/tọa độ được tính là thao tác CAD, không đổ vào ô quy cách. Thay đổi vật liệu và ghi chú đi kèm đặt trong phần có thể mở thêm.
- Tô số khác nhau trước/sau; dòng chỉ sửa hình học có mô tả để không xuất hiện ô trống. Số lượng đối tượng hiển thị là “trong kế hoạch”, không coi như đã sửa DWG trước khi tạo revision.
- Kế hoạch đang xem không còn bị reset về “Chọn kế hoạch trước” sau refresh lịch sử. Chặn kết quả refresh cũ hoặc thuộc tài liệu khác. Nhãn revision `validated` được giải thích là đã kiểm tra CAD nhưng chưa duyệt.
- Với kế hoạch mới có preview riêng, tính báo cáo phôi uốn/đóng gói từ snapshot thao tác preview đã kiểm chứng, thay vì từ danh sách thao tác của kế hoạch đầy đủ đã bị xóa vì còn câu hỏi. Với lịch sử chưa có báo cáo này, giao diện hướng dẫn đọc kết quả trên revision và giữ nút xem CAD đóng gói; không diễn giải báo cáo đầy đủ bị chặn thành kết quả preview.

## Kiểm chứng

**889 kiểm thử Python đạt**, log `storage/validation-fixtures/pytest-proposal-preview-final-2026-10-15.txt`. Các script Node `verify_frontend.js`, `verify_packaging_ui.js` và `verify_proposal_materials_ui.js` đạt; có kiểm tra binding STT, nguồn không đổi, mirror trùng, số STT trùng giữa các bảng, dữ liệu JSON và refresh đến sai thứ tự.

Đã mở lại giao diện bằng trình duyệt thật. Bảng nguồn của kế hoạch trên hiện đúng 14 dòng thay đổi theo STT 4, 5, 8–18 và 21. Các mã/thùng ở khung khác được tách nhãn, kế hoạch đã chọn vẫn là `65f1111c`. Ảnh: `storage/validation-fixtures/proposal-materials-65f1111c-fixed.png`.

Đã chạy lại đúng yêu cầu qua API thật trên #3D337A, không tạo/sửa DWG: kế hoạch mới `4325bf225f4440da947caa816ada96dd`, planner `checked_atomic_compound`, mất 123 giây để đọc CAD và kiểm tra scope lớn. Báo cáo preview nay xác nhận phôi 1374 → 1375,008 mm theo quy tắc nguồn và một bản cắt; báo cáo của kế hoạch đầy đủ bị chặn trước đó nói thiếu DIM phôi vì không còn operations. Đóng gói vẫn `unresolved_packaging` dù đã có các envelope/lớp đệm được cập nhật trong kế hoạch. Kế hoạch mới vẫn không được thực thi như backup đầy đủ. Kết quả API: `storage/validation-fixtures/proposal-preview-recheck-public.json`.

## Trạng thái backup

Sửa giao diện/báo cáo không làm backup đầy đủ. Kế hoạch đã cung cấp vẫn còn thiếu bằng chứng lắp ghép cho các mã `8.1.05060.013`, `8.1.05190.002`, `8.1.05191.002`, `8.1.05192.002`. Các hình cụm, phôi và đóng gói còn phải qua kiểm tra coverage tương ứng. Những DIM 697 mm đã đạt không chứng nhận toàn sản phẩm. Không bỏ chốt duyệt hoặc sửa file DWG khách hàng trong đợt này.
