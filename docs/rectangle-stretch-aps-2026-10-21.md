# Rectangle stretch: APS Automation đã chạy đạt

Ngày 21/10/2026. Sau khi người dùng cho phép upload bundle plugin và tạo alias thử nghiệm, đã đăng ký alias `rectangle_mvp` rồi chạy bài thử DWG tổng hợp 100×50 → 120×50 mm qua API cloud. Không dùng DWG khách hàng hoặc đề xuất xốp chưa xác nhận trong bài thử.

## Kết quả thực tế

Đã hoàn thành toàn chuỗi: nhập DWG bằng APS → đọc geometry/DIM/source binding → dựng ràng buộc và giải trên backend → gửi contract đến APS AutoCAD → ghi đúng vertex và điểm đo DIM → regen → lưu DWG → mở lại → kiểm native snapshot → tải kết quả → đọc DXF độc lập. Hình thực tế là 120×50 mm, cạnh trái giữ trong dung sai, DIM block chứa chữ `120`, DIMASSOC vẫn handle `45` và bind polyline `2F`, vertex 0/1 cho DIM `30`.

- Cloud engine: `Autodesk.AutoCAD+25_0` (AutoCAD 2025/.NET 8).
- Local đã kiểm trước đó: AutoCAD 2027/.NET 10. Chưa kiểm riêng AutoCAD 2026.
- Document tổng hợp: `40400e8520434f7fa29f3b018a67adfe`.
- Inspection APS: `cf9c8a609da54023bd9bd10b2556da79`.
- Edit APS: `b489b9797f944505be935e7b566d1fa1`.
- DWG nguồn SHA-256 `5f30e2980f9d77f9df9d945d4dc6f1db0e713d6060981e2399d686bdae29ae78` giữ nguyên.
- DWG kết quả SHA-256 `db0929f761c9d1e27de38b1e64d0ce5b19c8a46e06178f9114c762a81eca1246`.
- Solver rank 8, DOF 0, max residual ~1,42e-14 mm.

HTTP thật trên backend workspace: POST trả 202, GET job 200/ready, download 200; bytes tải khớp hash DWG. Gửi lại cùng request dùng lại job cũ, không tạo workitem mới. Source hash sai bị từ chối 422. Hai Automation jobs đọc/sửa đã đạt; bước đọc cũng gửi translation viewer theo pipeline APS hiện hữu. Không tạo customer revision hoặc xác nhận toàn sản phẩm.

## Endpoint

`POST /documents/{document_id}/aps/rectangle-stretch`

```json
{
  "inspection_id": "cf9c8a609da54023bd9bd10b2556da79",
  "polyline_handle": "2F",
  "dimension_handle": "30",
  "target_width_mm": 120,
  "source_hash": "5f30e2980f9d77f9df9d945d4dc6f1db0e713d6060981e2399d686bdae29ae78"
}
```

Ví dụ thuộc document tổng hợp nêu trên; không dùng inspection/hash này cho tài liệu khác. Endpoint cloud là thao tác gửi bản sao CAD và contract lên Autodesk. Cần inspection provider APS đã ready và còn đúng source hash. Endpoint local `/autocad/rectangle-stretch` vẫn dùng AutoCAD trên máy.

Các edit rectangle APS dùng activity riêng cùng base nickname/resource nhưng alias `rectangle_mvp`. Inspection và các operation cloud cũ vẫn dùng alias mặc định đang cấu hình. Không đổi `.env` hoặc alias cloud mặc định. `_advance` chọn lại activity từ loại operation và kiểm cấu hình lưu theo job để giữ khả năng tiếp tục sau restart.

Các khóa bảo toàn vẫn như local: một operation, đúng hai handle polyline/DIM, scope layout, source hash, before geometry, owner/DIMASSOC, cạnh trái và chiều cao, native save/reopen, DXF independent verification. Shared request schema ở `backend/rectangle_models.py`; service `rectangle_stretch_service` nhận provider rõ ràng, không dùng inspection local làm bằng chứng cho cloud hay ngược lại.

## Bundle và đăng ký

Gói `autodesk/MechanicalCad-rectangle-mvp.zip`, SHA-256 `ac5ef9354a616c2d96e99ac414b7eb102ae9a950c45747077a9c4e4649b2e869`: DLL đã biên dịch và PackageContents.xml. Gói cloud mặc định không bị ghi đè. Quyền upload bundle và tạo alias đã được người dùng cấp trực tiếp sau khi kiểm duyệt tự động yêu cầu xác nhận.

Lệnh register hoàn thành ở Autodesk nhưng console CP1252 lỗi khi in chữ tiếng Việt trong JSON. Đã kiểm chỉ đọc alias/activity/bucket để xác nhận thành công, không lặp upload/đăng ký. Proof `storage/validation-fixtures/rectangle-stretch-api-2026-10-21/cloud-registration.json`. Output JSON của nhánh register nay dùng ASCII escapes để tránh lỗi in gây hiểu nhầm phải đăng ký lại.

## Bằng chứng và tái lập

Thư mục `storage/validation-fixtures/rectangle-stretch-aps-2026-10-21/` chứa import-started.json, edit-started.json, api-verification.json, http-verification.json, inventory.json, receipt.json, modified.dwg và roundtrip.dxf. Backend đã nạp endpoint mới; PID khi khởi động lại là 23032.

Kiểm Python hồi quy: **179 đạt, 7 warning thư viện, 27,46 giây**. Thêm kiểm không đổi default alias, job rectangle dùng đúng activity, route dispatch provider APS và kiểm DXF cloud thật bằng verifier độc lập. Các bài dựa vào retained artifact sẽ skip nếu môi trường khác không có fixture. Native cloud test và HTTP thật được báo riêng, không thay bằng unit test.

```powershell
python -X utf8 scripts/verify_rectangle_stretch_api.py --provider aps --source storage/validation-fixtures/point-binding-mvp-final-2026-10-21/source.dwg --output storage/validation-fixtures/rectangle-aps-new-run
```

Lệnh tạo evidence directory mới và gửi DWG đã chọn lên Autodesk; dùng đúng mẫu tổng hợp hoặc dữ liệu đã được cho phép. Không tự gửi lại tác vụ có trạng thái submit không rõ; pipeline lưu workitem/job hiện hữu để kiểm tra tiếp.

## Phạm vi còn thiếu

Đây là MVP rectangle bốn cạnh thẳng có một DIM ngang, giữ cạnh trái/chiều cao và đổi width. Chưa có UI chọn nhóm/vertex và lịch sử revision tích hợp; chưa có writer solver cho LINE, polyline bất kỳ/bulge, multi-DIM stretch, đồng bộ BOM/đa hình chiếu hoặc chứng minh mọi quan hệ cơ khí. Không gọi là chỉnh được mọi DWG. Chưa chạy iterative stretch tiếp trên chính DWG kết quả bằng cloud, AUDIT/RECOVER hoặc kiểm corpus đa dạng. Đề xuất xốp vẫn chưa xác nhận.
