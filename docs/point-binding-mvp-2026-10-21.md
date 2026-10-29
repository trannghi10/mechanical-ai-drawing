# MVP: DWG Point Binding → Solver → Native Stretch

Ngày 21/10/2026. Đã hoàn thành chuỗi thử nghiệm đầu tiên trên mẫu chữ nhật LWPOLYLINE có DIM tuyến tính và DIMASSOC. Runtime thực tế là AutoCAD **2027**, không phải 2026; chưa có bằng chứng chạy trên 2026.

## Kết quả chính

DWG nguồn 100×50 mm → DWG kết quả 120×50 mm. Cạnh trái (vertex 0/3) giữ trong dung sai 1e-7 mm; cạnh phải (vertex 1/2) dịch +20 mm theo X. DIM đo thật 120 mm, block hiển thị có chữ `120`, DIMASSOC giữ handle `45` và trỏ về polyline `2F`, vertex 0/1 của DIM `30`. Đã lưu DWG, mở lại bằng AutoCAD và đọc DXF độc lập bằng ezdxf. File nguồn giữ nguyên hash.

Đây là mẫu tổng hợp được tạo có chủ đích, không phải xác nhận ý đồ trên DWG khách hàng. Điểm giữ/hướng kéo được khai báo rõ, không suy ra tự động từ việc geometry gần nhau. Chưa tự cập nhật BOM, chi tiết khác hoặc các nhóm liên kết ngoài mẫu.

| Giai đoạn | Trạng thái trong phạm vi mẫu |
|---|---|
| 1. Point Binding | Đạt: DWG → handle/owner/vertex/DIM/association và hash |
| 2. Solver Integration | Đạt: ánh xạ v0..v3, giữ trái, giải width=120, hạng 8/DOF 0 |
| 3. DWG Stretch Writer | Đạt: SetPointAt trên đúng polyline; topology/bulge không đổi |
| 4. DIM Synchronization | Đạt: cập nhật XLine points, regen, kiểm measurement/chữ và source binding |
| 5. Save/Reopen Validation | Đạt trên AutoCAD 2027 và DXF readback độc lập |
| 6. API / APS Automation | Chưa triển khai/kiểm chứng operation mới này trên APS; chưa nối UI/revision production |

LINE được dùng làm đối tượng kiểm ngoài vùng sửa, chưa có writer LINE theo solver trong MVP này. Chỉ hỗ trợ chữ nhật bốn đỉnh thẳng, đóng, XY normal +Z, cùng layout với rotated DIM ngang không ghi đè số. Không hỗ trợ bulge, proxy, block động, polyline bất kỳ hoặc suy ý đồ chung.

## Chuỗi lệnh và mã

`autodesk/MechanicalCad/PointBindingMvp.cs` thêm các command cố định:

1. `AICAD_BUILD_FIXTURE`: chỉ phục vụ test; nhập DXF tổng hợp thành `input.cad` dạng DWG. Không ghi đè file nguồn đã có.
2. `AICAD_EXPORT_POINTS`: mở DWG, kiểm đơn vị mm, geometry/owner/reactor/dictionary, DIM đo vertex 0/1. Xuất `point-binding.json` và `source-readback.dxf`.
3. Python `scripts/point_binding_mvp.py::solve_binding`: kiểm binding, DIM, rectangle và intent, tạo constraint IDs cho solver affine. Hai vertex trái fixed, cạnh ngang/đứng và width mục tiêu. Không nhận một trường DOF có sẵn làm bằng chứng.
4. `AICAD_APPLY_POINTS`: đọc `point-solution.json`, kiểm hash nguồn và hash binding, handles/owner/association, vertex nguồn, cạnh trái/chiều cao, hình chữ nhật và width mục tiêu. Ghi vertex và điểm đo DIM đúng đối tượng, recompute block DIM.
5. Lưu `point-candidate.dwg`, mở lại để kiểm geometry, DIM, association handle và inventory ngoài nhóm. Sau khi kiểm native đạt mới đổi tên thành `point-result.dwg` và tạo native receipt. Bản thất bại không được runner công nhận hoặc sao chép thành kết quả đạt. Không sửa nguồn để rollback; các file chẩn đoán riêng vẫn được giữ.
6. Runner `scripts/verify_point_binding_mvp.py` đọc DXF cuối, kiểm tọa độ, control LINE, số đo, chữ và DIMASSOC nguồn/vertex, kiểm hash nguồn/đầu ra rồi mới xuất receipt tổng hợp.

