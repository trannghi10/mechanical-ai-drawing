# Dọn dự án, trình bày và tải DWG — 15/10/2026

## Dọn dữ liệu có thể khôi phục

- Đã sao lưu **366 file, 8.891.638 byte** vào `storage/archives/cleanup-20261015-093828/recoverable.zip`: thư mục thử `scratch`, 52 script khảo sát/debug theo file cụ thể và 13 bản tải thử cũ được biên nhận xác định là dữ liệu tổng hợp.
- Đã so hash từng file trong ZIP trước khi gỡ **365 file** khỏi vị trí cũ; một helper FreeCAD còn được script kiểm chứng gọi đã được giữ lại. danh sách đường dẫn/hash ở `manifest.json` cùng thư mục. Giải nén ZIP vào thư mục gốc dự án sẽ khôi phục đúng cấu trúc đường dẫn.
- Giữ nguyên thư mục `tests`, các script `verify_*`, runtime, bản vẽ khách hàng, backup và dữ liệu mà mã kiểm chứng đang tham chiếu. Các kiểm thử có dùng chung fixture nên không xóa theo tên `test_*`.
- 19 upload thử còn dùng làm bằng chứng được đánh dấu từ biên nhận tổng hợp và ẩn bằng bộ lọc hiện có. Bật “Hiện bản trùng / file thử” hoặc mở trực tiếp ID vẫn truy cập được. Tên file lạ của khách hàng không tự bị coi là file thử.
- `scripts/cleanup_workspace.py` mặc định chỉ in danh sách; `--apply` mới thực hiện lưu trữ có kiểm tra đường dẫn trong workspace và xác minh ZIP. File cấu hình API không thuộc phạm vi dọn.

## Giao diện

Kết quả chính gồm trạng thái ngắn, kích thước được hiểu, nút **Tạo và tải DWG xem trước**, nút chỉ xem và bảng vật tư. Liên kết/công đoạn/phôi/đóng gói và cảnh báo chi tiết nằm trong các phần thu gọn. Câu hỏi giữ nguyên nội dung gốc trong phần kỹ thuật; nhãn chính nối số thứ tự vật tư khi có BOM nguồn.

Khi đã tạo bản sửa cho cùng kế hoạch, nút tải dùng lại revision đã lưu thay vì tạo thêm một revision giống nhau. Trạng thái tạo/xuất được hiển thị ngay cạnh nút; lựa chọn revision được giữ. Bảng đối chiếu mặc định hiện vật tư đã thay đổi, có nút hiện cả vật tư còn lại.

## Lỗi đã sửa

- Nút xuất trước đây chỉ tạo đường dẫn, người dùng phải tìm và bấm lần nữa. Nay thao tác xuất chủ động bắt đầu tải attachment khi file sẵn sàng, đồng thời giữ đường dẫn tải lại sau reload.
- Đường dẫn file xuất cũ không còn hợp lệ được đánh dấu lỗi, không tiếp tục hiển thị “sẵn sàng”; có thể tạo lại khi revision vẫn hợp lệ.
- Đối chiếu BOM của revision một phần đọc nhầm kế hoạch đầy đủ đã bị xóa operations. Nay dùng snapshot preview đúng hash nguồn, vẫn kiểm tra giá trị thực của các ô CAD. Dauphine #1ea6554a hiện được **14/28 vật tư thay đổi**, thay vì lỗi thiếu ô bảng kê của chi tiết 8.

## Kiểm chứng thực tế

Đã thử một lần bấm từ kế hoạch Dauphine **#7bdd90e6**: dùng lại revision **#1ea6554a**, tải thành công tới `C:\Users\nghi.tran\Downloads\PREVIEW-backup-1ea6554a.dwg`. File **2.230.384 byte**, SHA256 **579371b667569b86e07e6b9b2429864da8f082da78fa5a152a6605bc948e8f3a**, khớp DWG server đã kiểm chứng. Biên nhận: `storage/validation-fixtures/cleanup-download-receipt.json`; ảnh trình duyệt: `storage/validation-fixtures/cleanup-downloads-proof.png`.

Đây là **DWG xem trước một phần đang có**, không phải backup toàn sản phẩm mới. Nút duyệt backup hoàn chỉnh vẫn bị khóa vì còn hình cụm/công đoạn và đệm đóng gói chưa đồng bộ; không nới điều kiện kiểm tra để cho tải nhầm bản hoàn chỉnh.

**914 kiểm thử Python đạt**; các script JavaScript `verify_*.js` đều đạt. Log Python toàn bộ sau dọn: `storage/validation-fixtures/pytest-cleanup-downloads-final-2026-10-15.txt`. Bổ sung kiểm thử về file xuất mất sau reload, snapshot BOM của preview và bộ lọc upload thử có bằng chứng.
