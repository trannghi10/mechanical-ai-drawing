# Kiểm tra AI nội bộ — 08/10/2026

## 17/10/2026 — Khôi phục kết nối và tự khởi động khi phân tích

Nguyên nhân đợt này: backend website đang chạy nhưng `llama-server` không chạy. Các lệnh `run`/uvicorn mở website không đồng nghĩa model đã được nạp. Đã khởi động lại Qwen native và xác nhận `/ai/status`: `ready=true`, `local_only=true`. Không chuyển provider hoặc CAD lên cloud.

Adapter sync/async nay kiểm tra readiness trước khi gửi payload. Nếu kết nối bị từ chối, tự gọi launcher cài sẵn một lần; nếu model đang nạp thì chờ với tiến trình `runtime`, trong ngân sách chung và giới hạn 60 giây. Cho phép hủy trong lúc chờ. Model sai/không vision, thiếu file, lỗi cổng hoặc quá ngân sách vẫn được báo; không tải model, thay tiến trình khác hoặc phát lại lệnh sinh kết quả sau lỗi giữa chừng. Endpoint GET trạng thái chỉ đọc; không tự spawn từ thao tác xem trạng thái.

Kiểm chứng thật từ runtime đang tắt: Qwen tự nạp và trả JSON phép tính mẫu 20−5=15 trong 8,61 giây, trạng thái ready. Đây là kiểm tra kết nối, không phải chỉnh kích thước DWG. Receipt: `storage/validation-fixtures/native-cold-start-2026-10-17.json`.

Yêu cầu thật đang lỗi là MR-106, khung `frame_411BDE_404569`, “giảm chiều dài chi tiết số 7 thành 15”. Sau phục hồi kết nối, lần gọi model đủ 3.040 tokens vẫn hết ngân sách CPU 120 giây. Đã thêm kiểm tra trước model: khi CAD là mm, BOM cục bộ xác định đúng một mã, yêu cầu một kích thước đích nhưng chưa có hướng/mốc giữ, trả câu hỏi không thực thi từ nguồn. Không suy mặc định trái/đáy hoặc xác nhận hình đã được sửa.

Lần chạy cuối qua API website: lập kế hoạch `checked_missing_resize_datum` trong 12,7 giây kể cả đọc CAD, nhận đúng mã `8.1.05940.126`, bas 3×20×20 mm, hỏi hướng/mốc để giảm về 15 mm. Còn câu hỏi nên `execution_available=false`; chưa tạo revision/DWG mới của yêu cầu đó. Nguồn DWG/DXF đối chiếu hash không đổi. Receipt: `storage/validation-fixtures/mr106-native-retry-final-2026-10-17.json`.

Đây không phải hoàn thành backup MR-106/Dauphine hay khả năng sửa đúng mọi DWG.

Kiểm thử: 1.312 bài toàn bộ đạt (`storage/validation-fixtures/pytest-native-startup-full-2026-10-17.txt`); 150 bài AI/planning liên quan đạt (`pytest-native-startup-final-2026-10-17.txt`). Vẫn 19 module. Trình duyệt mở đúng kế hoạch MR-106, hiện câu hỏi và trạng thái Qwen nội bộ; không lỗi JavaScript. Ảnh: `storage/validation-fixtures/native-runtime-result-ui-2026-10-17.png`. Backend đã nạp mã cuối, `/ai/status` và PostgreSQL ready.

---


Runtime: llama.cpp đi kèm Ollama 0.40, model Qwen3-VL 4B Instruct đã tải bằng Ollama và xác minh SHA256. Chạy bằng CPU, địa chỉ 127.0.0.1:11436, offline, không context shift. Ứng dụng dùng AI_PROVIDER=native, AI_OFFLINE=1.

## Đã kiểm tra

- Runtime nạp model thành công và hỗ trợ vision. API /ai/status trả local_only=true, ready=true.
- Đọc ảnh mặt cắt thật: nhận đúng kích thước ngoài 60 × 30 mm, thành 2 mm; mã chi tiết đọc từ ảnh sai. Bằng chứng: storage/validation-fixtures/qwen4-native-probe.json.
- JSON schema phải dùng response_format.type=json_object cùng schema trong runtime này. Đã thử ép giá trị const với lời nhắc trái ngược và nhận đúng schema.
- Mô hình có thể tính sai chi tiết lắp ghép: bài thử giữ ngoài 30, thành 2→1.2, chi tiết lắp 25.6 và khe hở tổng 0.4 phải cho chi tiết lắp 27.2. Model từng trả 25.6. Kết quả đó chưa được dùng để sửa CAD.
- Bộ kiểm tra FitRule trong graph/fit_constraints.py tính khe hở trực tiếp từ geometry DIMENSION trước/sau và từ chối khi không giữ đúng khe hở. Đây là điều kiện thực thi, không phải chỉ lời nhắc AI.
- Client từ chối URL ngoài localhost, redirect, sai model/không vision, phạm vi quá nhiều token và kết quả chưa đầy đủ. Không tự chuyển sang Gemini.
- 81 bài kiểm thử toàn bộ đạt, gồm 8 bài native kiểm tra bảo vệ dữ liệu, giới hạn context và kết quả chưa đầy đủ.

## Giới hạn hiện tại

Chưa có bản sửa sản xuất LEG6949 được xác minh hoàn chỉnh cho yêu cầu đổi thành hộp hoặc giảm chiều cao toàn sản phẩm. Không được xem trạng thái AI sẵn sàng là bảo đảm sửa được mọi kết cấu. Mã vật tư, đường bao và quan hệ lắp ghép phải đối chiếu dữ liệu CAD; trường hợp sai hoặc thiếu bằng chứng bị chặn trước khi tạo bản sửa.

Model nhỏ chạy CPU có thể mất vài phút hoặc lâu hơn cho nhiều khung. Không gửi bản vẽ nội bộ tới dịch vụ ngoài để khắc phục độ chậm.
