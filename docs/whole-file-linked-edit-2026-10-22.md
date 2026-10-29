# Tìm chi tiết toàn file → sửa liên động → lưu/mở DWG — 22/10/2026

Đã kiểm chứng chuỗi thực thi trên DWG tổng hợp riêng bằng **AutoCAD local 2027**. File nguồn và hồ sơ khách hàng giữ nguyên; không gửi DWG lên cloud. Đây là bằng chứng cho trường hợp đã kiểm, chưa phải nghiệm thu mọi bản vẽ cơ khí hoặc chứng nhận tự phát hành sản xuất.

## Kết quả sau lưu và mở lại

Hồ sơ có hai mã PART-A/PART-B, ba khung nguồn được tự nhận diện từ đường bao/khung tên, hình chi tiết, hình cụm, BOM và hai đối tượng đối chứng ngoài nhóm. Không đưa handle hay ID khung vào yêu cầu HTTP.

Yêu cầu: `Chi tiết số 1 chiều cao từ 100 thành 120 mm, giữ đầu dưới; đồng bộ hình chi tiết và cụm lắp`.

| Nội dung đo | Trước | Sau lưu/mở DWG | Kết quả |
|---|---:|---:|---|
| Chiều cao biên dạng PART-A ở hai hình | 100 mm | 120 mm | Đạt, đo tọa độ polyline |
| Hai DIM của PART-A | 100 mm | 120 mm | Đạt, đọc phép đo DIM |
| Mốc dưới của PART-A | 0 mm | 0 mm | Giữ nguyên theo recipe đã kiểm |
| Vị trí Y của PART-B trong cụm | 100 mm | 120 mm | Đạt, dịch theo mặt tiếp xúc |
| Chiều cao PART-B | 100 mm | 100 mm | Giữ nguyên |
| DIM tổng cụm | 200 mm | 220 mm | Đạt |
| BOM PART-A | Bas 2x20x100 | Bas 2x20x120 | Đạt |
| BOM PART-B | Bas 2x20x100 | Bas 2x20x100 | Giữ nguyên |
| Block PART-B ngoài nhóm tại X=2000 | Vị trí/biên dạng/DIM ban đầu | Không đổi | Đạt |
| Đường thẳng ngoài nhóm | Tọa độ ban đầu | Không đổi | Đạt |

Hệ thống chọn khung gốc `A1`, tự mở rộng sang `A3`, `A5`. Bản sửa tạo bằng `checked_measured_profile_resize` và kiểm liên kết tiếp xúc 2D. Xuất toàn document qua AutoCAD Core Console đạt `validated_roundtrip`.

Đã tải chính DWG kết quả, nhập lại như một tài liệu độc lập bằng AutoCAD local và đo lại: hai biên dạng/hai DIM 120 mm, mốc PART-B 120 mm, DIM tổng 220 mm. Block sao sau sửa giữ provenance mã nguồn; yêu cầu tiếp theo 120→110 mm tìm được PART-A và lập được kế hoạch đủ điều kiện thực thi. Kế hoạch thứ hai chưa được áp dụng; không báo là đã xuất lần sửa thứ hai.

## Phần chức năng vừa nối

- Website có chế độ **Tìm chi tiết trong toàn file**, nhận yêu cầu không cần chọn khung trước. Tác vụ chờ đọc toàn hồ sơ xong rồi mới chọn phạm vi.
- Tìm theo mã chính xác, STT trong các BOM hoặc mô tả nguồn đầy đủ. Mô tả ngắn/chung không tự thành định danh chắc chắn.
- STT trùng trả các mã/mô tả/khung nguồn để chọn; lựa chọn gắn với ID hồ sơ và SHA-256. Không coi lựa chọn mã là xác nhận mặt lắp, mốc giữ hoặc quyền sửa hình học.
- Mã không tồn tại, mã/STT mâu thuẫn, nhiều STT chưa gắn đủ mã, định nghĩa nguồn xung đột và traversal chưa hoàn tất chặn lập phạm vi sửa.
- Ngữ cảnh lập kế hoạch nhận danh mục toàn file, bằng chứng của mã đã tìm và các cụm liên quan. Các bộ kiểm hình học/ảnh hưởng hiện có tiếp tục quyết định thao tác nào được thực thi.
- Tác vụ có tiến độ, hủy, nối lại sau tải trang; trạng thái cần chọn chi tiết là trạng thái kết thúc, không quay chờ vô hạn. Refinement giữ mã đã gắn và hồ sơ nguồn. Trước apply/preview phải kiểm lại hồ sơ chưa cũ.

