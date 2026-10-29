# Bộ kiểm thử dự án

Probe polyline–sáu DIM: **310 bài liên quan đạt**, 223 warning, 41,64 giây. Hai phép dịch cứng CAD thật giữ point binding, measurement, chữ và 54 primitive hiển thị; 39.856 inventory ngoài phạm vi khớp. Tham khảo `docs/polyline-six-dim-translation-probe-2026-10-21.md`; chưa có action production/stretch cho nhóm này.

DIMASSOC nested perpendicular: **1.755 bài hồi quy đạt**, 2.723 warning, 250,28 giây; log `storage/validation-fixtures/pytest-nested-perpendicular-final-2026-10-21.txt`. Mẫu mm đổi 90,5 → 95 và mẫu thêm dịch anchor Y−2 đều xuất/mở lại DWG đạt, giữ snap 8/last point, đúng chữ DIM và source binding. Đọc được bốn DIMASSOC thực tế; toàn nhóm sáu DIM vẫn native_required. Xem `docs/dimassoc-perpendicular-2026-10-21.md`.

Native topology inventory: **171 bài liên quan đạt**, 12,59 giây; plugin build/check đạt. Nhóm hai CenterMark qua CAD với snapshot thêm reactor/dictionary handles. Audit 39.917 entity khớp tập reactor; 10 khác biệt dictionary ACAD_TABLE được giữ nguyên trong báo cáo. Polyline+sáu DIM chưa được mở sửa vì một DIMASSOC thiếu/thừa point reference. Xem `docs/native-topology-inventory-2026-10-21.md`.

Hồi quy sau refactor dịch nhóm CenterMark: **1.741 bài đạt**, 2.723 warning, 256,03 giây; log `storage/validation-fixtures/pytest-centermark-batch-2026-10-21.txt`. CAD thật: nhóm 2 cặp khác vector và nhóm 11 cặp chung vector đạt, native preflight chặn cặp thứ hai sai action trước dịch, probe đơn hồi quy đạt. Kiểm lại artifact nhóm và harness JavaScript chọn nhiều cặp cũng đạt. Bằng chứng: `docs/native-centermark-batch-2026-10-21.md`.

Native action dependencies: **160 bài CenterMark/export jobs đạt**, 11,64 giây; plugin cuối build/check AutoCAD 2027 đạt. Inspector đọc GetDependencies có giới hạn, nhận 38 node/81 cạnh ở mẫu ba ARC/năm mark và chứng minh năm nguồn thực là CIRCLE. Một cặp mới và hồi quy HTTP tự tìm đều xuất/mở lại CAD đạt. Xem `docs/native-action-dependencies-2026-10-21.md`.

Kiểm chứng CAD thêm **9/9 cặp CenterMark** trong khung Dauphine: từng job dịch riêng qua HTTP production, lưu/mở lại DWG, đối chiếu 39.915 entry ngoài mục tiêu và DXF độc lập. Kiểm lại artifact hiện tại cũng đạt 9/9; tổng cộng 11 cặp của cùng khung có bằng chứng. Xem `docs/centermark-population-2026-10-21.md` và `storage/validation-fixtures/centermark-population-2026-10-21/artifact-verification.json`. Đây không phải kiểm chứng dịch cả cụm sản phẩm.

CenterMark HTTP trên bản sao Dauphine nhập native đã đạt: selection/context, inspection dependency, chặn tâm sai 422, sửa đúng 202 và DWG save/readback + DXF verification. Bộ startup/CenterMark/export jobs đạt **163 bài**, 18,26 giây. Console registry bị sandbox chặn được nhận diện riêng; xem `docs/native-centermark-production-2026-10-21.md` và `storage/validation-fixtures/native-centermark-http-2026-10-21/receipt.json`.

Hồi quy sau tích hợp CenterMark production: **1.722 bài đạt**, 2.723 warning, 255,34 giây; log `storage/validation-fixtures/pytest-centermark-production-2026-10-21.txt`. Bộ CenterMark bổ sung đọc DXF độc lập đạt riêng **16 bài**. Hai job CAD dương và một job action sai bị chặn có receipt trong `docs/native-centermark-production-2026-10-21.md`.

