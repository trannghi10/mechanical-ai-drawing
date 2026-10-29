# Bằng chứng và phần chưa hoàn tất — 07/10/2026

Phạm vi: chọn bản vẽ trực quan → yêu cầu AI → kế hoạch → dependency → sửa hình/BOM → validation → preview → duyệt → xuất DWG. Giữ nguyên nhận diện hiện có.

| Yêu cầu | Bằng chứng hiện tại | Trạng thái |
|---|---|---|
| Nhận diện và chọn hình | Catalog/sheets hiện có, preview trình duyệt; logic nhận diện không sửa trong bước phát triển engine | Có, theo phạm vi người dùng đã chấp nhận |
| AI nhận yêu cầu và đối chiếu hình/CAD | Gemini structured schema, ảnh PNG + CAD handles, kiểm thử tích hợp giả lập | Khóa Gemini thật đã xác nhận qua models API và structured output; kế hoạch CAD cần tiếp tục đối chiếu/validation |
| Chỉ sửa phạm vi đã chọn | Source hash, refs, copy-on-write block lồng, tests instance dùng chung | Có cho entity hỗ trợ |
| Sửa hình, dimension và bảng kê | Geometry primitives, dimension linear/aligned, native CELL_VALUE và mirror | Có cho format hỗ trợ; thiếu dynamic/custom/topology mới |
| Hiểu ảnh hưởng và tự lan truyền | Delta DAG được xác nhận, chuyển hệ tọa độ, chặn vòng/xung đột | Chưa có bộ giải tổng quát cho mọi liên kết lắp ghép |
| Bảng kê và hình đúng theo yêu cầu khách | BOM mẫu sáu cột đã đọc; regression đổi đúng hai ô Sắt lặp | Chưa áp dụng yêu cầu 724→700, 1,5→1 vào đúng sản phẩm thực |
| Validation và preview tất cả mục | 50 tests đạt; duyệt bị chặn nếu thiếu preview một target; có lịch sử revision | Có kiểm tra dữ liệu, chưa chứng minh cơ học |
| Duyệt rồi xuất DWG backup | Gemini thật hoàn tất fixture 724→700 gồm geometry/dimension/BOM và DWG; LEG6949 round-trip bảo toàn 41 bảng và cloned mirrors | Có trong ca đã kiểm chứng |

Chưa được đánh dấu hoàn thành. Đã chuyển sang Gemini API và kết nối thật thành công với gemini-2.5-flash; tiếp theo chọn đúng khung, làm rõ hình chiếu/mã chi tiết/ràng buộc và kiểm chứng toàn bộ yêu cầu của khách trên bản sao. Không dùng fixtures giả lập làm bằng chứng AI đã hiểu bản vẽ sản xuất.

Khung sản xuất đã chọn 43C372 có 1278 entity, gồm 422 spline. Context đầy đủ khoảng 2,57 triệu ký tự đã gặp hạn mức Gemini; đã bổ sung summary + truy xuất geometry theo ref để kiểm chứng tiếp. Lỗi layout của bảng CAD proxy đã sửa trong context, không thay logic nhận diện.

Gemini thật đã phân tích thành công khung sản xuất 43C372 bằng context hai bước, lưu plan a8f56620286647a688c228471cb3b7c3. Plan không có operations, hỏi xác định khung chứa 724 mm và xác nhận tấm 2 mm/1,5 mm. File sản xuất chưa sửa. Fixture Gemini thật xuất thành công revision e19db94c74774f07996049370d9b3716, DWG 13505 bytes; dùng fixture có chỉ dẫn handle cụ thể, không chứng minh suy luận cơ khí tổng quát.

Đã rà 546 DIMENSION trong toàn file LEG6949 với override DIMLFAC, không tìm số đo khớp 724 mm trong dung sai 0,01. Không có text khớp mẫu 724 hoặc tấm 1,5 mm/x trong entity text. Bằng chứng lưu request-value-search.json trong document. Chưa có câu trả lời xác nhận bản vẽ/thông số thực cần sửa.
