# Dịch nhiều cặp CenterMark trong một DWG

Action `translate_centermark` nhận nhóm từ 1 đến 16 cặp độc lập, chỉ dùng AutoCAD local, không trộn thao tác khác. Code giới hạn 16; bằng chứng CAD hiện có cho nhóm 1, 2 và 11 cặp, chưa chứng minh mọi nhóm trong giới hạn này đều sửa được.

Các handle circle, mark và action phải khác nhau giữa mọi cặp; phải chọn đủ circle và mark trong context native. Từng cặp vẫn phải khớp inspection dependency, owner, tâm trước và hash nguồn. API từ chối cặp trùng hoặc dependency sai trước khi tạo job.

## Lõi native và kiểm kết quả

Lõi dùng chung trong `autodesk/MechanicalCad/CenterMarks.cs` cho probe đơn và production. Đọc và kiểm tất cả cặp trên database gốc trước khi mở bất kỳ circle nào để ghi. Dịch toàn bộ circle trong một transaction, evaluate các action trong transaction kế tiếp, sau đó kiểm lại mọi cặp. Không suy ra quan hệ cơ khí giữa các cặp.

Chỉ lưu một DWG chung. Mở lại và kiểm tất cả trạng thái/hình học đã lưu trước khi evaluate bất kỳ action nào; sau khi evaluate toàn bộ, kiểm lại mọi cặp lần nữa để phát hiện action sau làm ảnh hưởng cặp trước. Đối chiếu thuộc tính circle/mark và inventory ngoài toàn bộ nhóm. Inventory bổ sung normal của INSERT để giữ kiểm tra normal dấu tâm cùng position, rotation, scale và các thuộc tính đã liệt kê.

Backend yêu cầu đúng tập effect, không thiếu/dư/trùng, cùng số cặp và số entry ngoài nhóm. Mỗi effect gắn cùng nguồn và DWG cuối. DXF được đọc độc lập một lần, kiểm mọi circle/mark, tâm, bán kính, owner, reactor và graph dependency. Một cặp sai làm toàn bộ job không được chấp nhận; nguồn không bị ghi đè và không cấp bản sửa thành công một phần.

## Bằng chứng CAD thực tế

Nguồn bản sao native-import: `51ec94944c4443b19fb8d5bd7930a6dd`, khung `3B3987`, SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.

| Phép thử | Kết quả | Job | DWG SHA-256 |
|---|---|---|---|
| Hai cặp, độ dịch riêng `[1.25,-0.75,0]` và `[1.375,-0.75,0]` | Đạt, 39.913 entry ngoài nhóm | 65a29ec94ad640ad876f7f6fab1f2b2f | 149f5f0716383cc399fa5068ff44396dcf49b2ce654d22dafc4e2a4c53d96202 |
| 11 cặp cùng độ dịch `[1.25,-0.75,0]` | Đạt, 39.895 entry ngoài nhóm | ee161e6da4a54b279c649d5b8c33a938 | 973ad4e4d8f33e8f4f94a5445cd9cd9604eda0bd4ac60904fe287fcc32f7dfe1 |

Inspection `2f40817354b24bccab4281b8eb0cd8ea`. Receipt/request/started ở `storage/validation-fixtures/centermark-batch-two-2026-10-21/` và `centermark-batch-eleven-2026-10-21/`. Từng job qua HTTP production, hash nguồn, native preflight, persisted state, evaluate ổn định và DXF độc lập. Cặp trùng trong request bị API chặn 422 ở cả hai lượt.

Probe đơn sau refactor vẫn đạt: `storage/validation-fixtures/native-center-probe-c0bf65bf/`, circle `3B7FF1`, mark `3B7FF2`, delta `[0.5,0.25,0]`, 39.915 entry ngoài cặp.

Kiểm chứng âm bên dưới API: cố ý dùng action `3B2DD8` cho cặp thứ hai. Job `eebb18c816dd4bd1bdfe4dfdb1a41391` bị native preflight từ chối đúng lỗi `CenterMark contract dependency/owner mismatch` trước bước dịch, không có result đã được chấp nhận, nguồn giữ nguyên. Receipt tại `storage/validation-fixtures/centermark-batch-rejection-2026-10-21/receipt.json`. API thông thường đã chặn dependency sai trước khi gọi host; phép thử này cố ý dùng job service nội bộ để kiểm lớp bảo vệ thứ hai, không mở endpoint bỏ qua API binding.

Plugin cuối build/check AutoCAD 2027 đạt, runtime key `0dc204ef4233ca2d0e03c6da02d4b7c41790b723f03433c0e5ef3b159f2ec244`. Bộ kiểm thử mục tiêu **167 bài đạt**, 12 giây, bao gồm DXF có cặp thứ hai sai và effect thiếu/trùng/sai số nhóm. Kiểm tra JavaScript native controls cũng đạt.

Hồi quy toàn dự án cuối lượt đạt **1.741 bài**, 2.723 warning thư viện, 256,03 giây. Log: `storage/validation-fixtures/pytest-centermark-batch-2026-10-21.txt`. `scripts/verify_native_centermark_artifacts.py` kiểm lại artifact hiện tại của hai job nhóm, hash commands/receipt/DWG và DXF độc lập: cả hai đạt. Receipt kiểm lại tại `storage/validation-fixtures/centermark-batch-eleven-2026-10-21/artifact-verification.json`.

## Giao diện và giới hạn

Danh sách CenterMark cho chọn nhiều cặp bằng Ctrl/Shift; mặc định chỉ chọn cặp đầu. Giao diện áp cùng độ dịch X/Y cho các cặp đã chọn, tối đa 16; API cho phép vector riêng từng cặp. Chặn chọn rỗng, quá giới hạn, số không hữu hạn, độ dịch bằng 0 và nguồn/phạm vi/provider cũ. Công cụ trình duyệt đang tắt nên chưa có kiểm tra trực quan form; logic DOM và luồng HTTP được kiểm riêng.

Đây là dịch nhóm các circle và dấu tâm liên kết, chưa phải dịch cả cụm cơ khí gồm các đường bao, lỗ, DIM, BOM hoặc chi tiết tiếp xúc. Vector thử không phải quyết định vị trí mới của sản phẩm. Không tạo revision khách, nguồn giữ nguyên; đề xuất tấm xốp tiếp tục chưa xác nhận.