DIMASSOC được giữ và được kiểm lại source reference/vertex bằng DXF. Writer chủ động cập nhật điểm đo DIM từ binding; chưa chứng minh AutoCAD tự cập nhật mọi DIM mà không có writer hoặc mọi lần thao tác tương tác tiếp theo. Không tháo association rồi tạo DIM độc lập.

Chỉ đối chiếu các entry entity inventory được liệt kê ngoài nhóm/visual ownership (2 entry trong mẫu), không khẳng định toàn database giống nhị phân. Bước này chưa chạy AUDIT/RECOVER hoặc chứng minh mọi cấu trúc database được bảo toàn.

## Artifact cuối

Thư mục: `storage/validation-fixtures/point-binding-mvp-final-2026-10-21/`.

- `source.dwg`, `source-readback.dxf`: nguồn thực tế đã mở native.
- `point-binding.json`: ánh xạ vertex/DIM/hash.
- `solver-result.json`: phương trình, residual và tọa độ mới.
- `point-solution.json`: dữ liệu writer.
- `point-result.dwg`, `point-result.dxf`: kết quả và native readback.
- `point-dim-diagnostics.json`: đối chiếu DIM line/style/measurement.
- `receipt.json`: kết quả xác minh tổng hợp.

Hash DWG nguồn: `5f30e2980f9d77f9df9d945d4dc6f1db0e713d6060981e2399d686bdae29ae78`.

Hash DWG kết quả: `e15166ce7808da95485085bb721c7603d620c75fc02bc18b961d9fb5242898c9`.

Kết quả: width nguồn 100 mm, width sau 120 mm, height sau 50,00000000000001 mm; sai số floating point nằm trong dung sai kiểm. Native plugin build/check đạt với runtime key `ed4ae64156c300dff88a4b994a73b2f0695ab784d00ae54aa31006b2f97385e5`.

## Kiểm âm và lỗi đã sửa

Hai kiểm âm native đạt, không tạo DWG kết quả hoặc receipt thành công, giữ hash nguồn:

- `point-binding-mvp-reject-hash-2026-10-21`: nguồn hash sai bị chặn.
- `point-binding-mvp-reject-fixed-edge-2026-10-21`: toàn bộ điểm bị cố ý dịch +1 X, làm đổi cạnh trái, bị chặn trước ghi.

Lượt đầu dừng do getter Measurement cần mở DIM ForWrite sau nhập DXF; đã sửa và xác minh lại. AutoCAD regen đổi DimLinePoint X từ 0 sang 120, vẫn cùng đường DIM ngang Y=-15: kiểm vị trí đường theo Y/Z, điểm đo và rotation, không buộc một điểm đại diện nằm trên đường phải giữ cùng X. Diagnostics ghi rõ sự thay đổi này.

Fixture ban đầu thiếu tham chiếu DIMSTYLE→text style nên regen mất chữ DIM; kiểm label đã phát hiện và không cấp receipt đạt. Fixture đã khai báo dimtxsty=`Standard`, font `txt.shx`; lượt sau đạt cả chữ DIM thật. Có kiểm thử giữ cấu hình này. Ảnh `before.png`/`after.png` trong lượt `point-binding-mvp-100-to-120-complete-2026-10-21` được dựng từ DXF native và đã xem kiểm, hiển thị 100/120; đây là lượt đạt trước lượt xác nhận cuối.

Kiểm Python binding/fixture, solver affine/phi tuyến và DIMASSOC perpendicular: **42 đạt, 7 warning thư viện, 0,94 giây**. Không dùng kết quả unit test để thay thế native run đã nêu.

## Chạy lại

Dùng thư mục mới cho mỗi lượt để giữ bằng chứng:

```powershell
python scripts/verify_point_binding_mvp.py --output storage/validation-fixtures/point-binding-mvp-new-run --target 120
python scripts/verify_point_binding_mvp.py --output storage/validation-fixtures/point-binding-mvp-new-rejection --negative fixed-edge
```

Bước tiếp theo: đưa command/contract vào job API có snapshot/hash/artifact integrity hiện hữu, chạy provider APS trên phiên bản engine được cấu hình và kiểm lại cùng fixture. Sau đó mở rộng LINE/rectangle khác và iterative edit; chưa mở khả năng stretch mọi DWG, chưa tạo customer revision và chưa xác nhận đề xuất xốp.
