# Phạm vi sửa trong block chứa nhiều bản vẽ — 15/10/2026

**Cập nhật tiếp:** đã triển khai xuất phạm vi bên trong block tĩnh theo chính sách phiên bản 3. Giới hạn giữ toàn INSERT mô tả dưới đây là trạng thái trước cập nhật này; xem `docs/nested-selection-export-2026-10-15.md` để biết phạm vi mới và các trường hợp còn bị chặn.

Đã sửa một nguyên nhân gây hiểu nhầm dữ liệu khi nhiều bản vẽ cùng nằm trong một INSERT lớn. Trước đây, nếu INSERT chạm nhiều khung, context gán mọi đối tượng con vào tất cả các khung đó. BOM của bản khác có thể xuất hiện trong yêu cầu đang chọn, và một bản sao ngoài phạm vi có thể bị đưa vào đồng bộ.

## Thay đổi đã triển khai

- Gán phạm vi từng đối tượng theo vị trí thật qua chuỗi INSERT và ma trận đặt block. Tách đúng BOM và chi tiết của các khung đã có; không sửa bộ nhận diện/chọn khung hoặc ID khung.
- Khi chỉ chọn một khung, loại các đối tượng thuộc bản khác khỏi context chỉnh sửa. Giữ đúng trạng thái chỉ đọc cho khung liên quan đang được xem xét; không biến khung đó thành phạm vi được sửa chỉ vì dùng chung block chứa.
- Khi người dùng chọn toàn bộ block, vẫn giữ toàn bộ nội dung của block trong phạm vi đã chọn.
- Một chi tiết native có mã khớp BOM nguồn được giữ nguyên vẹn: không bỏ lỗ/DIM nằm ngoài mép khung khi thân chi tiết chạm khung. Chỉ phân vùng block chứa các bản vẽ, không cắt hình học của chi tiết thành dữ liệu thiếu.
- Giữ các đối tượng cắt ngang nhiều khung trong các phạm vi liên quan. Nếu không xác định được extents, giữ đối tượng để kiểm tra thay vì âm thầm loại bỏ. Cache bounds cục bộ theo handle, chuyển vị riêng theo từng instance.

Mã chính: `cad/scope_membership.py`, `backend/services/change_service.py`. Bộ đọc toàn file và thư viện block không bị cắt bỏ; đây là sửa cách xây dựng phạm vi phân tích/thực thi.

## Hỏi đúng mốc giữ, tránh chờ model khi dữ liệu đã chỉ ra mâu thuẫn

Khi DIM đo ngang nhưng yêu cầu ghi “giữ dưới”, engine trả ngay câu hỏi chọn trái/phải hoặc tâm. Không gửi mâu thuẫn này sang model CPU. Câu trả lời được đối chiếu đúng mã chi tiết, ref DIM, số đo nguồn và câu hỏi đã phát sinh; chỉ thay mốc cho DIM đó. Câu trả lời chứa thêm một yêu cầu sửa khác không bị nuốt vào lựa chọn mốc giữ.

Đã kiểm tra API lập câu hỏi → trả lời → tạo bản sửa → xem trước → duyệt → tải DWG → ODA mở lại. Mốc giữ mới được lưu trong recipe và phần giải thích, không dùng lại nhãn mốc cũ.

Mã: `backend/services/measured_profile_planner.py`.

## Kiểm chứng DWG qua API thật

`scripts/verify_general_dwg_workflow.py --container-scopes` tạo ba file mới, đặt hai khung và một bản sao ngoài khung trong cùng block lồng nhau, upload tên ngẫu nhiên và dùng bộ nhận diện khung bình thường. Không cung cấp mapping riêng cho engine.

| File tổng hợp | Kết quả ODA mở lại | Luồng đầy đủ |
| --- | --- | --- |
| Hai khung trong block lồng | Khung chọn 100 → 80 mm; khung bên cạnh và bản sao ngoài phạm vi cùng mã giữ 100 mm | Duyệt/tải HTTP 200; 4,251 giây |
| Block xoay 90°, tỷ lệ 2 | Như trên; BOM khung chọn đổi `2x20x100` → `2x20x80`, BOM bên cạnh giữ nguyên | Như trên; 4,218 giây |
| Block phản chiếu và xoay | Như trên; giữ đúng từng phạm vi và nguyên liệu nguồn | Như trên; 5,023 giây |

Ở file xoay, câu hỏi mốc giữ được trả trong 0,091 giây; trả lời và lập kế hoạch mới trong 0,056 giây, không dùng model. Các thời gian là của fixture nhỏ trên máy hiện tại, không phải cam kết cho file bất kỳ.

Biên nhận, hash và đường dẫn các DWG: `storage/validation-fixtures/source-scopes-dwg-e82ffd85/receipts.json`. Đã đối chiếu DIM, hình học, BOM, bản sao không chọn và hash nguồn; kiểm tra profile bằng FreeCAD đạt. Đây là hồi quy tổng hợp, không thay thế nghiệm thu sản phẩm khách hàng.

Đã đọc kiểm tra một số khung của Sample, MR-106, Dauphine và LEG6949 mà không sửa file. Chỉ khung Dauphine được chọn trong audit có 28 dòng BOM; các khung đầu được lấy ở ba file còn lại không có bảng BOM. Kết quả này chứng minh đường đọc phạm vi chạy được, không chứng minh đã hiểu hoặc sửa toàn bộ sản phẩm. Biên nhận: `storage/validation-fixtures/source-scopes-customer-readonly-2026-10-15.json`.

**1.007 kiểm thử Python đạt**, gồm 13 trường hợp mới về phạm vi, BOM, khung chỉ đọc, chi tiết qua mép khung, đối tượng chưa có bounds và hỏi/trả lời mốc giữ. Log: `storage/validation-fixtures/pytest-source-scopes-release-2026-10-15.txt`. Vẫn giữ 19 file kiểm thử Python; không thêm file test rời. Backend đã nạp mã mới.

## Giới hạn còn lại

- Hình rời không có khung/mã sở hữu hoặc quan hệ lắp ghép vẫn chưa đủ căn cứ để tự gán vai trò. Không bỏ chốt kiểm tra công đoạn để ép tạo backup hoàn chỉnh.
- Xuất theo selection hiện giữ nguyên INSERT đã đặt cùng các resources của nó. Vì vậy các bản vẽ khác bên trong cùng INSERT có thể vẫn có mặt trong DWG xuất, nhưng phải giữ nguyên. Chưa phải chức năng tách/purge mọi dữ liệu ngoài khung khỏi block chứa.
- Block động/proxy và những liên kết thiết kế chưa xác định vẫn còn giới hạn. **Chưa hoàn thành sửa đúng mọi DWG; backup toàn Dauphine chưa hoàn chỉnh.** Đợt này không sửa thêm bản vẽ khách hàng; bản Dauphine gần nhất vẫn là preview `c75fb805`.
