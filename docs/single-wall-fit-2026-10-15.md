# Sửa một chi tiết và giữ kích thước ngoài cụm — 15/10/2026

Đã mở rộng bộ sửa dùng chung cho cụm native 2D: khi một mặt lắp thay đổi và người dùng yêu cầu giữ kích thước ngoài cụm, engine tự co/giãn chi tiết nằm giữa và giữ mặt đối diện. Bộ sửa không dùng tên file, mã sản phẩm hoặc tọa độ riêng của khách hàng.

## Cách dùng

Chọn khung hoặc block cụm có BOM, profile kín và DIM đo thật, rồi nhập ví dụ:

```text
Mã [mã chi tiết] độ dày từ 2 thành 1.2 mm, giữ dưới; giữ kích thước ngoài cụm
```

Hoặc:

```text
Mã [mã chi tiết] chiều dài từ 100 thành 80 mm, giữ trên; giữ kích thước ngoài cụm
```

Mốc dưới/trên phải phù hợp với hình và ý định thiết kế thực tế. Có thể ghi thêm số đo, ví dụ `giữ kích thước ngoài cụm 202 mm`; số này phải khớp DIM tổng nguồn. Nếu muốn đổi kích thước ngoài, cần yêu cầu thay đổi đó riêng thay vì coi là giữ nguyên.

## Phần được tự động hóa

- Tìm chi tiết nhận, hai mặt lắp và DIM tổng có điểm đo thật chạm hai biên ngoài.
- Tính lại chiều dài chi tiết nhận, giữ tiếp xúc hoặc khe hở được chứng minh bằng DIM nguồn.
- Giữ mặt ngoài của chi tiết đang sửa và mặt đối diện; cập nhật hình, DIM, BOM và bản chi tiết cùng mã.
- Hỗ trợ cụm xoay, block lồng nhau, POLYLINE cũ và profile có rãnh trong phạm vi bộ sửa profile hiện có.
- Kiểm tra được cả trường hợp chỉ đổi biên dạng mà không cần dịch INSERT.
- Lưu ràng buộc theo nguồn và dựng lại khi tạo, duyệt hoặc xuất. Thiếu/sai DIM tổng, mốc giữ, hình, BOM hoặc ý định giữ kích thước ngoài đều không được bỏ qua.

Chỉ kích hoạt quy tắc giữ kích thước ngoài khi có yêu cầu xác định, kể cả thông tin bổ sung. Không dùng DIM ghi đè làm căn cứ và không tự chọn một mặt đối diện khi chưa có đủ dữ liệu.

## DWG đầu cuối đã kiểm chứng

| Ca | Chi tiết được yêu cầu | Chi tiết nhận | Kích thước ngoài giữ lại |
| --- | --- | --- | --- |
| Cụm 2D thẳng | 100 → 80 mm | 100 → 120 mm | 300 mm |
| POLYLINE có rãnh, cụm lồng xoay −35° | 100 → 80 mm | 100 → 120 mm | 302 mm; khe hở 2 mm |
| Cụm lồng xoay 73° | 100 → 80 mm | 100 → 120 mm | 302 mm; khe hở 2 mm |
| Đổi độ dày một tấm | 2 → 1,2 mm | 100 → 100,8 mm | 202 mm |
| Đổi mặt lắp đối diện, cụm xoay 37° | 100 → 80 mm | 100 → 120 mm | 302 mm; khe hở 2 mm |

Cả năm file mới đã chạy qua API thật: upload DWG → chọn phạm vi → lập kế hoạch → tạo bản sửa → xem trước → duyệt → tải DWG → ODA mở lại. Kiểm tra đường bao, DIM, BOM, vị trí chi tiết nhận, khe hở, kích thước ngoài và hash nguồn không đổi. Không cung cấp mapping hoặc liên kết tham số thủ công cho engine.

Thời gian từng ca: 4,230; 3,700; 3,771; 3,382; 3,756 giây trên máy hiện tại. Đây là thời gian của các cấu trúc kiểm chứng này, không phải cam kết cho mọi file lớn.

Bằng chứng: `storage/validation-fixtures/native-span-dwg-63ad9e46/receipts.json`. Chạy lại: `python scripts/verify_native_span_dwg.py --one-wall`. Upload kiểm chứng được đánh dấu để không lẫn trong danh sách tài liệu khách hàng mặc định.

Kiểm tra cuối: **944/944 kiểm thử Python đạt** trong 121,11 giây; toàn bộ 11 script xác minh JavaScript đạt. Log: `storage/validation-fixtures/pytest-one-wall-fit-ready-2026-10-15.txt`. Backend đã nạp mã mới tại cổng 8765.

## Giới hạn còn lại

Đây chưa phải khả năng sửa đúng mọi DWG. Bộ sửa này cần cụm native 2D có danh tính chi tiết, profile/DIM và mặt lắp xác định. Nhiều chi tiết nhận khác nhau không có đủ phương trình, block động/proxy, phối cảnh hoặc các quan hệ thiết kế thiếu bằng chứng vẫn bị chặn.

Backup toàn Dauphine vẫn chưa hoàn chỉnh; năm file kiểm chứng không thay thế backup của sản phẩm đó. Bộ chọn/nhận diện khung, model/API và file gốc khách hàng không bị thay đổi. Không thêm công cụ trả phí hoặc file test Python mới; thư mục `tests` vẫn có 19 module.
