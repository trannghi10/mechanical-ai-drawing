# Engine dùng chung: tiếp xúc biên dạng có rãnh, SPLINE cung tròn và thuộc tính block

Trạng thái ngày 13/10/2026: đã triển khai và chạy trên backend cổng 8765. Đây là mở rộng theo cấu trúc CAD nguồn, không phải mapping riêng theo handle của một sản phẩm.

## Các thay đổi đã triển khai

- `graph/native_contacts.py`: giải tiếp xúc đầu mặt trên đường bao thẳng kín có bậc/rãnh. Hai đoạn cạnh thật phải có phần chồng theo phương tiếp tuyến; khung bao chạm hoặc một đỉnh chạm không đủ. Kiểm tra chồng lấn bằng polygon thật, giữ bằng chứng vertex CAD để cập nhật DIM cụm. Nhiều chi tiết dẫn động được phép khi mọi mốc giữ và phương trình tiếp xúc cùng có nghiệm duy nhất; mốc xung đột bị chặn. Adapter đóng gói vẫn chỉ nhận bao chữ nhật.
- `backend/services/change_service.py`: BOM và các chi tiết bên trong block được chọn giữ cùng ID phạm vi. Trước đây chọn block cụm có thể đọc được BOM nhưng bỏ qua giải tiếp xúc vì thiếu `source_sheet_ids`.
- `cad/spline_arcs.py`: nhận SPLINE bậc hai kẹp đầu, gồm các span Bezier có trọng số dương. Chỉ nhận cung tròn nếu phương trình đường tròn được kiểm chứng trên toàn đa thức đồng nhất, với chặn sai số hình học; không suy cung tròn từ ba điểm mẫu. Knots, weights, degree và loại SPLINE giữ nguyên. Chỉ dịch cứng control points trong một vùng đầu; không biến dạng NURBS tự do hoặc đưa spline thành polyline. Được nối với feature index, resize, frame conversion, DIM bán kính và kiểm tra FreeCAD.
- `cad/insert_motion.py`: dịch ATTRIB đi cùng INSERT trong WCS của parent/OCS của thuộc tính, cập nhật cả hai bản điểm canh lề native R2018 và kiểm tra sau khi mở lại. Có thể ghép với thay text trong cùng giao dịch. Metadata definition giữ nguyên; reactor/dictionary của instance hoặc ATTRIB và thuộc tính MTEXT chưa hỗ trợ vẫn bị chặn.
- `/cad/capabilities` và prompt lập kế hoạch mô tả đúng phạm vi các adapter trên.

## Kiểm chứng DWG thực tế qua HTTP

Hai tài liệu dưới đây được tạo độc lập để kiểm thử cấu trúc mới. Không phải bản sửa của khách hàng và không thay thế Dauphine.

### Cụm lắp có rãnh, chọn nguyên một block

Lệnh chạy: `python scripts/verify_contact_dwg_workflow.py`.

- Upload DWG → chọn block cụm → yêu cầu chi tiết 1 cao 100 thành 80 mm, giữ đáy.
- Biên dạng có rãnh được sửa; chi tiết 2 dịch từ Y100 về Y80; ATTRIB mã chi tiết dịch từ Y103 về Y83.
- DIM chi tiết/cụm mở lại đo được 80, 100, 180 mm; BOM chi tiết 1 thành `Bas 2x20x80`, chi tiết 2 giữ `Bas 2x20x100`.
- FreeCAD kiểm tra mặt kín trước/sau đạt. Đã mở preview, duyệt fixture, xuất và tải DWG qua đường dẫn bền trên server, chuyển lại DXF để đo và đối chiếu. Hash nguồn giữ nguyên.
- Bằng chứng: `storage/validation-fixtures/contact-workflow-bea07399/report.json`.
- DWG: `storage/validation-fixtures/contact-workflow-bea07399/download/checked-assembly-backup.dwg`.
- Ảnh đã kiểm tra: `storage/validation-fixtures/contact-workflow-bea07399/after.png`.
- Revision: `8ff244afd62f40048af5382ce71c3403 / b7546fec9400483dbb03dbf00f693936`.

