# Liên kết mặt lắp theo STT/BOM — 20/10/2026

## Thay đổi áp dụng cho file mới

Block không cần mang mã vật tư trong tên. Engine có thể nhận một thân chi tiết qua dòng BOM cục bộ, STT, đầu leader và biên kín đã đối chiếu. Việc nhận toàn bộ block yêu cầu chỉ có một thân đã xác định, các lỗ nằm trọn trong vật liệu và không còn nét/đối tượng lồng chưa rõ chủ sở hữu. Mã thuộc tính trái với BOM, nhiều biên, DIM chưa gắn, lỗ ngoài thân hoặc thiếu STT đều không được nhận.

Chi tiết nhận dịch chuyển không bắt buộc có DIM riêng nếu thân và mặt tiếp xúc đã được xác định. Engine giải vị trí từ mặt tiếp xúc thật, giữ hình/lỗ, cập nhật đầu leader và DIM tổng. Thân chưa có DIM không được cấp quyền co/giãn kích thước. Cụm xoay được tính trong hệ trục của mặt lắp; các thao tác xuất vẫn giữ tọa độ CAD gốc. Mọi bằng chứng được tính lại khi tạo bản sửa và duyệt.

Đã sửa thêm lỗi xuất AutoCAD: bản sao `AI_COPY_…` của block `*U…` giữ nhầm cờ anonymous. AutoCAD bỏ BlockTableRecord, INSERT có block_handle=0 và DXFOUT báo eNullObjectId. Bản sao có tên thông thường hiện bỏ riêng bit anonymous; các cờ khác, định nghĩa nguồn và instance không chọn được giữ nguyên. Không sửa plugin, không tự chuyển sang APS/ODA để bỏ qua kiểm tra.

## Luồng website đã chạy

DWG tổng hợp mới, ba khung được bộ đọc tự phát hiện, hai block ẩn danh, cụm xoay 23°, thân nhận dịch chuyển không có DIM riêng:

1. Upload DWG và chọn khung chi tiết.
2. Nhập `Chi tiết số 1 chiều cao từ 100 thành 80 mm, giữ đầu dưới`.
3. Tạo bản sửa; chi tiết kề dịch theo mặt lắp, DIM tổng 200 → 180 mm, STT/leader đi cùng.
4. Mở preview từng khung, duyệt, xuất bằng AutoCAD local và tải HTTP 200.
5. ODA mở lại DWG tải về và đo đúng vị trí cùng số đo; nguồn giữ nguyên.

- [DWG đã tải](../storage/validation-fixtures/leader-mount-198ef54e/download/leader-mount-backup.dwg)
- [Receipt](../storage/validation-fixtures/leader-mount-198ef54e/receipt.json)
- [Bằng chứng lỗi xuất và cách sửa](../storage/validation-fixtures/leader-mount-198ef54e/native-export-fix.json)
- [Mở phiên bản trên website](http://127.0.0.1:8765/explorer?doc=9c8ccb0e1fe44850a541d530d91f9f0e&target=B6&revision=72b01eaf931c4bb1a1486ba958822127)

Chạy lại bằng `python scripts/verify_general_dwg_workflow.py --anonymous-mount`. Đây là dữ liệu tổng hợp được đánh dấu phụ trợ và ẩn khỏi thư viện mặc định.

Đã tải DWG kết quả lên như một tài liệu mới và yêu cầu tiếp 80 → 70 mm. Engine nhận lại BOM/STT và mặt lắp, tạo revision mới được kiểm tra với trạng thái `verified_native_2d_contacts`; lượt thứ hai chưa xuất DWG. Bằng chứng `storage/validation-fixtures/leader-mount-198ef54e/repeat-edit.json`.

## Đối chiếu file khách hàng thực tế

Đã đọc lại MR-106 và Dauphine, giữ hash nguồn. Không gửi CAD khách hàng lên cloud.

- Dauphine: nhận thêm ba thân block ẩn danh cho mã 8.1.06128.196 và 8.1.06131.196 qua chuỗi BOM/STT/DIM. Tìm thêm được các bản chi tiết tương ứng. Tuy nhiên ba thân này không có cặp mặt tiếp xúc trực tiếp đã chứng minh trong phạm vi nguồn; kế hoạch xem trước cũ không có thêm thao tác lắp ghép từ quy tắc này. **Không tạo hoặc nghiệm thu backup toàn Dauphine.**
- MR-106 khung đang mở: hình cụm không có DIM đo thật; leader số 7 khớp hai vùng elip bao quanh trong hình phối cảnh. Không lấy vùng gần nhất hoặc gán mã cho toàn bộ cụm. Các hình này còn cần đối chiếu biên/mặt và quy tắc chiếu trước khi tự sửa.

Bằng chứng: `storage/validation-fixtures/leader-mount-customer-audit-2026-10-20.json`, `leader-mount-dauphine-final-audit-2026-10-20.json`, `mr-assembly-mount-audit-2026-10-20.json`.

## Phạm vi chưa hoàn tất

Kiểm thử toàn dự án: **1.534 bài Python đạt**, 212,46 giây, giữ 19 module. Có kiểm tra từ chối thiếu BOM/STT, nét/lỗ không thuộc thân, block lồng chưa phân loại, DIM chưa gắn, mã thuộc tính mâu thuẫn, sửa mũi tên sai và bỏ mất dịch chuyển bắt buộc. Thêm hồi quy cờ anonymous khi cô lập block; không xóa kiểm thử cũ. Log: `storage/validation-fixtures/pytest-leader-mount-release-2026-10-20.txt`.

Chưa chứng nhận sửa đúng mọi DWG. Hình phối cảnh thiếu cặp biên tương ứng, nhiều lớp chồng, mặt tiếp xúc ẩn, mối hàn chưa có mốc, đệm đóng gói thiếu hướng đặt, block động lồng phức tạp và proxy chưa có adapter vẫn giữ trạng thái cần đối chiếu. Nhận diện đúng tên/STT không tự chứng minh quan hệ cơ khí. Các bản xem trước một phần vẫn không được duyệt thành backup hoàn chỉnh.

Sau cập nhật, phân tích lại yêu cầu và tạo một revision mới; bản sửa cũ không tự được thay nội dung hoặc nâng trạng thái nghiệm thu.
