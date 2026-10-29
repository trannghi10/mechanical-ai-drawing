# API job: solver → rectangle stretch DWG

**Cập nhật:** sau khi người dùng cho phép, alias thử nghiệm đã được đăng ký và APS đã chạy đạt. Xem [báo cáo cloud mới](rectangle-stretch-aps-2026-10-21.md). Các mô tả “chưa upload” bên dưới là trạng thái lịch sử trước chấp thuận.

Ngày 21/10/2026. Đã đưa phép sửa chữ nhật có DIM/DIMASSOC vào contract job native, thêm endpoint riêng và kiểm bằng AutoCAD thật. Phạm vi geometry giữ như MVP: chữ nhật LWPOLYLINE đóng bốn cạnh thẳng trong layout, DIM ngang đo vertex 0/1, đơn vị mm, giữ cạnh trái/chiều cao. Chưa có UI chọn vertex, operation LINE, generic stretch hoặc BOM.

## Endpoint local đang hoạt động

`POST /documents/{document_id}/autocad/rectangle-stretch` trả HTTP 202, body:

```json
{
  "inspection_id": "9781e08ad9ae4f31a05b8bff334037c9",
  "polyline_handle": "2F",
  "dimension_handle": "30",
  "target_width_mm": 120,
  "source_hash": "5f30e2980f9d77f9df9d945d4dc6f1db0e713d6060981e2399d686bdae29ae78"
}
```

Ví dụ này thuộc document tổng hợp `b744011ff1c446f2b9b6c703ea810572`. Dùng inspection/hash/handle của chính tài liệu khi gọi trên tài liệu khác. Endpoint nhận ý đồ rõ giữ cạnh trái, không suy đoán quan hệ cơ khí từ vị trí gần nhau.

Đọc tiến độ tại `GET /documents/{document_id}/autocad/jobs/{job_id}`; tải theo download_url sau ready. Job được lưu và cùng contract/source/runtime sẽ được dùng lại, không chạy lặp khi gửi lại. File nguồn được giữ nguyên; đây là đầu ra job preview, chưa tạo revision khách hàng hoặc phê duyệt toàn sản phẩm.

## Quy trình kiểm

- `backend/services/rectangle_stretch_service.py`: kiểm inspection local đã ready và thuộc hash DWG hiện tại; lấy inventory/DXF cùng job qua artifact hash guard; xác minh DIMASSOC vertex nguồn, dựng binding và gọi solver.
- Bộ binding chuyển sang `cad/point_binding.py`; script cũ giữ import tương thích.
- `NativeOperation` thêm stretch_rectangle và dimension_handle/association_handle. Validator yêu cầu bốn XYZ hữu hạn, chữ nhật dương, cạnh trái và chiều cao giữ, width phải đổi. Job chỉ nhận đúng một operation trên DWG local, scope chính xác polyline và DIM. Không mở provider APS cho operation mới.
- Plugin `MECHANICALCAD` chạy nhánh rectangle: tự export binding từ DWG thực tế, đối chiếu before vertices, owner và association với contract; dùng native writer MVP đã kiểm chứng; lưu/mở lại rồi đóng gói bốn artifact chuẩn.
- Trước trạng thái ready, `cad/rectangle_stretch.py` đọc DXF độc lập để kiểm đơn vị/geometry/owner/topology, measurement, source binding DIMASSOC và chữ DIM. Sai nguồn/output hash, geometry, liên kết hoặc chữ đều không được công nhận.

Nguồn trước sửa được kiểm lại trên native database; kết quả không được công nhận chỉ từ số width hoặc success của solver. Kiểm inventory ngoài nhóm dùng snapshot native hiện có của MVP, không chứng minh toàn database đồng nhất nhị phân hoặc mọi liên kết cơ khí đầy đủ.

## Kết quả thực tế

Kiểm ASGI qua FastAPI TestClient kết hợp worker AutoCAD 2027 thật, sau đó khởi động backend và gọi HTTP localhost thật:

