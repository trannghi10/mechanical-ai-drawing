# Kiểm tra bản sửa chưa hoàn chỉnh — 15/10/2026

## Kết luận về Dauphine

Revision `c75fb80591264eacbfef7a78b2f378a3` vẫn là bản sửa một phần. Lượt này chưa tạo backup toàn sản phẩm và không đổi geometry của bản nguồn hoặc bản làm việc đó. Xuất/tải DWG thành công không thay thế nghiệm thu kích thước và kết cấu.

Đã đối chiếu trực tiếp CAD nguồn và DXF đã sửa:

- Sáu DIM khung nguồn 724 mm đo lại 697 mm.
- Hình cụm C4, khung `3ADF05`: DIM tổng `3AE2F1` là 721 → 695 mm. Thanh số 4 có biên dạng dài 692 mm theo quyết định giữ khe hở 0,5 mm mỗi đầu.
- DIM `3AF163` là 717 → 693 mm. Điểm đo nằm trên các mặt trong tấm; đây là khoảng lọt lòng, không đủ bằng chứng để thay nó thành chiều dài cắt 692 mm. Không tự sửa mọi số 693 thành 692.
- Ba thanh ngang `8.1.05190.002`, `8.1.05191.002`, `8.1.05192.002` và chốt `8.1.05060.013` vẫn chưa đủ binding mặt lắp/geometry. Một số hình cụm, phối cảnh và đệm đóng gói còn chưa đồng bộ.

Các ảnh nguồn để đối chiếu nằm trong `storage/validation-fixtures/incomplete-edit-audit-2026-10-15/`. Chúng không phải ảnh của một backup đã hoàn chỉnh.

## Lỗi engine đã sửa

`graph/core_stack_views.py` trước đây tính DIM theo các mặt tầng chung, có thể đưa DIM gắn với thanh về khoảng lọt lòng thay vì chiều dài thanh khi có khe hở. Nay engine tính lại điểm đo theo `DIMASSOC` của geometry thật, sau khi có đủ thao tác hình học. Cũng nhận các DIM có nhãn nằm ngoài vùng hình. Các DIM khoảng lọt lòng không có binding vào thanh vẫn đo theo mặt tấm; giữ liên kết native và kiểm tra lại trước ghi.

Trường hợp kiểm chứng độc lập: cụm cao 80 → 60 mm, tấm 2 → 1 mm trong hình, thanh có khe hở 0,5 mm mỗi đầu. Sau ghi và ODA mở lại DWG, thanh và DIM native dài **57 mm**, khoảng lọt lòng **58 mm**, tổng **60 mm**. DIMASSOC được giữ. Biên nhận: `storage/validation-fixtures/native-core-dimensions-53f50cda/report.json`. Đây là kiểm tra kernel với ràng buộc kỹ thuật cung cấp rõ, không chứng minh đã tự hiểu toàn bộ sản phẩm.

**1.045 kiểm thử Python đạt** trong 162,18 giây; vẫn 19 file test. Log: `storage/validation-fixtures/pytest-core-native-dimensions-release-2026-10-15.txt`.

## Quyết định mới của người dùng

Với ba thanh ngang số 1–3: **tính lại chiều dài theo mặt lắp mới, giữ khe hở nguồn**. Đã lưu trong `design-decisions-v1.json`, ràng buộc đúng hash nguồn Dauphine `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

Quyết định này không tự chứng minh hai mặt nào thuộc từng đầu thanh. Cặp mặt lắp đang cần xác định; không lấy chính sách giữ khe hở làm bằng chứng để bỏ chặn hoặc đổi chiều dài tùy ý. Chưa hoàn thành khả năng sửa đúng mọi DWG.
