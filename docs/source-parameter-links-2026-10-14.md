# Liên kết tham số dùng chung cho DWG mới — 14/10/2026

Đã triển khai sửa các chi tiết liên quan qua ràng buộc DIM nguồn có xác nhận. Không thêm nhánh theo tên file/handle, không đổi model hoặc yêu cầu công cụ trả phí. **Đây chưa phải khả năng tự sửa đúng mọi DWG hoặc backup toàn Dauphine.**

## Cập nhật 16/10: đồ thị và nguồn nhập AutoCAD

Sửa lỗi nạp liên kết đã lưu khi nguồn DXF nằm tại `autocad-converted/<job>/original.dxf` hoặc `aps-converted/<job>/original.dxf`. Liên kết được đọc từ thư mục tài liệu theo đúng đường dẫn nguồn đã đăng ký trong `status.json` và hash DXF. Cache CAD không giữ bản liên kết cũ. Bản sửa và bản mở lại để kiểm tra không thừa hưởng liên kết của nguồn, kể cả khi nội dung trùng hash.

`graph/dependency_graph.py` có `DesignGraph` cho dịch chuyển cứng trong cùng hệ tọa độ: duyệt cạnh cha thực theo thứ tự topo, xử lý chuỗi và nhánh hội tụ một lần, chặn vòng lặp và xung đột với cha ngoài chuỗi đang giữ cố định. `propagate_change()` trả đề xuất `Move`; đây không phải endpoint thực thi .NET. Engine đang chạy dùng chung thứ tự topo xác định qua `DependencyGraph`, vẫn kiểm tra tọa độ local/layout, phạm vi, snapshot và ràng buộc trước apply.

Không dùng cách đệ quy sửa mọi `INSERT` trong block definition. Định nghĩa dùng chung phải được cô lập theo đường dẫn instance của cả chuỗi cha trước khi sửa block động lồng nhau. Plugin hiện vẫn chặn trường hợp chưa cô lập và kiểm tra owner/giá trị nguồn/giá trị được phép/mở lại DWG. JSON `MaintainGap` chỉ có handle và số gap chưa xác định được mặt lắp; `AlignCenters` cũng cần tâm/hệ tọa độ/mốc giữ được xác minh. Hai loại đó không tự trở thành thao tác hợp lệ chỉ nhờ deserialize JSON hoặc source generation.

Hai DWG tổng hợp đã qua **AutoCAD đọc nguồn → lưu liên kết → nhập yêu cầu → sửa hình/DIM/BOM → duyệt → AutoCAD xuất → tải HTTP 200 → ODA mở lại**. Chuỗi đo lại 76/36/16 mm; đổi dày đo lại 1,2/27,2/30 mm; nguồn giữ nguyên. Receipt: `storage/validation-fixtures/parameter-links-dwg-d4763197/receipts.json`. Đây là bằng chứng hồi quy tổng hợp, không thay thế nghiệm thu sản phẩm Dauphine hoặc mọi DWG bên ngoài.

## Chức năng mới