### SPLINE cung tròn trong block lồng 9 cấp

Lệnh chạy: `python scripts/verify_general_dwg_workflow.py --spline --depth 9 --approve`.

- Upload → sửa chiều dài 140 thành 123 mm, giữ tâm → preview → duyệt fixture → tải DWG → mở lại.
- DIM aligned đo 123 mm; hai lỗ R2 giữ nguyên. Hai đường SPLINE vẫn là SPLINE; knots, weights, degree và bán kính R15 được giữ qua xuất/đọc lại DWG.
- FreeCAD: diện tích mặt sau trừ lỗ 3981,7256058 → 3471,7256058 mm²; hai lỗ/ba đường biên hợp lệ.
- Bằng chứng: `storage/validation-fixtures/general-workflow-d2f0936f/report.json`.
- DWG: `storage/validation-fixtures/general-workflow-d2f0936f/download/checked-preview.dwg` (fixture đã duyệt, tên file kiểm thử giữ như script cũ).
- Revision: `e46b4742077343ad8ad5b22fdc3ddd35 / 1e383cac74c24bfb84524c604f6444c7`.

## Kiểm thử

Toàn bộ suite: **551 passed**. Log: `storage/validation-fixtures/pytest-contacts-spline-20261013.txt`.

Các ca mới kiểm tra cả kết quả sửa và trường hợp không được suy đoán: điểm/khung bao chạm giả, polygon có rãnh, classic POLYLINE, nhiều mốc giữ phù hợp/xung đột, block cụm được chọn, SPLINE không tròn dù gần giống, knots/weights/flags không hỗ trợ, quay/tỷ lệ block, DIM bán kính ở điểm nối các span, OCS của ATTRIB, thứ tự ghép thay text và dịch, dữ liệu association opaque.

Kiểm tra JavaScript giao diện và luồng tải bền cũng đạt: `scripts/verify_frontend.js`, `scripts/verify_frontend_downloads.js`.

## Dauphine và giới hạn chưa hoàn thành

Phạm vi liên quan đã lưu của Dauphine có 37.125 bản ghi, gồm 3.380 SPLINE. Không SPLINE nào trong phạm vi này thuộc dạng cung tròn bậc hai adapter mới có thể chứng minh; không có cụm tiếp xúc được chứng minh bằng block chi tiết native có mã BOM cho adapter này. Vì vậy hai mở rộng trên **không tự giải quyết các hình phối cảnh/uốn/đóng gói còn thiếu của Dauphine**.

Các lựa chọn người dùng đã chốt được giữ: thành phẩm 700 mm, khung 697 mm, giữ đáy/chân, tấm 1 mm, giữ biên ngoài R406,5; nguyên liệu mới ghi chờ cấp mã. Không cần hỏi lại các mốc này. File `storage/backups/Dauphine-PREVIEW-tam-op-cao697-day1.dwg` vẫn là preview một phần, chưa phải backup toàn sản phẩm.

Chưa hoàn thành: chỉnh tham số/action/visibility của dynamic block; tái tính association proxy không có adapter; biến dạng spline/ellipse tổng quát; chủ sở hữu/quan hệ lắp ghép không có bằng chứng nguồn; các hình cụm, phôi uốn và đóng gói Dauphine chưa bao phủ. Dịch toàn instance và giữ nguyên metadata definition không đồng nghĩa với sửa tham số block động. Bộ chuyển đổi DWG và kiểm tra mặt FreeCAD không tự bổ sung các quan hệ thiết kế còn thiếu. Không công bố khả năng tự sửa mọi DWG hoặc chứng nhận cơ học/chất lượng sản phẩm từ các kiểm thử này.
