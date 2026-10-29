# Kiểm chứng đọc khung lắp ráp — 08/10/2026

File LEG6949 trong workspace: document `baf461e9c2764a5ba9000a48772f846c`, khung gốc `43C372`. Kế hoạch kiểm tra `312d1eb2519d4c698fd2b114275c16fa` dùng yêu cầu đổi hộp số 6 từ dày 2 xuống 1,2 mm, giữ độ vừa khít và kiểm tra công đoạn.

Graph phiên bản 7 đọc được 24 mã chi tiết, 41 bảng CAD và 34 khung đang sử dụng. Sáu liên kết ghi chú gồm 2 → 3 và 6 → 3 trong cụm C1, 6 → 4 lắp vừa, cùng 2/3/6 → 1 qua ghi chú hàn cụm C1. Số/mã được nối qua BOM kim loại nhất quán cùng sản phẩm; BOM đóng gói trùng số được tách bằng nhãn vật liệu nguồn. Các cạnh này không tự chứng minh mặt tiếp xúc hoặc quy tắc sửa.

Lượt AI nội bộ đã hoàn tất với Qwen3-VL 4B trên CPU. Model nhận bốn ảnh khung `434BBD`, `434C87`, `43C372`, `43BD0D`, rộng 900 pixel, cùng 59 ghi chú/DIMENSION và 9.068 ký tự dữ liệu đối chiếu. Runtime ghi khoảng 391 giây xử lý, không cắt context. Schema buộc đúng ba mã bas chưa rõ, các mã đi chung/khung/ref thuộc nguồn; model không được sinh thao tác CAD. Lượt đầu dùng danh sách mở đã bị từ chối do mã ngoài nhóm, trước khi bổ sung schema khóa theo mã nguồn.

Kết quả lưu đủ bas 1/2/3, nhận định có liên kết hàn, thiếu quyền sở hữu hình học và mặt ghép/đầu giữ cố định. Lời giải thích của model còn nghi ngờ số/mã dù parser đã nối được BOM: đây là giới hạn chất lượng suy luận, không phải BOM nguồn bị mất. Giao diện dùng định danh từ parser, dịch các trường thiếu kỹ thuật sang tiếng Việt, giữ lời giải thích AI trong phần mở rộng chưa kiểm chứng. Không dùng nhận định đó làm ràng buộc gia công.

Kế hoạch vẫn có 0 thao tác thực thi và chưa được tạo revision. API apply trả HTTP 422. Hash DXF nguồn vẫn là `3f1c8d90be4d3e8d858b15abfd017f17ae20c2dd323863e2af63fe983685662b`. Chưa có DWG backup mới hoàn chỉnh cho cả nhóm 1/2/3/4/6; bản tube/bas4 trước đây vẫn là preview một phần.

Chạy lại kiểm tra kết quả đã lưu, không gọi model hoặc duyệt CAD:

```powershell
Set-Location D:\mechanical-ai-drawing
python scripts/check_process_vision.py baf461e9c2764a5ba9000a48772f846c 312d1eb2519d4c698fd2b114275c16fa
```

Bằng chứng máy đọc: `storage/validation-fixtures/process-vision-check.json`. Bộ kiểm thử có 194 ca Python đạt; JavaScript kiểm tra cú pháp, điều kiện đọc tiếp AI, gom dòng đề xuất và vừa khung. Phần còn cần triển khai là truy vết số/leader tới hình học, mặt tiếp xúc có kích thước thật, adapter sửa bas/bản cắt và đồng bộ hình lắp. Không khẳng định model đã hiểu hoặc tự sửa được mọi kết cấu.