- Lưu quan hệ theo hash nguồn, DIM thật, chủ sở hữu chi tiết, các khung và mốc giữ. Các số thứ tự của BOM không được dùng làm định danh toàn file.
- **Giữ chênh lệch:** `B_mới = B_nguồn + A_mới − A_nguồn`. Giải được chuỗi, quan hệ vòng nhất quán và thay đổi từ đầu nhận. Không chấp nhận kích thước mới âm hoặc xung đột.
- **Giữ khe hở:** `chi_tiết_lắp_mới = kích_thước_ngoài − N × độ_dày_mới − khe_hở_nguồn`, với N là một hoặc hai thành/tấm do người dùng xác nhận. Kích thước ngoài được giữ cố định; khe hở tính từ DIM nguồn, không lấy một hằng số AI tự đặt.
- Khi sửa một chi tiết, mở phạm vi liên quan qua graph, tạo recipe cho chi tiết nhận, đồng bộ các biểu diễn native giống nhau, lỗ và BOM. Đường bao/lỗ/mốc vẫn qua các bộ kiểm tra hình học hiện có và FreeCAD trước khi apply.
- Dùng lại mốc đã lưu khi yêu cầu sau không nhắc lại mốc. Nếu yêu cầu dùng mốc khác hoặc mâu thuẫn phương trình, trả lỗi ngay; không chuyển sang chờ model để tìm cách bỏ qua ràng buộc.
- Mỗi lần apply và duyệt đều đọc lại liên kết hiện tại. Kế hoạch bỏ sót chi tiết nhận hoặc sửa riêng chữ DIM không vượt kiểm tra.
- Khung bị bỏ làm liên kết nguồn tương ứng mất hiệu lực; cần xóa/gắn lại trước khi sửa chi tiết đó. Liên kết này không kéo khung bỏ vào graph và không chặn chi tiết độc lập khác.
- Chọn riêng block cần CAD host/native adapter sẽ báo ngay trước khi gọi model. Không bật khả năng sửa tham số block động/proxy bằng việc bỏ kiểm tra.

Các liên kết số này **không chứng minh tiếp xúc không gian, độ bền, hệ số uốn hoặc đồng bộ mọi phối cảnh**. Những phần đó vẫn qua kiểm tra riêng; không dùng một phương trình DIM để chứng nhận toàn sản phẩm.

## Cách dùng

1. Tải lại Explorer, tải DWG mới và chọn bản vẽ như trước.
2. Trong **Hồ sơ chi tiết và hình biểu diễn**, bấm **Lập hồ sơ CAD đã chọn**.
3. Nếu liên kết chưa được CAD chỉ rõ, dùng **Gắn liên kết kích thước còn thiếu**. Có thể đọc thêm khung liên quan, tối đa bốn khung trong mỗi lần gắn; các cặp đã lưu có thể nối thành chuỗi dài hơn.
4. Chọn DIM thứ nhất, DIM liên quan, kiểu quan hệ và hai mốc giữ. Với khe hở, chọn thêm DIM ngoài và số thành/tấm. Nút **Xem CAD của DIM này** mở đúng khung nguồn và vẫn giữ bản vẽ đang làm việc.
5. Xác nhận quan hệ rồi bấm **Lưu liên kết để tự đồng bộ**. Nhập/phân tích lại yêu cầu; kiểm tra preview và tải DWG qua các nút hiện có. Lần sau trên cùng nguồn không cần gắn lại quan hệ đã xác nhận.

Chỉ gắn DIM linear/aligned đo thật, đơn vị mm và có một chủ sở hữu được xác định từ CAD/BOM. Số ghi đè, quy cách BOM có nhiều vị trí số giống nhau chưa xác định được vai trò, đơn vị chưa rõ hoặc thiếu adapter đều bị báo cần xử lý; không đoán để tạo file.

## API và lưu trữ

- `GET /documents/{id}/parameter-links`.
- `POST /documents/{id}/parameter-links`: `ids`, `source_hash`, `rule`, `confirmed:true`; server tự xác minh lại refs/ownership/nguồn. Rule gồm kiểu quan hệ, DIM thứ nhất/nhận/ngoài, số thành và hai mốc giữ. Không nhận hệ số hoặc code tùy ý do client đặt.
- `DELETE /documents/{id}/parameter-links/{link_id}?source_hash=...`.
- `parameter-links-v1.json` nằm trong thư mục tài liệu. Cache đọc CAD không giữ bản liên kết cũ; graph và hồ sơ thiết kế được cập nhật khi file liên kết thay đổi.

## Kiểm chứng

