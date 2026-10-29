# Bằng chứng native vertex cho nhóm sáu DIM, 21/10/2026

Đã đọc trực tiếp subentity từ AutoCAD 2027 trên bản sao nguồn, không sửa bản vẽ khách hàng. Native getter trả về một vertex cho mỗi geometry dependency, không phải hai đầu DIM.

| DIM | Dependency | Action | Transient vertex ID | Vertex polyline (zero-based) | Đầu DIM khớp duy nhất |
|---|---|---|---|---|---|
| `3DFA24` | `3E032B` | `3E0329` | 3 | 2 | `defpoint3` |
| `3DFA29` | `3E0331` | `3E032F` | 8 | 7 | `defpoint3` |

Không suy ra quy tắc index trừ một cho mọi entity. Ánh xạ được đối chiếu từ tọa độ vertex mà native getter trả về, danh sách điểm polyline và điểm đo DIM, với đúng một kết quả khớp. Các dependency này không cache geometry. Persistent ID là lớp nội bộ `ImpAssocPersSubentityId`; không giải mã bộ nhớ hoặc binary của lớp đó.

Tài liệu Autodesk mô tả [AssocGeomDependency giữ persistent subentity ID](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_AssocGeomDependency.html), [TransientSubentIds](https://help.autodesk.com/cloudhelp/2024/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_AssocGeomDependency_TransientSubentIds.html) và [VertexSubentityGeometry](https://help.autodesk.com/cloudhelp/2024/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_AssocGeomDependency_VertexSubentityGeometry.html). Kết luận hai đầu DIM cụ thể ở đây đến từ kiểm tra trên file, không phải giả định rằng mọi native action đều ánh xạ tương tự.

## Bằng chứng lưu trên máy

Dưới `storage/validation-fixtures/`:

- `native-poly-dim-probe-00d2a570/poly-dim-subentities.json`: đọc nguồn; nguồn giữ nguyên, không tạo DWG đầu ra.
- `native-poly-dim-probe-773e6a38`: kéo 905→925 mm; đối chiếu hai native vertex binding trước và sau lưu/mở lại.
- `native-poly-dim-probe-c55b6378`: thu 905→885 mm; đối chiếu hai native vertex binding trước và sau lưu/mở lại.
- `native-poly-dim-probe-1e3f7b4a`: hồi quy dịch X=3, Y=2 mm sau khi bổ sung đọc subentity.

Hai lượt stretch đều đạt sáu DIM/54 primitive và kiểm 39.856 mục ngoài nhóm. `native_endpoint_bindings_verified_after_reopen.count=2`. Receipt giữ hai báo cáo native, fingerprint trước/sau và hash DWG tương ứng; parser kiểm lại dependency/action, vertex index và transient ID không đổi. Native preflight kiểm lại topology, live vertex, đầu DIM và đích kéo trước khi ghi; sau worker, Python còn so fingerprint báo cáo nguồn vừa đọc với báo cáo đầu vào trước khi chấp nhận receipt.

## Native action tự cập nhật đầu DIM

Đã thêm chế độ thử `--native-auto-endpoints` (phải kèm `--subentity-evidence`). Trong chế độ này, writer không gán `XLine2Point` của hai DIM có native vertex evidence. Nó cũng không gán lại `XLine1Point` khi điểm đó không đổi; các điểm còn thiếu binding vẫn được ghi bằng writer và vẫn là giả định thử nghiệm.

| Phép thử | Thư mục dưới `storage/validation-fixtures/` | Kết quả |
|---|---|---|
| Native auto, 905→925 mm | `native-poly-dim-probe-41f4a640` | Đạt native evaluate, sáu DIM/54 primitive, save/reopen và hai vertex bindings |
| Native auto, 905→885 mm | `native-poly-dim-probe-6c3afb34` | Đạt cùng các kiểm tra |

Receipt ghi `native_auto_endpoints=true` và `native_updated_endpoints[].writer_assigned=false`. DIM `3DFA29` tự cập nhật đầu B theo đỉnh 7 dịch ±20 mm, số đo 625→645/605; đầu B của DIM `3DFA24` thuộc đỉnh 2 giữ nguyên. Không coi việc giữ nguyên này là phép thử chuyển động cho đầu B đó. Báo cáo `poly-dim-native-evaluation.json` ghi action cuối cùng `IsUpToDateAssocStatus` và các điểm DIM sau evaluate; native code kiểm trạng thái cả hai action.

Lượt thử ban đầu khi vẫn gán lại đầu A không đổi bị chặn bởi action chưa up-to-date (`native-poly-dim-probe-e8ca2c98`), không tạo DWG đầu ra. Sau khi bỏ thao tác gán thừa trong chế độ native auto, hai chiều kéo đạt. Bằng chứng lỗi được giữ; không suy rộng cách xử lý này cho mọi native action hoặc DWG.

Plugin local build/check đạt với runtime key `50cd1fb90b5c3f221fb4a6c90aba28187c3b1a10c023edae061ab6dae5d617d4`. Chế độ auto chỉ thuộc probe cục bộ, chưa mở thành API/UI sản phẩm.

Hồi quy writer mặc định sau khi tách chế độ auto: `native-poly-dim-probe-affd524d` đạt 905→925 mm, sáu DIM/54 primitive và hai vertex bindings sau save/reopen; `native_auto_endpoints=false`. Các lượt probe giữ nguyên hash file nguồn và không tạo customer revision.

Trạng thái mới của 12 đầu DIM: 6 đầu có DIMASSOC, 2 đầu có native vertex evidence, 2 đầu native còn là ứng viên vertex, 2 đầu chưa có liên kết. Các đầu `defpoint2` của `3DFA24`/`3DFA29` chưa có bằng chứng subentity; không tự coi chúng đã được native action ràng buộc.

`release_gate.allowed=false`, `mechanical_group_complete=false`, `customer_revision_created=false`. Bằng chứng native vertex không chứng minh ý đồ cơ khí hay quan hệ toàn sản phẩm. Đề xuất xốp 3.8.01312 vẫn chưa xác nhận.

## Sử dụng

```powershell
python scripts/probe_native_polyline_dimensions.py 51ec94944c4443b19fb8d5bd7930a6dd 3DFA1C --inspection-job ea4b1d186ca4453e9db9cd06c55ef263 --inspect-subentities

python scripts/probe_native_polyline_dimensions.py 51ec94944c4443b19fb8d5bd7930a6dd 3DFA1C --inspection-job ea4b1d186ca4453e9db9cd06c55ef263 --stretch-width 925 --allow-unbound-test-assumptions --subentity-evidence storage/validation-fixtures/native-poly-dim-probe-00d2a570/poly-dim-subentities.json

# Thử native tự cập nhật hai đầu DIM đã có binding, không gán trực tiếp chúng:
python scripts/probe_native_polyline_dimensions.py 51ec94944c4443b19fb8d5bd7930a6dd 3DFA1C --inspection-job ea4b1d186ca4453e9db9cd06c55ef263 --stretch-width 925 --allow-unbound-test-assumptions --subentity-evidence storage/validation-fixtures/native-poly-dim-probe-00d2a570/poly-dim-subentities.json --native-auto-endpoints
```

Chế độ đọc subentity không được kết hợp với stretch hoặc negative test. Báo cáo không đúng SHA-256 nguồn, topology, thiếu dữ liệu, có lỗi getter, geometry cache, nhiều đỉnh, sai tọa độ hoặc không khớp duy nhất đầu DIM đều bị từ chối.

Kiểm tập trung: **41 passed, 7 warnings** cho `test_native_subentity_bindings.py`, `test_octagon_width.py`, `test_native_polyline_dimensions.py`. Bao gồm trường hợp báo cáo cũ/sai nguồn, sai action/dependency, thiếu/trùng dữ liệu và native geometry không phù hợp. Không phải lần chạy lại toàn suite.