Action CenterMark production 21/10/2026: hai job trên bản sao thực tế qua host MECHANICALCAD và bộ nhận kết quả chuẩn, kiểm persisted state trước evaluate, 39.915 entry ngoài mục tiêu và DXF độc lập. Native preflight chặn action của cặp khác trước dịch. Kiểm thử mục tiêu đầu lượt đạt **155 bài**; bằng chứng và giới hạn tại `docs/native-centermark-production-2026-10-21.md`.

Probe dịch CenterMark 21/10/2026: **140 bài export/native jobs đạt**, 10,38 giây; plugin build/check AutoCAD 2027 đạt. Hai cặp thực tế được dịch trên bản sao, xuất/mở lại DWG, evaluate lần hai và đọc DXF độc lập; 39.915 entry inventory ngoài cặp mục tiêu được đối chiếu. Trường hợp không có dependency bị chặn. Chưa thêm action dịch production. Xem `docs/native-centermark-translation-probe-2026-10-21.md`.

Kiểm kê dependency native 21/10/2026: **140 bài export/native jobs đạt**, 11,95 giây. Plugin cuối build/check trên AutoCAD 2027 đạt; audit Detail C nhận 17 node/35 liên kết CenterMark, kiểm tra path sai/handle mất trả partial đúng. Đây là dữ liệu chỉ đọc, chưa thêm quyền sửa geometry/association. Xem `docs/native-centermark-dependencies-2026-10-21.md`.

Đề xuất khe hở Detail C 21/10/2026: **157 bài geometry đạt**, gồm chín bài mới cho solver hình học chỉ đọc. Audit production đo khe kê 0,5 → 1 mm nếu hộp đứng yên; phương án giữ hai khe còn làm hở tiếp xúc đường tròn khoảng 0,576 mm nếu không dịch cả nhóm. Chưa nối apply/export, chưa tạo DWG khách từ đề xuất. Xem `docs/detail-c-clearance-proposal-2026-10-21.md`; log `storage/validation-fixtures/pytest-clipped-fit-geometry-2026-10-21.txt`.

Bảo toàn nhóm HATCH + DIMASSOC 21/10/2026: **1.697 bài toàn dự án đạt**, 244,49 giây; 39 bài HATCH tập trung đạt. DWG tổng hợp qua website, AutoCAD xuất và ODA mở lại giữ đúng dictionary, DIMASSOC, điểm đo và liên kết HATCH/biên/reactor. Adapter chỉ bảo toàn nhóm không bị sửa. Audit nguồn phân biệt definition với instance: nhóm bốn DIMASSOC trong Dauphine hiện không có INSERT/ACAD_TABLE tham chiếu. Xem `docs/preserved-hatch-dimassoc-2026-10-21.md`.

Bảo toàn nhóm HATCH association 21/10/2026: **1.679 bài toàn dự án đạt**, 251,14 giây; sau bổ sung biên TEXT/MTEXT và metadata association, **375 bài thuộc nhóm bị ảnh hưởng đạt**, 62,70 giây. DWG tổng hợp giữ đúng ánh xạ biên LWPOLYLINE + vùng chừa MTEXT, reactor ngược qua AutoCAD xuất/ODA mở lại. Audit thực tế 11/15 HATCH association phù hợp adapter bảo toàn nhóm không bị sửa; 4 còn DIMASSOC. Xem `docs/preserved-hatch-associations-2026-10-21.md`.

Bảo toàn HATCH analytic 21/10/2026: **1.673 bài toàn dự án đạt**, 249,82 giây. Kiểm chứng DWG cung tròn/cạnh thẳng và elip ngược trên mặt nghiêng, gồm pattern ANSI31/seed, qua AutoCAD xuất và ODA mở lại. 25 bài tập trung cuối và 9 bài metadata OCS đạt. Association vẫn bị chặn; audit Dauphine không sửa nguồn. Xem `docs/preserved-ocs-hatch-2026-10-21.md`; log `storage/validation-fixtures/pytest-hatch-analytic-paths-release-2026-10-21.txt`.

