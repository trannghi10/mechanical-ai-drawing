# Gắn hình CAD với đúng chi tiết — 17/10/2026

## Bước tiếp theo: sửa đồng bộ trong bản mới riêng

Đã nối đối chiếu biên dạng với bộ sửa tham số cho trường hợp cùng chi tiết được vẽ bằng block/polyline và bằng LINE/ARC rời. Không chỉ dùng mã Part Map: cần **một phép biến đổi duy nhất**, đầy đủ lỗ, DIM thật tương ứng trên mỗi hình (DIM lặp chỉ được gộp khi đã chứng minh cùng một chuyển động CAD), đúng hai đầu đo, mốc giữ và phạm vi được phép sửa. Mỗi recipe nhận vẫn đi qua bộ kiểm tra hình học, BOM và lắp ghép hiện có. Hình đối xứng có nhiều cách xoay hợp lệ vẫn đọc được cùng mã nhưng không tự quyết định đầu giữ để sửa.

Bộ ghi DXF, cô lập block, xuất phạm vi và bước chuyển đổi revision native kiểm tra đầu ra không trùng nguồn, kể cả hard link/đường dẫn trung gian. Kiểm tra lại hash trước khi nhận bản sửa. Mỗi lần tạo có ID revision mới; lưu bằng chứng hash DWG gốc và DXF nguồn trong `source_preservation`, giao diện báo bản mới được lưu riêng. Không có thao tác ghi thay đổi vào DWG khách hàng trong lượt này.

**DWG tổng hợp mới, không dùng mã chi tiết cố định:** `synthetic-exploded-view-sync-48b23e15.dwg` đã qua upload → nhận STT/BOM → sửa → tạo bản mới → tải DWG → mở lại đo. Block và hình LINE rời xoay 90°, tỷ lệ 2 đều đạt **76 mm**, từ nguồn 100 mm. BOM đổi `Bas 2x20x100` thành `Bas 2x20x76`; instance ngoài giữ 100 mm, đầu leader cập nhật theo hình. Lập kế hoạch 0,44 giây trong lượt này. DWG/DXF nguồn giữ nguyên; file tải bằng liên kết trên website khớp SHA-256 với DWG đã kiểm chứng.

Đây là bản kiểm thử xem trước: kiểm tra cụm tổng thể vẫn báo chưa hoàn chỉnh, nên không mở khóa duyệt backup đầy đủ. Không thay thế backup toàn Dauphine.

**1.276 kiểm thử Python toàn bộ, 7 script frontend đạt**, vẫn 19 module; hồ sơ thiết kế phiên bản 15, Part Map phiên bản 3. Kiểm tra bổ sung xoay/tỷ lệ, đảo thứ tự DIM, không đoán hướng hình đối xứng, trùng nguồn/hard link/đường dẫn tạm, nguồn đổi trong lúc kiểm tra và hai revision độc lập. Trình duyệt tải thật `PREVIEW-backup-26591c5b.dwg`, không có lỗi JavaScript trong lượt kiểm tra.

Bằng chứng mới:

- `storage/validation-fixtures/exploded-view-sync-48b23e15/report.json`
- `storage/validation-fixtures/exploded-view-sync-48b23e15/download/checked-preview.dwg`
- `storage/validation-fixtures/exploded-view-workflow-2026-10-17.log`
- `storage/validation-fixtures/copy-only-dwg-ui-2026-10-17.jpg`
- `storage/validation-fixtures/pytest-copy-outline-full-2026-10-17.txt`
- `storage/validation-fixtures/pytest-copy-outline-final-focused-2026-10-17.txt`

## Kết quả thực tế

Đã thêm **Bản đồ chi tiết · STT → hình CAD** theo hướng nhận diện trước, giải ràng buộc và chỉnh sửa sau. Kết quả là dữ liệu đọc từ CAD nguồn; không coi ảnh giống nhau là quyền sửa hình học.

Trên Dauphine, chọn khung C1 `3AAABC`, mở 8 khung liên quan:

| STT | Mã chi tiết | Số vùng hình đã gắn | Vùng có DIM trực tiếp |
| --- | --- | ---: | ---: |
| 8 | 8.1.06126.196 | 3 | 1 |
| 9 | 8.1.06127.196 | 3 | 0 |
| 10 | 8.1.06128.196 | 3 | 2 |

Có 9 cặp hình được đối chiếu theo toàn định nghĩa native. Lượt đầu sau khi nạp backend mất **13,48 giây**. Ba preview trả HTTP 200. Ba đường bao tấm nguyên liệu `3A33E0`, `3A3EEF`, `3A4A3B` có DIM 2500/1220 **không nhận mã chi tiết** từ tên khung. Còn 9 vùng chưa xác minh mã và một cặp tương đồng thiếu danh tính nguồn; chúng được trình bày riêng, không tự gán.