Giao diện thật trên Dauphine: STT 6 có ít nhất hai mã `3.8.01311` và `8.1.05060.013`; hệ thống hiển thị cả hai và không gọi bộ lập kế hoạch hình học. Không tự chọn theo khung đang mở hoặc theo kích thước gần giống. Lựa chọn xốp `3.8.01312 / 745→718` vẫn chưa được xác nhận.

## Bằng chứng có thể kiểm tra

- Receipt: [receipt.json](../storage/validation-fixtures/whole-file-edit-d55a996b13fe/receipt.json).
- Mở độc lập: [independent-reopen.json](../storage/validation-fixtures/whole-file-edit-d55a996b13fe/independent-reopen.json).
- DWG trước: [before.dwg](../storage/validation-fixtures/whole-file-edit-d55a996b13fe/before.dwg).
- DWG sau: [after.dwg](../storage/validation-fixtures/whole-file-edit-d55a996b13fe/after.dwg).
- Giao diện STT trùng: [whole-file-request.png](../storage/validation-fixtures/whole-file-edit-d55a996b13fe/whole-file-request.png).
- Document `ee45b86b58234ab09c9695a6a9df1dc7`, plan `9435eaef6dff4990b62960a94a923b8d`, revision `e2ad2562e3ee443592e9f97fb08477ef`.
- DWG kết quả SHA-256: `32bf81ec55765b60899962468de28076a7100cd2b719a8e4f939aa9518ff73dd`.

Chạy lại khi server nội bộ đang mở:

```powershell
python scripts/verify_whole_file_edit_dwg.py
python scripts/verify_whole_file_edit_dwg.py --reopen storage/validation-fixtures/whole-file-edit-d55a996b13fe/receipt.json
```

Kiểm hồi quy: nhóm yêu cầu toàn file/native contacts/dependencies/jobs/review/atlas đạt 444 bài; nhóm planning/assembly/context/dataset đạt 314 bài. Sau bổ sung hai kiểm về refinement và chống trộn lựa chọn, nhóm yêu cầu toàn file đạt 23 bài. Tổng **760 bài Python khác nhau trong các nhóm này**; 21 bài được chạy lại, không cộng trùng. **13 script frontend đạt**. Không báo đây là lần chạy toàn bộ test suite.

PostgreSQL kiểm tra lại đã kết nối. DWG gốc Dauphine vẫn có SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`; DWG native revision cũ vẫn có SHA-256 `cc0b48deece01f5bd64f8cf82711b1a977a6c478b50f75d135c6b97aa4ae47a8`. Không sửa lại các artifact đó.

## Giới hạn còn lại

Một hồ sơ tổng hợp, hai mã chi tiết, tiếp xúc phẳng 2D và hình học đã được hỗ trợ. Chưa chứng minh suy luận mọi ý đồ thiết kế, cơ cấu 3D ẩn, mọi block động/XREF/proxy hoặc tự đọc mọi chuẩn BOM. Bộ dữ liệu vẫn 0/500 hồ sơ nghiệm thu kỹ sư. Tài khoản nhiều nhân viên, vận hành VPN và cơ chế chứng nhận/tự phát hành toàn công ty chưa hoàn thành.
