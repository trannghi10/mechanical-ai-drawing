# Đối chiếu yêu cầu và mở rộng sửa DWG — 13/10/2026

Người dùng báo bản sửa chưa đáp ứng yêu cầu. Đã kiểm tra số đo nguồn và kế hoạch Dauphine: tấm ốp đạt 697 mm, nhưng ba DIM của khung `8.1.05234.265` vẫn 724 mm. Vì vậy việc xuất được DWG không chứng minh toàn sản phẩm đã sửa đúng.

## Sửa kiểm tra liên kết

Đã bỏ hai điều kiện cho phép một lựa chọn `height_anchor` bỏ qua chi tiết/công đoạn chưa có quy tắc. Mốc giữ chỉ xác định chuyển động; không thay bằng chứng chủ sở hữu, tiếp xúc hay thao tác thực thi. Kiểm thử bảo đảm chọn giữ đáy vẫn chặn chi tiết chưa xác minh.

`graph/request_fulfillment.py` đối chiếu từng DIM chiều cao có chủ sở hữu nguồn: trước, đích, sau và trạng thái. Giao diện hiện bảng này và phân biệt thao tác CAD đã kiểm tra với toàn bộ mục tiêu sản phẩm. Kế hoạch thiếu liên kết dùng luồng xem trước riêng, không dùng luồng hoàn chỉnh.

## Sửa thêm hình khung Dauphine

BOM công đoạn sau của cùng mã sản phẩm có thể dùng mã khung khác trang BOM đầu. Engine nay lấy các mã ấy từ bảng kê đã xác minh và tiêu đề sản phẩm đúng nguồn. Không ghép các chi tiết chỉ vì cùng con số chiều cao.

Khi một hình cùng mã không hỗ trợ, engine thử độc lập từng đường bao/DIM đã xác minh, giữ toàn bộ entity để kiểm tra ownership/giao cắt. Không đổi khung tên của hình chưa sửa được. Dauphine đã thêm hai DIM `3C75E2` và `3D29F8` từ 724 → 697 mm. Tổng đối chiếu đạt 5/6 DIM; `3B62C6` trong hình cụm hàn vẫn 724 mm do block lắp bên trong chưa có binding đủ.

Các receipt cũ vẫn ghi đúng lịch sử tại thời điểm tạo. Bảng so sánh trước nâng cấp: `storage/validation-fixtures/dauphine-goal-coverage-20261013.json`; kế hoạch thử cải thiện: `storage/validation-fixtures/dauphine-height-subset-improved.json`. Các hình cụm khác, tấm bên trong và đệm đóng gói chưa được coi là hoàn tất.

Đã chạy lại yêu cầu qua API của giao diện, tạo kế hoạch `e29ee929e88246deaded6ce39c0a2b46` sau 79 giây: luồng hoàn chỉnh bị chặn đúng, luồng xem trước riêng vẫn dùng được. Revision `fd7444290c2a43d6b3132ef7504646e3` có 215 thay đổi native và 19 mặt trước/sau được FreeCAD kiểm tra. File `storage/backups/Dauphine-PREVIEW-them-2-hinh-khung.dwg`, SHA256 `d779573009fd7bda8174eac1b11dc67830e995fb0d8ef32734c290b6f5b0c5f1`, đã tải HTTP 200 và ODA mở lại đo hai DIM mới 697 mm; DIM cụm hàn còn 724 mm. Đã thử duyệt và nhận chặn HTTP 422. Receipt: `storage/validation-fixtures/dauphine-fulfillment-public.json` và `dauphine-fulfillment-export.json`.

## Sửa lỗ trên DWG mới

Đã thêm `HoleResize` và bộ biên dịch câu lệnh đổi đường kính lỗ tròn giữ tâm. Cần phôi kín có chủ sở hữu và DIM nguồn, lỗ duy nhất hoặc lựa chọn trái/phải không mơ hồ. Giữ tâm, đường bao và lỗ khác; sửa DIM bán kính và DIM đường kính đo thật. Kiểm tra tất cả lỗ, khoảng hở tới biên và giao nhau bằng cả engine CAD và FreeCAD/OpenCASCADE.

Những ghi chú/BOM có quy cách lỗ ghép nhóm chưa có binding hoặc DIM có proxy association vẫn không được sửa bằng cách thay chữ. Adapter DIM đường kính mới giữ loại DIM, điểm đo và dung sai; association không hỗ trợ bị chặn, không bị tháo bỏ.

Hai DWG mẫu độc lập, tên/handle mới, block lồng 8 và 12 cấp đã đi đủ luồng upload → sửa → SVG preview → duyệt → tải DWG → ODA mở lại. Lỗ được chọn 4 → 6 mm, tâm giữ nguyên, lỗ còn lại 4 mm, chiều dài phôi 140 mm giữ nguyên. DIM bán kính đo 3 mm, DIM đường kính đo 6 mm.

- Mẫu 8 cấp: `storage/validation-fixtures/hole-dwg-f9ec5758/receipt.json`, `download/hole-backup.dwg`.
- Mẫu 12 cấp: `storage/validation-fixtures/hole-dwg-8b43bdb1/receipt.json`, `download/hole-backup.dwg`.

Đây là kiểm chứng một khả năng dùng chung mới, không phải chứng nhận sửa mọi DWG. Hai file mẫu này không thay thế backup Dauphine.

695 kiểm thử đạt, gồm chặn DIM lỗ có tỷ lệ mâu thuẫn với DIM phôi. Log: `storage/validation-fixtures/pytest-fulfillment-holes-20261013.txt`. Giao diện qua kiểm tra cú pháp JavaScript. Script tái kiểm chứng: `scripts/verify_hole_dwg_workflow.py --depth 8` hoặc `--depth 12`.
