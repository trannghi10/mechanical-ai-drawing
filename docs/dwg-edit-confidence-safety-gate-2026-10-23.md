# DWG Edit Confidence & Safety Gate — 23/10/2026

## Mục đích

Gate là lớp quyết định chung cho mọi đề xuất và revision DWG 2D. Nó không dùng điểm tin cậy do AI hoặc trình duyệt gửi lên. Mỗi lượt đánh giá đọc lại nguồn hiện tại, kế hoạch đã được kiểm, hash artifact và bằng chứng native trước khi trả về một trong ba trạng thái.

| Trạng thái | Ý nghĩa | Hành động được phép |
|---|---|---|
| `AUTO` | Loại sửa có chứng nhận kỹ sư còn hiệu lực và toàn bộ bằng chứng hiện tại đạt | Tự phát hành revision đã kiểm |
| `REVIEW` | Bản sửa có thể xem xét, nhưng còn thiếu chứng nhận, phạm vi, bằng chứng native hoặc xác nhận quan hệ | Tạo/xem bản đề xuất; phát hành thủ công chỉ sau khi các kiểm tra bắt buộc đạt |
| `BLOCK` | Nguồn, kế hoạch, hình học hoặc artifact không còn đáng tin | Không ghi CAD và không phát hành |

`AUTO` chỉ xuất hiện ở bước phát hành, không xuất hiện chỉ vì một kế hoạch có vẻ hợp lý.

## Bằng chứng được kiểm

Gate kiểm hash nguồn với kế hoạch, trạng thái đọc toàn hồ sơ, validator hình học/ràng buộc, câu hỏi về ý đồ thiết kế, phụ thuộc cần xác nhận, tính bất biến file gốc, phạm vi tác động, DXF kết quả và DWG toàn hồ sơ đã lưu/mở lại bằng native. Nó cũng lấy từ design model các mơ hồ chỉ liên quan trực tiếp đến entity hoặc mã chi tiết đang sửa: chủ sở hữu hình học trùng là `BLOCK`; hình chi tiết chưa gắn, DIM mơ hồ và quan hệ chưa có mốc/quy tắc là `REVIEW`. Mơ hồ ở một chi tiết không liên quan vẫn được hiển thị trong model nhưng không chặn sai một bản sửa độc lập. Revision đã được tự phát hành được đánh giá lại trước mỗi lần dùng artifact; chứng nhận bị thu hồi, hết hạn, thay đổi code xử lý, đổi native backend hoặc sửa benchmark sẽ hạ về `REVIEW`.

## Chứng nhận loại sửa

Không có chứng nhận dựng sẵn. Kỹ sư hoặc quản trị viên phải tạo chứng nhận có thời hạn tối đa 90 ngày, nêu rõ khoảng kích thước, độ thay đổi, số thao tác và tối thiểu hai hồ sơ nguồn độc lập đã được kỹ sư duyệt thủ công, có DXF/DWG native hash đúng. Phiên bản hiện tại chỉ cho phép chứng nhận họ sửa hẹp `linear_profile_resize_2d`: LINE/LWPOLYLINE/POLYLINE đoạn thẳng, DIM tuyến tính, không bulge, không có câu hỏi hay công thức/recipe khác.

Mỗi chứng nhận gắn fingerprint của code/solver và phiên bản phụ thuộc; metadata có hash toàn vẹn. Chứng nhận không thay thế nghiệm thu một thiết kế cụ thể và không biến DWG thiếu quan hệ thành đủ bằng chứng.

## Điểm tích hợp

- Lập kế hoạch và preview đánh giá Gate trước khi tạo bản sửa.
- Tạo revision, xuất DXF/DWG và tải artifact sản xuất đều kiểm lại nguồn và revision.
- `GET /documents/{document}/change-plans/{plan}/edit-gate` và `GET /documents/{document}/revisions/{revision}/edit-gate` trả lời lý do hiện tại.
- Trang **Điều kiện phát hành** hiển thị các kiểm tra gốc cùng quyết định Gate. Trang chỉ đọc; không có thao tác bỏ qua kiểm tra.
- `POST /documents/{document}/revisions/{revision}/auto-release` chỉ thành công khi Gate đang là `AUTO`; mọi lần thử đều ghi audit. Tạo hoặc thu hồi chứng nhận yêu cầu tài khoản kỹ sư/quản trị viên.

## Kiểm chứng

`tests/test_edit_gate.py` có 29 ca kiểm: nguồn đổi hash, đọc thiếu toàn file, thao tác/sự liên kết bị sửa, preview có câu hỏi, phạm vi mơ hồ liên quan/không liên quan, artifact native bị thay đổi, phát hành không chứng nhận, chứng nhận bị thu hồi/hết hạn/đổi fingerprint/đổi backend/tắt kỹ sư/đổi benchmark và hồi phục bằng duyệt thủ công. Ngày 23/10, 29 ca này đạt; chuỗi tích hợp revision, export, release-review và parametric đạt 436 ca. Frontend release-review cũng được kiểm tra text escaping và chỉ đọc.

Các chứng nhận trong test dùng storage tạm; không có chứng nhận sản xuất nào được tạo và không có DWG công ty nào được tự phát hành bởi thay đổi này.

## Phần còn lại

Gate quyết định khi nào hệ thống chưa đủ bằng chứng; nó chưa tạo ra quan hệ cơ khí còn thiếu. Nhận diện nét khuất và hình chiếu, block động phức tạp, XREF/proxy và tập dữ liệu DWG công ty đa dạng vẫn cần mở rộng và kiểm chứng riêng trước khi có thể mở rộng các loại sửa được chứng nhận.
