# DIMASSOC có snap perpendicular và last point lồng nhau

Đã bổ sung phân tích `hasLastPointRef` và cập nhật liên kết perpendicular cho một dạng thực tế: điểm đo thứ hai của DIM rotated lấy chân vuông góc trên cạnh thẳng của LWPOLYLINE đóng XY; last point là endpoint cùng polyline và phải khớp đúng điểm đo đầu.

Autodesk mô tả code 72=8 là Perpendicular và code 75 là hasLastPointRef trong [DIMASSOC DXF reference](https://help.autodesk.com/cloudhelp/2020/ENU/AutoCAD-DXF/files/GUID-C0B96256-A911-4B4D-85E6-EB4AF2C91E27.htm). Việc phân nhóm tham chiếu lồng được đối chiếu với thứ tự tag thực tế và kiểm chứng qua AutoCAD, không suy ra chỉ từ tọa độ cache.

## Dữ liệu Dauphine

DIM `3DFA20`, association `3DFA22`, flags 3 có hai point reference chính nhưng ba đoạn `AcDbOsnapPointRef`: endpoint đầu, perpendicular thứ hai với code 75=1, rồi endpoint last point lồng. Bộ đọc cũ đếm phẳng ba đoạn thành ba điểm đo và từ chối.

Source polyline `3DFA1C`: last point là vertex 1, cạnh perpendicular là edge 5 (GS marker 6). Chân vuông góc cách vertex 6 khoảng `2.8205420676385984e-05` đơn vị CAD, lớn hơn dung sai 1e−6, nên không được thay bằng endpoint gần nhất. Cache chứa Z `2e50` không được dùng làm tọa độ nguồn.

Sau thay đổi, bốn DIMASSOC `3DFA1D`, `3DFA20`, `3DFA25`, `3DFA2A` đều xác minh point binding về cùng polyline. Đây là kiểm tra chỉ đọc, không sửa bản vẽ thật. Receipt `storage/validation-fixtures/dimassoc-perpendicular-real-binding-2026-10-21/receipt.json`.

## Mã và giới hạn

`cad/osnap_references.py` phân tích cấu trúc có giới hạn 64 đoạn và độ sâu 4; chặn cờ sai, thiếu last point hoặc dữ liệu lớp khác. `cad/dimension_associations.py` kiểm đúng marker, nguồn, endpoint last point và hình chiếu vuông góc duy nhất trên đoạn thẳng. Khi source thay đổi, chân vuông góc được tính lại từ anchor nguồn; không gắn nó vào vertex gần nhất.

Giữ snap 8, cờ last point và tham chiếu source; cập nhật marker, tham số và cache WCS của cả root lẫn child. Bộ verify kiểm cây tham chiếu, point nguồn, cache sau ghi và snap/flag sau native readback. Các dạng child khác, nguồn khác polyline, cạnh cung, chân nằm ngoài đoạn, anchor không khớp hoặc góc DIM chưa được chứng minh không được dùng để suy rộng phạm vi hỗ trợ. Bằng chứng native hiện là DIM rotated góc 0.

## Sửa và xuất/mở lại CAD

Mẫu tổng hợp tái tạo cấu trúc lồng và cache cũ của dữ liệu thật, với chân vuông góc nằm trong cạnh, cách endpoint 3e−6. Đã nhập native, sửa chiều ngang **90,5 → 95 mm**, xuất DWG và mở lại bằng AutoCAD 2027:

- Document `643b81ca4337409cb1e033a23a26f6b8`, đặt rõ `$INSUNITS=4` (mm); kiểm mm cả trước và sau native export.
- Native import `c19effb39a8741fba5d24bb2bef90250`.
- Export `77a69b84cc5440cabe232a73d011a310`.
- DWG SHA-256 `356c3ae3f4c7070dbf87a90e5449de225b855689b1de516188e64f52e20cb79c`.
- Readback đo 95 mm; snap vẫn là perpendicular 8, last point vẫn là endpoint cùng nguồn. `verify()` đối chiếu cache, source geometry, marker và cấu trúc lồng qua DXF xuất từ DWG mở lại.
- Receipt và patch: `storage/validation-fixtures/dimassoc-perpendicular-native-mm-2026-10-21/`.

Mẫu đầu trong `dimassoc-perpendicular-native-2026-10-21/` dùng đơn vị mặc định mét của ezdxf, chỉ chứng minh liên kết với số đo theo đơn vị CAD. Receipt đó đã sửa nhãn đơn vị; không dùng làm bằng chứng 95 mm. Bằng chứng mm là lượt có kiểm `$INSUNITS` nêu trên.

Script `scripts/verify_dimassoc_perpendicular.py` lặp lại toàn luồng trên file tổng hợp và giữ nguồn. `scripts/dimassoc_perpendicular_fixture.py` dùng chung cho kiểm thử và CAD probe. Kiểm thử trực tiếp còn xác nhận chân được chiếu lại khi anchor thay đổi, thay vì đi theo endpoint, và từ chối projection ra ngoài đoạn.

Lượt CAD thứ hai thêm `--anchor-dy -2`: document `13bd6025f4a74ae684f7800eb01afd3f`, export `c2624e6289984f54894281361ba99aa4`. Chân vuông góc và anchor đổi từ Y=76,499997 xuống 74,499997 mm, tham số root đổi từ khoảng 0,999999952 thành 0,967999952; DIM vẫn đo 95 mm, snap 8 và last point được giữ qua DWG readback. SHA-256 `162e9e946aed26ebb48656aac2c433eec3a809984cfbbac31eeb9ed92f49bed4`; receipt ở `storage/validation-fixtures/dimassoc-perpendicular-moving-anchor-2026-10-21/`.

Cả hai mẫu mm có `annotation-verification.json`: chữ trong block DIM của native readback là `95`, số đo là 95, đơn vị mm. SVG/PNG `readback.svg` và `readback.png` được render từ readback thật; đã xem ảnh mẫu moving-anchor, nhãn 95, đường dóng và biên dạng hiển thị đúng. Không dùng ảnh đề xuất AI làm bằng chứng.

**166 bài** geometry/nested-perpendicular đạt, 223 warning thư viện, 38,01 giây. Không tạo revision khách. Toàn nhóm polyline–sáu DIM của Dauphine vẫn cần adapter cho hai `AcDbAssocRotatedDimActionBody` còn lại và kiểm CAD chung; việc xác minh được bốn DIMASSOC chưa đủ để sửa toàn nhóm. Đề xuất tấm xốp vẫn chưa xác nhận.

Hồi quy cuối **1.755 bài đạt**, 2.723 warning thư viện, 250,28 giây; log `storage/validation-fixtures/pytest-nested-perpendicular-final-2026-10-21.txt`. Parser giữ tương thích thứ tự tag của tham chiếu phẳng (không bắt code 75 nằm cuối). Source capability `3DFA1C` vẫn là `native_required`, actions rỗng vì còn native association; snapshot tại `dimassoc-perpendicular-real-binding-2026-10-21/remaining-source-capability.json`. Không mở quyền sửa cả nhóm bằng việc chỉ sửa lỗi parser.
