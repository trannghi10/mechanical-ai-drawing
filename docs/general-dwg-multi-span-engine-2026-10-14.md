# Sửa DWG dùng chung — biên dạng có rãnh và lắp ghép hai trục

Đã triển khai vào luồng upload, lập kế hoạch, apply, preview, duyệt và xuất DWG. Đợt này phát triển chức năng cho file mới; không sửa thêm sản phẩm Dauphine, không đổi model, không thêm công cụ trả phí và không thay bộ nhận diện/chọn khung đã được chấp nhận.

## Phần bổ sung

- `graph/native_span_fits.py`: mở rộng chi tiết nhận từ hình chữ nhật sang profile thẳng đóng có rãnh. Hai mặt lắp phải có tiếp xúc thật hoặc khe hở gắn với DIM thật; hai mốc ngoài của các chi tiết dẫn động phải giữ nguyên. Bộ resize kiểm tra hướng cạnh, tính kín, rãnh và lỗ trước/sau sửa. Cạnh chéo và đường cong chưa có adapter phù hợp vẫn bị chặn.
- Cho phép cùng chi tiết nhận co/giãn hai trục X/Y độc lập. Mỗi trục có một DIM nguồn, hai mặt lắp và phương trình riêng. `resize_many` kiểm tra kết quả độc lập với thứ tự; một entity chỉ có một thao tác cuối, bao gồm lỗ và DIM chung.
- Ghép các kích thước thay đổi vào cùng ô BOM/quy cách dựa trên vị trí số trong bản nguồn. Không thay tiếp trên chuỗi đã sửa: kích thước mới có thể trùng với kích thước nguồn của trục khác mà vẫn không sửa nhầm. Số nguồn lặp chưa xác định được vai trò, hai DIM yêu cầu hai giá trị khác nhau cho cùng vị trí và BOM xung đột đều bị chặn.
- Tái kiểm chứng cả hình tổng hợp, từng DIM, lỗ, bảng kê và từng phương trình trước apply/duyệt. Kế hoạch thiếu một trục, sai mốc, thiếu lỗ hoặc chỉ sửa một số trong BOM không được chứng nhận.
- `graph/native_contacts.py` và `graph/drawing_sync.py`: khi cụm còn block có mã vật tư nhưng chưa xác định đủ profile/DIM để kiểm tra lắp ghép, báo rõ mã đó và chặn duyệt backup hoàn chỉnh. Có thể tải bản xem trước; tên block/mã BOM không được coi là bằng chứng đã kiểm tra tiếp xúc.

Phạm vi liên quan vẫn tự mở tới các hình/bản chi tiết cùng mã được xác định từ nguồn. Không có mapping theo tên file, handle hoặc mã vật tư của một sản phẩm trong engine mới.

## Kiểm chứng bằng DWG mới

Chạy `python scripts/verify_native_multi_span_dwg.py` khi backend ở cổng 8765. Script tạo file có tên upload ngẫu nhiên, dùng catalog và khung được đọc bình thường, không cung cấp mapping hoặc liên kết tham số thủ công cho engine.

| DWG tổng hợp | Chi tiết nhận sau sửa | Kết quả |
| --- | --- | --- |
| Hai trục tăng, LWPOLYLINE | 60×100 → 75×115 mm | Duyệt, tải DWG, ODA mở lại đo đúng |
| Hai trục giảm, POLYLINE cũ có rãnh | 60×100 → 55×95 mm | Như trên; giữ độ sâu rãnh và đường kính lỗ |
| Block lồng nhau có rãnh | 60×100 → 75×115 mm | Như trên; bản chi tiết và hình cụm đều đồng bộ |
| Giá trị mới trùng số nguồn của trục khác | 60×100 → 100×60 mm | Ghép đúng hai số trong BOM, không thay nhầm |
| Cụm có thêm chi tiết chưa có DIM | Bản sửa hỗ trợ ở chế độ preview | Duyệt bị từ chối HTTP 422 và nêu mã UNMEASURED; DWG preview vẫn tải/mở lại được |

Cả bốn backup được duyệt đã kiểm tra profile, hai DIM của chi tiết nhận, hai lỗ và bán kính, năm dòng BOM, kích thước ngoài 140×160 mm và hash nguồn không đổi. FreeCAD/OpenCASCADE kiểm tra các mặt/lỗ đã sửa. Các trường hợp nhỏ mất khoảng 5 giây, không cam kết tốc độ đó cho DWG lớn. Đã xem ảnh raster từ SVG preview của trường hợp tăng hai trục; hình và hai lỗ hiển thị, bảng kê có quy cách mới.

**873 kiểm thử Python đạt** sau bản sửa cuối. Biên nhận API cuối: `storage/validation-fixtures/native-multi-span-dwg-c78fa194/receipts.json`. Log Python cuối: `storage/validation-fixtures/pytest-native-multi-span-final.txt`. Kiểm thử bổ sung gồm profile có rãnh, lỗ/handle được clone, hai trục tăng/giảm, thay số chéo trong BOM, nguồn/context không đổi, trường hợp thiếu/sửa sai dữ liệu và từ chối chứng nhận cụm có chi tiết chưa đo được.

## Giới hạn còn lại

Các DWG trên là hồi quy tổng hợp; không thay thế nghiệm thu file sản xuất thực tế. Bộ giải cần profile native 2D được đo thật, mặt lắp và mốc giữ đủ bằng chứng; nó không tự suy ra quan hệ 3D ẩn, độ bền hoặc thông số xưởng. Khe hở thiếu DIM, số BOM lặp chưa có vai trò rõ, cạnh chéo, đường cong/biểu diễn không có binding phù hợp vẫn cần xử lý thêm.

Block động, proxy và association tùy biến chưa có adapter chỉnh sửa native đầy đủ với bộ công cụ hiện tại. Chưa đạt sửa đúng mọi DWG bất kỳ. Backup toàn Dauphine chưa hoàn chỉnh và không được thay thế bằng các file kiểm thử này.
