# Dịch CenterMark qua hợp đồng native

Đã thêm action `translate_centermark` vào job AutoCAD local. Mỗi cặp cần đường tròn XY ở layout cùng dấu tâm static và action CenterMark có đúng hai dependency. Đã mở rộng sang [nhóm nhiều cặp](native-centermark-batch-2026-10-21.md), kiểm chứng CAD với nhóm 2 và 11 cặp. Không hỗ trợ nested instance, mixed operations, đổi bán kính hoặc dịch theo Z trong adapter này.

API native-edits yêu cầu inspection đã gắn với working document, lựa chọn chứa cả đường tròn và dấu tâm, cùng một `dependency_inspection_id` local đã ready trên cùng hash nguồn. Hai handle, action, owner và tâm trước phải khớp ứng viên dependency. `before` và `after` là chuỗi JSON mảng ba tọa độ hữu hạn. Các trường `mark_handle` và `action_handle` ràng buộc đúng cặp. Job service cũng chặn provider cloud, nhiều thao tác hoặc thiếu scope dấu tâm.

Plugin dùng cùng lõi dịch đã kiểm chứng bởi probe: đọc lại dependency native trực tiếp, kiểm đúng expected owner/action/mark/center trước khi sửa, dịch đường tròn và evaluate riêng action bằng callback framework. Lưu DWG, mở lại, kiểm trạng thái và hình học trước evaluate, rồi evaluate lần nữa để kiểm ổn định. Đối chiếu inventory ngoài mục tiêu vẫn giữ nguyên cơ chế dung sai và handle của probe.

Kết quả dùng gói bốn artifact chuẩn. `inventory.json` thêm `centermark_effects`. Backend kiểm hash nguồn/đầu ra, handle/action, vector, tâm trước/sau, kiểm trạng thái persisted, số entry inventory đã đối chiếu và dependency sau xuất; sau đó đọc DXF độc lập để kiểm đường tròn, INSERT, owner, bán kính, tâm và reactor trước khi đánh dấu job ready.

## Bằng chứng CAD

Plugin build và host check đạt trên AutoCAD 2027, runtime key `5d5e381ec331ada622ad58c55f13e7e3380712840d40e3e952e4c1d83bfb496b`.

Hai job kiểm chứng trên bản sao nguồn Dauphine chạy qua `aps_jobs.start` → host production `MECHANICALCAD` → `_accept_result`:

- Circle `3B7FF1`, mark `3B7FF2`, delta `[3,-2,0]`: inspection `f23fee4b36e54078b70bb4f4566fb4cc`, edit `782ce4706cc748aaa66a1cce72c72e9f`, DWG SHA-256 `78675d136306e9ed42dc6b514a5dd5e17b7fa25b03d874f66d68587cb8e182be`. Receipt: `storage/validation-fixtures/native-centermark-job-88d6d8d8/receipt.json`.
- Circle `3B7FD1`, mark `3B7FD6`, delta `[-4,1.25,0]`: inspection `4f699eafc9cb4c3a9d89392b77fe6b73`, edit `5bfcc912ad254dc3a9cd216889b1e9b7`, DWG SHA-256 `06abc80a298ab0483b52f95a2cd91577ae7dca7ef71ec88b8f67cacc1474f6ab`. Receipt: `storage/validation-fixtures/native-centermark-job-bc6fed5f/receipt.json`.

Mỗi lượt đối chiếu 39.915 entry inventory ngoài cặp mục tiêu. Hai bộ artifact được chạy lại hàm đọc DXF độc lập sau khi siết điều kiện số entry/dung sai và đều đạt. Nguồn giữ SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.

Bằng chứng âm: cố ý truyền action `3B8023` của cặp khác cho circle `3B7FF1`. Job `f3ecf3c6fcf242fc9d56bb02663fa703` bị plugin chặn với `CenterMark contract dependency/owner mismatch`, trước bước dịch; không có thư mục result đã được chấp nhận, nguồn giữ nguyên. Receipt: `storage/validation-fixtures/native-centermark-rejection-559381c2/receipt.json`. Lặp lại bằng `--reject-action-handle WRONG_HANDLE` trên script kiểm chứng. CLI chỉ công nhận trường hợp âm khi job failed và lỗi native đúng lý do dự kiến.

`scripts/verify_native_centermark_job.py` lặp lại job này trên bản sao, không tạo customer revision. Vector thử chỉ kiểm chứng adapter, không xác nhận dịch cả cụm hộp–chốt của sản phẩm. API selection/dependency binding có kiểm thử riêng bằng mock và đã được kiểm chứng HTTP toàn luồng ở phần tiếp theo.

## Kiểm chứng HTTP trên bản sao nhập native

Tạo bản sao kiểm chứng `51ec94944c4443b19fb8d5bd7930a6dd` bằng endpoint import local. Lượt đầu job `803079de0afb41249f351b989ec6ef94` thất bại trước đọc CAD vì backend kế thừa sandbox không mở được registry hồ sơ AutoCAD. Console UTF-16 ghi rõ `Can't open user root registry key`; đây không phải bằng chứng lỗi license hoặc geometry. Đã khởi động backend ngoài sandbox rồi tiếp tục đúng tài liệu, không tạo lại hoặc sửa nguồn. Inspection native `daacc85086d44bb3afb76f277e7ade6f` hoàn thành, catalog 1.290 mục.