DWG độc lập `82bba95b325741eebb6011ad8273333e` cũng có 2 vùng/1 mã và 1 cặp native xác minh; 0,81 giây. Cả hai lượt giữ nguyên hash DXF nguồn. Không có thao tác chỉnh sửa hoặc xuất backup sản phẩm trong lượt nhận diện này.

## Cách sử dụng

1. Chọn một khung cụm hoặc bản chi tiết.
2. Mở **Kiểm tra dữ liệu bản vẽ → Bản đồ chi tiết · STT → hình CAD**.
3. Bấm **Gắn hình với chi tiết**; chọn kiểm tra khung liên quan để đối chiếu bản chi tiết/bản cắt của cùng mã.
4. Thẻ hiển thị STT cục bộ, mã vật tư, mô tả BOM và ảnh entity CAD nguồn màu xanh. Hình trong khung đang chọn được ưu tiên. Bản sao trên bản cắt được gom thành ảnh đại diện, ghi số instance đã đối chiếu.
5. **Xem hình đã gắn** và **Xem khung nguồn** chỉ đổi cách xem; phạm vi yêu cầu vẫn là bản vẽ đã chọn. Mở **Cần đối chiếu** để xem hình chưa đủ bằng chứng.

## Bằng chứng được chấp nhận

- Mã native/instance được chọn hoặc BOM cục bộ + STT + leader kết thúc trong một vùng vật liệu duy nhất, có kiểm tra lỗ và viền giấy.
- Đối chiếu toàn định nghĩa native một-một; hỗ trợ bản sao đổi handle/tên, xoay và tỷ lệ đều. Nhận diện hình chưa có DIM không tự cấp quyền co/giãn.
- Với hình vẽ rời: so khớp chính xác LINE/ARC/polyline và lỗ CIRCLE sau hiệu chỉnh theo DIM thật. Kiểm tra nét bên trong chưa phân loại; không ghép hình khác lỗ, khác mã, nét thừa hoặc tỷ lệ vật lý không khớp.
- Tên khung chỉ tạo mã ứng viên. Chỉ truyền danh tính đọc sang ứng viên cùng mã khi có cặp hình học đã kiểm tra; một hình vô danh giống hệt vẫn là ứng viên.
- ID gắn hash CAD và đường dẫn instance. Preview được dựng từ bản sao entity thật, kiểm tra lại source/detection hash, từ chối map cũ hoặc view không thuộc map.
- AI nội bộ có thể lấy `part_views`, `view_matches`, `part_view_chunks` theo trang nhỏ. Giữ trạng thái ứng viên/xác minh và `executable=false`; không gửi toàn hình học vào prompt hoặc gửi CAD lên cloud.

## Kiểm chứng và giới hạn

**1.257 kiểm thử Python toàn bộ đạt**; **7 script frontend đạt**. Vẫn 19 module kiểm thử, bổ sung trường hợp vào các module có sẵn. Giao diện thật đã kiểm tra ba thẻ, ảnh nguồn, nút xem hình/khung và giữ phạm vi; không có lỗi JavaScript trong lượt đó.

Đây là bước nhận diện của kiến trúc đề xuất. Chưa chứng minh toàn bộ hình chiếu/phối cảnh, quan hệ tiếp xúc, block động/proxy hoặc mọi NURBS tổng quát đã được gắn đúng. Hình cạnh của C1 chưa đủ bằng chứng được giữ trong nhóm đối chiếu. Bản đồ đọc chưa thay thế kiểm tra mốc, khe hở và solver khi sửa; chưa hoàn thành backup toàn Dauphine hoặc sửa đúng mọi DWG.

Phạm vi đọc tối đa 64 khung, 1.000 đối chiếu sinh ứng viên native và 2.000 cặp kiểm tra trong một map; khi vượt ngân sách có trạng thái hoãn rõ ràng. Không báo phần hoãn là đã kiểm tra. Không thay đổi bộ nhận diện khung được người dùng chấp nhận.

## File minh chứng

- `storage/validation-fixtures/part-map-dauphine-c1-final-2026-10-17.json`
- `storage/validation-fixtures/part-map-independent-final-2026-10-17.json`
- `storage/validation-fixtures/part-map-c1-ui-2026-10-17.jpg`
- `storage/validation-fixtures/part-map-c1-cards-2026-10-17.jpg`
- `storage/validation-fixtures/pytest-part-map-final-full-2026-10-17.txt`
- `storage/validation-fixtures/pytest-part-map-final-focused-2026-10-17.txt`


## Chọn ảnh để yêu cầu chỉnh sửa — 17/10

Trong thẻ có hình đã gắn mã, bấm **Chọn chi tiết để sửa**. Banner hiện mã đang chọn; nhập ví dụ “Chiều dài từ 100 thành 76 mm, giữ đầu trái”. Không cần lặp STT/mã. Dùng **Bỏ chọn chi tiết** trước yêu cầu toàn sản phẩm. Hướng dẫn có trong `/help#part-map`.

