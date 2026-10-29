# Sửa tiếp xốp bên hông và lòng thùng — 14/10/2026

Đã giải quyết bốn giao hình được phát hiện trong revision xem trước trước đó. Hai hình xốp bên hông trong khung đóng gói Dauphine nay được nối với quy cách BOM, bốn footprint nhìn từ trên và bản chi tiết có DIM thật. Không dùng tên file, mã Dauphine hoặc handle cố định trong engine.

## Quy tắc và bằng chứng

`graph/packing_side_layers.py` yêu cầu khung thùng nhìn từ trên có hai DIM thật, trùng trục X với khung nhìn bên; quy cách xốp duy nhất trong BOM đã xác minh; số footprint đúng số lượng; tất cả hình nhìn bên đăng ký được với các footprint tương ứng; một mặt đệm dưới đứng yên; mặt lót trên đã gắn với chuyển động sản phẩm; bản chi tiết xốp có chủ sở hữu và DIM nguồn. Mã dùng lại với các quy cách BOM mâu thuẫn bị từ chối.

Giữ khe hở thực vẽ trong nguồn: xốp phải 745 → 718 mm, xốp trái 743 → 716 mm với khe hở trên 2 mm. Đây là bảo toàn khoảng hở nguồn, không phải kết luận về độ nén vật liệu. Quy cách vật tư danh nghĩa và DIM bản chi tiết `3.8.01312` đều đổi từ 745 → 718 mm; độ dày 40 mm, rộng 635 mm và số lượng 4 giữ nguyên.

`cad/hatch_translation.py` đã hỗ trợ đường kín gồm native LINE edges và co/giãn HATCH chữ nhật theo polyline đã gắn nguồn. Giữ loại EdgePath/PolylinePath, thứ tự đỉnh, pattern, seed và dữ liệu native. Association, gradient, đường cong, thay topology, seed sai hoặc HATCH không có đúng đường bao cùng phép biến đổi vẫn bị chặn.

Trong hình thùng đo được, một đường bao lồng đồng tâm có bốn khoảng cách bằng nhau 7 mm được cập nhật cùng đường bao ngoài: lòng thùng 836 → 809 mm. Giữ đáy và các khoảng cách thành. Không gắn một tập hợp đường bao bất kỳ thành thùng.

Đã sửa lỗi đối chiếu thao tác theo mỗi ref bảng: thay nhiều ô của cùng ACAD_TABLE phải dùng `(ref, cell_index)`. Bảng đóng gói nay cập nhật được cả dòng thùng và dòng xốp, cùng text mirror.

## DWG đã mở lại

- File: `storage/backups/Dauphine-PREVIEW-xop-ben-hong-va-long-thung.dwg`.
- Plan: `ddf983e1c9ce48f1b888062a3ddf9178`.
- Revision: `3f73a32c7200467a84f0a76f2166a1b0`.
- Export: `2373cdd5ab754a0885e4bc8acaa238c8`.
- SHA256: `b4d45987f7bdc3076d79cb9c0d21641b39b51dfe09e1acd026d6673ad677aec3`.
- 239 thao tác đề xuất được cô lập/gộp thành 229 thay đổi native; 20 kiểm tra mặt trước/sau FreeCAD đạt.
- ODA mở lại đo khớp xốp, HATCH, DIM 718 mm, lòng thùng 809 mm và hai dòng BOM. Nguồn giữ nguyên SHA256.
- Receipt: `storage/validation-fixtures/dauphine-combined/3f73a32c7200467a84f0a76f2166a1b0/side-layers-readback.json`.

Đã xem ảnh raster khung đóng gói và bản chi tiết xốp sau sửa. Giao diện hiển thị quy cách danh nghĩa, số đo từng hình và khe hở nguồn, không lặp cùng mã xốp. Script UI đạt. 718 kiểm thử Python đạt (79,14 giây), bao gồm mẫu độc lập dùng xốp 5×65×115 → 5×65×95, bản chi tiết xoay 90° được sửa theo trục DIM thật, loại HATCH khác nhau, thiếu đăng ký hình chiếu, thiếu tiếp xúc, số lượng thiếu, BOM mâu thuẫn và thiếu thao tác DIM/BOM/HATCH. Kế hoạch Dauphine đã được biên dịch lại với quy tắc mới nhất: 239 thao tác native đề xuất giữ nguyên và qua validation. Log: `storage/validation-fixtures/pytest-packing-side-layers-20261014.txt`.

## Phần chưa hoàn tất

Chỉ các hình và quy tắc đã gắn nguồn ở trên được kiểm chứng. Các hình thùng khác, phối cảnh và vật tư đóng gói còn lại chưa được xác minh hết. Hình cụm hàn còn DIM 724 mm; tấm bên trong còn DIM 721 mm. Block cụm `3B5A77` có 225 LINE, 7 TEXT, 3 LWPOLYLINE và các INSERT con nhưng không có identity mã BOM native; chưa có binding tiếp xúc/chủ sở hữu đủ để lan truyền các thay đổi. Audit: `storage/validation-fixtures/dauphine-unresolved-members-20261014.json`.

`complete_product_backup=false`, `complete_packaging=false`; thử duyệt vẫn bị chặn. File này chưa phải backup toàn sản phẩm hay chứng nhận dùng cho sản xuất. Chưa hoàn thành sửa mọi DWG.

Backend đã nạp bản mới ở cổng 8765; health HTTP 200, tải DWG HTTP 200 và SHA256 khớp. API revision hiển thị các binding mới và không còn bốn giao hình cũ; thử duyệt backup toàn sản phẩm nhận HTTP 422. Receipt HTTP: `http-readback.json` cùng thư mục trên.

Tái kiểm chứng: `python scripts/verify_dauphine_side_layers.py`; chỉ mở lại receipt đã xuất: `python scripts/verify_dauphine_side_layers.py --readback 3f73a32c7200467a84f0a76f2166a1b0`.