Script `scripts/verify_native_centermark_http.py` đã chạy qua API thật:

- Chọn khung `3B3987`, kiểm native context gắn đúng import inspection và hash nguồn.
- Scoped dependency inspection `fd5a540c093a4b8085d2044abec19d37` nhận đúng cặp `3B7FF1` / `3B7FF2`.
- Lệnh cố ý sai tâm nguồn nhận HTTP 422 trước khi tạo job sửa.
- Lệnh đúng nhận HTTP 202; edit job `522a1436fc594c33bba5c6592ae29f1b` hoàn thành qua bộ kiểm kết quả production.
- DWG SHA-256 `de572894bdf6f36d3bec570114ccc8bd0a8cf57f368ef4028c4bb097e15696bb`; hash nguồn vẫn giữ nguyên như trên.

Receipt và request: `storage/validation-fixtures/native-centermark-http-2026-10-21/`. Không tạo customer revision, không xác nhận mating hoặc backup toàn sản phẩm. Backend hiện phải chạy trong ngữ cảnh Windows có quyền truy cập registry hồ sơ AutoCAD; không suy ra chỉ cần API server hoạt động là engine có thể khởi động.

Đã bổ sung phân loại lỗi startup registry cho log UTF-8/UTF-16 LE và sửa thông báo tiếp tục import local dùng đúng tên AutoCAD local. Bộ kiểm thử startup/CenterMark/export jobs đạt **163 bài**, 18,26 giây. Bộ phân loại cũng nhận diện đúng console lỗi thực tế của job đầu; không in đường dẫn registry hoặc nội dung console tùy ý ra thông báo người dùng.

## Giới hạn còn lại

Hồi quy toàn dự án đạt **1.722 bài**, 2.723 warning thư viện, 255,34 giây; log `storage/validation-fixtures/pytest-centermark-production-2026-10-21.txt`. Bộ CenterMark sau bổ sung kiểm thử DXF độc lập đạt **16 bài** riêng (0,98 giây). Các kiểm thử này bao gồm contract không hợp lệ, inspection thiếu/sai, scope không đủ, receipt sai và DXF thực tế sai vị trí. Kết quả CAD thực tế nêu trên vẫn là bằng chứng riêng, không được thay bằng kiểm thử mock.

Đã có giao diện chọn một hoặc nhiều cặp và nhập độ dịch trong công cụ AutoCAD local, với [bằng chứng CAD cho batch](native-centermark-batch-2026-10-21.md). Chưa hỗ trợ dịch nhóm chi tiết phụ thuộc bên ngoài circle/mark. Các quan hệ cơ khí với ống hộp và chi tiết khác vẫn chưa được xác nhận. Đây không phải backup hoàn chỉnh Dauphine, cũng không chứng minh sửa mọi DWG. Đề xuất tấm xốp tiếp tục chưa xác nhận.

## Giao diện chọn dấu tâm và tự tìm theo khung

Nút **Đọc dấu tâm của bản vẽ đang chọn** gọi `POST /documents/{id}/autocad/centermark-inspections` với IDs đang chọn. Server chỉ lấy root layout editable từ context gắn nguồn native; tìm đường tròn và INSERT static đồng tâm/cùng owner để đọc dependency. Đây chỉ là bước lấy ứng viên, không suy ra liên kết từ vị trí. Giới hạn 64 root; cặp hợp lệ vẫn cần graph và native preflight.

Form liệt kê handle và tọa độ để phân biệt các cặp đồng tâm. Nhập độ dịch X/Y theo đơn vị tọa độ CAD nguồn, giữ Z; hình có tỷ lệ cần quy đổi riêng. Chặn rỗng, số không hữu hạn, độ dịch bằng 0, tọa độ overflow, nguồn đổi hoặc selection/provider đổi. Job hiển thị vector đã kiểm chứng và link tải/xem hình. Chưa tự dịch chi tiết xung quanh.

HTTP tự tìm đã đạt: inspection `14697ba4627d4970990a17960f7df3b7` đọc 47 root trong khung `3B3987`, tìm 11 cặp có graph phù hợp. Script chọn cặp `3B7FF1`/`3B7FF2`, chặn tâm sai 422 và nhận lại job `522a1436fc594c33bba5c6592ae29f1b` đã kiểm chứng (cache cùng hợp đồng). Receipt: `storage/validation-fixtures/native-centermark-selection-ui-2026-10-21/receipt.json`. Chín cặp mới sau đó đều đã qua job dịch riêng và xuất/mở lại CAD; xem [kiểm chứng tập cặp](centermark-population-2026-10-21.md).

`node --check frontend/aps.js` và `node scripts/verify_frontend_aps.js` đạt; harness kiểm hợp đồng gửi, chặn độ dịch 0, selection đổi, hash đổi và phản hồi đến muộn sau đổi provider. Bộ Python liên quan đạt 165 bài trước khi thêm kiểm thử endpoint selection; bộ CenterMark cuối đạt riêng 19 bài. Công cụ trình duyệt báo `Local browser use is disabled in Work settings`, nên chưa có kiểm chứng ảnh hoặc thao tác trình duyệt thực tế cho form. Không thay đổi setting để vượt giới hạn đó.
