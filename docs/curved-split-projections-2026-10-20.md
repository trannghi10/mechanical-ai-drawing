# Chi tiết cong và hình chiếu bằng nét rời — 20/10/2026

## Chức năng đã bổ sung

- Nhận thân block cong qua STT/BOM, biên LINE + ARC hoặc polyline có bulge khép kín. Kiểm tra toàn thân và lỗ, mặt phẳng, đầu leader nằm trong vật liệu; từ chối nhiều mã cùng trỏ vào một thân, nét thừa, block con chưa phân loại và lỗ nằm ngoài thân. Định danh này chỉ dùng đối chiếu toàn bộ hình học nguồn; không tự cấp DIM hoặc suy ra mặt tiếp xúc ẩn.
- Đồng bộ giữa bản chi tiết có DIM và hình cụm không có DIM khi toàn bộ hình học cục bộ khớp một-một và hai hình đã có mã vật tư được xác định độc lập. Giữ loại entity, cung/bulge/bán kính và đường kính lỗ. Không chép DIM/ghi chú vào hình vốn không có chúng; DIM khác chưa gắn vẫn bị chặn.
- Đối chiếu mặt phẳng vẽ nghiêng có đường bao gồm nhiều LINE, POLYLINE hoặc LWPOLYLINE. Giữ các entity gốc; không nối khe hở hoặc chuyển ảnh thành nét thay thế. Một lỗ hoặc không có lỗ vẫn được xét, nhưng toàn bộ đỉnh biên và lỗ phải xác định đúng một phép đối chiếu. Hình đối xứng có nhiều cách gắn không được chọn tùy ý.
- Phân tách các mặt ghép bằng LINE dùng chung cạnh native: tất cả nét phải thuộc mặt kín, mọi mặt phải được đối chiếu, cạnh/đỉnh chung phải chuyển động giống nhau. Hai mặt chỉ tạo một thao tác trên cạnh chung. Nét treo, nét trùng, giao cắt cần sinh đỉnh mới, mặt chưa gắn hoặc kết quả mâu thuẫn đều không được chứng nhận.
- Giữ sai lệch tọa độ nhỏ có sẵn khi lan truyền thay đổi; chuẩn hóa đỉnh đóng lặp chỉ để đối chiếu, giữ topology/đỉnh gốc khi xuất. Kiểm tra lại độ phẳng và metric elip, kể cả trường hợp chỉ có một lỗ.

Các quy tắc chạy từ dữ liệu CAD/BOM của mỗi file. Không có nhánh mới theo tên Dauphine/MR-106, mã vật tư hoặc handle cố định trong mã thực thi.

## Kiểm tra trên tài liệu khách hàng thực tế

Đã đọc lại MR-106 và Dauphine với phạm vi của kế hoạch thực tế. Hash DWG/DXF nguồn được giữ nguyên; không gửi CAD khách hàng lên cloud.

| Trường hợp | Kết quả thực tế |
|---|---|
| Dauphine C1–C3 | Nhận thêm sáu block cong cho STT 8, 9, 11, 12, 14, 15. Cùng ba block thẳng trước đó, chín thân được nối với mã BOM; cả các bản chi tiết tương ứng tạo thành 15 occurrence có chủ sở hữu. |
| Dauphine, hình chiếu phẳng | Tăng từ một lên ba mặt có thể xét đối chiếu; chưa có phép chiếu nguồn–đích đủ điều kiện cho kế hoạch chiều cao/độ dày hiện tại. Không thêm thao tác hình học vào kế hoạch cũ. |
| MR-106, các khung cụm | Vẫn chưa có mặt đủ điều kiện. Các hình hở/biên chồng và mũi tên chưa gắn duy nhất cần được đối chiếu tiếp. |

