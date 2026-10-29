# Detail C: đối chiếu khoảng hở từ CAD nguồn — 21/10/2026

Đã quay lại Detail C đang dùng trong Dauphine và đọc 48 đối tượng lân cận trực tiếp từ phạm vi production của kế hoạch `da06e34f11134530a55fec6bc4016cea`. Đây là phân tích và đề xuất chỉ đọc; chưa thêm thao tác vào kế hoạch hoặc tạo revision khách.

## Kết quả đo

Trong vòng trích có một cặp đường bao hộp khớp tiết diện BOM 14×14×1,2 mm, ứng viên mã `8.1.03172.001`. Lựa chọn sửa gauge của người dùng đã có trên cùng bản Detail, nhưng chưa đủ chứng minh chuyển động của cả cụm hộp/chốt. Bộ đọc giữ cả nét trùng trên đường bao ngoài, không tự xóa CAD.

Tỷ lệ lấy từ DIM native của dải cong là 0,2; không đo kích thước từ ảnh. Nét nguồn đủ đỉnh và cao độ được giữ trong phép tính, chỉ dùng lượng tử tọa độ để tìm liên kết graph.

| Khoảng hở | Nguồn | Sau đổi dải cong, hộp đứng yên | Đề xuất giữ hai khe |
| --- | ---: | ---: | ---: |
| Với mặt kê | 0,500 mm | 1,000 mm | 0,500 mm |
| Hướng kính với cung trong | 0,914613 mm | 1,414613 mm | 0,914613 mm |

Phương án giữ cả hai khe dịch tiết diện hộp khoảng 0,553208 mm sang phải và 0,500 mm xuống dưới trong hình. Đây là khoảng dịch vật lý sau áp hệ số DIM; khoảng dịch CAD gốc là (+2,766041; −2,5) đơn vị bản vẽ.

Hộp không tiếp xúc trực tiếp mặt kê hoặc cung ở nguồn. Không tự dùng chính sách giữ khe hở theo chiều dài thanh làm quyết định dịch tiết diện ngang này. Cần chứng minh danh tính, vị trí lắp và nhóm chốt/ren/chú thích phải đi theo trước khi tạo thao tác CAD.

Đã tìm thấy đường tròn `3B7FF1` gần tiếp xúc với góc hộp trong dung sai đọc 0,0001 đơn vị CAD. Nếu chỉ dịch hộp theo đề xuất mà đường tròn đứng yên, khe đó mở ra khoảng **0,575671 mm**. Đây là bằng chứng cụ thể rằng giữ được hai khe với dải cong chưa đủ để sửa riêng hộp. Quan hệ với chốt/ren và cả nhóm lắp vẫn chưa được xác nhận.

## Phần được bổ sung

`cad/clipped_detail_fit.py` tính đề xuất giữ đồng thời khe với mặt kê ngang và cung trong bằng hình học giải tích. Solver kiểm tra chữ nhật đủ đỉnh, mặt phẳng, tâm cung, phía cung, góc nằm trong cung trích, mặt kê phủ tiết diện, nguồn không chồng và đỉnh chi phối khoảng hở duy nhất. Không nối solver này vào apply/export hoặc tự cấp quyền sửa.

`scripts/audit_curved_detail_neighbors.py` đọc lại context production và proof Detail cong, tìm ứng viên tiết diện khớp BOM/lựa chọn đã có, lưu mọi nét lân cận và đề xuất. Ảnh dựng từ LINE/ARC/CIRCLE native, ghi rõ phần chốt vẫn chưa gắn và chưa sửa DWG.

- Audit và tọa độ: `storage/validation-fixtures/detail-c-neighbors-2026-10-21/audit.json`.
- Ảnh nguồn: `detail-1.png` trong cùng thư mục.
- So sánh ba phương án: `fit-1.svg`, `fit-1.png` trong cùng thư mục.
- Lặp lại: `python scripts/audit_curved_detail_neighbors.py DOCUMENT_ID PLAN_ID --output OUTPUT_DIRECTORY`.
- Nguồn giữ hash `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

## Kiểm thử và giới hạn

157 bài geometry đạt, gồm chín trường hợp mới cho solver đề xuất: hai phía cung, tọa độ lớn, giữ hai khe và từ chối chữ nhật lỗi, khác mặt phẳng, chồng nguồn, mốc không duy nhất hoặc không có giao điểm. Log `storage/validation-fixtures/pytest-clipped-fit-geometry-2026-10-21.txt`.

Chưa xuất DWG từ phương án dịch này vì chưa xác nhận chuyển động cả cụm. Bằng chứng DWG của các adapter trước không được dùng để tuyên bố phương án này đã sửa được khách. Đề xuất tấm xốp riêng vẫn chưa xác nhận; các quyết định đã lưu của người dùng được giữ nguyên.
