# Hình hộp chiếu trực giao theo ba kích thước — 20/10/2026

Đã bổ sung một nhóm biểu diễn có chiều sâu: hình hộp chữ nhật dựng bằng 9 LINE (ba mặt nhìn thấy, 7 đỉnh) hoặc 12 LINE (đủ khung dây, 8 đỉnh). Toàn bộ cạnh hiện có phải khớp topology hộp, đồng phẳng trong bản vẽ 2D và tương thích ba kích thước BOM theo một camera trực giao có tỷ lệ đều. Không thêm cạnh bị che, suy chiều sâu từ ảnh hoặc chấp nhận một hình bình hành tùy ý.

## Đọc, sửa và giới hạn

- Danh tính phải đến từ block riêng có mã hoặc STT/leader/BOM cục bộ được đọc lại từ CAD. Hình thiếu mã vẫn là ứng viên, kể cả chỉ có một hình khớp kích thước.
- Bộ sinh thao tác yêu cầu recipe/DIM nguồn được thực thi và mọi ô mô tả BOM liên quan được cập nhật đúng. Đối chiếu lại cả ba kích thước và toàn bộ cạnh sau sửa; giữ LINE native và hệ chiếu nguồn.
- Luồng tự động áp dụng khi yêu cầu giữ tâm và các nét nối nguồn vẫn được bảo toàn. Adapter cũng kiểm tra được một đỉnh cố định nếu có quyết định kỹ thuật đã xác nhận theo hash, đúng hình/mã/DIM. [Ngày 21/10 đã bổ sung giao diện lưu mốc và gắn hình thiếu mã](confirmed-cuboid-links-2026-10-21.md). Không tự biến mốc đầu/đáy của bản chi tiết thành mốc của một hình tách rời chưa gắn tương ứng.
- Kích thước bằng nhau gây nhiều cách gán trục chỉ được nhận nếu mọi cách gán cho cùng một kết quả native. Nét dư, lỗ chưa gắn, nét chồng, sai BOM, camera xiên, đổi Z, thiếu nguồn hoặc instance đã bỏ đều không được dùng để cấp quyền sửa.
- Ghi chú quy cách trong block có mã riêng được đồng bộ khi trùng văn bản nguồn và đúng mã. Không lấy chữ lân cận cho một chi tiết con trong block cụm.
- Chỉ cấp bằng chứng cho các cạnh/ghi chú đã kiểm tra. Không cấp quyền sở hữu toàn bộ block cụm hoặc xác nhận toàn bộ công đoạn/đóng gói từ một hình hộp.

Mã: `cad/cuboid_projection.py`, `graph/cuboid_projections.py`. Gắn vào đồng bộ/kiểm tra native và báo cáo hình cụm. Hồ sơ CAD và Part Map hiển thị danh sách hình hộp đã đối chiếu.

## DWG mới đã xuất và mở lại

Mẫu độc lập `UNSEEN-CUBOID-2c532508` qua upload website → yêu cầu giữ tâm → sửa → duyệt → AutoCAD xuất → tải HTTP 200 → ODA mở lại.

| Hạng mục | Kết quả mở lại DWG |
| --- | --- |
| DIM và chiều cao đường bao nguồn | 100 → 76 mm |
| BOM | Foam 2×80×100 → 2×80×76 mm |
| Hình có chiều sâu | Đủ 9 LINE, tương thích 2×80×76 mm; không còn khớp kích thước cũ |
| Vị trí minh họa | Giữ tâm bao hình, giữ camera; có phản chiếu |
| Ghi chú trong hình | Foam 2×80×76 mm |
| File gốc | Hash giữ nguyên |

- Receipt: `storage/validation-fixtures/cuboid-projection-2c532508/receipt.json`.
- DWG: `storage/validation-fixtures/cuboid-projection-2c532508/download/cuboid-backup.dwg`.
- SHA-256: `a6730bab4ba705564afee80b34d57db7a7d055e7c06fd9d759a7d0fd2d2a580e`.
- Lặp lại: `python scripts/verify_cuboid_projection.py`.

## File Dauphine thực tế

Audit dựng lại context production từ nguồn hiện hành, không dùng kết quả nhận diện đã lưu để cấp quyền sửa. Đã xác định thêm hai hình trong trang đóng gói tách rời:

- `3.8.01309`: tấm lót 7×895×895 mm, 9 cạnh, tỷ lệ chiếu 0,75.
- `3.8.01280`: tấm xốp 40×895×895 mm, 9 cạnh, tỷ lệ chiếu 0,75.

Cả hai có STT/leader/BOM nguồn. Kích thước của chúng chưa đổi trong yêu cầu hiện tại; không phát sinh thêm thao tác sửa Dauphine. Hình tấm lót 7×580×580 còn nét chồng bị từ chối. Tấm xốp cần đổi chiều dài có hình mang STT bị che cạnh; hình đủ cạnh còn lại chưa có danh tính độc lập, nên chưa được tự ghép.

Audit: `storage/validation-fixtures/cuboid-customer-audit-2026-10-20.json`. Nguồn DXF giữ hash `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

Đã sửa thêm phạm vi đọc Part Map: các trang trong bộ số tờ có BOM đã được chứng minh được mở theo cả hai chiều. Không dùng tên sản phẩm/công đoạn chung để mở các trang không liên quan. Website đã trả hai hình hộp trong phạm vi 10 khung từ trang BOM đóng gói; receipt `storage/validation-fixtures/cuboid-website-reading-2026-10-20.json`.

## Kiểm chứng

**1.642 bài Python toàn bộ đạt**, 236,88 giây, 1.281 cảnh báo thư viện. 21 bài tập trung đạt, gồm native DXF mở lại, đối tượng phản chiếu, khung dây đủ cạnh, lỗ/nét dư, sai mã/BOM/camera, thiếu thao tác, mốc đỉnh và hash cũ, BOM có trục bằng nhau, STT/leader thực, chú thích native và phạm vi đọc bộ số tờ. Bảy script frontend đạt, gồm hiển thị nguồn CAD và chống phản hồi cũ khi đổi tài liệu. Logs:

- `storage/validation-fixtures/pytest-cuboid-release-focused-2026-10-20.txt`
- `storage/validation-fixtures/pytest-cuboid-release-full-2026-10-20.txt`
- `storage/validation-fixtures/frontend-cuboid-release-2026-10-20.txt`

Chưa nghiệm thu toàn Dauphine hoặc mọi DWG. Còn hình bị che nét, mốc lắp/Detail chưa gắn, đối tượng chuyên ngành và đóng gói chưa đầy đủ.