**Chưa xuất hoặc nghiệm thu backup toàn Dauphine.** Nhận được mã cho chi tiết cong không chứng minh các mặt lắp, hình C4, phối cảnh hoặc đóng gói đã được sửa. Hai phép thăm dò trực tiếp bộ biên dịch với kích thước danh nghĩa cũng không tạo bản sửa: DIM thật của chi tiết cong đang khác BOM; đó không phải kiểm chứng chỉnh sửa thành công trên file khách hàng.

Bằng chứng đọc thực tế:

- `storage/validation-fixtures/curved-body-customer-audit-2026-10-20.json`
- `storage/validation-fixtures/curved-split-customer-audit-2026-10-20.json`
- `storage/validation-fixtures/curved-body-real-compiler-2026-10-20.json`

## Kiểm tra luồng website và DWG xuất

Ba DWG tổng hợp mới đi qua upload → nhận khung → yêu cầu 100 → 85 mm → tạo revision → AutoCAD xuất → tải HTTP 200 → ODA mở độc lập đo lại. Kiểm tra biên dạng, tâm lỗ, DIM thật theo tỷ lệ hình chiếu và nguồn không đổi.

| Cấu trúc | Bằng chứng |
|---|---|
| Mặt bất đối xứng ghép từ LINE, không có lỗ | `storage/validation-fixtures/projected-face-7e9a6d6f/receipt.json` |
| Mặt ghép từ LINE, một lỗ tròn/elip | `storage/validation-fixtures/projected-face-6e0b57e0/receipt.json` |
| Hai mặt dùng chung một LINE, bốn lỗ, hai DIM | `storage/validation-fixtures/projected-face-9acd4ff8/receipt.json` |

Trường hợp hai mặt đã mở preview, duyệt qua API website và tải bản backup. File duyệt có cùng SHA-256 với file đã mở bằng ODA đo đúng cả hai DIM 85 mm; cạnh chung vẫn là một LINE, toàn hình vẫn bảy LINE và bốn ELLIPSE. Các file kiểm tra được đánh dấu phụ trợ, ẩn khỏi thư viện mặc định. Chúng không thay thế tài liệu khách hàng.

- [DWG kiểm chứng hai mặt đã duyệt](../storage/validation-fixtures/projected-face-9acd4ff8/download/projected-backup.dwg)
- [Receipt](../storage/validation-fixtures/projected-face-9acd4ff8/receipt.json)
- [Mở phiên bản kiểm chứng trên website](http://127.0.0.1:8765/explorer?doc=ef7751856e204e3cb2ad9d6aea537d76&target=AF&revision=f9552436a79f4e53824369f664b1e7e3)

Chạy lại:

```powershell
python scripts/verify_general_dwg_workflow.py --projected-lines
python scripts/verify_general_dwg_workflow.py --projected-lines --projected-line-holes 1
python scripts/verify_general_dwg_workflow.py --projected-shared-seam --approve
```

## Cách sử dụng và giới hạn còn lại

Bộ kiểm thử toàn dự án: **1.559 bài Python đạt**, 216,01 giây; vẫn 19 module. Các hồi quy gồm biên hở/nhánh/nét trùng, cạnh chung mâu thuẫn, đối xứng thiếu điểm phân biệt, sai metric một lỗ, thay Z, bỏ thao tác đồng bộ, sai mã và thân cong có hình học không khớp. Log `storage/validation-fixtures/pytest-curved-split-final-2026-10-20.txt`.

Tải lại trang, chọn đúng khung/chi tiết rồi phân tích lại yêu cầu và tạo revision mới. Các bản sửa cũ không tự đổi nội dung hoặc được nâng trạng thái hoàn chỉnh. Hướng dẫn có trong `/help#mount-gap-projections`.

Chưa bảo đảm tự sửa đúng mọi DWG. Các mặt khuất, chiều sâu không có liên kết, nhiều cách đặt hình, đường cong tổng quát, mối hàn thiếu mốc và các lớp đóng gói chưa xác định vẫn cần quan hệ nguồn đủ rõ. Engine tiếp tục chặn duyệt backup toàn sản phẩm khi còn hình chưa đồng bộ.