Danh tính được xác thực từ map có cùng nguồn/khung/BOM rồi lưu vào job, kế hoạch và revision; refine/apply/duyệt kiểm tra lại nguồn. Mã/STT khác với hình, map cũ, danh tính ứng viên hoặc yêu cầu toàn sản phẩm khi chọn một chi tiết bị từ chối. Lựa chọn không cung cấp tọa độ thi hành hay bỏ qua các solver/validation hiện có. Các hình chưa có danh tính BOM duy nhất vẫn chưa được chọn để tự sửa.

Bài kiểm chứng tạo một DWG tổng hợp mới có code ngẫu nhiên, block và nét rời xoay/tỷ lệ 2. Chọn ảnh, nhập yêu cầu không có mã/STT, engine sửa cả hai hình và BOM, giữ instance ngoài cùng nguồn gốc. Luồng API lập kế hoạch 0,34 giây. Luồng UI riêng cũng tạo/tải được DWG qua AutoCAD, ODA mở lại có DIM 76/152 mm (chiều dài thật 76 mm cả hai hình). File vẫn là xem trước một phần do chưa xác minh toàn cụm; không thay thế backup Dauphine.

- API receipt: `storage/validation-fixtures/exploded-view-sync-b5618e67/report.json`
- UI receipt: `storage/validation-fixtures/exploded-view-sync-b5618e67/ui-download-report.json`
- DWG tải từ UI: `storage/validation-fixtures/exploded-view-sync-b5618e67/ui-download/selected-part.dwg`
- Toàn bộ Python: `storage/validation-fixtures/pytest-selected-part-full-2026-10-17.txt` (1.294 đạt).
- Kiểm tra cuối: `storage/validation-fixtures/pytest-selected-part-final-focused-2026-10-17.txt` (98 đạt); 7 script frontend đạt.


## Nhiều DIM đo cùng chi tiết — 17/10

Bộ lập kế hoạch trước đây có thể dừng khi một profile có nhiều DIM cùng kích thước, hoặc khi hình nhận có hai DIM cùng đầu đo. Nay engine biên dịch từng driver độc lập từ cùng snapshot nguồn và chỉ gộp nếu **toàn bộ tập entity, hình học trước/sau đều khớp**: đường bao, lỗ, DIM liên quan và leader đã gắn. Không gộp chỉ vì số đo bằng nhau. Kết quả chỉ sửa hình một lần, vẫn cập nhật các DIM có liên kết hợp lệ theo CAD nguồn.

Áp dụng cả block cùng định nghĩa và hình nét rời có phép đối chiếu duy nhất, xoay/tỷ lệ và DIM đảo đầu. Mốc giữ khác nhau, chủ sở hữu khác, số đo ghi đè hoặc trường hợp chưa được bộ biên dịch hỗ trợ vẫn giữ là xung đột/chưa đủ dữ liệu. Không thay đổi nhận diện khung hoặc nới điều kiện duyệt backup toàn sản phẩm.

Chạy lại kiểm chứng: `python scripts/verify_general_dwg_workflow.py --redundant-dim-sync`. Lệnh tạo hai DWG tổng hợp mới với mã ngẫu nhiên; gửi qua upload, chọn ảnh, lập kế hoạch, sửa, xuất native DWG, tải và mở lại bằng ODA. Không dùng kết quả này thay cho nghiệm thu Dauphine hoặc mọi DWG.

Hai lượt native DWG đã đạt:

- Block lặp: `storage/validation-fixtures/bom-view-sync-e5bacddb/report.json`.
- Block và nét rời xoay 90°, tỷ lệ 2: `storage/validation-fixtures/exploded-view-sync-519f8334/report.json`.
- Cả hai: bốn DIM sau sửa đều 76 mm theo hệ số tỷ lệ nguồn; BOM 2×20×76; instance ngoài giữ 100 mm; mũi tên đi theo hình; tải HTTP 200, mở lại bằng ODA; DWG/DXF nguồn bất biến. Lập kế hoạch 0,33/0,30 giây trong hai lượt này, không phải cam kết tốc độ mọi tài liệu.
- Nguồn còn hình cụm chưa xác minh nên trạng thái vẫn `complete_product_backup=false`; không mở khóa duyệt backup đầy đủ.
- Có thể chạy lại với `--redundant-dim-sync`; script tạo tài liệu mới được đánh dấu file thử và ẩn mặc định.

Bộ kiểm tra có thêm DIM đảo đầu, mã/mốc giữ khác, số ghi đè, bằng chứng ngoài nguồn và không thay đổi context. Các trường hợp âm không được gộp thành một driver.

Kiểm chứng: 1.302 bài toàn bộ đạt (`pytest-redundant-dim-full-2026-10-17.txt`); sau kiểm tra bổ sung evidence cache, 295 bài parametric/profiles/planning đạt (`pytest-redundant-dim-final-focused-2026-10-17.txt`), trong `storage/validation-fixtures`. Giữ 19 module kiểm thử. Backend đã nạp mã mới.
