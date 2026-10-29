# Đọc file DWG mới — kiểm chứng 10/10/2026

Bộ đọc CAD và luồng đưa dữ liệu vào AI là hai phần khác nhau. Preview có hình không bảo đảm model đã nhận được dòng vật tư và hình học cần thiết.

## Các lỗi đã sửa

- Bộ đọc BOM trước đây chỉ chấp nhận thứ tự `STT / Mã Hàng / Vật Tư / Vật Liệu / SL / Ghi chú`. MR-106 dùng `STT / Mã / Tên / SL / VL / Ghi chú`, vì vậy các dòng vật tư bị bỏ khỏi context. Nay ánh xạ theo tiêu đề, giữ nguyên index ô native và binding mirror; nhận số đánh dấu dạng A/B/C1, bỏ mã placeholder `!!`. Tiêu đề thiếu/trùng vẫn không được tự đoán.
- Cache chuyển DWG trực tiếp nay dùng SHA-256 nội dung. Các upload cùng tên `original.dwg` không dùng nhầm cache hoặc DXF ở thư mục bên cạnh. ODA chỉ chuyển bản sao của file yêu cầu trong thư mục riêng.
- Inventory toàn bộ có cả block ẩn danh chứa hình học/kích thước/bảng. Bổ sung dữ liệu POLYLINE, ATTRIB/ATTDEF, LEADER, MULTILEADER và số đo DIMLFAC. Đối tượng chỉ đọc được metadata được đánh dấu rõ.
- Context AI có dữ liệu chỉ đọc cho các loại chưa có bộ sửa được kiểm chứng. Mở block để truy xuất dữ liệu không tự cấp quyền sửa loại đối tượng đó.
- Khi đổi file, xóa phạm vi/kết quả cũ, cập nhật URL và bỏ phản hồi đến chậm của file trước. Nút “Mở file này” tải lại được file hiện hành.

## Cách kiểm tra trong ứng dụng

1. Chạy `./start-project.ps1` từ thư mục dự án, mở `http://127.0.0.1:8765/explorer`.
2. Tải file hoặc chọn file trong “Bản vẽ đang mở”. Chọn đúng khung, block hoặc bảng CAD.
3. Bấm **Đọc dữ liệu CAD**: xem loại/số đối tượng trong phạm vi, các dòng BOM, kích thước và dữ liệu nguồn.
4. Bấm **AI đọc bản vẽ**: model nội bộ đọc ảnh cùng dữ liệu nguồn; mỗi nhận xét phải dẫn ref CAD trong phần dữ liệu đã cung cấp. Các phần dữ liệu lớn được chia lượt, không cắt bỏ rồi báo đã đọc đủ.
5. Nhập yêu cầu sửa bằng phần phân tích thay đổi hiện có. Chỉ kế hoạch qua kiểm chứng hình học/BOM/liên kết mới được tạo revision và DWG.

Kết quả đọc được lưu tại `storage/documents/<document-id>/inspections/`. Đây là báo cáo đọc, không phải DWG đã sửa. File CAD gốc được giữ nguyên.

## Bằng chứng thực tế

MR-106: parser xác định 12 mã vật tư duy nhất qua các bảng kê đã nhận dạng. AI nội bộ Qwen3-VL 4B đã đọc đúng 8 dòng của bảng `41A8FC`: tấm mặt, tấm lót, ống trụ, chân bàn, tấm đế, la viền, bas và chân đế nhựa; có mô tả vật liệu/kích thước/công đoạn nguồn. Báo cáo và ảnh tại `storage/validation-fixtures/mr106-ai-reading.json` và `mr106-reading-ui.png`.

Sample_recover: parser đọc 3.181 thực thể Modelspace, 1.044 block definitions, gồm 244 POLYLINE và MULTILEADER. Lượt AI thực tế trên khung `14620` đọc phạm vi 512 đối tượng và 29 DIMENSION. Bước đối chiếu chấp nhận 6/8 nhận xét; loại tên sản phẩm gán nhầm và số 17,2 mm vì DIMENSION được dẫn đo 27,4 mm. Mã chi tiết `8.1.06931.014` được hiển thị trực tiếp từ CAD dù model từng nói thiếu mã. Báo cáo tại `storage/validation-fixtures/sample-ai-reading.json`. Bảng kê dạng LINE/TEXT vẫn được đọc chữ nguồn; chưa tự coi đó là bảng native có thể sửa ô.

Kiểm tra cuối: 263 bài kiểm thử Python đạt, ba script JavaScript đạt; hai file gốc giữ nguyên SHA-256.

Các kiểm thử bổ sung bao gồm cache cùng tên khác nội dung, block ẩn danh, truy xuất POLYLINE trong block, chia batch giữ đủ ô bảng, từ chối ref ngoài phạm vi, giữ nguyên nguồn và từ chối báo cáo thuộc phiên bản CAD cũ. Kiểm tra JavaScript dùng hàm giao diện thực tế để xác minh đổi file không nhận phản hồi cũ.

## Đối chiếu nhận xét với nguồn

