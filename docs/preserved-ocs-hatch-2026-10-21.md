# Giữ HATCH nghiêng khi sửa block — 21/10/2026

Cập nhật tiếp theo: [Bảo toàn HATCH liên kết nội bộ](preserved-hatch-associations-2026-10-21.md) bổ sung sao chép nguyên nhóm association không bị sửa, với ánh xạ biên/reactor kiểm chứng. Các giới hạn association trong các biên nhận dưới đây phản ánh thời điểm của từng lượt kiểm tra.

Đã mở rộng khả năng sửa các hình được hỗ trợ nằm cùng block với HATCH không liên kết có mặt phẳng nghiêng hoặc đảo pháp tuyến, cao độ khác 0 và đường bao polyline chứa bulge. Bổ sung đường bao cạnh thẳng/cung tròn/cung elip native, kiểm tra hướng cạnh và vòng kín. HATCH được giữ nguyên khi tạo block riêng; thay đổi này không cấp quyền co/giãn chính HATCH đó.

Bộ kiểm tra vùng nét đọc OCS và cao độ native, biến đổi đầy đủ các góc của vùng bao bulge trước khi xét frame của block. Không còn coi tọa độ OCS như tọa độ phẳng +Z. Thiếu dữ liệu mặt phẳng hoặc đường bao chưa hỗ trợ vẫn cần kiểm tra thêm.

Khi cô lập block, HATCH được sao chép bằng các tag gốc. HATCH có association, reactor, extension dictionary, tham chiếu biên hoặc gradient thực vẫn bị chặn. Bước xuất phạm vi có snapshot chỉ đọc riêng để đối chiếu đường bao, mặt phẳng, pattern và seed; snapshot sửa HATCH giữ nguyên giới hạn cũ. Bộ chuyển DWG có thể chuẩn hóa pháp tuyến và ghi gradient kind=0 cho solid fill; kiểm tra chấp nhận hai biểu diễn tương đương đó.

## Bằng chứng CAD

Lệnh `python scripts/verify_cuboid_projection.py --confirm-uncoded --ocs-hatch` đã đi qua đọc DWG, xác nhận trên fixture tổng hợp, lập kế hoạch, sửa, duyệt fixture, AutoCAD xuất, tải HTTP 200 và ODA mở lại.

- DIM nguồn 100 → 76 mm, BOM 2×80×100 → 2×80×76 mm.
- Hình hộp đích giữ đúng 9 LINE, camera trực giao và đỉnh đã chọn.
- Hai HATCH có pháp tuyến âm/nghiêng, cao độ 17 và bulge giữ nguyên đường bao, cao độ và hướng mặt sau mở lại.
- File gốc giữ hash.
- Receipt: `storage/validation-fixtures/cuboid-projection-2ebd7ae6/receipt.json`.
- DWG: `storage/validation-fixtures/cuboid-projection-2ebd7ae6/download/cuboid-backup.dwg`.
- SHA-256: `e926c4dfc56427342bbf180db7bc63bb9476b38d3dc395514ab7c09ff810f2d3`.

Ghi chú trong block hỗn hợp vẫn là 2×80×100 vì chưa có bằng chứng ghi chú thuộc riêng hình hộp. Receipt ghi rõ `projected_note_verified=false`, `unowned_parent_note_preserved=true`. Fixture này chứng minh sửa hình được hỗ trợ và bảo toàn nội dung lân cận, không chứng minh đồng bộ toàn bộ ghi chú của block hỗn hợp.

Các lần kiểm chứng đầu phát hiện lần lượt chặn clone, chặn snapshot khi xuất và phép kiểm ghi chú quá rộng; logs/artifact được giữ. Lần cuối kiểm tra đủ hai HATCH trong phạm vi xuất. HATCH ngoài phạm vi xuất vẫn bị lọc đúng theo phạm vi đã chọn.

## Kiểm thử

Ba trường hợp vùng bao HATCH kiểm bằng mẫu độc lập trên đường cong native với pháp tuyến +Z, −Z và (1,2,3), kết hợp quay/tịnh tiến block. Kiểm tra clone so sánh toàn bộ tag HATCH, giữ instance không chọn, từ chối association/tham chiếu biên và phát hiện sai cao độ sau sao chép.

337 bài của geometry, nesting, revisions và assembly đạt trong 65,90 giây. Kiểm tra bổ sung ba trường hợp clone với snapshot bảo toàn cuối cùng đạt. Log: `storage/validation-fixtures/pytest-ocs-hatch-export-2026-10-21.txt`.

