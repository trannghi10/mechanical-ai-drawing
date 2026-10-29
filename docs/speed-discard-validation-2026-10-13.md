# Lọc bản gạch bỏ và giảm thời gian chờ AI

Đã triển khai ngày 13/10/2026. Giữ AI nội bộ; không đổi provider sang cloud và không đọc/hiển thị API key.

## Lỗi đã xử lý

- Bộ lọc cũ bỏ sót đường chéo đơn màu đen. Đã nhận nét gạch bỏ dài qua khung có thông tin bản vẽ, độc lập với màu nét; hỗ trợ khung nằm trong block quay/phóng tỷ lệ. Đường chéo ngắn bên trong chi tiết không đủ để loại cả bản vẽ. Block riêng có nét gạch từ layout được đối chiếu theo layout và các góc khung bao, không chỉ theo độ dài một đường bất kỳ. Giữ bản gốc; chỉ lọc khỏi danh mục/phạm vi chọn.
- Cache loại bỏ được gắn phiên bản và dấu thời gian/kích thước nguồn. Cập nhật cache khung, không đưa bản đã bỏ trở lại bằng fallback toàn layout. Mỗi layout chỉ lập chỉ mục một lần trong lượt kiểm tra catalogue.
- Giảm dữ liệu CPU: phạm vi ít entity vẫn có thể chứa hàng nghìn điểm locator của đường cong trong `source_features`. Các điểm hiển thị trùng không còn được gửi vào raw prompt. Hình học gốc và feature index đầy đủ vẫn giữ trên server. Dữ liệu được mã hóa cột không mất giá trị; block sâu dùng overview, ma trận chỉ hoãn khi không có geometry/placement đầy đủ và được trả lại qua truy xuất nguồn.
- Prompt nội bộ ngắn hơn, preview gửi model rộng 512 px. Preview người dùng và dữ liệu CAD xuất ra không đổi độ nét/hình học. Ngưỡng CPU mặc định 4.096 input tokens; cấu hình tối đa 5.000. Context được đối chiếu với runtime đang chạy và giới hạn 8.192, không dựa riêng vào cấu hình cũ 32k. Output tối đa 2.048 tokens; kết quả chưa đầy đủ bị từ chối.
- Tác vụ phân tích nền có trạng thái CAD → feature → compiler → AI → validation. Gửi trùng cùng nguồn/phạm vi/yêu cầu dùng chung tác vụ. Trình duyệt lưu ID để tải lại trang vẫn theo dõi được. Thêm nút hủy; với AI native, hủy đóng kết nối HTTP bất đồng bộ để ngắt cả prefill. Có ngân sách 120 giây cho phân tích native qua tác vụ/endpoint; số vòng truy xuất nội bộ được giới hạn. Restart server đánh dấu tác vụ đang dở là cần thử lại, không giả vờ vẫn chạy.
- Không tự gọi thêm AI đọc công đoạn sau khi đã hiển thị kế hoạch. Người dùng vẫn có nút đọc bổ sung riêng.
- Câu như `Giảm chiều cao xuống 82 mm, giữ đáy`, `Hạ chiều cao 18 mm, giữ đáy` được biên dịch trực tiếp khi mã chi tiết và DIM đo thật trong phạm vi chọn xác định duy nhất. Không lấy chiều cao của sản phẩm khác từ lựa chọn lưu để thay cho DIM của chi tiết đang chọn. Mốc giữ vẫn phải có trong yêu cầu/lựa chọn đã xác nhận.

## Kiểm chứng thực tế

1. **Khung trong ảnh Dauphine:** `39AD6B`, nét gạch `3F8546`, layer 0, màu ByLayer. GET danh sách khung không còn trả khung đó. Danh mục/khung đầu tiên mất 11,891 giây; GET catalogue đã cache mất 0,078 giây trên máy này. Còn 71 khung trong lần đối chiếu; không diễn giải số này thành số chi tiết đã sửa. [Receipt](../storage/validation-fixtures/discarded-dauphine-20261013.json).
2. **Prompt trên block thử lồng 7 cấp:** trước sửa vượt context 8.192; bỏ locator trùng còn 6.880; sau tối ưu prompt/khung/preview còn **3.633 tokens**, đếm bằng runtime thật trước generation. [Receipt](../storage/validation-fixtures/cpu-prompt-budget-20261013.json). Đây là trường hợp đo cụ thể, không cam kết mọi file đều dưới ngưỡng.
3. **Hủy/phục hồi trên trình duyệt thật:** khởi chạy AI với 3.633 tokens → reload → hiện lại đúng yêu cầu/tác vụ → bấm hủy. Tác vụ chuyển `cancelled`; mọi native slot báo `is_processing=false`. Số kế hoạch và revision của fixture giữ 1/1; lần hủy không tạo thêm bản sửa. [Receipt](../storage/validation-fixtures/planning-cancel-live-20261013.json).

   ![Giao diện xác nhận hủy trên bản thử](../storage/validation-fixtures/planning-cancel-ui-20261013.png)

4. **Luồng DWG qua tác vụ nền:** upload DWG mới có SPLINE bậc ba không tròn, block lồng 7 cấp → yêu cầu 140 thành 123 mm → kế hoạch khoảng **5,625 giây** → tạo preview → duyệt fixture → tải DWG → ODA mở lại đo đúng 123 mm, giữ hai lỗ R2, knots/weights/degree và hash nguồn. [Receipt](../storage/validation-fixtures/general-workflow-0766148a/report.json), [DWG kiểm thử](../storage/validation-fixtures/general-workflow-0766148a/download/checked-preview.dwg). Đây không phải backup Dauphine.

**586 kiểm thử Python đạt**, 581 warnings, 65,80 giây; log `storage/validation-fixtures/pytest-speed-exclusions-20261013.txt`. Các kiểm chứng giao diện `verify_frontend.js`, `verify_frontend_downloads.js`, `verify_frontend_planning.js` đạt. Có kiểm thử riêng cho hủy kết nối native đang prefill, nguồn thay đổi khi đang xếp hàng, cache cũ, source frame phục hồi và DIM suy ra duy nhất.

## Cách dùng và giới hạn

Tải lại trang để nhận nút **Hủy phân tích** và luồng nền. Chọn một bản vẽ còn hiệu lực rồi nhập yêu cầu; bản gạch bỏ được ẩn tự động. Có thể reload trong khi phân tích. Tạo bản sửa/xuất DWG vẫn dùng các kiểm tra CAD, vật tư và liên kết hiện hành.

Không cam kết suy luận CPU hay Gemini luôn xong trong 2–3 giây. Ngân sách thời gian là giới hạn chờ, không phải bảo đảm hoàn thành hình học trong thời gian đó. Kết quả thiếu dữ liệu hoặc quá ngưỡng phải báo rõ; không xuất thiếu rồi ghi nhãn backup hoàn chỉnh. Sửa mọi DWG, tham số block động, proxy association và backup toàn sản phẩm Dauphine vẫn chưa hoàn tất.
