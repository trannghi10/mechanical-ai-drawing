# Sửa block động nằm trong cụm lồng — 20/10/2026

Đã mở rộng adapter dùng chung cho file mới; không thêm nhánh theo tên MR-106 hoặc Dauphine. Nguồn CAD giữ nguyên. Đây là nghiệm thu một nhóm khả năng native, chưa phải sửa đúng mọi DWG hoặc backup toàn Dauphine.

## Thay đổi đã có

- Lệnh sửa mang toàn bộ đường dẫn occurrence, ví dụ `A/B/C`, cùng handle/owner/loại/giá trị nguồn và hash. Hai nhánh chứa cùng handle C được phân biệt bằng A/B.
- AutoCAD kiểm tra toàn bộ chuỗi chủ sở hữu, clone riêng các định nghĩa cha tĩnh trên nhánh được chọn, ánh xạ handle mới rồi sửa tham số block động con. Các thao tác trong một job dùng chung bản clone đúng nhánh; không sửa định nghĩa gốc dùng chung.
- Sau lưu DWG, mở lại và kiểm tra giá trị tham số, owner và tất cả dynamic block nguồn không được chọn. Kết quả giữ đường dẫn nguồn và handle mới để đối chiếu.
- Form đọc tham số hỗ trợ từng trang 25 block; bấm **Đọc thêm block có tham số** để đọc tiếp và giữ các giá trị đang nhập. Trang mới phải cùng inspection/hash/phạm vi. Một lần áp dụng tối đa 200 tham số.
- Yêu cầu có #đường_dẫn_instance truy xuất riêng đúng occurrence ngoài trang đầu, không gửi toàn bộ inventory vào prompt AI. DIM bị hoãn không bị tính nhầm là tham số chưa đọc.
- Sửa lỗi nhận nhầm yêu cầu BOM/STT như “Chi tiết số 7 chiều dài…” thành yêu cầu sửa một block động Length khác trong cùng phạm vi. Mệnh đề hỗn hợp không được bỏ qua để sửa một phần ngầm.

## File kiểm chứng và kết quả

| Luồng | Phạm vi | Kết quả |
|---|---|---|
| AutoCAD 2027 local | Hai nhánh dưới hai cấp cha tĩnh, root xoay 27°, tỷ lệ 1,5 | Tham số cục bộ một nhánh 80 mm; hai nhánh 80 và 70 mm; các nhánh không chọn giữ nguyên |
| APS AutoCAD 2025 | Cùng cấu trúc, DIM 300 mm, MTEXT và ELLIPSE trong khung cha | Hai trường hợp trên đều đạt; tải DWG và ODA mở lại độc lập |
| AutoCAD 2027 local | File mới có 30 nhánh dùng chung; đọc hai trang; sửa nhánh đầu và cuối | Tham số cục bộ 80 và 70 mm đúng hình học, 28 nhánh còn lại và instance ngoài giữ nguyên; nguồn bất biến |
| Tham số ngoài bước nguồn | Yêu cầu 65 mm nhưng native nhận 60 mm | Từ chối kết quả, không cung cấp file sai số |

Với root tỷ lệ 1,5, tham số cục bộ 80/70 mm tạo hai cạnh thân dài 120/105 mm tại layout; script đã kiểm tra cả hai hệ tọa độ. Không báo tham số cục bộ thành số đo thành phẩm. Lượt 30 nhánh cuối được tạo DWG native rồi **upload lại chính DWG đó như tài liệu mới**, trước khi sửa/tải/mở lại.

File tải là DWG thật tạo từ fixture tổng hợp có block động do Autodesk định nghĩa; không phải nghiệm thu sản phẩm khách hàng. Script xác nhận hai cạnh thân bu-lông có chiều dài thực tương ứng, không chỉ kiểm tra text hoặc bbox. Có cảnh báo ezdxf về record representation khi phân rã để đối chiếu; AutoCAD đã đọc/lưu/mở lại và ODA kiểm tra độc lập các DWG kết quả.

- Local hai nhánh: `storage/validation-fixtures/native-nested-0cf7d41f/report.json`.
- APS hai nhánh: `storage/validation-fixtures/native-nested-e4d9c9be/report.json`.
- Local 30 nhánh: `storage/validation-fixtures/native-nested-aa15dc76/report.json` và `backup-2-branches.dwg` (108.275 byte).
- [Tải DWG kiểm chứng 30 nhánh](http://127.0.0.1:8765/documents/dc6ac5305ad6483481d65d64368a88a0/autocad/jobs/318f0ead868241b2a9a5674feaf9e3e1/files/modified.dwg).
- Plugin local mới đã qua `setup_autocad.py check`. Plugin APS được build/đăng ký lại và smoke đọc → sửa TEXT → lưu/mở lại hình/DIM 80 mm thành công; bằng chứng mới `storage/aps-cloud-check.json`, log `storage/validation-fixtures/aps-live-2026-10-20/nested-smoke.log`.
- Năm trường hợp block động layout hiện có (lookup, Length, flip, visibility, Size) đã chạy lại và đạt trên mẫu Autodesk; không mất khả năng cũ.

## Kiểm thử hồi quy

**1.520 bài Python toàn bộ đạt**, 1.047 cảnh báo từ thư viện, 213 giây; sau các chỉnh đọc tham số/nhận diện yêu cầu, 139 bài native/export đạt. Bảy script frontend đạt. Giữ 19 module kiểm thử. Log `storage/validation-fixtures/pytest-nested-native-final-full-2026-10-20.txt`.

## Cách dùng

1. Mở khung hoặc block cha cần sửa.
2. Mở **Công cụ AutoCAD và chẩn đoán file → AutoCAD trên máy / Autodesk APS**; chọn đúng bộ xử lý đã dùng nhập native.
3. Bấm **Đọc tham số bản vẽ đang chọn**; nếu còn trang, bấm **Đọc thêm block có tham số**.
4. Chọn đúng đường dẫn instance, nhập giá trị và tạo DWG xem trước. Hoặc ghi yêu cầu `#A/B/C Length từ 50 thành 80 mm` với đường dẫn/tên tham số thực trong file. Không dùng lại handle ví dụ cho file khác.
5. Xem tác vụ, hình sau sửa và tải DWG. BOM, mặt lắp và hình bên ngoài block vẫn phải được kiểm chứng riêng.

## Giới hạn chưa thay đổi

Cha động, XREF, thuộc tính trên cha, proxy hoặc association chưa có adapter không được tự phá để sửa. Các đối tượng của khung clone phải thuộc loại được hỗ trợ; HATCH associative và extension dictionary không được bỏ âm thầm. Giới hạn sâu tối đa tám handle trong một đường dẫn.

Đọc lại inventory MR-106 thực tế phát hiện 10.067 entity và không có tham số block động; Dauphine nguồn đang dùng chưa có native inspection. Vì vậy lượt này không tạo bản hoàn chỉnh mới cho hai sản phẩm đó. Receipt kiểm tra nguồn: `storage/validation-fixtures/nested-native-customer-audit-2026-10-20.json`. Các quan hệ phối cảnh, lắp ghép và đóng gói còn thiếu bằng chứng vẫn giữ điều kiện kiểm tra hiện có.

Tham chiếu API Autodesk: [BlockReference.BlockTableRecord](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_BlockReference_BlockTableRecord.html), [định nghĩa dynamic block](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_BlockReference_DynamicBlockTableRecord.html).
