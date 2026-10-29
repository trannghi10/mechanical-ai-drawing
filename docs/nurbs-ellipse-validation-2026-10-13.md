# Bộ sửa dùng chung: B-spline không tròn và ellipse

Ngày 13/10/2026. Đã triển khai bằng mã nguồn dùng chung, không thêm mapping theo handle/sản phẩm. ODA và FreeCAD hiện có chạy cục bộ; không gửi CAD sang dịch vụ ngoài.

## Phạm vi mới

- `cad/nurbs_profiles.py`: đọc B-spline kẹp đầu bậc 1–8, tối đa 257 control points, trọng số dương (tỷ lệ nhỏ nhất/lớn nhất ≥ 1e-12). Hỗ trợ các bội knot nội bộ hợp lệ, dùng knot insertion chính xác để phân rã thành rational Bezier. Ellipse phẳng được biểu diễn toán học bằng các span quadratic rational chính xác để kiểm tra. File CAD đầu ra vẫn giữ nguyên loại SPLINE/ELLIPSE.
- Locator dùng chặn convex hull với sai số tối đa 1e-6 đơn vị bản vẽ cho mỗi đoạn NURBS. Locator chỉ phục vụ tìm đường bao, DIM và kiểm tra sơ bộ; không được xuất thay cho đường cong CAD. Có giới hạn độ sâu, số điểm, bộ nhớ đệm và lọc theo vùng DIM trước khi chia nhỏ đường cong.
- `cad/curved_profiles.py`, `cad/parametric.py`: sửa chiều dài theo DIM nguồn với các đầu cong dịch cứng; chỉ cạnh thẳng song song trục đo được kéo/thu. Giữ knots, degree, weights, tham số ellipse, trục ellipse, lỗ và mốc người dùng chọn. Curve/control hull đi qua cả hai vùng co/giãn bị từ chối; không suy diễn biến dạng tự do.
- `cad/planar_profiles.py`, `cad/freecad_worker.py`: dựng lại chính các rational curves trong OpenCASCADE, kiểm tra mặt thật trước/sau và BOPCheck, lỗ bên trong, lỗ không giao nhau. Không dùng polygon xấp xỉ để chứng nhận bản xuất. Kiểm thử riêng xác nhận kernel từ chối đường NURBS tự giao.
- Bổ sung extrusion vào snapshot ellipse, giữ mặt phẳng khi sửa, sửa vùng truy xuất và planning context để bao đủ trục nhỏ. Curve chưa hỗ trợ nhưng có thể cắt vùng sửa không được âm thầm bỏ qua vì mọi control point nằm ngoài vùng.
- Prompt và `/cad/capabilities` mô tả các giới hạn thực tế. Luồng nhận diện khung/bản vẽ hiện tại không đổi.

## Luồng DWG qua server thật

Hai tài liệu độc lập dưới đây là fixture kiểm thử cấu trúc, không phải backup sản phẩm khách hàng. Trong mỗi luồng: tạo CAD → ODA chuyển DWG → upload → chọn block → nhập chiều dài 140 → 123 mm giữ tâm → apply → xem SVG → duyệt fixture → xuất/tải DWG → ODA mở lại → đo native DIM và kiểm tra đường cong/lỗ. SHA-256 file nguồn giữ nguyên.

