# Sửa tấm theo hai DIM thực tế — 17/10/2026

Người dùng chốt bas số 7 MR-106: DIM thực tế phải đúng 15 mm, cả ngang và đứng, giữ tâm lỗ. BOM nguồn ghi 3×20×20 mm, hai DIM đo 20,2 mm. Đây là các dữ kiện khác nhau; không tự cộng 0,2 mm vào đích.

## Quy tắc dùng lại cho file mới

- Đọc giá trị cuối ("thành 15") riêng với lượng giảm ("giảm đi 15"); bỏ STT/mã khỏi phép đọc số.
- Ghi riêng quy cách BOM, DIM nguồn, giá trị đích, hướng và mốc được xác nhận. Chưa đủ dữ liệu thì trả câu hỏi cụ thể.
- Chỉ sửa một mặt tấm có chủ sở hữu xác minh và hai DIM vuông góc. Mốc tâm lỗ phải trùng tâm hai DIM; chưa hỗ trợ tự đổi sang tâm bao khi không trùng.
- DIM ở góc bo được gắn với giao điểm tiếp tuyến khi hai cạnh nguồn nối và tiếp xúc đúng cung 90°. Hai phép co trục phải độc lập thứ tự, giữ cung tròn/R nguồn.
- Hai vòng lỗ bậc cần DIM native chứng minh đường kính nhỏ/lớn. Giữ vị trí tương đối nguồn; không suy hai vòng thành hai lỗ xuyên chồng nhau. FreeCAD kiểm tra từng hình chiếu khẩu độ, không chứng nhận cấu trúc lỗ 3D.
- Hình cạnh cần cùng mã, khung chi tiết, hai mặt đầu trùng nguồn và DIM chiều dày. Lỗ trên hình cạnh cần DIM đường kính và giới hạn chiếu khớp chính xác. Hình khác vẫn phải có liên kết riêng.
- Cập nhật hai trường rộng/dài trong quy cách, giữ độ dày, mã, STT, số lượng và mô tả công đoạn. Chỉ đổi tên trên bản chi tiết có chủ sở hữu xác minh.
- Giữ toàn bộ biểu mẫu khung tên có ô chữ native và logo khi xuất phạm vi. Biểu mẫu cần lưới vùng, nhãn khung tên và vùng vẽ giữa trống; khung chứa hình chi tiết không được áp dụng cách giữ tài nguyên này.

## Kết quả thực tế

Document `1c7d831296ff402bb1a838479063a99d`; plan `f783ff23a5164103aa2792fd8ad53189`; revision `a60ea2deb661433e81d743b75fe07fac`.

DWG đã xuất qua cả ODA và AutoCAD Core Console, sau đó mở lại: DIM ngang/đứng 15 mm; bao mặt 15×15 mm; hình cạnh cao 15 mm; dày 3 mm; bán kính hai vòng 2,5 và 4,5 mm; góc bo R2. Hai vòng nguồn lệch tâm khoảng 0,040787 mm và độ lệch đó được giữ nguyên. Hash file gốc và DXF nguồn không đổi. Tệp AutoCAD tải qua endpoint website trả HTTP 200, 929.465 bytes, roundtrip `validated_roundtrip`.

- Receipt: `storage/validation-fixtures/mr106-part7-verified-2026-10-17.json`.
- Đã bấm link tải trên trình duyệt, nhận `C:/Users/nghi.tran/Downloads/PREVIEW-backup-a60ea2de.dwg`; hash trùng bản AutoCAD đã kiểm chứng. Ảnh UI: `storage/validation-fixtures/mr106-part7-download-ui-2026-10-17.png`.
- Hình sau sửa từ DWG mở lại: `storage/validation-fixtures/mr106-part7-after-2026-10-17.png`.
- 1.322 bài toàn bộ đạt: `pytest-plate-size-full-2026-10-17.txt`; 268 bài liên quan mã cuối đạt: `pytest-plate-size-final-2026-10-17.txt`. Giữ 19 module kiểm thử.

**Giới hạn:** còn bốn khung cụm có `unverified_projection_mapping`. DWG này là xem trước phần đã kiểm chứng; chưa được duyệt backup toàn sản phẩm và không chứng minh khả năng sửa mọi DWG. Bản gốc được giữ nguyên.