Gắn hình hộp có xác nhận 21/10/2026: **1.648 bài Python toàn bộ đạt**, 250,19 giây; 24 bài tập trung và tám script frontend đạt. Luồng ứng viên → xác nhận đúng file/DIM/hình/mốc → sửa → AutoCAD xuất/tải/mở lại đạt trên DWG tổng hợp chưa có mã ở hình đích. Bổ sung kiểm tra kế hoạch sau xóa liên kết, bỏ khung, nét nối, cực trị cung elip và OCS HATCH. Đề xuất tấm xốp Dauphine chưa được người dùng xác nhận nên chưa tạo revision khách. Xem `docs/confirmed-cuboid-links-2026-10-21.md`; log `storage/validation-fixtures/pytest-cuboid-links-release-full-2026-10-21.txt`.

Hình hộp chiếu trực giao 20/10/2026: **1.642 bài Python toàn bộ đạt**, 236,88 giây; 21 bài tập trung và bảy script frontend đạt. DWG mới 2×80×100 → 2×80×76 mm qua website/AutoCAD/tải/mở lại; đủ 9 cạnh, DIM, BOM và ghi chú giữ đúng. Audit nguồn thực tế nhận thêm hai hình đóng gói có STT/BOM; chưa có thêm thao tác trên Dauphine. Part Map đã đọc đúng các trang trong bộ số tờ. Xem `docs/metric-cuboid-projections-2026-10-20.md`; log `storage/validation-fixtures/pytest-cuboid-release-full-2026-10-20.txt`.

Mặt cong ARC/CIRCLE 20/10/2026: **1.622 bài Python toàn bộ đạt**, 254,22 giây; 16 bài tập trung và hai bài bổ sung thay tâm/bán kính lỗ chạy riêng đạt. DWG mới phản chiếu/xoay/tỷ lệ qua website, AutoCAD xuất và ODA mở lại; giữ ARC/CIRCLE native, BOM/ghi chú đồng bộ. Audit Dauphine chưa thêm liên kết đủ điều kiện. Xem `docs/circular-face-copies-2026-10-20.md`; log `storage/validation-fixtures/pytest-circular-projection-2026-10-20.txt`.

Mặt cong chiếu thành elip 20/10/2026: **1.596 bài Python toàn bộ đạt**, 240,01 giây; 14 bài tập trung đạt, giữ 19 module. Log `storage/validation-fixtures/pytest-curved-projection-final-2026-10-20.txt`. Kiểm tra toàn biên/cung/lỗ, phản chiếu, mã sai, mất/thêm nét, phép gắn mơ hồ, geometry trước sai, đổi Z, lỗ sau sửa không vừa, instance bị bỏ và mô tả khác mã. Hai DWG tổng hợp mới qua upload/sửa/duyệt/AutoCAD xuất/tải/ODA mở lại; lượt cuối đồng bộ cả ghi chú. Bảy script frontend đạt. Kết quả không thay thế nghiệm thu phối cảnh C4/mặt lắp/đóng gói Dauphine. Xem `docs/analytic-curved-projections-2026-10-20.md` và receipts trong `storage/validation-fixtures/curved-projection-089795f2/`.

Khung bao công đoạn và hình cạnh C4 20/10/2026: **1.582 bài Python toàn bộ đạt**, 226,64 giây; 33 bài tập trung sau tối ưu và bảy script frontend đạt; giữ 19 module. Kiểm tra đọc mới BOM nhiều thành viên, bảo toàn hash đồ thị, khung native không mang mã, sáu mặt nguồn, nét xiên/mặt thiếu, chữ căn giữa và đầu leader; bao hình học loại nét ngoài vùng nhưng không bỏ sót bulge. Log `storage/validation-fixtures/pytest-c4-stage-release-2026-10-20.txt`. DWG Dauphine thực tế qua revision/xuất AutoCAD/tải/mở lại; hình cạnh 695 mm, tấm giữa 1 mm, 96 thao tác hình cạnh được đối chiếu. Chưa nghiệm thu toàn sản phẩm hoặc mọi DWG. Xem `docs/c4-stage-links-2026-10-20.md`.

