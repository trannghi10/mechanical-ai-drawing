# Engine DWG dùng chung — chuỗi chi tiết lắp nối tiếp

Đã triển khai ngày 15/10/2026 vào luồng upload → lập kế hoạch → apply → preview → duyệt → xuất DWG. Không sửa thêm Dauphine hay file khách hàng, không thay bộ nhận diện/chọn khung và không thêm model hoặc công cụ trả phí.

## Chức năng mới

- Nhận diện chuỗi từ 2 đến 32 chi tiết cùng mã nằm giữa hai chi tiết dẫn động đã có mốc ngoài giữ nguyên. Cần đường bao đo thật, tiếp xúc đầu mặt hoặc khe hở có DIM thật, đường nối duy nhất không có nhánh và định nghĩa CAD native tương đương hoàn toàn.
- Việc dùng chung định nghĩa CAD chứng minh các tham số của chi tiết giống nhau. Tính một kích thước đích từ tổng khoảng lắp và các khe hở nguồn; cập nhật tất cả hình chi tiết, các instance trong cụm, lỗ, DIM và BOM cùng mã. Số lượng vật tư nguồn được giữ nguyên.
- Mỗi chi tiết trong chuỗi tự dịch tới vị trí đúng sau co/giãn; giữ hai mặt ngoài và khe hở nguồn. Block và khung bao mô tả cùng nhóm instance được kiểm tra nhất quán, bao gồm khe hở giữa các thanh.
- Lưu chuỗi, DIM, khe hở và phương trình theo hash nguồn. Trước apply/duyệt, tính lại tất cả bindings và yêu cầu đủ recipe/hình/DIM/BOM/dịch chuyển cho từng thanh. Không chứng nhận kế hoạch thiếu một thanh hoặc bị sửa sai.
- Sửa nhận diện khe hở: DIM có hai đầu đo trùng với chiều dài của một chi tiết nằm giữa không chứng minh đó là khe hở. Kiểm tra hành lang giữa hai mặt có đang bị chi tiết khác chiếm chỗ trước khi dùng DIM làm khoảng hở.

Không tự chia đều mức thay đổi cho các chi tiết khác mã hoặc cùng mã nhưng định nghĩa CAD khác nhau. Khi thiếu ràng buộc hoặc chuỗi có nhánh, vẫn giữ chốt kiểm tra thay vì tạo backup hoàn chỉnh giả.

Mã chính: `graph/native_series_fits.py`, `graph/native_span_fits.py`, `graph/native_contacts.py`. Các quy tắc không chứa tên file, mã vật tư hoặc handle riêng của một sản phẩm.

## Kiểm chứng

**888 kiểm thử Python đạt**, log `storage/validation-fixtures/pytest-native-series-final.txt`. Kiểm thử mới bao gồm tăng/giảm, profile có rãnh, POLYLINE cũ, block lồng nhau, khe hở thật, các khung trùng phạm vi, quantity/nguồn không đổi, thiếu một instance/recipe/DIM/BOM, phương trình hoặc manifest bị sửa sai và từ chối phân chia khi thiếu bằng chứng.

`scripts/verify_native_series_dwg.py` tạo các DWG mới với tên upload ngẫu nhiên. File đi qua API thật và bộ nhận diện khung bình thường; không cung cấp mapping riêng hoặc liên kết tham số thủ công cho engine.

| Trường hợp | Kết quả | Nghiệm thu luồng |
| --- | --- | --- |
| Hai thanh nối tiếp | Mỗi thanh 100 → 105 mm; giữ ngoài 400 mm | Duyệt, tải HTTP 200, ODA mở lại đo đúng |
| Ba thanh có rãnh, POLYLINE cũ | Mỗi thanh 100 → 93 mm; giữ ngoài 500 mm | Như trên; giữ rãnh và đường kính lỗ |
| Ba thanh có rãnh trong block lồng nhau | Mỗi thanh 100 → 103 mm; giữ ngoài 504 mm và hai khe hở 2 mm | Như trên; kiểm tra cả block và khung bao |
| Hai thanh khác mã | Không có quy tắc chia mức thay đổi | Kế hoạch bị chặn, không có thao tác thực thi, nguồn không đổi |

Biên nhận: `storage/validation-fixtures/native-series-dwg-23163f89/receipts.json`. Đã đối chiếu chiều dài và vị trí từng thanh sau mở lại, DIM ngoài, DIM khe hở, BOM và quantity. FreeCAD/OpenCASCADE kiểm tra các profile/lỗ đã sửa. Đây là hồi quy tổng hợp, không phải nghiệm thu một sản phẩm của khách hàng.

## Giới hạn còn lại

Adapter này kiểm tra tiếp xúc native 2D và chỉ xử lý chuỗi có nghiệm duy nhất. Chưa suy ra ràng buộc lắp ghép ẩn, độ bền, hệ số xưởng hoặc quan hệ phối cảnh. Nhóm có nhiều loại chi tiết, thiếu DIM/mốc, cùng mã nhưng khác CAD, có nhánh hoặc quá phạm vi adapter vẫn cần thêm bằng chứng/bộ giải.

Block động, proxy và association tùy biến vẫn cần adapter chỉnh sửa native phù hợp. Chưa đạt sửa đúng mọi DWG bất kỳ; backup toàn Dauphine vẫn chưa hoàn chỉnh và không được thay bằng các file kiểm thử này.
