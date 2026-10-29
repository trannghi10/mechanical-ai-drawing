# Gắn hình hộp thiếu mã và mốc giữ — 21/10/2026

Đã bổ sung luồng trên website để đối chiếu một hình hộp CAD với DIM/BOM nguồn, chọn mốc giữ và lưu liên kết riêng theo hash file. Hình đủ cạnh nhưng chưa có mã không tự nhận danh tính chỉ vì khớp kích thước.

## Cách sử dụng

1. Chọn bản chi tiết có DIM đo thật. Mở **Kiểm tra dữ liệu bản vẽ → Hồ sơ chi tiết và hình biểu diễn → Lập hồ sơ CAD đã chọn**.
2. Trong **Gắn hình hộp còn thiếu mã hoặc mốc giữ**, chọn DIM nguồn và khung chứa hình đích. Bấm **Đọc các hình hộp có thể gắn**.
3. Đối chiếu ảnh các cạnh CAD và ký hiệu đỉnh. Chọn giữ tâm hoặc một đỉnh. Mốc không giữ được nét nối nguồn bị khóa; mỗi kích thước đích vẫn được kiểm tra lại khi lập kế hoạch.
4. Xác nhận đúng mã vật tư và mốc giữ rồi lưu. Phân tích lại yêu cầu để đồng bộ. Có nút xóa liên kết.

Luồng này lưu quyết định kỹ thuật; không sửa DWG ở bước xác nhận. Khi thực thi, engine đọc lại đầy đủ cạnh, DIM, BOM, phép chiếu và phạm vi. Liên kết chỉ áp dụng cho đúng tập LINE đã chọn, không gán mã cho toàn bộ block cụm. Phạm vi hình liên quan được mở riêng, không biến khung cụm thành bản chi tiết của một mã.

## Bảo toàn nguồn và kiểm tra

- Danh sách ứng viên chưa phải xác nhận danh tính. Server dựng lại ứng viên trước khi lưu; không nhận tọa độ mốc tùy ý từ client.
- Quyết định nằm trong `design-decisions-v1.json`, gắn hash, mã, DIM, các ref hình và mốc native. Các quyết định kỹ thuật khác được giữ lại.
- Xóa liên kết hoặc bỏ khung làm kế hoạch cũ mất điều kiện sử dụng phép gắn; phải đọc và phân tích lại. Phản hồi giao diện của tài liệu/lựa chọn cũ không được dùng để lưu.
- Giữ tiếp nối nét CAD hiện có và từ chối chồng hình mới sau co/giãn. Với cung elip, bộ đọc tính cực trị của đúng đoạn cung trong mặt phẳng native, kể cả pháp tuyến âm; không thay cung bằng vòng tròn bao để kết luận có nét chồng.
- Kiểm kê HATCH bổ sung pháp tuyến và cao độ, để bộ định vị không dùng tọa độ OCS thiếu bằng chứng như tọa độ phẳng đã xác định.

Mã chính: `backend/services/cuboid_link_service.py`, `graph/cuboid_links.py`, `graph/cuboid_projections.py`. API đọc ứng viên, xem SVG nguồn, lưu/xem/xóa liên kết đã được nối vào website. Registry version 20.

## DWG tổng hợp độc lập

Mẫu `UNSEEN-CUBOID-c7d8d9f9` ban đầu có hình đích không mang mã. Kịch bản đã đi qua API đọc ứng viên → xem cạnh nguồn → xác nhận danh tính và đỉnh A → phân tích giữ đầu dưới của bản chi tiết → sửa → xem trước → duyệt → AutoCAD xuất → tải HTTP 200 → ODA mở lại.

- DIM/đường bao nguồn: 100 → 76 mm.
- BOM và ghi chú hình đích: 2×80×100 → 2×80×76 mm.
- Hình đích giữ đủ 9 LINE và đúng camera trực giao; đỉnh đã chọn giữ nguyên.
- File gốc giữ hash. Đây là file tổng hợp dùng để kiểm chứng luồng xác nhận, không phải xác nhận thay người dùng trên file khách.
- Receipt: `storage/validation-fixtures/cuboid-projection-c7d8d9f9/receipt.json`.
- DWG: `storage/validation-fixtures/cuboid-projection-c7d8d9f9/download/cuboid-backup.dwg`.
- SHA-256: `78f35ecf6d2179981fac5a5c05fc9acc2dbd6104704142a35fc947ba4455401e`.
- Lặp lại: `python scripts/verify_cuboid_projection.py --confirm-uncoded`.

## Dauphine: giữ đề xuất chưa xác nhận

Đã tìm được một ứng viên đủ 9 cạnh cho mã đề xuất `3.8.01312`, theo DIM `3DFA60` và quy cách 40×635×745 mm. Đối chiếu kế hoạch hiện có cho kích thước đích 40×635×718 mm. Cung elip thực tế chỉ nối vào cạnh, không nằm chồng trong tấm; đã xác định ba điểm tiếp nối nguồn.

Giữ tâm không bảo toàn các nét nối đó. Các đỉnh B/D/E/G giữ phía trên vượt kiểm tra; bản đề xuất minh họa chọn B. Các điểm nối được kiểm tra lại trên toàn hình sau sửa dự kiến.

**Người dùng đã chọn: “Giữ bản đề xuất, tôi chưa xác nhận”.** Chưa lưu liên kết danh tính/mốc giữ cho hình khách, chưa tạo revision khách từ đề xuất này. Không hỏi lại hoặc coi thời gian chờ là sự xác nhận; chỉ thay đổi quyết định khi người dùng cung cấp lựa chọn mới.

- Ảnh trước/dự kiến: `storage/validation-fixtures/cuboid-dauphine-proposal-2026-10-21/proposal.png`.
- Đề xuất có trạng thái người dùng: cùng thư mục, `proposal.json`.
- Bằng chứng đọc website và mốc: `storage/validation-fixtures/cuboid-dauphine-candidates-2026-10-21/receipt.json`.
- Hash nguồn DXF giữ nguyên `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

Phối cảnh C4 bị che, các mặt lắp/Detail và những hình đóng gói khác vẫn chưa hoàn chỉnh. Tính năng này mở thêm cách xử lý dữ liệu thiếu qua xác nhận có nguồn; không chứng minh tự sửa đúng mọi DWG.

## Kiểm thử

**1.648 bài Python toàn bộ đạt**, 250,19 giây; 24 bài tập trung đạt. Tám script frontend đạt, gồm chọn DIM, xác nhận danh tính/mốc, đổi mốc phải xác nhận lại, xóa và chống phản hồi cũ. Có kiểm tra mất phạm vi, hash cũ, kế hoạch sau xóa liên kết, tiếp nối nét và cực trị cung elip âm/nghiêng.

Logs: `storage/validation-fixtures/pytest-cuboid-links-release-full-2026-10-21.txt`, `pytest-cuboid-links-release-focused-2026-10-21.txt`, `frontend-cuboid-links-release-2026-10-21.txt`.