Chi tiết cong và mặt bằng nét rời 20/10/2026: **1.559 bài Python toàn bộ đạt**, 216,01 giây, vẫn 19 module. Thêm nhận thân cong qua STT/BOM, khớp toàn bộ body có/không có DIM, biên LINE/POLYLINE, mặt không/một lỗ với phép đối chiếu duy nhất, hai mặt dùng chung LINE với kiểm tra mép ghép; giữ các gate mâu thuẫn/mất bằng chứng. Log `storage/validation-fixtures/pytest-curved-split-final-2026-10-20.txt`. Ba DWG mới qua upload/xuất/tải/ODA đo lại; hai mặt đã duyệt backup. Audit thật nhận thêm sáu block cong nhưng chưa tạo thêm phép chiếu thực thi trên Dauphine. Xem `docs/curved-split-projections-2026-10-20.md`.

Liên kết mặt lắp STT/BOM 20/10/2026: **1.534 bài Python toàn bộ đạt**, 212,46 giây, vẫn 19 module. Thêm thân block ẩn danh theo local BOM/leader, receiver không có DIM chỉ được dịch chuyển, cụm xoay, từ chối thiếu chủ sở hữu/nét lạ/lỗ ngoài/DIM chưa gắn/mã mâu thuẫn và thao tác mũi tên sai; sửa cờ anonymous khi clone có tên mới. Log `storage/validation-fixtures/pytest-leader-mount-release-2026-10-20.txt`. DWG mới đã qua website/duyệt/AutoCAD/tải/mở lại và đo hình/BOM 80/100 mm, DIM tổng 180 mm. Audit Dauphine nhận thêm ba thân nhưng chưa có tiếp xúc đủ chứng minh; không nghiệm thu toàn Dauphine hoặc mọi DWG. Xem `docs/assembly-mount-validation-2026-10-20.md`.

Kiểm chứng APS thật 20/10/2026: **235 bài liên quan đạt**, 30,50 giây, bảy script frontend đạt, vẫn 19 module. Thêm kiểm tra Activity command/dependency/script, bằng chứng smoke gắn cấu hình/bundle/hash và từ chối CAD khách trong lệnh smoke. Log `storage/validation-fixtures/aps-live-2026-10-20/pytest-final.txt`. Model Derivative và ba workitem AutoCAD đã chạy thật trên DWG tổng hợp, website tải HTTP 200, ODA mở lại đo hình/DIM 80 mm. Xem `docs/aps-migration.md`; không chứng nhận backup Dauphine hoặc mọi DWG.

Kiểm chứng tiếp theo 20/10/2026: **1.477 trường hợp đạt**, 230,81 giây, vẫn 19 module; bảy script frontend đạt. Thêm nhiều mặt trong một block, kiểm tra mép chung/DIM/lỗ và quyền đồng bộ toàn root; giữ khe hở nguồn theo yêu cầu rõ ràng, chặn thiếu mốc/DIM mâu thuẫn/vật tư xen giữa; đệm khác bề rộng, HATCH/DIM đúng mặt phẳng và tiếp xúc. Sáu bài cuối về mặt phẳng/DIM/báo cáo đạt sau bổ sung assert. Logs `pytest-multiface-final-2026-10-20.txt`, `pytest-multiface-coplanar-final-2026-10-20.txt`, `frontend-multiface-2026-10-20.txt`. Hai DWG tổng hợp qua website/AutoCAD/tải/mở lại: receipts `projected-face-9ea9e883/` và `mount-gap-4d35f8e2/`. Audit thực tế `multiface-customer-audit-2026-10-20.json` vẫn chưa có thêm cặp mặt tương ứng trên MR-106/Dauphine; chưa nghiệm thu mọi DWG hoặc toàn sản phẩm.

