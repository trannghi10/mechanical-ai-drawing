# Đồng bộ lớp đóng gói trên — 14/10/2026

Đã bổ sung quy tắc dùng chung cho các lớp xốp/tấm lót phía trên trong hình đóng gói 2D. Engine cần BOM cùng sản phẩm, hình chữ nhật kín có kích thước khớp duy nhất và một chuỗi mặt tiếp xúc nguồn. Giữ độ dày, footprint, khoảng hở từng đầu; chỉ dịch vị trí. Không sử dụng mã/handle Dauphine trong bộ biên dịch.

`graph/packing_top_layers.py` gắn lớp vào hình bao đã kiểm chứng. `cad/hatch_translation.py` dịch đường bao và seed HATCH cùng polyline nguồn, giữ các tag pattern. Chặn association, gradient, đường cong/OCS nghiêng, HATCH bị stretch hoặc thiếu đường bao. Đã mở rộng cô lập block tĩnh chứa HATCH thẳng để vị trí dùng chung khác giữ nguyên. Bộ nhận diện danh mục/khung không thay đổi.

Trong Dauphine, tấm lót `3.8.01309` dày 7 mm và xốp `3.8.01280` dày 40 mm đã hạ 27 mm cùng thùng. Giữ khe hở nguồn 6 mm với sản phẩm và 8,5 mm với thùng. Thùng cao 823 mm; tổng thùng/pallet 953 mm. HATCH/seed và đường bao trong DWG được ODA mở lại đo khớp; nguồn không thay đổi. Không đổi BOM của hai lớp vì kích thước vật tư vẫn giữ nguyên.

- Plan: `69d45c3fa8ed4b0ba207b049f059c361`.
- Revision: `daed92c218a344c9abe4badfc9ca9b54`.
- Export: `ea23bdb0227a45fa8251ab484e47b6c1`.
- File: `storage/backups/Dauphine-PREVIEW-dong-bo-dem-tren.dwg`.
- SHA256: `29687a0f9be97da6b5524dcf1f2dab7a0a96a6c1b875b0b06895f38b569faabc`.
- 229 thao tác đề xuất được cô lập/gộp thành 219 thay đổi native; 19 mặt trước/sau FreeCAD đạt.
- Receipt mở lại: `storage/validation-fixtures/dauphine-combined/daed92c218a344c9abe4badfc9ca9b54/top-layers-readback.json`.

## Giới hạn quan trọng

Đây là bản xem trước chưa hoàn chỉnh. Sau khi dịch các lớp trên, hai đệm bên hông `3E5DEA`/`3E5DEC` còn ở vị trí nguồn, tạo bốn giao hình 2D với tấm lót/xốp đã dịch. Engine và giao diện báo rõ các giao hình này; không coi việc ghi đúng tọa độ native là đã lắp ghép đúng. Chi tiết tại `top-layers-intersections.json` cùng thư mục receipt. Bản này **chưa dùng được cho đóng gói sản xuất**.

Hình cụm hàn, chi tiết bên trong, các lớp đệm còn lại và các hình thùng khác chưa đồng bộ đủ. 5/6 DIM chiều cao khung đạt 697 mm; DIM cụm hàn vẫn 724 mm. `complete_product_backup=false`, `complete_packaging=false`; thử duyệt vẫn bị chặn. Chưa hoàn thành backup Dauphine hoặc khả năng tự sửa đúng mọi DWG.

Kiểm thử mới bao gồm lưu/mở lại HATCH, pattern và seed, cô lập block tĩnh dùng chung, từ chối association, thiếu thao tác, biến dạng và giao hình với đệm chưa đồng bộ. Script UI kiểm tra hiển thị/deduplicate và điều hướng CAD. Hình raster sau sửa đã được xem; chưa kiểm thử thao tác trực tiếp toàn bộ trình duyệt.

705 kiểm thử đạt (79,67 giây); script UI đạt. Backend đã nạp bản mới ở cổng 8765; health HTTP 200. Tải DWG qua API HTTP 200 và SHA256 khớp file đã mở lại. Tái kiểm chứng: `python scripts/verify_dauphine_top_layers.py` (tạo revision xem trước riêng, không ghi đè nguồn). Log bộ kiểm thử: `storage/validation-fixtures/pytest-packing-top-layers-20261014.txt`.
