# Engine dùng chung: cụm native 2D xoay — 15/10/2026

## Chức năng đã thêm

Engine trước đây giải tiếp xúc đầu mặt theo X/Y của layout. Cùng một chi tiết đặt xoay trong hình cụm có thể nhận đúng kích thước mới qua block, nhưng chi tiết khác mã lắp tiếp vào nó chưa được dịch theo.

`graph/contact_frames.py` lấy hệ trục từ DIM/profile native đã đo và có chủ sở hữu. Engine giải lại tiếp xúc trong từng hệ trục vuông góc của các cụm đang thay đổi, sau đó giữ nguyên địa chỉ entity và tọa độ native của mọi thao tác. Phép quay chung chỉ tồn tại trong dữ liệu phân tích, không xoay file nguồn hoặc phá block để biến thành hình vẽ mới.

`graph/native_contacts.py` kết hợp nghiệm vị trí của các hình/cụm xoay khác nhau, giữ hình dạng chi tiết nhận, cập nhật DIM cụm và tạo quan hệ nguồn để kiểm tra lại trước apply/duyệt. Không dùng góc riêng hoặc mã riêng của Dauphine trong engine. Mô tả quan hệ nay ghi hệ trục cụm thay vì gọi nhầm đó là X/Y của layout.

Kiểm tra vẫn yêu cầu mặt CAD thật có đoạn tiếp xúc đủ chiều dài, DIM nguồn, ownership và nghiệm vị trí duy nhất. Bounding box chạm nhau, ảnh gần giống, khe hở không có số đo hoặc mối lắp 3D ẩn không trở thành bằng chứng tiếp xúc.

## Kiểm chứng

- **911 kiểm thử Python đạt**. Thêm 6 kiểm thử nguồn: cụm xoay 30°, −35° với POLYLINE có rãnh, block lồng nhau có góc cụm 73° và góc cha −17°, hai cụm xoay khác nhau trong một khung; kiểm tra từ chối thiếu/sai vị trí, thiếu quan hệ và khe hở không có DIM.
- Đã kiểm tra ngược thao tác qua dependency propagation; source context/file không đổi. Các kiểm thử tiếp xúc, hai trục, span và chuỗi trước đây vẫn đạt. Log toàn bộ: `storage/validation-fixtures/pytest-rotated-contacts-final-2026-10-15.txt`.
- Script `scripts/verify_rotated_contacts_dwg.py` tạo ba DWG mới độc lập, chuyển bằng ODA và dùng API thật: upload → nhận diện → yêu cầu chiều dài 100 → 80 mm, giữ tâm → apply → preview → duyệt → tải DWG HTTP 200 → ODA mở lại.
- Mỗi file đã đo lại hai hình chi tiết 80 mm, DIM cụm 180 mm, BOM theo mã và vị trí chi tiết nhận trong world coordinates; FreeCAD/OpenCASCADE đạt. Không gửi CAD ra cloud, không cung cấp mapping riêng cho engine. Mỗi trường hợp tổng hợp nhỏ mất khoảng 3–4 giây; đây không phải thời gian cam kết cho DWG thực tế lớn.

Biên nhận cuối có kiểm tra tọa độ chi tiết nhận: `storage/validation-fixtures/rotated-contact-dwg-d44d0419/receipts.json`. DWG mẫu được tải tại các thư mục `rotated-30/download`, `notched-classic-minus35/download`, `nested-73/download` bên trong batch này. Đây là dữ liệu kiểm thử tổng hợp; không phải backup Dauphine.

Đã tải chính DWG đã xuất của trường hợp 30° lên lại như một nguồn mới, yêu cầu 80 → 70 mm, duyệt/tải/mở lại thành công: hai DIM chi tiết 70 mm, DIM cụm 170 mm, BOM `Bas 2x20x70`. Biên nhận `rotated-contact-dwg-d44d0419/reedit-80-to-70/receipt.json`. Luồng sửa tiếp dùng identity nguồn được bảo toàn sau clone và ODA, không lấy lại mapping của file đầu.

## Giới hạn còn lại

Đợt này bổ sung **dịch cứng chi tiết nhận ở cụm 2D xoay**, không mở rộng co/giãn span sang mọi hệ trục nghiêng, không xử lý proxy/dynamic block và không chứng minh liên kết phối cảnh hay tiếp xúc cơ khí thiếu trong file. Block có hình học nằm nghiêng trong chính định nghĩa native có thể cần adapter vector nguồn bổ sung; góc nghiêng không tự được biến thành một hệ số tọa độ phỏng đoán.

Backup toàn Dauphine và yêu cầu sửa đúng mọi DWG vẫn chưa hoàn thành. Không sửa file khách hàng, không đổi bộ nhận diện/chọn khung và không nới chốt duyệt trong đợt này.