Ref CAD có thật chưa chứng minh giá trị model nói là đúng. Nhận xét phải khớp text nguồn; số đo phải khớp scaled_measurement của chính DIMENSION được dẫn. Nhận xét chưa khớp được chuyển vào phần thu gọn, không dùng để sửa CAD. Tóm tắt tự do của model được giữ trong báo cáo phục vụ kiểm tra, không trình bày như kết luận đã xác nhận. Đây là kiểm tra giá trị/text, chưa phải chứng minh ý nghĩa lắp ghép.

## Giới hạn còn tồn tại

Không thể khẳng định đọc/hiểu/sửa đúng mọi DWG bất kỳ. OLE/proxy hoặc loại đối tượng chưa giải mã có thể chỉ có metadata. Báo cáo liệt kê đối tượng chỉ có metadata và block chưa mở hết; chúng không được coi là hình học đã đọc đủ. Khung vẫn được nhận diện theo biên chữ nhật và chữ nguồn; cần đối chiếu preview, nhất là khung tự do hoặc đối tượng tham chiếu ngoài.

Số đo có trong mô tả BOM khác với số đo hình học. Ghi chú công đoạn khác với bằng chứng mặt tiếp xúc/ràng buộc. Việc AI đọc được vật tư không tự chứng minh quan hệ co/giãn của sản phẩm, độ bền hoặc khả năng sửa mọi biên dạng. Các trường hợp chưa có quy tắc CAD được kiểm chứng vẫn bị chặn ở bước tạo bản sửa.

AI chạy trên localhost theo cấu hình hiện có, không thêm dịch vụ trả phí hoặc fallback cloud. Trên CPU, một lượt đối chiếu ảnh và dữ liệu có thể mất vài phút.

## Sửa nhận diện khung trong block và danh sách file (10/10/2026)

MR-106 có khung tên trong INSERT nhưng hình CAD và bảng kê nằm rời trong Modelspace. Bộ bổ sung tìm biên LWPOLYLINE/POLYLINE hoặc bốn LINE nối kín trong block, đọc chữ ở block lồng, áp dụng base point, scale và rotation của từng instance; dùng phạm vi khung để lấy hình rời và bảng đi cùng. Hai đường biên giấy trong cùng instance được gom thành một mục. Vùng gạch chéo đỏ vẫn bị bỏ qua.

Các upload đã có cache khung cũ được bổ sung riêng các khung INSERT còn thiếu, giữ nguyên ID và bbox các khung đang dùng. Cache mới có phiên bản và SHA-256 nguồn; preview dùng namespace mới. Đối chiếu thực tế: MR-106 từ 4 khung tiêu chuẩn thành **18 khung sản phẩm + 4 khung tiêu chuẩn**; Sample_recover giữ 25 khung; LEG6949 giữ 34 khung, không mất ID hay đổi bbox nguồn. Audit tại `storage/validation-fixtures/detection-v4-audit.json`.

Khung lắp tổng MR-106 `frame_411BDE_404569` đọc **530 thực thể, một bảng kê đủ 8 dòng, không có lỗi parse ghi nhận trong phạm vi này**. Đây là hình lắp và hình tách chi tiết đi cùng BOM, không chỉ là bảng `41A8FC`. AI nội bộ đã đọc ảnh và một lượt dữ liệu nguồn, không cắt context. Tám mô tả chi tiết đều khớp số thứ tự và mô tả trên cùng dòng BOM sau khi sửa bộ đối chiếu tiền tố `Chi tiết N:`. Sai số chi tiết hoặc sai độ dày vẫn bị loại. Kết quả model gốc được lưu nguyên; API đối chiếu lại báo cáo cũ theo phiên bản kiểm chứng, không cần chạy model lại. Báo cáo: `storage/validation-fixtures/mr106-full-frame-ai-grounded.json`.

Đồ thị hiện có 12 mã vật tư, sáu mã nối được tới khung chi tiết; chưa có cạnh lắp ghép được xác nhận từ ghi chú của MR-106. Việc đọc đủ BOM và thấy hình không đồng nghĩa đã có quy tắc sửa tự động cho kết cấu này.

Danh sách file chính gom upload trùng theo SHA-256 nội dung, giữ nguyên các phiên bản khác nội dung dù cùng tên, giữ lịch sử của upload đang mở và ẩn các fixture có tên xác định. Hiện còn ba file thực tế thay vì chín mục lẫn bản trùng/file thử. Bật **Hiện bản trùng / file thử** để truy cập toàn bộ; không xóa file hay lịch sử. Khung tiêu chuẩn có bộ lọc riêng, không xen vào 18 hình sản phẩm MR-106 mặc định.

Kiểm tra sau cùng: **271 bài kiểm thử Python đạt**, bốn script JavaScript đạt. Kiểm thử bao gồm khung block có base point/scale/rotation, LINE borders, chữ ở block lồng, đường biên trùng, loại vùng gạch đỏ, giữ ID/bbox cũ, gom file theo nội dung, phân biệt phiên bản cùng tên, chống phản hồi danh sách đến chậm, báo đối tượng metadata và từ chối mô tả đúng nhưng gán sai số chi tiết. Kết quả API thật và ID báo cáo AI ở `storage/validation-fixtures/upload-reading-final-audit.json`.
