# Kết quả thử Gemini 3.8 Flash — 08/10/2026

Người dùng đã xác nhận cho phép gửi ảnh và dữ liệu CAD trong phạm vi chọn, cùng khung liên quan, tới Google để thử phân tích.

Yêu cầu thử: chi tiết số 6, hộp 30 × 60, thành 2 → 1.2 mm, giữ kích thước ngoài, chiều dài và vị trí lỗ; đồng bộ bảng kê và chi tiết lắp có bằng chứng. Khung gốc 43C372 trong file LEG6949.

## Quan sát thực tế

- API key truy cập được gemini-3.8-flash. Kiểm tra kế hoạch JSON bằng dữ liệu giả thành công.
- Gửi riêng ảnh mặt cắt thật thành công. Model nhận đúng hộp 30 × 60 × 2 mm.
- Gửi cùng ảnh và schema hai trường thành công: wall_mm=2, outside_mm=[60,30].
- Hai lần chạy luồng lập kế hoạch trên file thật thất bại; lần có thông báo chi tiết trả HTTP 503.
- Các bài thử schema lớn hơn, gồm định dạng responseFormat mới, cũng trả 503. Google ghi UNAVAILABLE và thông báo model đang có nhu cầu cao. Chưa đủ bằng chứng kết luận schema là nguyên nhân.
- Không có revision sản xuất được tạo. Không có DWG sửa thử được xuất. Hash DWG gốc và DXF nguồn giữ nguyên so với baseline.

## Thay đổi hỗ trợ kiểm tra

Gửi inventory theo tổng quan và truy xuất geometry khi cần, không đổi thuật toán nhận diện bản vẽ. Hiện thông báo riêng cho lỗi Google 500/503. 19 bài kiểm thử liên quan tới Gemini, kế hoạch thay đổi và ràng buộc lắp ghép đạt.

Kết quả đọc ảnh và JSON đơn giản không chứng minh đã tự sửa được geometry, bảng kê hoặc toàn bộ chi tiết phụ thuộc. Cần một kế hoạch thực thi hợp lệ, kiểm tra bản sửa và xem trước trước khi xuất DWG.
