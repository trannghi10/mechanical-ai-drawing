# Liên động bản chi tiết, hình lắp và DIM khe hở — 23/10/2026

Phạm vi người dùng yêu cầu là DWG cơ khí **2D**, gồm các hồ sơ mới tải lên sau này. Đợt này mở rộng quan hệ dùng chung theo dữ liệu trong file: DIM khe hở, chi tiết vẽ rời và bản chi tiết/hình lắp ở các khung hoặc layout khác nhau. Không dùng tên DWG, mã chi tiết, handle hay kích thước mẫu để chọn quy tắc sản phẩm.

## Phần đã bổ sung

- Bộ đọc quan hệ tìm DIM tuyến tính/aligned đo đúng hai mặt thẳng đối diện của hai chi tiết đã định danh bằng BOM/leader/đường bao. Mỗi quan hệ giữ DIM nguồn, hai mặt, phương đo, khoảng hở, khung và bằng chứng định danh.
- Chỉ nhận DIM thật, hệ số 1 và đơn vị mm; loại chữ ghi đè, điểm đo sai mặt, số đo không khớp, đối tượng chỉ đọc, liên kết native trỏ chi tiết khác hoặc khác layout/phạm vi. Khoảng trống không có DIM không tự trở thành liên kết cần giữ.
- Bộ giải dùng chung giữ cả tiếp xúc và khe hở đo được. Khi chi tiết điều khiển đổi kích thước, tính lại chuỗi chuyển vị; dịch đường bao/lỗ/DIM của chi tiết nhận, giữ vòng STT/chữ và đưa đầu leader theo hình.
- Các hình cùng chi tiết được đối chiếu đường bao và toàn bộ lỗ bằng phép biến đổi duy nhất có bằng chứng định danh riêng. Chuỗi hiện có đã được kiểm nối với bộ giải khe hở mới: thay đổi từ bản chi tiết sang hình lắp và ngược lại, kể cả hình xoay hoặc ở Layout khác. Hình giống nhau nhưng chưa rõ mã hoặc có nhiều phép ánh xạ vẫn không tự được gán.
- Tái tạo thao tác và phương trình ở bước kiểm trước thực thi; chặn mất thao tác, DIM sai, bỏ ràng buộc, hình chồng lấn hoặc đụng đối tượng chưa rõ quan hệ. Chuẩn hóa hướng phân tích cho DIM đảo đầu và hình gần 90° để không giải cùng phương hai lần.
- Mô hình cơ khí nguồn phiên bản 25 và trang dữ liệu cho AI có loại `planar_measured_clearance`, DIM bằng chứng và khoảng hở. Web phân biệt mặt tiếp xúc và khe hở có DIM; tên CAD hiển thị dưới dạng text an toàn.

Mã chính: [quan hệ mặt/khe hở](../graph/planar_face_relations.py), [bộ giải liên động](../graph/flat_contacts.py), [mở rộng giữa các hình](../graph/measured_views.py), [kiểm thử mới](../tests/test_planar_clearances.py).

## Bốn DWG mới qua luồng web và AutoCAD

Đây là các DWG tổng hợp mới có mã/kích thước sinh độc lập, **không phải bốn hồ sơ sản xuất được kỹ sư nghiệm thu**. Chúng được tạo bằng AutoCAD, tải lên dưới dạng DWG mới và nhận yêu cầu tiếng Việt tìm mã trên toàn file, không truyền handle hoặc quan hệ vào API.

Luồng mỗi ca: tải DWG → đọc toàn hồ sơ → tìm mã → lập kế hoạch → tạo revision → xuất DWG toàn document → nhập DWG kết quả bằng AutoCAD độc lập → đo kiểm. Các bản sửa là bản xem trước, không phát hành sản xuất. CAD và AI đều cấu hình cục bộ.

| Ca | Bố trí | Đổi chiều dài, giữ tâm | Khe giữ nguyên | DIM tổng sau sửa |
|---|---|---|---|---|
| 3161 | Polyline trong hình lắp, LINE trong bản chi tiết xoay 90°, hai khung Model | 98,5 → 121,5 mm | 8 mm | 214,5 mm |
| 7319 | Cụm LINE rời xoay 31° | 100,5 → 123,5 mm | 12,5 mm | 219 mm |
| 8423 | Hình lắp xoay 119°, bản chi tiết xoay 241° | 108,5 → 131,5 mm | 17 mm | 228,5 mm |
| 9107 | Hình lắp trong Model xoay 17°, bản chi tiết trong Layout riêng xoay 90° | 74,5 → 97,5 mm | 14 mm | 202,5 mm |

