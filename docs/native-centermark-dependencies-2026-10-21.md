# Đọc dependency dấu tâm bằng AutoCAD gốc — 21/10/2026

Cập nhật tiếp theo: [probe dịch CenterMark](native-centermark-translation-probe-2026-10-21.md) đã kiểm chứng phép dịch native trên hai cặp, chưa cấp action sửa qua website.

Đã bổ sung kiểm kê quan hệ native theo handle vào plugin AutoCAD và endpoint local. Mục đích là đọc các quan hệ bị biểu diễn thành proxy trong DXF, trước khi phát triển adapter chỉnh sửa. Chưa cấp quyền dịch đường tròn/dấu tâm hoặc cụm hộp–chốt.

## Bằng chứng trên Detail C đang được đặt

Nguồn dùng trực tiếp DWG gốc của Dauphine. AutoCAD 2027 nhận được lớp native, thay vì `ACAD_PROXY_OBJECT` của DXF:

| Đường tròn | Block dấu tâm | Action | CenterMark action body |
| --- | --- | --- | --- |
| `3B7FD1` | `3B7FD6` | `3B8023` | `3B8024` |
| `3B7FF1` | `3B7FF2` | `3B80C3` | `3B80C4` |

Mỗi đường tròn có `AcDbAssocGeomDependency`, block dấu tâm có `AcDbAssocDependency`; `DependentOnObject` và `OwningAction` được đọc qua native property. Hai action body được AutoCAD nhận là `AcDbCenterMarkActionBody`. Cả hai nối vào cùng `AcDbAssocNetwork`.

Lượt cuối thu được **17 đối tượng, 35 liên kết**, không có lỗi đọc và không chạm giới hạn. Trạng thái `inspected` chỉ nói đã đọc hết những loại quan hệ được liệt kê trong policy; không có nghĩa đã đọc mọi property của network/action hoặc hiểu đầy đủ nhóm cơ khí.

- Job cuối: `6e32706015954a58acbb31221d1aec3d`.
- Receipt: `storage/validation-fixtures/detail-c-native-dependencies-2026-10-21/receipt.json`.
- Đồ thị với lớp native và managed: `inventory.json` trong cùng thư mục, trường `native_dependencies`.
- DWG gốc giữ SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.
- Không tạo revision khách; tác vụ chỉ ở mode inspect.

Điều này chứng minh hai cặp đường tròn–dấu tâm có quan hệ native. Nó chưa chứng minh các đường tròn đồng tâm còn lại, chữ ren, hộp và chốt phải chuyển cùng nhau. Không dùng việc cùng tâm hoặc nằm gần nhau để cấp quyền dịch cả cụm.

## Phần triển khai

`autodesk/MechanicalCad/Commands.cs` thêm `NativeDependencies` vào inventory. Đọc persistent reactor, owner của non-entity, extension dictionary, dictionary entry và bốn property ObjectId cố định: DependentOnObject, OwningAction, ActionBody, ParentAction. Không phân tích binary proxy, không gọi lệnh evaluate hay ghi đối tượng.

Giới hạn 256 node, sâu 6 và tối đa 128 entry mỗi dictionary. Lỗi hoặc hết giới hạn có trạng thái partial và cờ truncated; node lỗi không được coi là không có liên kết. Đường dẫn nested phải khớp owner thật của từng block reference. Owner layout/block chỉ là metadata, không được diễn giải thành quan hệ lắp.

POST `/documents/{id}/autocad/jobs` vẫn chấp nhận không có body như trước. Có thể gửi `handles` để đọc thêm dependency; tối đa 64 đường dẫn hex, tối đa 8 thành phần. Các trường operations/mode không được nhận. Endpoint này luôn tạo tác vụ inspect local; không gửi cloud.

Lặp lại:

`python scripts/audit_native_dependencies.py DOCUMENT_ID --handle HANDLE --handle HANDLE --output OUTPUT_DIRECTORY`

## Kiểm chứng

- Plugin cuối build được với SDK AutoCAD 2027/net10; `setup_autocad.py check` đạt nạp native, dictionary, sửa text có giới hạn, geometry/DIM 100 mm, xuất/mở lại DWG và giữ nguồn. Runtime key `07836d9f50af16ccd2f006d5b550ff36c85286db8fcb770e8ac7e05e583e86d3`; chứng cứ `storage/autocad-host-check.json`.
- **140 bài export/native jobs đạt**, gồm endpoint cũ, scope mới và chặn path sai định dạng, handle quá dài, quá 64 roots, operations/mode. Log `storage/validation-fixtures/pytest-native-dependency-inventory-2026-10-21.txt`.
- Kiểm tra thật qua AutoCAD với root không tồn tại và đường dẫn parent là CIRCLE thay vì INSERT: trả partial, 0 node, 2 lỗi đúng root; không nhầm thành đọc đủ. Receipt `storage/validation-fixtures/native-dependency-invalid-roots-2026-10-21/receipt.json`, job `58cbff80f088460a819d2aa61f149080`.

Chưa có adapter dịch CenterMark và kiểm tra evaluate/readback tương ứng. Quyết định dịch cả cụm trong Detail C vẫn chưa được xác nhận; đề xuất tấm xốp riêng tiếp tục chưa xác nhận. Backup toàn sản phẩm và khả năng sửa mọi DWG chưa hoàn thành.
