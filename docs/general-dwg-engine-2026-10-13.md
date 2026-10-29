# Mở rộng engine cho DWG mới — 13/10/2026

Yêu cầu là đọc và sửa bản vẽ do người dùng mới tải lên, không gắn thuật toán vào một mã sản phẩm hoặc handle của file mẫu. Đợt này mở rộng kernel dùng chung; chưa hoàn tất khả năng tự sửa mọi DWG hoặc mọi liên kết lắp ghép.

## Cập nhật 16/10 — chọn vật tư trong file mới và sửa lỗi thực thi BOM

- Yêu cầu đổi dày hộp có thể tìm vật tư bằng quy cách nguồn, ví dụ `Hộp 40 × 80 dày 2 mm thành 1 mm`, không bắt buộc biết mã hoặc STT. Chỉ chọn khi quy cách ngoài và độ dày khớp duy nhất một mã trong BOM đang chọn; không tìm số tương tự ở sản phẩm khác.
- Hiểu STT chữ/số như `chi tiết A`, `chi tiết số C4`, `STT 19`, `chi tiết 6B`. Mã vật tư dạng chấm không bị hiểu thành STT đầu tiên. Mã được chỉ định nhưng không tồn tại không được thay bằng chi tiết duy nhất đang xem.
- Quy cách hộp hỗ trợ dấu `x`/`×`, khoảng trắng và dấu phẩy thập phân; số liệu được lấy từ file mới. Quy tắc không gắn với tên file, mã khách hàng, handle hoặc STT 6.
- Sửa lỗi tạo hai lệnh cho cùng text BOM khi hình chi tiết và bảng kê nằm chung vùng Model. Text đã được binding/cập nhật như ô BOM không bị cập nhật lần hai như chú thích. Giữ các chặn xung đột, kiểm tra hình học, công đoạn và toàn cụm.
- Trùng quy cách nhiều mã hoặc không có vật tư khớp được trả câu hỏi có mã nguồn ngay từ bộ biên dịch; không đẩy tình huống này sang model CPU để đoán. Khi có đủ bằng chứng, các liên kết hộp–bas và bản cắt vẫn đi qua cùng bộ giải đã kiểm chứng.

### Kiểm chứng DWG mới

Ba nguồn tổng hợp độc lập mới, mã ngẫu nhiên, STT 11/27/A, đã qua upload → lập kế hoạch trực tiếp → apply → AutoCAD xuất → tải → ODA mở lại đo DIM, bán kính trong/ngoài và BOM. Nguồn DWG giữ nguyên. Chỉ thời gian lập kế hoạch đo được khoảng 0,16–0,27 giây; không phải thời gian hoàn tất chuyển đổi DWG hoặc cam kết tốc độ cho file khác.

| Yêu cầu | DIM sau mở lại | Kích thước ngoài/chiều dài giữ nguyên |
|---|---|---|
| Hộp 30×60: dày 2 → 1,2 mm | 1,2 mm | 30×60×571,5 mm |
| Hộp 40×80: dày 2 → 1 mm | 1 mm | 40×80×853,2 mm |
| STT A, hộp 25×50: dày 2 → 1,6 mm | 1,6 mm | 25×50×320,3 mm |

Receipt: `storage/validation-fixtures/tube-specifications-80c30b10/receipts.json`. DWG tải xuống nằm trong các thư mục `60-30/download`, `80-40/download`, `50-25/download` của cùng batch. Chạy lại bằng `python scripts/verify_general_dwg_workflow.py --tube-specifications`.

Các DWG này là **bản xem trước** của dữ liệu tổng hợp. Chặn duyệt toàn cụm vẫn hoạt động khi BOM nhiều chi tiết chưa có đủ liên kết/biểu diễn; không bỏ chặn để biến bài thử thành backup hoàn chỉnh. Đây chưa phải nghiệm thu mọi DWG mới hoặc backup toàn Dauphine. Bộ kiểm thử cuối đạt **1.188/1.188**, log `storage/validation-fixtures/pytest-new-dwg-specifications-final-2026-10-16.txt`; kiểm tra live hai trường hợp mã/quy cách sai trong `storage/validation-fixtures/new-dwg-specification-gates-2026-10-16.json`. Các số kiểm thử và receipt phía dưới là lịch sử đợt 13/10.

Cập nhật tiếp trong ngày: classic POLYLINE 2D đã có adapter, ownership/BOM lồng sâu và kiểm tra mặt/lỗ bằng FreeCAD. Xem [biên nhận DWG mới và giới hạn còn lại](polyline-kernel-validation-2026-10-13.md). Các số liệu phía dưới ghi đợt kiểm chứng trước đó.

## Thay đổi đã triển khai

