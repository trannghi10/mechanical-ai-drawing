# Engine DWG dùng chung — co/giãn chi tiết giữa hai mặt lắp

Đợt này phát triển chức năng của dự án cho file người dùng tải lên, không sửa thêm file khách hàng hoặc thêm mapping Dauphine. Giữ nguyên bộ nhận diện và chọn khung.

## Chức năng mới

- Từ block native có mã BOM và DIM đo thật, xác định chi tiết chữ nhật lắp giữa hai chi tiết đang được sửa. Chỉ tự co/giãn khi chứng minh được hai mốc ngoài giữ nguyên; giữ tiếp xúc hoặc khe hở có DIM thật của bản nguồn.
- Tính lại chiều dài chi tiết nhận, cập nhật biên dạng, lỗ, DIM, BOM và các hình native cùng mã. Mở rộng phạm vi tới bản chi tiết/công đoạn liên quan đã xác định qua đồ thị nguồn, kể cả chi tiết nhận không có trong yêu cầu ban đầu.
- Liên kết gắn với hash nguồn, hai mặt lắp và các DIM cụ thể. Apply/duyệt tính lại phương trình, hình và bảng kê; thiếu thao tác, sai mốc, mã chi tiết cần hai kích thước khác nhau hoặc chiều dài không hợp lệ đều bị chặn.
- Block đã chọn và khung bao chứa cùng một cụm native dùng một liên kết cho mỗi chuyển động. Các khung vẫn được kiểm tra riêng về tiếp xúc, giao hình, DIM và hình học chưa có chủ sở hữu trước khi duyệt.

Mã chính: `graph/native_span_fits.py`, `graph/native_contacts.py`, `backend/services/native_fit_scope_service.py`. Tích hợp vào lập kế hoạch và kiểm tra revision. Không cần thêm model hoặc công cụ trả phí cho nhóm cấu trúc này.

## Kiểm chứng bằng DWG mới

`scripts/verify_native_span_dwg.py` tạo DWG có tên ngẫu nhiên, upload qua API và dùng catalog/khung được đọc bình thường. Không cung cấp mapping riêng cho engine, không gắn liên kết tham số thủ công. Cả ba trường hợp đi qua upload → lập kế hoạch → apply → preview → duyệt → xuất DWG → tải HTTP 200 → ODA mở lại đo kiểm.

| Trường hợp tổng hợp | Chi tiết nhận | Kích thước ngoài / khe hở |
| --- | --- | --- |
| LWPOLYLINE, nhiều khung | 100 → 110 mm | Giữ ngoài 300 mm |
| POLYLINE cũ, nhiều khung | 100 → 90 mm | Giữ ngoài 300 mm |
| Block lồng nhau và khung bao | 100 → 110 mm | Giữ ngoài 302 mm, khe hở DIM 2 mm |

Đã đối chiếu DIM chi tiết và cụm, ba dòng BOM, nguồn không đổi và kết quả FreeCAD/OpenCASCADE của các profile/lỗ. Biên nhận: `storage/validation-fixtures/native-span-dwg-800e9985/receipts.json`. Lượt thử nhỏ mất khoảng 4,6–5,1 giây mỗi trường hợp; đây không phải cam kết tốc độ DWG lớn. **857 kiểm thử Python đạt** sau bản sửa cuối, log `storage/validation-fixtures/pytest-native-span-final.txt`. Các kiểm thử bao gồm co/giãn, hệ tọa độ quay/tỷ lệ, khung/block cùng cụm, khe hở có DIM, nguồn không đổi và kế hoạch bị sửa sai hoặc thiếu hình/DIM/BOM/ràng buộc.

## Giới hạn

Đây là dữ liệu hồi quy tổng hợp, không thay thế nghiệm thu DWG sản xuất. Chưa tự sửa đúng mọi DWG: chi tiết nhận không phải hình chữ nhật, thiếu DIM thật/mốc ngoài, khe hở chưa có bằng chứng, co/giãn đồng thời hai trục và các liên kết 3D ẩn vẫn cần bộ giải hoặc thông tin bổ sung. Block động/proxy/association chưa có adapter native phù hợp vẫn được chặn.

Không có backup toàn Dauphine mới trong đợt này. Bản Dauphine hiện có vẫn là preview một phần; hình cạnh/phối cảnh, một số hình cụm/công đoạn và đệm đóng gói chưa hoàn tất. Các kiểm tra mặt 2D không chứng nhận độ bền hay thông số chấn/uốn của xưởng.
