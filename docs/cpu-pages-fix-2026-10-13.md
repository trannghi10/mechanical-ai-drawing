# Sửa lỗi phạm vi CAD 23.150 tokens — 13/10/2026

Đã tái hiện đúng tác vụ Dauphine `567da24b029b4cef8b8eadd5fb596826`, chọn khung `3D337A`. Yêu cầu có hai thay đổi nối bằng dấu phẩy và cụm “chiều cao tổng thể sản phẩm”; bộ phân tích cũ không bắt được hai mệnh đề nên chuyển sang gửi phạm vi bảng kê/liên kết lớn cho model 8.192 tokens.

## Thay đổi

- Tách dấu phẩy chỉ khi theo sau là một lệnh rõ ràng. Dấu phẩy thập phân, mã vật tư và mốc giữ được giữ nguyên.
- Bộ sửa chiều cao tổng thể dùng các lựa chọn người dùng gắn với hash nguồn: thành phẩm 727 → 700, khung 724 → 697, giữ đáy. Nó chỉ sửa các hình có DIM và chủ sở hữu nguồn đã kiểm tra; không chứng nhận toàn cụm từ các hình này.
- Model nội bộ dùng `source_pages_v1`: dữ liệu vật tư, chi tiết, hình học, liên kết, công đoạn và quyết định được đọc theo trang. Mỗi trang có số lượng, cursor và trạng thái hoàn tất. CAD đầy đủ ở server, không bị xóa/cắt khỏi nguồn.
- `geometry_requests` và `context_requests` được trả qua các trang `requested_records`, kể cả các đối tượng bên trong block. Lấy quá bốn đối tượng không làm mất những ref còn lại; chúng vẫn lấy được bằng cursor.
- Trường CAD dài có thể lấy dưới dạng các mảnh JSON có thứ tự rồi khôi phục nguyên văn. Query hình học vẫn trả đúng các ref được lọc theo vùng/loại.
- Kiểm tra token vẫn chạy trên runtime thật trước suy luận. Vượt ngân sách sẽ tự giảm kích thước trang và thử lại; không tăng bộ nhớ model hay chuyển sang cloud. Luồng giải ý định ban đầu cũng chuyển sang các trang nguồn khi vượt ngân sách.

## Bằng chứng

Scope 71 khung, 37.845 thực thể của nguồn Dauphine: runtime Qwen đếm **2.478 tokens** cho trang nguồn và ảnh 512 px, dưới ngân sách CPU 4.096 và slot 8.192. Bằng chứng: `storage/validation-fixtures/cpu-pages-token-proof.json`. Đây là phép đo chuẩn bị dữ liệu, không phải khẳng định model đã hiểu/sửa toàn sản phẩm.

Đã gửi lại **đúng câu yêu cầu và đúng khung cũ** qua `/planning-jobs`. Tác vụ `bfab9b866bfa425bb6a12cb174cb8189` hoàn tất sau 91 giây, tạo kế hoạch `8d1f423db8ac435b9fbb961038522896` bằng `checked_atomic_compound`, không gọi model, có 209 thao tác. Cả hai mệnh đề được biên dịch. Receipt: `storage/validation-fixtures/cpu-pages-public-request.json`.

Luồng tạo bản sửa qua API của giao diện đã chạy thành công: 17 kiểm tra FreeCAD, chuyển đổi ODA và tải HTTP 200. Revision `090ca8c37c8e46a2b9884d39b0268cfd` có 199 thay đổi native sau khi gom thao tác trên định nghĩa block chung; kế hoạch có 209 thao tác trên các instance. File `storage/backups/Dauphine-PREVIEW-loi23150-da-sua.dwg`, 2.201.607 bytes, SHA256 `2b4897eb31708dc1d68d8569347282c5b7f1cd7b1c06f4be3b85054a252123bc`. Bước tạo và xuất sau khi đã có kế hoạch mất 120,75 giây. Receipt: `storage/validation-fixtures/cpu-pages-public-export.json`. Bản sửa này được đánh dấu xem trước một phần; trạng thái ấy được xác định lại khi mở kế hoạch đã lưu, không dựa vào checkbox do model tạo.

682 kiểm thử đạt. Log: `storage/validation-fixtures/pytest-cpu-pages-20261013.txt`. Có kiểm thử 300 dòng BOM, khôi phục nội dung dài nguyên văn, scope/ref không tồn tại, giảm ngân sách, nhiều ref được yêu cầu, luồng query → lấy geometry → sửa thật trong DXF và các quyết định chiều cao mâu thuẫn.

## Giới hạn và sử dụng

Nạp lại trang Explorer và bấm phân tích lại. Tác vụ thất bại cũ không tự biến thành kế hoạch mới. Không cần đổi API hoặc tăng context lên 32k để thử lại yêu cầu này.

Sửa lỗi bộ nhớ không hoàn tất khả năng sửa mọi DWG. Hình cụm, chi tiết lắp bên trong, phối cảnh và lớp đệm Dauphine chưa đồng bộ đầy đủ vẫn chặn duyệt backup toàn sản phẩm. Chỉ tải bản xem trước cho các thao tác đã kiểm chứng.
