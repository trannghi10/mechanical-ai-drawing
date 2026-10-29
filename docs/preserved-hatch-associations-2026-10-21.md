# Bảo toàn HATCH liên kết nội bộ — 21/10/2026

Cập nhật tiếp theo: [Bảo toàn HATCH cùng DIMASSOC](preserved-hatch-dimassoc-2026-10-21.md) xử lý thêm bốn trường hợp từng bị chặn ở audit dưới đây, bằng cách giữ cả DIM và các đối tượng sở hữu không thay đổi. Các nhóm LEADER/chú thích khác vẫn cần adapter riêng.

Đã bổ sung adapter sao chép nguyên nhóm HATCH–biên–reactor trong một block khi sửa đối tượng độc lập khác. Engine giữ association thay vì tháo liên kết. Chưa hỗ trợ đổi chính HATCH hoặc hình/chữ làm biên của nhóm đó.

## Điều kiện kiểm tra

- Mọi đường bao phải có tham chiếu nguồn, tồn tại cùng owner và thuộc LINE/LWPOLYLINE/CIRCLE/ARC/ELLIPSE/TEXT/MTEXT được hỗ trợ bảo toàn.
- Reactor ngược trên mỗi biên phải khớp đầy đủ các HATCH liên kết đã đọc. Reactor khác, extension dictionary, gradient hoặc dữ liệu ngoài chưa có adapter vẫn bị chặn.
- Đường bao native phải được đọc và kiểm tra vòng kín. Liên kết nguồn không tự chứng minh yêu cầu thiết kế hoặc cho phép đổi kích thước biên.
- Không thao tác nào của kế hoạch được sửa thành viên của nhóm. Clone đổi cả handle biên và reactor sang definition mới, kiểm tra lại nhóm sau ghi và khi xuất phạm vi.
- Đối chiếu cả ánh xạ handle cụ thể: trỏ vào một đường bao khác dù cùng hình học cũng không đạt.
- Snapshot bảo toàn là dữ liệu chỉ đọc. Adapter chỉnh sửa HATCH và kiểm tra capability vẫn giữ các giới hạn cũ.

Mã: `cad/hatch_association.py`, `cad/block_isolation.py`, `cad/nested_scope_export.py`. Metadata HATCH đọc cả edge path sau chuyển DWG; registry version 22. Bộ chuyển có thể đổi đường bao polyline liên kết thành edge path, nên kiểm tra dựa trên CAD nguồn đã nhập vào dự án.

## Kiểm chứng DWG

Lệnh `python scripts/verify_cuboid_projection.py --confirm-uncoded --associated-hatch` chạy qua website đọc ứng viên, xác nhận trên fixture tổng hợp, sửa, xem trước, duyệt fixture, AutoCAD xuất, tải HTTP 200 và ODA mở lại.

- DIM 100 → 76 mm; BOM 2×80×100 → 2×80×76 mm.
- Hình hộp giữ đủ 9 LINE, camera và đỉnh nguồn đã chọn.
- Ba HATCH lân cận được giữ. Một HATCH có biên ngoài LWPOLYLINE và vùng chừa MTEXT, cả hai còn đúng association sau clone/xuất.
- Kiểm tra đường bao, mặt phẳng, seed, handle đích và reactor ngược sau mở lại. File gốc giữ hash.
- Ghi chú chưa xác định chủ sở hữu trong block hỗn hợp được giữ nguyên; `projected_note_verified=false`. Đây chưa phải bằng chứng đồng bộ mọi ghi chú hay toàn sản phẩm.
- Receipt: `storage/validation-fixtures/cuboid-projection-96087b33/receipt.json`.
- DWG: `storage/validation-fixtures/cuboid-projection-96087b33/download/cuboid-backup.dwg`.
- SHA-256: `4c9e84188c6476e8fceb4f0af1b1efb51dc8bc89c60c732a438f79b44f44d5b0`.

Lượt fixture trước chỉ có đường bao ngoài đạt tại `cuboid-projection-ce23f1ee/receipt.json`. Lượt đối chiếu đầu tiên phát hiện AutoCAD thêm seed trong bước nhập DWG; verifier đã sửa để đối chiếu đúng nguồn CAD đã nhập, không bỏ qua seed. Bước thêm MTEXT phát hiện edge path sau chuyển DWG chưa được đưa vào metadata chỉ đọc; đã bổ sung và có bài hồi quy riêng.

## Audit Dauphine

Audit chỉ đọc `storage/validation-fixtures/hatch-association-dauphine-2026-10-21.json` giữ hash nguồn `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

Trong 15 HATCH association, 11 đối tượng đủ điều kiện kiểm tra nguyên nhóm nội bộ. Bốn đối tượng trong một definition còn biên liên kết với DIMASSOC; chưa sao chép nhóm đó. Số liệu là coverage adapter, không chứng minh block chứa chúng không có liên kết khác hoặc toàn sản phẩm đã sửa xong. Chưa áp dụng thay đổi lên khách từ audit này.

Đề xuất tấm xốp Dauphine tiếp tục chưa xác nhận theo lựa chọn người dùng. Không lưu danh tính/mốc giữ và không tạo revision khách từ đề xuất đó.

## Kiểm thử

Lượt toàn dự án đạt **1.679 bài**, 251,14 giây (`pytest-hatch-association-release-2026-10-21.txt`). Sau bổ sung biên TEXT/MTEXT và metadata edge path có association, chạy lại toàn bộ nhóm geometry/assembly/revisions/nesting: **375 bài đạt**, 62,70 giây (`pytest-hatch-association-final-2026-10-21.txt`). Các log nằm trong `storage/validation-fixtures/`.

18 trường hợp nhóm liên kết kiểm tra biên circle/TEXT/MTEXT, tham chiếu mất, biên khác owner, reactor không khớp, sửa biên/HATCH và trỏ nhầm biên cùng hình học. Bài metadata riêng chứng minh đọc vùng bao HATCH có association không cấp quyền chỉnh sửa. Luồng DWG MTEXT cuối dùng cùng adapter cuối đã kiểm thử.