Kiểm thử gồm chuỗi ba chi tiết, đổi dày/giữ khe hở, thay đổi từ đầu nhận, nhiều biểu diễn native, đồng bộ BOM/lỗ, nguồn cũ, mốc mâu thuẫn, số DIM ghi đè, quy cách BOM mơ hồ, đơn vị chưa biết, khung bỏ và kế hoạch cố tình thiếu thao tác. Script giao diện kiểm tra xác nhận, refs/mốc/hash gửi đi, xóa và phản hồi cũ khi chuyển phạm vi.

`scripts/verify_parameter_links_dwg.py` tạo **hai DWG mẫu mới**, tải qua API như file người dùng, gắn quan hệ rồi nhập yêu cầu không nhắc lại mốc. Luồng đi qua compiler, apply, FreeCAD, preview, hàng đợi xuất và tải file; mở lại đúng DWG tải xuống bằng ODA để đo DIM và đọc BOM.

| Mẫu | Thay đổi kiểm chứng |
|---|---|
| Chuỗi ba chi tiết | 100 / 60 / 40 → 76 / 36 / 16 mm; giữ đường kính lỗ và khoảng cách tới đầu gần nhất |
| Giữ khe hở | Dày 2 → 1,2 mm; chi tiết lắp 25,6 → 27,2 mm; ngoài 30 mm và khe hở 0,4 mm giữ nguyên |

Đây là mẫu hồi quy do dự án tạo, không phải file sản xuất độc lập có đáp án từ kỹ sư. Kết quả không thay thế nghiệm thu nhiều DWG thực tế hoặc backup Dauphine còn thiếu C4, Detail C và một số đóng gói.

## Mã chính

- `graph/parameter_links.py`: binding nguồn, hệ phương trình, recipe, BOM và kiểm tra lại.
- `backend/services/parameter_link_service.py`: lưu/xóa theo hash và xác nhận.
- `backend/services/change_service.py`, `parametric_service.py`, `part_graph_service.py`: tích hợp phân tích, lan truyền và apply.
- `frontend/index.html`: gắn DIM/mốc và xem nguồn.
- `tests/test_dependencies.py`, `scripts/verify_frontend_parameter_links.js`, `scripts/verify_parameter_links_dwg.py`: kiểm chứng.

## Kết quả cuối và file mẫu

**804 kiểm thử Python đạt; 6 script JavaScript đạt.** Backend đã nạp mã mới trên cổng 8765. Đây là các DWG mẫu kiểm thử, không phải sản phẩm khách hàng.

- [DWG backup mẫu chuỗi ba chi tiết](http://127.0.0.1:8765/documents/7917263ce84c49eea9d251a6a7dad90c/revisions/070c0b6226ae4a2e8db974591697f0c9/exports/5227f39673e64faf8aca607028c0c60d/download): 12 thao tác, duyệt và tải HTTP 200, ODA mở lại đo đúng; hash `6e84ae4d560fc268fd29d80eac0576614a4da8980af3926b2b31c4c0a7a1d720`.
- [DWG backup mẫu giảm dày và giữ khe hở](http://127.0.0.1:8765/documents/457e9ce3f47149008afe8b83874a4b2e/revisions/253cf826edb64c6eb015820a0eeadfd2/exports/7f1e2ba36df14747a39f854baa49994a/download): 7 thao tác, duyệt và tải HTTP 200, ODA mở lại đo đúng; hash `018164bbd995701203d7c751dd34acc6df0ceb44b67d28e8a03621ea67e04fec`.

Receipts: `storage/validation-fixtures/parameter-links-dwg-6cc242cc/receipts.json`. Log toàn bộ kiểm thử: `storage/validation-fixtures/pytest-parameter-links-final.txt`. Lỗi ràng buộc không hợp lệ trả HTTP 422 sau 0,015 giây trong phép thử riêng, không tạo thêm revision (`parameter-links-dwg-8d612df5/failfast.json`). Các thời gian đo trên file mẫu nhỏ không đại diện thời gian sửa DWG sản xuất lớn.
