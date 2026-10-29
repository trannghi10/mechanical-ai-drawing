# Tích hợp native reference vào revision/undo — 22/10/2026

Cập nhật tiếp theo: [scope lấy từ bằng chứng và sửa trạng thái review](native-scope-release-2026-10-22.md). Revision mới đang chọn là `c76cb7153bc140b2bd75f95098014841`; các ID và giới hạn khóa file dưới đây mô tả bản triển khai trước đó.

## Thay đổi

Proposal schema 2 hỗ trợ `adapter=native_pointrefs` và một revision legacy nền đã ready. Proposal khóa hash DWG/DXF nền, báo cáo native và DLL. Backend chỉ cho chạy khi revision nền đúng đang được chọn; kiểm lại source, scope, base và DLL trước/sau thực thi. Phạm vi v1 vẫn khóa vào file/nhóm đã kiểm chứng, không mở rộng tùy ý sang DWG khác.

Worker chạy mới adapter trên bản sao revision nền, kiểm inventory, đồ họa sáu DIM, bốn liên kết legacy, hai DIM hybrid A/B; sau đó chạy tám phép kéo A/B ±10 mm và bốn phép native B độc lập. Chỉ sau khi đủ bằng chứng mới sao chép DWG/DXF, lưu hash evidence và thêm revision vào history. Lỗi giữ nguyên lựa chọn trước đó. Undo/redo dùng version và kiểm hash artifact; không ghi đè nguồn hoặc xóa revision.

Giao diện xem xét liên kết có nút lập proposal native từ revision legacy đang chọn; hiển thị kết quả kiểm native sau khi ready. Không đánh dấu ý đồ cơ khí đã xác nhận. Mọi file vẫn là bản sửa để kiểm tra, chưa phải backup đầy đủ sản phẩm.

PostgreSQL index nhận `validation.output_sha256` và file `modified.dwg` ngay tại thư mục revision, giữ loại `dwg_preview` khi chưa phát hành.

## Phục hồi PostgreSQL

PostgreSQL 18 từng báo recovery, không nhận kết nối trong khi postmaster cũ giữ cổng 5432. Không có standby/recovery signal. Dừng bằng dịch vụ và `pg_ctl fast` không hoàn tất. Sau quyền quản trị UAC, `pg_ctl immediate` dừng được postmaster; dịch vụ được mở lại, nhận kết nối và `SELECT pg_is_in_recovery()` trả false. Không reset/xóa WAL, không initdb, không đổi thông tin đăng nhập hoặc tự chuyển SQLite. Đây là phục hồi vận hành; chưa xác định nguyên nhân sâu của lần treo.

Đã chạy lại `setup_postgres.py index` để đồng bộ receipt đã lưu trong lúc database không khả dụng. Bằng chứng: `storage/validation-fixtures/native-revision-release-2026-10-22/postgres-recovery.json`. Kiểm AutoCAD chuẩn đã đạt lại, runtime key `ba4516dd9a184aad977c0ef16f2cab4510813e8ee1912593a21973faaccc6963`.

## Bằng chứng phát hành

Các receipt chạy HTTP, undo/redo, hash download, metadata PostgreSQL và restart được lưu tại `storage/validation-fixtures/native-revision-release-2026-10-22`. Kiểm giao diện dùng DOM harness; chưa thực hiện QA bằng trình duyệt thật trong phiên này.

- Proposal HTTP `201`: `ed3436e2cda244f6bb75bd29334a50da`.
- Apply HTTP `202`, revision `f1e25b7472f64ce2b64571d5687909df` đã `ready`, đang được chọn. Toàn bộ 12 challenge chạy mới trong worker đạt, có 8 kiểm A/B và 4 kiểm native B riêng sau save/reopen.
- 54 thành phần đồ họa DIM, 39.896 đối tượng inventory ngoài phạm vi và 15 đối tượng ngoài nhóm được đối chiếu; bốn DIM legacy giữ đủ hai liên kết.
- Download HTTP của DWG/DXF khớp hash receipt; preview SVG thành công. DWG SHA-256 `33e646c813b8ffbe8797fbb98276b232b6b8eee439ed93825131aefa75e6c212`.
- Undo về `fc3037b7d2bc4588ad3c0df9b15e2494`, redo về native revision; version cũ và apply khi sai active base đều bị từ chối `422`. History version cuối 11, cursor 2. Kiểm lại sau backend restart giữ nguyên revision ready và hash DWG.
- PostgreSQL đã lưu revision ready, output hash và đường dẫn DWG kiểu `dwg_preview`. `pg_is_in_recovery=false`. Nguồn SHA-256 vẫn `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.
- Toàn bộ lần chạy Python đạt **1.920 test**, 2.737 cảnh báo deprecation, 653,53 giây. Hai test proposal và một test database được thêm sau lúc full-suite collection; đã chạy riêng cùng nhóm tương ứng, đạt 8 test proposal và 6 test database. Không cộng chồng các nhóm thành tổng mới.
- 10 script kiểm frontend đạt, gồm DOM harness cho proposal native từ base revision, apply/undo/redo/error.
