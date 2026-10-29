# Đối chiếu yêu cầu kích thước — 15/10/2026

Người dùng báo kích thước sửa sai nhưng chưa chỉ ra DIM/chi tiết hoặc giá trị sai cụ thể. Đợt này sửa được những lỗi giải nghĩa có thể tái hiện trong code, không coi đây là bằng chứng rằng toàn bộ sai lệch của bản khách hàng đã được khắc phục.

## Lỗi và thay đổi

- Nhánh chiều cao tổng thể trước đây không đọc mốc giữ trong yêu cầu/clarification mới, chỉ dùng mốc lưu. Nay kiểm tra mốc mới, số đo đích, chiều cao khung/thành phẩm và phần chênh đúng hash/product nguồn. Yêu cầu trái với quyết định hiện hành được báo rõ; không để model đổi mục tiêu hoặc tự chọn mốc khác.
- Mốc chiều cao ngầm định của hai compiler chữ nhật/profile nay phải gắn đúng hash CAD và sản phẩm đã chọn. Không dùng lựa chọn của file hoặc sản phẩm khác.
- Thêm kiểm tra ngữ nghĩa độc lập trước khi đồng bộ và trước cả apply đầy đủ/apply preview của kế hoạch lưu: recipe, DIM đo thật, chủ sở hữu chi tiết, chiều cao đích và first/second/center phải khớp yêu cầu. Kích thước thành phẩm không tự trở thành chiều cao một chi tiết. Kiểm tra trục DIM trong tọa độ bản vẽ; DIM đứng có điểm dóng ở hai góc khác nhau vẫn hợp lệ.
- Giao diện và revision mới có bảng phân biệt thành phẩm, khung và phần chênh. Bảng này là mục tiêu; kết quả từng DIM và coverage toàn sản phẩm vẫn được kiểm tra riêng.

## Kiểm chứng

**905 kiểm thử Python đạt** trong `storage/validation-fixtures/pytest-height-intent-final-2026-10-15.txt`. Bao gồm 16 trường hợp mới về mốc trên/đáy/tâm, hash/sản phẩm cũ, mục tiêu khác, recipe/DIM bị sửa sai, chiều cao chi tiết và chiều cao tổng thể. Các script Node kiểm tra frontend, đóng gói và bảng đề xuất đều đạt.

Đã chạy lại đúng câu yêu cầu #3D337A qua API thật: job `13da50b0f1994fb0b8cf00003b244638`, kế hoạch `5708565ad2ac4ca59f8c25d5aa63a4e6`, 127 giây. Không gọi model/cloud và không tạo revision/DWG mới. Theo lựa chọn người dùng đã chốt và nguồn hiện hành: thành phẩm **727 → 700 mm**, khung **724 → 697 mm**, phần chênh giữ **3 mm**, giữ đáy/chân. Trình duyệt thật đã hiển thị đúng bảng và giữ kế hoạch đang chọn. Kết quả: `storage/validation-fixtures/height-intent-recheck-public.json`; ảnh: `storage/validation-fixtures/height-intent-5708565a.png`.

## Còn thiếu

Kế hoạch vẫn chỉ cho xem trước phần đã kiểm chứng. Các mã `8.1.05060.013`, `8.1.05190.002`, `8.1.05191.002`, `8.1.05192.002` còn thiếu liên kết lắp ghép; coverage các hình cụm/lớp đệm đóng gói chưa đủ. Không tuyên bố backup toàn Dauphine hoặc sửa đúng mọi DWG. Chưa có DIM sai cụ thể do người dùng chỉ ra để tái hiện trực tiếp báo cáo lỗi mới nhất; phần giải nghĩa mới không thay thế việc đối chiếu CAD thực tế.