Đã đo biên thật của chi tiết điều khiển và mốc giữ tâm; giữ chiều ngang/bán kính lỗ; kiểm vị trí lỗ và đầu leader. Hai chi tiết nhận dịch 11,5 mm trong hệ trục cụm, DIM riêng giữ nguyên; cả hai đầu DIM khe hở cùng dịch và giữ đúng khoảng đo. Bản chi tiết riêng khớp kích thước hình lắp. Mọi dòng mô tả BOM của mã sửa được kiểm riêng sau mở lại, các dòng mã khác giữ nguyên. Vòng STT/chữ, đối tượng đối chứng ngoài cụm và hash nguồn giữ nguyên.

[Manifest kết quả đo và hash](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/run.json) · [Mô hình nguồn ca 3161](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/source-mechanical-model.json) · [Script có checkpoint](../scripts/verify_unseen_2d_clearances.py).

Ca 3161: [DWG nguồn](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/3161/unseen-input.dwg) / [DWG kết quả](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/3161/after.dwg); [hình lắp trước](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/assembly-before.png) / [sau](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/assembly-after.png); [bản chi tiết trước](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/detail-before.png) / [sau](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/detail-after.png). Hình được dựng từ dữ liệu AutoCAD nguồn và DWG đã nhập lại độc lập, cùng phạm vi trước/sau.

Sau cập nhật máy chủ cuối, ca Model/Layout 9107 được lập kế hoạch lại qua HTTP: hai recipe, 23 thao tác, không câu hỏi còn thiếu, `execution_available=true`. [Kế hoạch đối chiếu](../storage/validation-fixtures/unseen-2d-clearances-2026-10-23/final-server-plan.json). Đây là quyền thực thi theo kiểm nguồn của planner, chưa phải chứng nhận/tự phát hành sản xuất.

## Kiểm thử

- Toàn bộ Python: **2.206 passed**, 2.777 cảnh báo từ thư viện, 499,99 giây. [Log](../storage/validation-fixtures/pytest-2d-clearances-full-2026-10-23.txt).
- Nhóm cuối sau bổ sung chuẩn hóa phương đo và DIM đảo đầu: **208 passed**, 709 cảnh báo, 65,34 giây. [Log](../storage/validation-fixtures/pytest-clearances-final-2026-10-23.txt).
- **16 script frontend đạt**. [Log](../storage/validation-fixtures/frontend-2d-clearances-2026-10-23.txt).
- Bốn DWG đều đạt kiểm native export/reopen và nhập lại độc lập. [Log](../storage/validation-fixtures/native-2d-clearances-live-2026-10-23.txt).

Các lượt Python có phần trùng nhau, không cộng thành tổng. Kiểm âm gồm DIM sai mặt, cùng một chi tiết, sai số đo/hệ số, chữ ghi đè, khác layout/khung, native trỏ đối tượng khác, thiếu chuyển vị lỗ, sai hai đầu DIM hoặc bỏ phương trình.

## Phần chưa hoàn thành trong phạm vi 2D

Chưa bảo đảm hiểu và sửa đúng mọi DWG. Adapter khe hở mới còn cần đường bao thẳng kín, chi tiết có định danh, DIM phù hợp và phép ánh xạ giữa các hình đủ bằng chứng. Chưa suy tự động quan hệ từ nét khuất, hình không đủ biên/DIM, ký hiệu hàn/lắp hoặc dung sai phức tạp. Block động phức tạp, XREF, proxy và mạng LINE chung cạnh chưa phân định được vẫn có giới hạn. Các adapter hình cong có phạm vi kiểm chứng riêng, chưa được mở rộng bằng đợt này.

Tiêu chí tiếp tục là mở rộng quan hệ và loại hình học dựa trên nhiều hồ sơ độc lập, kiểm đủ phạm vi tác động rồi đo lại sau lưu/mở DWG. Không lấy số bài kiểm hoặc bốn ca tổng hợp làm bằng chứng nghiệm thu mọi bản vẽ 2D. Không thay đổi đề xuất xốp Dauphine chưa được xác nhận, không truy cập thêm kho dữ liệu riêng của công ty.
