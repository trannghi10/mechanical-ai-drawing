# Phôi uốn và bản DWG Dauphine — 13/10/2026

Đã bổ sung sửa phôi uốn theo lựa chọn của người dùng: giữ quy tắc hiệu chỉnh từ bản nguồn khi tấm 1,5 → 1 mm, giữ R ngoài 406,5 và vị trí lắp. Đây vẫn là bản xem trước một phần, chưa phải backup toàn sản phẩm.

## Kết quả trên chính file Dauphine

Nguồn `34ee84f35e1a44fb81c56044397a0fff/converted/original.dxf` giữ nguyên SHA256 `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`. Đã đọc 71 khung đang dùng và 37.845 thực thể; các khung bị gạch bỏ không được đưa lại vào phạm vi sửa.

Revision `cbffa02f58df4d22940cdd0e79b078ca`, kế hoạch `8c2d95393b8c41609d6e356cec53d06b`, có 209 thao tác CAD, 12 mã tấm laser, 16 recipe DIM và 2 mặt cắt cong. Phôi tấm ốp cung và bản cắt native tương ứng mở lại từ DWG đo **1.375,008 × 697 mm**. DIM chiều dài giữ dung sai **+0,5/−0 mm**, độ chính xác ba chữ số thập phân. Phần dư bên phải đo **1.114,992 mm**; khoảng trên 37 mm, dưới 486 mm trên tấm 2.500 × 1.220 mm. Quy cách thành phẩm rộng 812 mm trong BOM được giữ riêng, không thay bằng chiều dài phôi.

Thùng trong hình bao đo **823 mm**, pallet giữ **130 mm**, DIM tổng thùng cộng pallet đo **953 mm**. BOM thùng cập nhật 925 × 925 × 823 mm. Các lớp xốp, hình tách rời và phối cảnh chưa được coi là hoàn tất.

File tải: `storage/backups/Dauphine-PREVIEW-12tam-laser1-cao697-thung823.dwg`. SHA256 `1f8fe80cf9f23d804f369ac811fee45c11282e37342b6e6599fcfdcc0a91f580`.

Đường tải lưu trên server: `/documents/34ee84f35e1a44fb81c56044397a0fff/revisions/cbffa02f58df4d22940cdd0e79b078ca/exports/3e3b09db6d3f4277afdec999766e42e0/download`. HTTP 200 đã đối chiếu đúng hash. ODA chuyển DWG → DXF lại và kiểm tra hình học, DIM, dung sai, bảng native, layer và layout. 17 mặt trước/sau được kiểm tra bằng FreeCAD/OpenCASCADE.

## Cách tính dùng chung

`cad/forming_calibration.py` dựng đường trung hòa trong một mặt cắt kín gồm hai cung đồng tâm, bốn chân thẳng theo trục và hai mép đóng. Các chân được nối bằng đầu mút CAD thật. Quy tắc chỉ được dùng khi có lựa chọn người dùng gắn với hash nguồn, chủ sở hữu chi tiết duy nhất, công đoạn cắt laser → uốn → chặt và DIM phôi đúng dung sai.

Phôi nguồn 1.374 +0,5/−0 cho miền hệ số trung hòa hiệu chỉnh khoảng 0,35794–0,46403. Sau giảm độ dày, miền chiều dài tính được 1.375,00860–1.375,34194 mm. Engine chọn danh nghĩa 1.375,008 mm sao cho toàn miền nằm trong dung sai nguồn. Đây là quy tắc kinh nghiệm của bản nguồn được người dùng cho phép tái sử dụng, không phải bộ thông số vật liệu/xưởng mới và không chứng minh độ bền.

`backend/services/forming_service.py` tìm mặt cắt trước chặt, phôi đo được và định nghĩa native trên bản cắt. Không dùng mặt cắt đã chặt để suy ngược chiều dài phôi đầy đủ. Sai chủ sở hữu, sai công đoạn, thiếu lựa chọn, phôi ngoài miền vật lý, bản cắt thiếu thao tác hoặc vượt khổ tấm đều không được chứng nhận phôi hoàn tất. Các hình phối cảnh/uốn tổng quát chưa có ràng buộc vẫn bị chặn.

`cad/vertex_dimensions.py` cập nhật DIM khi cả hai điểm đo khớp đỉnh CAD nguồn và có chuyển động duy nhất. Không suy chuyển động chỉ từ con số hay khoảng cách gần nhau. Đã dùng để đồng bộ DIM tổng thùng/pallet.

## Tốc độ và kiểm thử

Lọc theo miền UVZ bảo thủ trước phép giao cạnh đã loại bỏ hàng triệu cặp nét xa phôi. Bộ lọc không dùng đầu mút để bỏ qua polyline có bulge, block INSERT hoặc đường cong không có miền bao chắc chắn. Tái kiểm tra bản 208 thao tác giữ nguyên toàn bộ trước/sau, mất 16,641 giây. Lượt tạo/kiểm chứng/xuất bản 209 thao tác mất 210,703 giây; con số này bao gồm đọc lại nguồn, kiểm tra yêu cầu, FreeCAD và chuyển đổi DWG. Không có cam kết xuất mọi file trong vài giây.

666 kiểm thử Python đạt, có kiểm thử mẫu uốn độc lập khác kích thước, kiểm thử thao tác bị thiếu, dung sai bị đổi, không đủ khổ tấm và DIM tổng đóng gói bị bỏ sót. Log: `storage/validation-fixtures/pytest-forming-20261013.txt`. Giao diện hiển thị kết quả phôi trước/sau khi đã kiểm chứng; kiểm tra cú pháp JavaScript đạt.

Receipt và ảnh mở lại: `storage/validation-fixtures/dauphine-combined/cbffa02f58df4d22940cdd0e79b078ca/receipt.json`, `forming-readback.json`, `formed-blank-after.png`, `cut-blank-after.png`, `packing-after.png`.

## Phần chưa hoàn thành

- Chiều cao khung cụm và tấm lắp bên trong còn cần liên kết hình học đầy đủ; không được coi phôi 697 mm là toàn sản phẩm đã sửa xong.
- Hình phối cảnh, các chi tiết trong block cụm không có mã, lớp đệm và hình tách rời đóng gói chưa đồng bộ hết.
- Block động, proxy association và quan hệ thiết kế thiếu bằng chứng vẫn chưa được hỗ trợ tổng quát.

Revision giữ `complete_product_backup=false` và `complete_packaging=false`. Đã kiểm tra nút duyệt bị chặn đúng. File DWG này dùng xem trước; không thay thế backup hoàn chỉnh theo yêu cầu của người dùng và không chứng minh khả năng sửa mọi DWG bất kỳ.