Bộ kiểm thử toàn dự án đạt 1.654 bài trong 262,32 giây, log `storage/validation-fixtures/pytest-ocs-hatch-release-2026-10-21.txt`. Lượt toàn bộ này chạy với phần vùng bao/clone; các bổ sung snapshot xuất sau đó được kiểm tra tập trung và qua luồng DWG nói trên.

Audit lại Dauphine chỉ đọc: 9 bộ cạnh hoàn chỉnh, 3 hình có danh tính được chứng minh, chưa thêm binding thực thi từ kế hoạch hiện tại. Nguồn giữ hash `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`. Biên nhận `storage/validation-fixtures/cuboid-dauphine-ocs-hatch-audit-2026-10-21.json`.

Quyết định Dauphine vẫn chưa xác nhận; không lưu liên kết hoặc tạo revision khách từ đề xuất tấm xốp. Phối cảnh bị che, mặt lắp thiếu dữ liệu, proxy và các adapter còn thiếu vẫn chưa được giải quyết bởi thay đổi này.

## Đường bao cạnh cung tròn/elip

Lệnh `python scripts/verify_cuboid_projection.py --confirm-uncoded --edge-hatch` đã kiểm chứng thêm một vòng cung tròn + cạnh thẳng theo hướng ngược và một vòng elip theo hướng ngược, trên hai mặt phẳng đảo/nghiêng. Không chuyển thành polyline xấp xỉ. DIM/BOM và chín cạnh hình hộp đạt kích thước đích; hai HATCH giữ đường bao, pattern, seed và mặt phẳng sau AutoCAD xuất/ODA mở lại. Ghi chú chưa xác định chủ sở hữu vẫn giữ nguyên như fixture trước.

- Receipt: `storage/validation-fixtures/cuboid-projection-12eba21c/receipt.json`.
- DWG: `storage/validation-fixtures/cuboid-projection-12eba21c/download/cuboid-backup.dwg`.
- SHA-256: `99b3691758d08ae03a71a093dd6d90be9b0d62af93278c97ea0e4367660c783d`.
- 25 kiểm thử tập trung đạt: vòng polyline/cung/elip/hỗn hợp, association, liên kết biên, vòng hở, sao chép tag và cực trị OCS. Log `storage/validation-fixtures/pytest-hatch-analytic-paths-focused-2026-10-21.txt`.
- Registry version 21 để đọc lại metadata đường bao analytic.

Lượt bổ sung kiểm chứng cùng lệnh với HATCH elip dùng pattern ANSI31 góc 23°, tỷ lệ 0,75 và seed native. Receipt `storage/validation-fixtures/cuboid-projection-30726e7b/receipt.json`; DWG trong thư mục `download/` của fixture đó, SHA-256 `eac19d0eabab0b170316712bc31e4df773a5a96a2ff30a0ecdbd2030b1c3cc33`. Snapshot pattern/seed đạt sau xuất/mở lại, 25 kiểm thử tập trung cuối đạt (`pytest-hatch-analytic-paths-pattern-2026-10-21.txt`).

Audit HATCH Dauphine chỉ đọc ghi nhận 449 đối tượng trong các definition: 434 đủ điều kiện adapter sao chép riêng, 15 còn association. Các đường bao thực tế gồm polyline và cạnh LINE; không lấy fixture cung/elip làm bằng chứng rằng file này có các dạng đó. Số đối tượng không phải số instance và không chứng minh toàn bộ block chứa chúng đủ điều kiện cô lập. Biên nhận `storage/validation-fixtures/hatch-preservation-dauphine-2026-10-21.json`; chạy lại bằng `python scripts/audit_hatch_preservation.py DOCUMENT_ID --output OUTPUT_JSON`.

15 HATCH association có 96 tham chiếu biên: đều tồn tại, cùng owner với HATCH và có reactor ngược. Đây là bằng chứng để phát triển adapter association tiếp theo, chưa được dùng để cho phép clone hoặc chỉnh sửa các đối tượng đó.

Release đường bao analytic: **1.673 bài toàn dự án đạt**, 249,82 giây, log `storage/validation-fixtures/pytest-hatch-analytic-paths-release-2026-10-21.txt`. Fixture pattern bổ sung được chạy riêng 25 bài đạt; tối ưu tránh lặp metadata polyline được kiểm tra riêng 9 bài OCS đạt (`pytest-hatch-metadata-final-2026-10-21.txt`). Backend đã nạp registry 21.
