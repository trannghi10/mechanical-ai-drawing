# Liên kết kích thước native và bản xem trước Dauphine — 15/10/2026

Đã mở rộng bộ sửa DIMASSOC cho các trường hợp nguồn xác định được và sửa hai lỗi gây sai/trùng thay đổi trên file mới. **Chưa hoàn thành sửa đúng mọi DWG hoặc backup toàn Dauphine.**

## Các lỗi đã sửa

- DIM bám trung điểm LINE/cạnh thẳng LWPOLYLINE được tính từ hai đầu cạnh sau sửa. Ví dụ cạnh cao 100 → 80 mm thì trung điểm 50 → 40 mm, thay vì giữ theo đầu cạnh gần nhất.
- DIM tuyến tính bám tâm CIRCLE/ARC XY theo đúng tâm sau sửa. Giữ loại snap, cập nhật cache WCS và kiểm tra lại con trỏ nguồn; không tháo DIMASSOC để đổi thành chữ thường.
- Quét cả reactor và con trỏ geometry trong DIMASSOC trước khi ghi. Nếu một geometry bị sửa nhưng DIM phụ thuộc bị bỏ sót hoặc không còn bám đúng nguồn, giao dịch bị chặn trước khi tạo file đích. File mất reactor tham chiếu ngược cũng được kiểm tra.
- DIM có liên kết tới geometry khác được ưu tiên theo nguồn native, không bị kéo theo chỉ vì tọa độ nằm trong vùng chi tiết đang sửa.
- Bản tính kích thước tạm cho hình chiếu cạnh không kế thừa DIMASSOC của hình chiếu gốc. Bản tính này không được ghi thành DIM mới vào CAD; DIM nguồn vẫn được giữ và kiểm chứng riêng. Lỗi kế thừa trước đó làm bộ biên dịch Dauphine thất bại và chuyển sang gọi model.
- Bộ sửa hình chữ nhật cập nhật ô BOM một lần, không đưa cùng ô vào cả thao tác BOM và chú thích. Mô tả ở khung khác được giữ nguyên, kể cả khi có cùng chuỗi quy cách.

Phạm vi association mới là các đối tượng layout và điểm nguồn được adapter kiểm chứng. Association xuyên không gian, snap khác, proxy association và việc clone block có object/association ngoài definition chưa được hỗ trợ tổng quát.

## Kiểm chứng

**974 kiểm thử Python và 11 script giao diện đạt.** Vẫn giữ 19 module kiểm thử hiện có. Log: `storage/validation-fixtures/pytest-native-snaps-final-release-2026-10-15.txt`.

Hai file DWG kiểm thử mới đã qua upload → chọn bản chi tiết → sửa geometry/DIM/BOM → xem trước → duyệt → tải DWG → ODA mở lại. Các pointer và snap native cũng được đối chiếu sau chuyển đổi:

| Trường hợp | Chiều cao | DIM phụ thuộc | Kết quả |
| --- | --- | --- | --- |
| Trung điểm cạnh | 100 → 80 mm | 50 → 40 mm | Giữ DIMASSOC, BOM sửa một lần |
| Tâm lỗ | 100 → 80 mm | 90 → 70 mm | Giữ tâm theo mốc gần đầu, giữ bán kính và DIMASSOC |

Biên nhận: `storage/validation-fixtures/native-snap-4cb09053/report.json` và `native-snap-957a31ea/report.json`. Đây là file kiểm thử tổng hợp, không thay thế nghiệm thu sản phẩm khách hàng. Chạy lại bằng:

```powershell
python scripts/verify_general_dwg_workflow.py --association midpoint --approve
python scripts/verify_general_dwg_workflow.py --association center --approve
```

## Dauphine thực tế

Yêu cầu gốc được chạy lại với các lựa chọn người dùng đã chốt: thành phẩm 700 mm, khung 697 mm, giữ đáy; tấm laser 1,5 → 1 mm; giữ biên ngoài tấm cung; giữ các khe hở và quy tắc uốn nguồn.