| Trường hợp | SPLINE bậc ba có trọng số, không tròn | Ellipse không tròn |
|---|---|---|
| Block lồng | 7 cấp, quay từng cấp, root scale 2 | 8 cấp, quay từng cấp, root scale 2 |
| Native DIM sau mở lại | 123 mm | 123 mm |
| Lỗ | 2 lỗ R2 giữ nguyên | 2 lỗ R2 giữ nguyên |
| Diện tích mặt trước/sau, mm² | 4018.0535785152 → 3508.0535785245 | 3917.3450548358 → 3407.3450548364 |
| Kiểu CAD đầu ra | SPLINE, bậc/nút/trọng số giữ nguyên | ELLIPSE, trục/ratio/start/end/extrusion giữ nguyên |
| Document | `fc7a74e102d54d8fad1b91cc682d218c` | `5c581fb2087f4e13a161f8f896ae2c44` |
| Revision | `92f97b27d64b457ba299e50772c5b8f5` | `784a1b71ef1641948103e1f850f022ac` |
| Receipt | [SPLINE](../storage/validation-fixtures/general-workflow-416471a5/report.json) | [Ellipse](../storage/validation-fixtures/general-workflow-28510a74/report.json) |
| DWG tải về | [SPLINE](../storage/validation-fixtures/general-workflow-416471a5/download/checked-preview.dwg) | [Ellipse](../storage/validation-fixtures/general-workflow-28510a74/download/checked-preview.dwg) |
| Preview đã kiểm tra bằng mắt | [SPLINE](../storage/validation-fixtures/general-workflow-416471a5/after.png) | [Ellipse](../storage/validation-fixtures/general-workflow-28510a74/after.png) |

Lệnh tái kiểm chứng: `python scripts/verify_general_dwg_workflow.py --nurbs --depth 7 --approve` hoặc `--ellipse --depth 8 --approve`. `--approve` chỉ duyệt fixture tổng hợp do script tạo.

Kiểm thử có BOM riêng xác nhận mô tả `Bas 2x20x100` → `Bas 2x20x76`, DIM đổi tương ứng, block khác dùng chung definition không bị sửa và nguồn giữ nguyên.

## Đối chiếu Dauphine

Đã kiểm tra SHA-256 ngữ cảnh lưu trùng file DXF nguồn hiện hành: `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

Trong **ngữ cảnh liên quan gồm 37.125 entities**, adapter nhận định nghĩa 3.373/3.380 SPLINE và 1.616/1.616 ELLIPSE. Đây là khả năng đọc hình học, không phải số chi tiết được sửa hay toàn bộ file. Index mới tìm 116 feature đo được, nhưng **0 feature có SPLINE/ELLIPSE gắn đủ DIM và chủ sở hữu nguồn**. Vì vậy các số này không chứng minh hình cụm/uốn/đóng gói Dauphine đã đồng bộ.

- [Coverage định nghĩa](../storage/validation-fixtures/dauphine-nurbs-definition-coverage-20261013.json).
- [Feature bindings kiểm tra lại](../storage/validation-fixtures/dauphine-nurbs-features-20261013.json).

Các lựa chọn đã chốt của user vẫn giữ: thành phẩm 700, khung 697, giữ chân/hạ mặt trên 27; tấm 1 mm chờ cấp mã; giữ biên ngoài R406,5 và vị trí lắp. Không đổi thành chỉ sửa một công đoạn rồi ghi nhãn hoàn chỉnh.

## Chưa hoàn thành

Không phải khả năng sửa mọi DWG bất kỳ. Chưa có sửa tham số dynamic block, tái tính opaque proxy association, biến dạng NURBS tự do, periodic/fit-point-only SPLINE hoặc ellipse nghiêng. Quan hệ giữa các mã chi tiết, hình phối cảnh, quy tắc triển khai phôi uốn và tiếp xúc đóng gói vẫn cần bằng chứng thiết kế nguồn; adapter đường cong không tự cung cấp những bằng chứng đó.

Backup toàn sản phẩm Dauphine vẫn chưa hoàn chỉnh. Hai file DWG kiểm thử phía trên không thay thế bản đó. Không gỡ các cổng kiểm tra để xuất bản chưa đồng bộ.

Kiểm thử toàn bộ: **567 passed, 301 warnings trong 66,83 giây**; log `storage/validation-fixtures/pytest-nurbs-20261013.txt`. Hai kiểm tra giao diện `verify_frontend.js` và `verify_frontend_downloads.js` cũng đạt. Kiểm thử kernel độc lập trả lỗi `Self-intersecting wire / Unorientable shape` cho curve tự giao, không chứng nhận mặt đó. Kiểm chứng tải sau khi nạp lại server được ghi trong các receipt ở bảng trên.
