# Scope native lấy từ bằng chứng — 22/10/2026

Đã bỏ khóa hash DWG/revision cụ thể trong adapter và bỏ chọn hai DIM theo handle cố định ở nhánh native point-reference. Proposal schema 3 có `execution_scope`, được suy lại từ inspection nguồn, cây native và DXF của revision legacy nền mỗi lần đọc. Scope khóa polyline, sáu DIM, hai cặp vertex, action/body/dependency và tọa độ; hash source/base/DLL tiếp tục được kiểm.

Phạm vi hình học vẫn là polyline kín tám vertex, bulge bằng 0, normal Z, bốn DIM legacy đủ hai đầu và hai DIM native có B được chứng minh. Cạnh đo phải dài hơn 20 mm và song song trục DIM. Không suy diễn quan hệ cơ khí chưa được xác nhận. Chưa kiểm đầu-cuối trên một DWG độc lập có topology khác; việc tổng quát hóa mã không phải bằng chứng sửa mọi DWG.

Writer managed và bộ thử A/B nhận handle/vertex từ scope; vector kéo ±10 mm được tính theo span thực tế. Finalizer kiểm chính scope đó. Bộ so sánh OLE/tolerance lấy danh sách đối tượng có thật trong inventory, không đọc danh sách 15 handle từ fixture cũ.

Đã sửa giao diện: mở proposal tự điền thông tin nguồn; báo đang tải; history trả trạng thái revision đang kiểm; khóa apply/undo/redo khi có job pending và tự refresh; tránh response history cũ ghi đè lựa chọn mới; khóa apply native khi không chọn revision nền đúng, kể cả sau khi apply hoàn tất. Revision ready có mô tả đúng trạng thái đã thực thi. Kiểm thực tế bằng trình duyệt xác nhận thông tin nguồn, hai hàng DIM, preview, revision mới và nút apply bị khóa đúng; không thao tác nút tạo job thêm trên trình duyệt.

## Kiểm chứng

- Plugin build/check đạt; runtime key `ca46283bc0381b92064208ad83636d1afa1daa7ef91a803618b1a26f043ec7e7`.
- 39 test Python tập trung đạt, 9 cảnh báo deprecation; có ca handle/vertex khác mẫu, hướng đo đảo chiều, source/revision hash mới, thiếu bằng chứng, trùng dependency và out-of-scope. Không chạy lại full suite trong lượt này; kết quả 1.920 test ở lượt trước không được coi là full-suite của thay đổi mới.
- Sau đó thêm một test migration: proposal native schema 2 vẫn xem được nhưng apply bị chặn trước khi tạo job; nhóm revision/scope 21 test đạt lại. HTTP thực xác nhận trả 422 với hướng dẫn lập lại proposal. Không cộng các lượt có test trùng nhau thành tổng full-suite.
- 10 script frontend đạt, gồm pending-lock, restore fields và wrong-base lock.
- Proposal schema 3 `d25ca4481a514802893ee29d2f4dfa42`; revision mới `c76cb7153bc140b2bd75f95098014841` đã ready và đang được chọn.
- Worker chạy mới đủ 8 phép kéo A/B và 4 phép kiểm riêng native B sau save/reopen. 54 thành phần đồ họa DIM giữ nguyên; 39.896 đối tượng ngoài phạm vi đạt inventory audit; 15 OLE/tolerance được đối chiếu theo inventory thực tế. Bốn liên kết legacy được giữ.
- HTTP download DWG/DXF khớp hash, undo/redo và stale-version rejection đạt. PostgreSQL còn hoạt động, `pg_is_in_recovery=false`, metadata revision/hash đúng.
- DWG output SHA-256 `cc0b48deece01f5bd64f8cf82711b1a977a6c478b50f75d135c6b97aa4ae47a8`. 61 artifact revision đều khớp hash. Nguồn vẫn `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`. Các bản sửa trước vẫn giữ trên đĩa.

Bằng chứng ở `storage/validation-fixtures/native-scope-release-2026-10-22`. Bản DWG mới ở `storage/documents/51ec94944c4443b19fb8d5bd7930a6dd/revisions/c76cb7153bc140b2bd75f95098014841/modified.dwg`.