Bộ biên dịch đã xử lý cả hai mệnh đề mà không gọi model. Lượt chạy trên web lập kế hoạch 400 thao tác, sau cô lập/gộp block dùng chung có 381 thao tác ghi CAD. Thời gian lập kế hoạch trong lượt kiểm chứng có các bài kiểm thử chạy đồng thời là 130 giây; **không cam kết thời gian 2–3 giây cho file này**. Bản sao đã qua kiểm tra hình học được engine khai báo và xuất/mở lại bằng ODA.

- Kế hoạch: `1e3e67aa6a9440f69d7785abbe616c18`.
- Revision: `c75fb80591264eacbfef7a78b2f378a3`.
- DWG xem trước: `storage/backups/Dauphine-PREVIEW-c75fb805.dwg` — 2.231.055 byte.
- SHA256: `7242ee35923aeab873f8add8a1e6b80beb01f950ed37684dd553f990133fcf6d`.
- Sáu DIM nguồn `3B8BF1`, `3B9477`, `3C75E2`, `3D29F8`, `3B62C6`, `3B8BAA` đều đo lại **697 mm** trong DWG đã mở lại.
- Giữ/kiểm chứng 14 association được cập nhật và kiểm tra 15 quan hệ geometry–DIM. FreeCAD trả `passed` cho phạm vi hình học được mô hình hóa; kết quả này không chứng nhận toàn bộ kết cấu hoặc độ bền.
- Đường dẫn tải trả HTTP 200; hash nguồn DXF vẫn `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.
- Biên nhận: `storage/validation-fixtures/dauphine-native-snaps-readback-2026-10-15.json`.

**Đây vẫn là bản xem trước một phần.** Yêu cầu duyệt toàn sản phẩm tiếp tục bị chặn; không đổi trạng thái chỉ vì đã xuất được DWG.

## Còn thiếu để hoàn tất

| Phần | Dữ liệu/khả năng còn thiếu |
| --- | --- |
| Chốt ren `8.1.05060.013` | Chủ sở hữu geometry và mốc/vị trí lắp khi chiều cao thay đổi |
| Thanh giằng `8.1.05190.002` | Quan hệ mặt lắp/mốc giữ của thanh dài 347,5 mm trong các hình cụm |
| Thanh giằng trái/phải `8.1.05191.002`, `8.1.05192.002` | Quan hệ của hai thanh dài 282 mm với các công đoạn/hình lắp |
| Hình cụm và phối cảnh | Gắn từng nét/hình với chi tiết và phép chiếu; các hình được sửa riêng không chứng minh toàn cụm đã đồng bộ |
| Đóng gói | Một số lớp đệm/góc và hình tách rời chưa có đủ binding; thùng/lớp xốp đã sửa không chứng minh toàn bộ đóng gói |
| Block động/proxy | CAD host/SDK tương thích để chỉnh tham số và tái tính; với custom proxy còn phụ thuộc ứng dụng tạo hoặc Object Enabler tương ứng |

Máy hiện có ODA File Converter 27.9 và DWG TrueView 2025, chưa có CAD host chỉnh sửa được cấu hình cho dự án. Converter có giao diện chuyển đổi và audit; đây không phải API chỉnh tham số block động. Thêm model không cung cấp được bộ tái tính native hoặc những mốc lắp chưa có trong dữ liệu.

Tài liệu chính thức: [DIMASSOC DXF](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-DXF/files/GUID-C0B96256-A911-4B4D-85E6-EB4AF2C91E27.htm), [Dynamic Block API](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-DevGuide/files/GUID-81D407FB-5C58-4197-A8DE-83A10F13091E.htm), [giới hạn chỉnh sửa proxy do ứng dụng tạo quy định](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-DevGuide/files/GUID-83C009B4-70A2-479B-B5AD-F93BEDD76892.htm), [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter).

Ngay cả khi bổ sung CAD host, DWG thiếu mốc giữ, khe hở hoặc chủ sở hữu geometry vẫn cần bổ sung ràng buộc trước khi có thể bảo đảm sửa đúng ý đồ thiết kế.