- Document `b744011ff1c446f2b9b6c703ea810572`.
- Inspection `9781e08ad9ae4f31a05b8bff334037c9`.
- Edit job `a770d9df24564c08adc62c30cdf8367e`.
- Solver rank=8, DOF=0, max residual ~1,42e-14 mm.
- Nguồn 100×50 → kết quả 120×50, DIM text 120, liên kết vertex 0/1 hợp lệ sau native reopen và DXF readback.
- HTTP POST=202, GET job=200/ready, download=200; bytes tải xuống khớp artifact hash. Gửi lại trả cùng job; source hash sai trả 422.
- DWG đầu ra SHA-256 `0272a1ca67317ed828c57ac9dcbc9f979a4339c076c765d57f219d6ffe44706f`.
- Nguồn giữ SHA-256 `5f30e2980f9d77f9df9d945d4dc6f1db0e713d6060981e2399d686bdae29ae78`.

Bằng chứng tại `storage/validation-fixtures/rectangle-stretch-api-2026-10-21/`: api-verification.json, http-verification.json, inventory.json, receipt.json, modified.dwg và roundtrip.dxf. Endpoint thực tế đã được nạp trên backend localhost:8765; PID lúc khởi động 21644.

Plugin local build/check đạt runtime key `071f34acf273f3e06166518e1687d44449ecee2eeed2bcc1b3b7127b0813301b`.

Kiểm Python liên quan **175 đạt, 7 warning thư viện, 14,66 giây**. Bao gồm validator/action/API schema, binding/fixture, export jobs/CenterMark và kiểm làm sai receipt, tọa độ, chữ DIM, association trên artifact thật. Các bài dùng fixture thật sẽ skip nếu fixture không có trên môi trường khác. Chưa kiểm interactive browser/UI mới.

Chạy lại mẫu trên một evidence directory mới:

```powershell
python scripts/verify_rectangle_stretch_api.py --source storage/validation-fixtures/point-binding-mvp-final-2026-10-21/source.dwg --output storage/validation-fixtures/rectangle-api-new-run
```

## APS: gói đã sẵn sàng duyệt, chưa upload

Cấu hình APS hiện bật và có đủ khóa. Runtime cloud hiện ghim `Autodesk.AutoCAD+25_0` (.NET 8); local là AutoCAD 2027 (.NET 10). Đã tìm được DLL SDK Autodesk 2025 tại DWG TrueView và build cloud thành công với .NET SDK 8.0.426 (3 warning tham chiếu, 0 lỗi).

Thêm tham số PackagePath vào build-aps.ps1 để xuất gói riêng, giữ nguyên gói cloud mặc định. Gói mới `autodesk/MechanicalCad-rectangle-mvp.zip`, SHA-256 `ac5ef9354a616c2d96e99ac414b7eb102ae9a950c45747077a9c4e4649b2e869`, chỉ chứa:

- MechanicalCad.bundle/Contents/MechanicalCad.dll (140.800 byte).
- MechanicalCad.bundle/PackageContents.xml (751 byte).

Manifest review: `storage/validation-fixtures/rectangle-stretch-api-2026-10-21/cloud-package-review.json`. Đây là mã plugin nội bộ đã biên dịch và manifest; DWG không nằm trong gói.

Đã yêu cầu đăng ký bundle vào alias riêng rectangle_mvp để chạy mẫu tổng hợp, nhưng automatic approval review từ chối trước khi chạy lệnh: chưa có ủy quyền rõ cho việc gửi payload mã nội bộ cho Autodesk hoặc tạo/cập nhật alias cloud cụ thể. Không retry bằng đường khác; chưa upload bundle, chưa tạo alias và chưa đổi .env/alias cloud hiện tại.

Bước cần người dùng cho phép: tải chính gói đã build này lên Autodesk APS, tạo alias rectangle_mvp riêng và chạy mẫu DWG tổng hợp. Sau đó mới kiểm operation/provider APS và tích hợp cloud endpoint. Build thành công không được coi là cloud round-trip đã đạt; AutoCAD 2026 cũng chưa được kiểm riêng.
