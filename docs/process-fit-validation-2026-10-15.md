# Đồng bộ chi tiết cùng công đoạn — 15/10/2026

Đã sửa luồng mở bản chi tiết liên quan và bổ sung kiểm chứng chi tiết giữ nguyên theo mốc ngoài cụm. Thay đổi dùng cấu trúc CAD nguồn, không gắn với tên sản phẩm hoặc handle cụ thể.

## Lỗi đã khắc phục

- Chi tiết nhận được tìm thấy trong hình lắp nhưng bản chi tiết của nó vẫn ở chế độ chỉ đọc do ban đầu chỉ là ứng viên cùng công đoạn. Đồng bộ native instance thất bại trước bước mở rộng phạm vi. Nay engine tái dựng quan hệ mặt lắp/DIM nguồn trước, mở đúng các bản chi tiết có quan hệ đã chứng minh, rồi mới sửa đồng bộ.
- Khi một mặt lắp đổi kích thước và người dùng giữ kích thước ngoài cụm, chi tiết ở mặt đối diện giữ nguyên đúng theo quy tắc CAD nhưng vẫn bị báo thiếu kiểm tra công đoạn. Nay engine kiểm chứng lại DIM tổng, mặt tiếp xúc, khe hở và hình học chi tiết nhận để ghi rõ **Giữ nguyên, đã kiểm tra**.
- Luồng model đề xuất cũng được bổ sung các kết quả kiểm chứng của engine; bản đề xuất chưa đủ bằng chứng vẫn bị chặn. Kiểm tra trước duyệt/xuất sử dụng đúng khung gốc, phạm vi và dữ liệu nguồn của kế hoạch.

## Điều kiện được áp dụng

Cụm native 2D phải có mã vật tư xác định từ BOM, đường bao có DIM thật, các mặt lắp/khe hở đã xác định và yêu cầu giữ kích thước ngoài cụm. Mỗi hình công đoạn liên quan phải có kiểm chứng tiếp xúc đầy đủ. Mọi instance trong hình lắp của mã giữ nguyên phải có ràng buộc tương ứng; bản chi tiết riêng cần có chủ sở hữu nguồn rõ ràng.

Không dùng việc “chưa có thao tác sửa” để kết luận chi tiết không bị ảnh hưởng. Thay đổi hình, vị trí, INSERT cha, chữ hoặc ô BOM của chi tiết làm mốc sẽ làm mất chứng nhận giữ nguyên. Thiếu khung công đoạn, thêm instance chưa gắn quan hệ, bỏ geometry/BOM của chi tiết nhận, đổi hash/mốc giữ hoặc thiếu bằng chứng số đo đều tiếp tục bị chặn. Các bảng trùng mã/công đoạn được kiểm tra chung trước khi gộp thành một dòng hiển thị.

Ví dụ với cụm đủ dữ liệu:

```text
Mã [mã chi tiết] độ dày từ 2 thành 1.2 mm, giữ dưới; giữ kích thước ngoài cụm
```

Engine giữ mặt đối diện, tính lại chi tiết lắp giữa, cập nhật geometry/DIM/BOM và bản chi tiết tương ứng. Câu lệnh này không tự cấp quyền suy đoán mặt lắp hoặc bỏ qua kiểm tra chất lượng.

## Kiểm chứng

**963 kiểm thử Python đạt**, gồm luồng biên dịch trực tiếp và model đề xuất được mô phỏng, lỗi bản chi tiết chỉ đọc, giữ mốc khi chọn cả block/khung bao chứa và kiểm tra chống thiếu/sai bằng chứng. **11 script giao diện đạt.** Bộ kiểm thử vẫn nằm trong 19 module hiện có.

Ba DWG kiểm thử mới có bảng kê ghi công đoạn `(Cắt laser)` đã đi hết API: upload → chọn khung → lập kế hoạch → sửa → preview → duyệt → xuất/tải DWG → ODA mở lại.

| Yêu cầu | Chi tiết nhận sau sửa | Kích thước ngoài giữ nguyên | Thời gian toàn luồng |
| --- | --- | --- | --- |
| Mặt dưới 100 → 80 mm | 100 → 120 mm | 300 mm | 4,618 giây |
| Tấm dưới dày 2 → 1,2 mm | 100 → 100,8 mm | 202 mm | 3,900 giây |
| Mặt trên 100 → 80 mm | 100 → 120 mm | 300 mm | 4,204 giây |

Đã đối chiếu geometry, vị trí, DIM và BOM trong DWG mở lại; nguồn không đổi. Thời gian trên chỉ áp dụng cho các file kiểm thử nhỏ, không phải cam kết tốc độ mọi DWG. Không gọi model trong ba bài API này; bài luồng model trong pytest dùng phản hồi mô phỏng.

- Biên nhận: `storage/validation-fixtures/native-span-dwg-46c071bf/receipts.json`.
- Log Python: `storage/validation-fixtures/pytest-process-fit-final-2026-10-15.txt`.
- Chạy lại: `python scripts/verify_native_span_dwg.py --process`.
- File do script sinh được đánh dấu kiểm thử ngay sau khi kiểm tra hash upload, kể cả khi bài thử thất bại, để không làm rối danh sách tài liệu người dùng. Không xóa bản vẽ khách hàng.

## Phần chưa hoàn thành

**Chưa có backup toàn Dauphine; chưa tự sửa đúng mọi DWG bất kỳ.** Ba file trên kiểm chứng một nhóm chức năng dùng chung, không thay thế sản phẩm khách hàng.

Các hình cụm/hình cong/phối cảnh và đóng gói còn thiếu quan hệ nguồn vẫn cần adapter hoặc ràng buộc được xác nhận. Block động và proxy association cần CAD host tương thích để tái tính native; ODA File Converter hỗ trợ chuyển đổi, không thay thế bộ chỉnh sửa này. Việc đọc đủ entity cũng không tự cung cấp ý đồ thiết kế, mặt lắp hoặc thông số công nghệ còn thiếu.

Backend đã được nạp mã mới tại `http://127.0.0.1:8765/explorer`. Cần phân tích lại yêu cầu để dùng luồng mới; không tự nâng bản xem trước cũ thành backup hoàn chỉnh.