Kiểm chứng 20/10/2026: **1.443 trường hợp đạt**, 197,60 giây, giữ 19 module; bảy script frontend đạt. Bổ sung mặt phẳng vẽ nghiêng (đỉnh + tròn/elip, mã native hoặc STT/leader/BOM, DIM theo tỷ lệ thật), chặn thiếu/sai/mơ hồ, giữ bản nguồn; mũi tên mặt lắp LINE/LEADER và cụm xoay; trường cao thùng L×W×H có các số bằng nhau. Chạy lại 34 bài tập trung sau cập nhật báo cáo mặt. Log `pytest-planar-projections-release-2026-10-20.txt`, `pytest-planar-projections-final-focused-2026-10-20.txt`. Hai DWG mới qua upload → AutoCAD → tải → mở lại; receipts trong `projected-face-65db4b46/`, `projected-face-0ad94901/`. Là dữ liệu tổng hợp, chưa nghiệm thu mọi DWG; kiểm tra trên MR-106/Dauphine không tìm được cặp mặt tương ứng theo adapter mới.

Kiểm chứng 20/10/2026: **1.409 trường hợp đạt**, 197,40 giây, giữ 19 module; bảy script frontend đạt. Bổ sung STT cụm 7/07 trong đúng BOM, va chạm số cục bộ, nhiều hình chi tiết đệm xoay/phóng, hình bằng đặt phía dưới, DIM thùng sai đầu đo, HATCH thân/nắp và block clone cùng mã (giữ pattern riêng/instance ngoài). Log `storage/validation-fixtures/pytest-packaging-release-2026-10-20.txt`. Revision Dauphine thật `4e64546e…` đã xuất AutoCAD/tải HTTP 200/mở lại; receipt trong `packaging-backup/4e64546ecf13482e866cd6556eee5e9a/`. Vẫn là preview một phần, không chứng nhận toàn sản phẩm hoặc mọi DWG.

Kiểm chứng tiếp theo 20/10/2026: **1.392 trường hợp đạt**, 242,76 giây, 19 module; bảy script frontend đạt. Bổ sung khung không có nhãn hàng, STT 07/7, ranh giới khung chồng/loại bỏ, chuỗi BOM/leader/DIM tự đọc từ CAD và reset phạm vi khi đổi file. Log `storage/validation-fixtures/pytest-frame-callouts-full-2026-10-20.txt`, `frontend-frame-callouts-2026-10-20.txt`. Đã chạy thêm trên DWG MR-106/Dauphine thực tế và thao tác nhập lại AutoCAD/sửa/tải/mở lại MR-106 qua website; receipt trong `mr106-native-frame-callouts-2026-10-20/receipt.json`. Kết quả vẫn là preview một phần, không chứng nhận mọi DWG hoặc toàn bộ cụm.

Kiểm chứng tiếp theo 20/10/2026: **1.384 trường hợp đạt**, 187,79 giây, giữ 19 module. Bổ sung nhiều hình của tấm, clone xoay/tỷ lệ, lỗ bậc với hệ số DIM, thiếu mapping/hình nhận và gán nhầm block giống hình khác mã. Log `storage/validation-fixtures/pytest-plate-linked-views-full-2026-10-20.txt`. Hai DWG tổng hợp đa khung đã tải/mở lại đo đúng; thêm cụm tiếp xúc thật A/B qua duyệt và xuất DWG. Chi tiết và receipt trong `docs/linear-intent-validation.md`; không thay thế nghiệm thu mọi DWG hoặc toàn Dauphine.

Kiểm chứng 20/10/2026: **1.361 trường hợp đạt**, giữ 19 module; 186,07 giây. Bổ sung chọn khung chi tiết có BOM ở khung khác, đối chiếu đúng occurrence nguồn và chặn mượn BOM khi sai bảng/STT/mô tả/khung/chủ sở hữu. Nhóm liên quan đạt 305 bài. Log `storage/validation-fixtures/pytest-detail-bom-full-2026-10-20.txt`. Hai DWG tổng hợp mới qua upload → sửa → xuất/tải → mở lại đo đạt; receipt `storage/validation-fixtures/plate-intent-84b9b887/receipts.json`. Đây chưa phải nghiệm thu mọi DWG hoặc toàn bộ sản phẩm.

