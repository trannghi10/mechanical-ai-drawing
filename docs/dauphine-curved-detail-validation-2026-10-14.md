# Detail C cong — kiểm chứng ngày 14/10/2026

Đã bổ sung sửa **Detail C của khung hàn bước 2**, giữ cung ngoài R406,5 và vị trí lắp; cung trong đổi về R405,5, chân thẳng và hai DIM độ dày đổi 1,5 → 1 mm. Đây là phần bổ sung vào bản xem trước đang có, **chưa phải backup toàn sản phẩm**.

## File và cách xem

- DWG: [Dauphine-PREVIEW-cum-xuong-thanh692-DetailCD.dwg](../storage/backups/Dauphine-PREVIEW-cum-xuong-thanh692-DetailCD.dwg), 2.230.384 byte.
- [Mở bản sửa trên web](http://127.0.0.1:8765/explorer?doc=34ee84f35e1a44fb81c56044397a0fff&target=3B3987&revision=1ea6554aeec14e23931b9e52c40e74a7).
- [Tải DWG qua backend](http://127.0.0.1:8765/documents/34ee84f35e1a44fb81c56044397a0fff/revisions/1ea6554aeec14e23931b9e52c40e74a7/exports/3fe41a1f268d4a139f49be064df7f41e/download).
- [Detail C phóng lớn từ chính DWG đã mở lại](../storage/validation-fixtures/dauphine-combined/1ea6554aeec14e23931b9e52c40e74a7/detail-c-enlarged.png).

Plan `7bdd90e64b9a4e36ae0b5ad96e719556`; revision `1ea6554aeec14e23931b9e52c40e74a7`. DWG SHA256 `579371b667569b86e07e6b9b2429864da8f082da78fa5a152a6605bc948e8f3a`.

## Chức năng được thêm

`cad/clipped_curved_detail.py` tái tính giao điểm đường thẳng/cung và hai vòng tròn bằng hình học giải tích. `graph/curved_detail_contacts.py` tìm cung, chân thẳng, mép nối và DIM đo thật từ dữ liệu CAD; chỉ nhận khi nguồn, mã sản phẩm và lựa chọn lắp ghép khớp hash. Không hardcode mã hoặc handle Dauphine trong engine. Hệ số DIM nguồn xác định tỷ lệ hình trích; không suy kích thước từ pixel.

Các đầu nét cũ lệch nhẹ chỉ được nhận trong dung sai in trên bản nguồn; giao điểm mới được dựng lại chính xác. Giữ cung ngoài, chân ngoài, vòng trích, tiết diện hộp, chốt và các ghi chú lịch sử. Chặn khác mặt phẳng, mơ hồ nhánh giao, sai chân DIM hoặc thiếu thao tác nhận. Apply và validation kiểm tra lại liên kết; báo cáo hình cụm liệt kê Detail đã sửa nhưng vẫn giữ trạng thái chưa hoàn tất cho các hình còn thiếu.

Bản sửa có 400 thao tác, thêm 5 thao tác cho Detail C vào 395 thao tác đã có. Vẫn bao gồm tấm 21, thanh 4/5, hình chiếu đứng C4, ba cụm la xương, Detail D, các tấm laser, phôi uốn và phần đóng gói đã kiểm chứng trước đó.

## Bằng chứng

- **822 kiểm thử Python đạt**, gồm DIM tỷ lệ khác nhau, tọa độ modelspace lớn, nguồn không hợp lệ, khác mặt phẳng, DXF độc lập của sản phẩm khác và kiểm tra thiếu thao tác. Log `storage/validation-fixtures/pytest-clipped-curved-detail-final.txt`.
- DWG được ODA xuất và mở lại. Hai DIM aligned có khoảng cách chân đo × DIMLFAC lần lượt 1,0000000002 và 1 mm; group 42 và chữ trong block DIM đều khớp 1 mm. Với DIM aligned nguồn có angle tùy chọn bằng 0, kiểm tra đo theo hai chân DIM, tránh dùng phép chiếu của hàm đo chung.
- FreeCAD/OCC dựng từ hình học đọc lại của DWG: đường bao kín, mặt hợp lệ, 6 cạnh, diện tích 1.653,5967548 đơn vị bản vẽ². Kiểm tra này chứng minh riêng dải cong/chân thẳng 2D, không chứng nhận cả cụm hoặc độ bền.
- Luồng apply thông thường vẫn kiểm tra 27 mặt từ các recipe. Hash DXF nguồn giữ nguyên `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.
- Tạo và xuất bản xem trước mất 257,14 giây trong lượt này, không gọi model AI. Chưa đạt mục tiêu xử lý vài giây cho phạm vi CAD lớn.
- Duyệt thành backup hoàn chỉnh tiếp tục bị chặn; `complete_product_backup=false`, `complete_packaging=false`.
- Backend đã nạp mã mới tại cổng 8765. Tải HTTP 200 trả đúng 2.230.384 byte và SHA256 nêu trên; báo cáo hình cụm có Detail cong đã kiểm chứng. Thử duyệt qua HTTP vẫn trả 422, giữ chốt bản một phần.

Biên nhận tại `storage/validation-fixtures/dauphine-combined/1ea6554aeec14e23931b9e52c40e74a7/receipt.json`, `curved-detail-readback.json`, `detail-c-occ.json`, `http-checks.json`.

Lặp lại: `python scripts/verify_dauphine_curved_detail.py`. Chỉ đọc lại bản đã xuất: `python scripts/verify_dauphine_curved_detail.py --readback 1ea6554aeec14e23931b9e52c40e74a7`.

## Còn thiếu

Hình cạnh/phối cảnh C4, một số hình cụm/công đoạn và đệm góc đóng gói chưa được gắn đủ. Cần chốt C4 giãn ngang/sâu theo lòng mới để giữ khe hở nguồn hay giữ kích thước ngang/sâu; các mốc đã xác nhận trước đó tiếp tục được giữ.

Máy chỉ có ODA File Converter và DWG TrueView theo xác nhận người dùng. Bộ chuyển đổi không bổ sung cho dự án khả năng chỉnh tham số block động hay tái tính mọi proxy/association. Chưa chứng minh sửa đúng mọi DWG; mỗi file mới vẫn cần kiểm kê khả năng, chủ sở hữu, mốc và quan hệ có bằng chứng.