- **DIM linear và aligned:** xác định trục đo từ hai điểm dóng đối với DIM aligned, không dùng trường góc hiển thị có thể bằng 0 hoặc đã cũ. Dùng chung cách tính trong nhận diện profile, stretch, ghép hai trục vuông góc, đồng bộ hình chiếu và mặt cắt.
- **Block lồng:** bỏ việc âm thầm dừng đọc ở cấp 6. Đã đọc và sửa được block lồng 10 cấp trong kiểm thử. Phát hiện tham chiếu vòng và báo lỗi rõ; trên 128 cấp cũng báo lỗi thay vì tạo phạm vi thiếu dữ liệu.
- **Block độc lập không có BOM:** người dùng chọn trực tiếp một INSERT có profile đóng và DIM đo thật thì có thể sửa profile đó. Chủ sở hữu được ghi là `selected_native_instance`, định danh `BLOCK@<handle>`; đây không phải mã vật tư. Không tự đồng bộ những instance khác cùng tên. Nếu có bảng chưa giải mã được thì không được bỏ qua bảng để dùng luồng này.
- **Bỏ kích thước mẫu:** nhánh “giảm khung xuống…” không còn mặc định chiều cao nguồn 724 mm. Chỉ dùng giá trị nguồn đã xác định trong dữ liệu thiết kế.
- **Kiểm thử:** lệnh `pytest` chỉ thu thập thư mục `tests`. Các script thử CAD trong `scratch`/`scripts` có thao tác chạy ngay khi import được loại khỏi việc thu thập tự động.

Không thay thuật toán nhận diện khung, không cài thêm model hoặc dịch vụ trả phí và không gửi file nội bộ sang dịch vụ AI cloud trong luồng kiểm chứng mới.

## Bằng chứng

`tests/test_general_dwg_profiles.py` có 22 trường hợp: mã chi tiết mới, nhiều góc quay/tỷ lệ, đảo thứ tự điểm đo, block lồng, DIM ghi đè/khác mặt phẳng/khác hình chiếu, hai trục aligned cùng góc hiển thị, hình chiếu tương ứng quay khác nhau, bảo toàn lỗ và instance ngoài phạm vi, bảng chưa giải mã và nguồn bất biến. Đây là dữ liệu tổng hợp có kiểm soát, không phải 22 file sản xuất đã được kỹ sư duyệt.

Toàn bộ bộ kiểm thử đạt **475 passed, 177 warnings trong 33,59 giây**. Hai script kiểm tra frontend và tải file cũng đạt. Backend đã nạp mã mới; `/health` trả 200.

Luồng HTTP thật được chạy bằng `scripts/verify_general_dwg_workflow.py`:

1. Tạo một DWG độc lập qua ODA: profile có rãnh và hai lỗ, block lồng 8 cấp, quay và tỷ lệ 2, không có BOM, DIM aligned native.
2. Upload qua `/documents`, chọn block, nhập `Chiều dài từ 140 thành 123 mm, giữ tâm`.
3. Planner `checked_measured_profile_resize` tạo thao tác; apply và preview trả HTTP 200.
4. Hàng đợi xuất tạo đường dẫn GET; tải DWG có chữ ký `AC1032`.
5. Mở chính DWG tải xuống qua ODA: DIM đo 123 mm, hai lỗ vẫn bán kính 2 mm, nguồn không đổi.

Biên nhận: `storage/validation-fixtures/general-workflow-507b3774/report.json`.

DWG tải xuống: `storage/validation-fixtures/general-workflow-507b3774/download/checked-preview.dwg`.

Document `9b850a3e89a74cedbc038ee0f30c43e7`, revision `228ffb30d74b4f57badfe5e4b262f31f`. File này có tên synthetic nên được xếp vào nhóm kiểm thử phụ trong danh sách; không phải backup của sản phẩm khách hàng.

## Kiểm tra file khác và giới hạn còn lại

Đã quét các khung chi tiết của MR-106 bằng bộ nhận diện feature chung. File có profile đo thật nhưng một yêu cầu sửa chiều dài ống 478 → 460 mm vẫn bị chặn: đường tâm nằm trong block có association/reactor native chưa có adapter bảo toàn. Chưa xuất backup MR-106 từ yêu cầu đó. Dữ liệu khảo sát nằm trong `storage/validation-fixtures/generalization-mr106-*.json`.

Những phần chưa được hoàn tất gồm:

- Tự xác định đầy đủ contact, chủ sở hữu và mốc giữ trong mọi bản vẽ lắp 2D; hình gần nhau không tự chứng minh quan hệ cơ khí.
- Sửa tổng quát profile SPLINE/ELLIPSE, POLYLINE curve-fit/spline-fit/mesh, dynamic block, XREF ngoài file và các association native chưa hỗ trợ. Đọc được những đối tượng này không đồng nghĩa engine đã sửa được chúng.
- Tự tính phôi uốn, phối cảnh và đóng gói của mọi sản phẩm. Dauphine vẫn chưa có backup toàn sản phẩm/đóng gói hoàn chỉnh.
- Hỗ trợ sửa tham số ở mọi đơn vị, phép phản chiếu hoặc tỷ lệ không đều; kernel hiện yêu cầu mm và frame 2D hỗ trợ.

Model có thể phân tích ý định hoặc đề xuất quan hệ; kết quả đó vẫn cần liên kết nguồn và kiểm tra hình học trước khi xuất bản sửa được duyệt. Các mở rộng trên không bỏ các cổng kiểm tra này.

## Chạy lại

```powershell
Set-Location D:\mechanical-ai-drawing
python -m pytest -q
python scripts/verify_general_dwg_workflow.py
```

Lệnh thứ hai cần backend đang chạy tại cổng 8765 và ODA File Converter đã cài; tạo một tài liệu kiểm thử phụ mới mỗi lần chạy. Log toàn bộ kiểm thử: `storage/validation-fixtures/pytest-general-engine-20261013.txt`.