PostgreSQL 16/10/2026: **1.090 trường hợp đạt**, vẫn 19 module kiểm thử. Bổ sung schema dùng chung, JSONB/parameter binding, index revision/file, phân biệt preview và backup, che credential khi lỗi và giữ local receipt khi index database lỗi. `conftest.py` cô lập toàn bộ pytest khỏi database thật. Smoke test PostgreSQL riêng đạt và rollback dữ liệu thử. Log `storage/validation-fixtures/pytest-postgresql-2026-10-16.txt` (166,65 giây).

Kiểm chứng mới nhất 16/10/2026: **1.085 trường hợp đạt**, vẫn 19 file Python. Bao gồm APS upload/native import, nguồn/owner/hash, idempotency, resume sau restart, bảo vệ lệnh native, tải artifact, metadata lỗi không mất CAD và giải phóng khóa khi chờ cloud. Log: `storage/validation-fixtures/pytest-aps-native-final-2026-10-16.txt` (153,72 giây). Bảy script giao diện frontend đạt, gồm `verify_frontend_aps.js`. Đây là kiểm thử cục bộ/HTTP giả lập; chưa có smoke test Autodesk thật.

Kiểm chứng tiếp theo 15/10/2026: **1.045 trường hợp đạt**, vẫn 19 file Python. Bổ sung DIM native của thanh có khe hở trong cụm nhiều tầng, kể cả nhãn ngoài vùng hình; phân biệt chiều dài cắt và khoảng lọt lòng. Log: `storage/validation-fixtures/pytest-core-native-dimensions-release-2026-10-15.txt`.

Kiểm chứng mới nhất 15/10/2026: **1.043 trường hợp đạt**, vẫn 19 file Python. Bổ sung cô lập khi xuất các instance cần member khác nhau, ánh xạ ref/ATTRIB, thứ tự vẽ, BLKREFS, bảo vệ pointer native và phân biệt tài nguyên SCALE do ODA cấp lại. Log: `storage/validation-fixtures/pytest-export-isolation-verified-2026-10-15.txt` (154,93 giây).

Kiểm chứng tiếp theo 15/10/2026: **1.026 trường hợp đạt**, vẫn 19 file Python. Đã thêm hồi quy tách phạm vi trong block, bảo toàn thuộc tính/POLYLINE, SORTENTS, DIMASSOC và cache tác vụ tải. Log: `storage/validation-fixtures/pytest-nested-export-release-2026-10-15.txt`.

Kiểm chứng mới nhất 15/10/2026: **1.007 trường hợp đạt**, vẫn trong **19 file Python**. Các kiểm tra phạm vi/mốc giữ mới được bổ sung vào `test_context.py`. Log: `storage/validation-fixtures/pytest-source-scopes-release-2026-10-15.txt`. Số 914 dưới đây là kết quả tại thời điểm gộp file; các chức năng sau đó đã bổ sung thêm kiểm thử.

Thư mục hiện có **19 file Python**, được gộp từ 91 file ở lượt dọn tiếp theo ngày 15/10/2026 (ban đầu 118 file). Các đường dẫn file lẻ cũ đã được xóa; nội dung kiểm thử được chuyển vào nhóm tương ứng. Giữ đủ 914 trường hợp, bao gồm các trường hợp tham số; chạy lại đạt **914/914** trong 121,70 giây. Không thay đổi mã engine hoặc mã chạy ứng dụng.

