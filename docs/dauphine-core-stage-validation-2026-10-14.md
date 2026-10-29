# Cụm xương, thanh cắt và Detail D — 14/10/2026

## Phần sửa mới

- Tấm 21: `1,5×721×808 → 1×695×809,002 mm`, giữ khe hở nguồn với lòng tấm cung và hai tấm ngoài 17–18. Cửa lắp có DIM thật giảm `724 → 697 mm`.
- Thanh 5: chiều dài cắt `721 → 695 mm`, tiết diện `14×14×1,2 mm`, giữ số lượng 12. Thanh 4: `717 → 692 mm`, giữ khe hở 0,5 mm mỗi đầu theo quyết định của người dùng.
- Hình chiếu đứng C4: cao `721 → 695 mm`; ba tầng tấm đổi về 1 mm, tầng giữa giữ đối xứng; khoảng trống giữa hai mặt trong trên/dưới là 693 mm, thanh 692 mm nằm giữa với hai khe 0,5 mm. Khoảng trống hai tầng bằng nhau là 346 mm. Phụ kiện/ren thuộc block nhỏ được dịch nguyên instance; các tiết diện hộp giữ kích thước nguồn.
- Ba cụm la xương C1/C2/C3: mặt cắt đo thật, tên bản công đoạn và BOM đổi `1,5 → 1 mm`. Chỉ lan truyền khi toàn bộ thành viên trong bảng kê cụm cùng vật liệu và đều có thao tác đổi dày thực sự được thực thi.
- Detail D ở khung hàn bước 2: thành hộp `2 → 1,2 mm` theo BOM, hai mặt tấm `1,5 → 1 mm`, cụm ren giữ tiếp xúc mặt trong. Cắt lại các nét tại vòng trích cố định. Các nhãn `2` có gạch lịch sử vẫn được giữ, không coi là kích thước đang dùng.
- Sửa lỗi dung sai bị vẽ hai lần trên DIM danh nghĩa của hình rút ngắn. Giữ nguyên dung sai native, không sửa `DIMLFAC` để giả chiều dài hình vẽ.
- Sửa bộ dựng DIM góc khi hai cạnh giao ở giữa/ngoài đầu nét: giữ sector nguồn, kiểm tra cung dựng lại và lưu group 42 theo radian. Mở lại DWG kiểm tra 7 góc vuông vẫn hiển thị 90°, không biến thành 270°. Giữ phía chữ nguồn của DIM thẳng đo theo chiều ngược để hạn chế chồng nhãn.

## File xuất đã kiểm chứng

- DWG mới: `storage/backups/Dauphine-PREVIEW-cum-xuong-thanh692-DetailD.dwg`.
- [Tải DWG xem trước](http://127.0.0.1:8765/documents/34ee84f35e1a44fb81c56044397a0fff/revisions/48791a88907c46b7991c962106d86499/exports/c1222591406b425c960232730db28900/download).
- [Xem hình chiếu đứng C4](http://127.0.0.1:8765/explorer?doc=34ee84f35e1a44fb81c56044397a0fff&target=3ADF05&revision=48791a88907c46b7991c962106d86499).
- Revision `48791a88907c46b7991c962106d86499`, plan `a7c123c47b0a49ac90a6429b62afd838`.
- SHA256 DWG: `3b6724404f945762eb94be0db72830f38452c648c245adfcdcac9b48d64fb88a`.
- 395 thao tác; mở lại DWG kiểm tra riêng 129 thao tác mới, 7 dòng BOM native, 2 DIM cắt danh nghĩa giữ dung sai và hình rút ngắn. FreeCAD kiểm tra 27 mặt; không phải kiểm tra toàn cụm lắp.
- Tải qua API: HTTP 200, 2.227.891 byte, hash khớp; preview HTTP 200; duyệt toàn sản phẩm vẫn bị chặn (422). Nguồn không đổi.
- Luồng tạo revision, kiểm tra CAD và xuất cần khoảng **215 giây** trên máy này, chưa bao gồm toàn bộ bước dựng các ảnh đối chiếu sau xuất. Đây chưa phải tốc độ tức thì; không dùng thời gian suy luận model để mô tả tốc độ xuất DWG.
- Biên nhận, kết quả mở lại và HTTP: `storage/validation-fixtures/dauphine-combined/48791a88907c46b7991c962106d86499/{receipt,core-stage-readback,http-readback}.json`. Các revision xuất trước đó trong lượt thử này là bản trung gian.

## Cơ chế kiểm chứng

Các quyết định kỹ thuật được gắn với SHA256 của nguồn. Bản gốc không bị sửa. Engine dùng mã/BOM, đường bao, DIM và bảng công đoạn nguồn; không nhúng handle Dauphine trong bộ sửa dùng chung.

`graph/laminar_stage_gauges.py` kiểm tra toàn bộ vật tư của cụm tấm, màu vật liệu không được dùng làm bằng chứng. `graph/confirmed_inner_tubes.py` phân biệt chiều dài cắt danh nghĩa và chiều dài hình rút ngắn. `graph/core_stack_views.py` chỉ sửa hình chiếu đứng có chuỗi DIM đối xứng, mặt trên/dưới và hai nhóm thanh nguồn được kiểm chứng. `graph/corner_wall_contacts.py` chỉ sửa vòng trích có ba DIM đo thật và cụm ren tiếp xúc đã xác định.

Kiểm thử Python: **766 passed**, log `storage/validation-fixtures/pytest-core-stage-20261014-ship.txt`. Có các mẫu sản phẩm khác kiểm tra giữ tiết diện, khe hở, chuyển block nguyên khối, BOM công đoạn, dung sai, góc thường/góc lớn và phía chữ DIM; các trường hợp sai hash, thiếu DIM, vật liệu khác, thêm vật tư chưa đổi hoặc mốc không nhất quán phải bị chặn.

Chạy lại xuất/mở DWG thực tế:

```powershell
Set-Location D:\mechanical-ai-drawing
& 'C:\Users\nghi.tran\AppData\Local\Programs\Python\Python310\python.exe' scripts/verify_dauphine_core_stage.py
```

Script sử dụng luồng tạo revision, kiểm tra FreeCAD, ODA, mở lại DWG và kiểm tra số đo/BOM/dung sai; không gọi model hay gửi bản vẽ ra cloud. Biên nhận nằm trong `storage/validation-fixtures/dauphine-combined/<revision_id>/receipt.json`, kết quả đo trong `core-stage-readback.json`.

## Phần chưa hoàn chỉnh

Đây vẫn là **xem trước một phần**. Hình chiếu cạnh/phối cảnh C4, Detail C cong, các hình cụm/công đoạn khác và một số đệm/góc đóng gói còn chưa đồng bộ đầy đủ. Kiểm tra mặt FreeCAD của các recipe không thay thế kiểm tra toàn cụm lắp. Không chứng nhận độ bền, khả năng chế tạo, không tuyên bố sửa đúng mọi DWG.

File xuất không được duyệt thành backup hoàn chỉnh khi các phần này còn thiếu. Dynamic block, proxy association và liên kết thiết kế thiếu bằng chứng vẫn cần bộ xử lý tương ứng; thêm model không tự tạo ra các ràng buộc đó.