| File | Nội dung được gộp |
| --- | --- |
| `test_ai_providers.py` | Gemini, OpenAI, AI nội bộ, runtime và đọc hình công đoạn |
| `test_cad_io.py` | Đọc/upload DWG/DXF, danh mục, block, khung và khung loại bỏ |
| `test_bom.py` | BOM native/bảng nét kẻ, ô bảng, text và bằng chứng mã chi tiết |
| `test_geometry.py` | Sửa hình học, DIM/association, thêm nét và cô lập block |
| `test_profiles.py` | Biên dạng cong, spline/NURBS, POLYLINE cũ và góc bo |
| `test_parametric.py` | Co/giãn tham số, hình đo được, lỗ, tấm và nhận diện yêu cầu |
| `test_dependencies.py` | Đồ thị chi tiết, phạm vi, tham số liên kết và lan truyền thay đổi |
| `test_native_contacts.py` | Tiếp xúc 2D, block xoay, chuỗi và nhiều mặt lắp |
| `test_planning.py` | Lập kế hoạch chiều cao/độ dày và yêu cầu nhiều mệnh đề |
| `test_assembly.py` | Hình cụm, hình chiếu và các chi tiết bên trong |
| `test_curved_wall.py` | Tấm ốp cung, phôi uốn và Detail cong |
| `test_packaging.py` | Thùng, khe hở và các lớp đệm đóng gói |
| `test_nesting.py` | Bố trí phôi và bản cắt |
| `test_review.py` | Kiểm tra công đoạn, mốc giữ và điều kiện cho phép sửa |
| `test_revisions.py` | Tạo/duyệt bản sửa, lịch sử, so sánh và xuất theo phạm vi |
| `test_validation.py` | Kiểm tra hình phẳng và kiểm tra hình khối bằng kernel |
| `test_context.py` | Truy xuất dữ liệu CAD và giới hạn ngữ cảnh AI |
| `test_export_jobs.py` | Tác vụ xuất/tải bản DWG |
| `test_planning_jobs.py` | Tác vụ phân tích yêu cầu chạy nền |
| `test_document_requests.py` | Tìm chi tiết toàn file, STT trùng, phạm vi nhiều mã, hồ sơ cũ, refinement và chặn sửa khi chưa gắn đúng mã nguồn |

Hàm tạo dữ liệu mẫu được giữ trong nhóm tương ứng. Các import giữa nhóm và các script `verify_*` đã được cập nhật sang tên mới; không cần giữ file cũ làm lớp chuyển tiếp.

Chạy toàn bộ từ thư mục gốc:

```powershell
python -m pytest -q
```

Chạy một nhóm:

```powershell
python -m pytest tests/test_geometry.py -q
```

Lượt dọn mới lưu bản gốc của 91 file kiểm thử và các script xác minh đã cập nhật tại `storage/archives/test-consolidation-final-20261015/original-files.zip`. `groups.json` ghi file cũ được chuyển vào nhóm nào; `manifest.json` ghi các đường dẫn đã xóa và SHA-256 bản gốc. Bằng chứng đối chiếu từng trường hợp và kết quả chạy nằm tại `storage/validation-fixtures/test-consolidation-final-2026-10-15/`.

Bản lưu lượt dọn đầu vẫn ở `storage/archives/test-consolidation-20261015/original-tests.zip`.
# Kiểm chứng mới nhất — AutoCAD local 16/10/2026

**1.115 trường hợp đạt**, vẫn 19 module test, log `storage/validation-fixtures/pytest-autocad-final-release-2026-10-16.txt` (198,50 giây). Kiểm thử unit cô lập DATABASE_URL và backend CAD khỏi `.env` thật. Có thêm kiểm tra cài AutoCAD ở ổ khác, fingerprint runtime/plugin, nguồn bất biến, timeout, cách ly archive khi engine crash, báo nguồn cần RECOVER và bản sao phục hồi bắt buộc đối chiếu. Native check, năm luồng DWG tổng hợp và đọc/phục hồi file thực chạy riêng qua AutoCAD; xem `docs/local-autocad-2027.md`.


20/10: kiểm chứng block động lồng, phân biệt occurrence, đọc tham số theo trang và tránh nhận nhầm yêu cầu BOM/STT; [file DWG và receipt](../docs/nested-native-validation-2026-10-20.md). Giữ 19 module test.

Bộ cuối 20/10: **1.520 passed**, 1.047 cảnh báo thư viện, 213 giây; log `storage/validation-fixtures/pytest-nested-native-final-full-2026-10-20.txt`.
