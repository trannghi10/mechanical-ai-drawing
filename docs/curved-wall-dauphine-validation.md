# Dauphine: mặt cắt tấm ốp cung và số đo đóng gói — 12/10/2026

Bản mới đã áp dụng mốc giữ đáy và chiều cao tấm ốp 697 mm: xem [biên nhận chiều cao/độ dày mới](dauphine-height-wall-validation.md). Nội dung dưới đây là lần kiểm chứng chỉ đổi độ dày trước đó.

Đã áp dụng lựa chọn người dùng: giữ biên ngoài R406,5 và vị trí lắp; chỉnh biên trong khi đổi tấm 1,5 → 1 mm. Lựa chọn gắn với SHA256 của DXF nguồn, không áp dụng sang file khác.

## Chức năng mới

- `cad/curved_wall.py` tính lại mặt cắt kín gồm hai ARC đồng tâm và sáu LINE. Giữ cung/chân ngoài, tính giao điểm cung trong với mặt cắt nguồn, dịch chân trong, nối mép và cập nhật DIM đo thật. Không xấp xỉ cung bằng đoạn thẳng hoặc ghi đè số DIM.
- `curved_wall_planner.py` nhận lệnh đổi độ dày một chi tiết, tìm đường bao theo mã native/khung chi tiết có chủ sở hữu duy nhất, kiểm tra mốc ngoài, cập nhật BOM và quy cách khung nguồn. Không có handle Dauphine hardcode trong planner. Nhiều mặt cắt ứng viên, thiếu mốc hoặc sai chủ sở hữu không được đoán.
- Đã sửa lỗi `chi tiết 8.1.05417.258` bị hiểu thành STT 8. Mã có dấu chấm và số bóng gọi chi tiết được phân biệt.
- Proposal/revision có `forming_review`; giao diện hiển thị phần phôi uốn chưa kiểm chứng và khóa duyệt backup hoàn chỉnh. API kiểm tra lại điều kiện này từ nguồn khi duyệt/xuất. Bản xem trước vẫn có thể thể hiện mặt cắt đã sửa.
- `graph/packing_envelopes.py` đọc toàn bộ block thân/đỉnh chữ nhật và DIM thùng để đối chiếu chiều cao thành phẩm đã chốt. Đây là số đo nguồn, chưa phải thao tác tự sửa toàn bộ đóng gói.

## DWG khách hàng đã sửa và mở lại

File: `storage/backups/Dauphine-PREVIEW-mat-cat-tam-op-cung-t1.dwg`.

- Nguồn: document `34ee84f35e1a44fb81c56044397a0fff`, SHA256 `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.
- Planner `checked_curved_wall`; mã `8.1.05417.258`; 9 thao tác CAD/BOM/quy cách.
- Đã xác nhận sau DXF → DWG → DXF: R ngoài 406,5, R trong 405,5; đường bao kín, BOM tấm 1 mm; nguồn không đổi.
- SHA256 DWG: `5fb049317469543593006f43b68fc12fc939286b12dcc802e00ae3cd82804521`.
- Biên nhận/plan/ảnh: `storage/validation-fixtures/dauphine-curved-wall/340192a60d2344be95a334afed7bd109/`.
- Đây là **preview riêng mặt cắt và bảng kê**, chưa duyệt và **không phải backup hoàn chỉnh Dauphine**. Chiều cao trên preview vẫn 724 mm; các vật tư khác trong bảng vẫn là nguồn.

Lặp lại bằng `python scripts/verify_dauphine_curved_wall.py`. Script dùng planner chung để nhận diện; handle cố định chỉ dùng đối chiếu kết quả của nguồn kiểm chứng.

## Đóng gói đọc được từ CAD Dauphine

Khung `3E5E8C`, block thân `3E5DB5`: thân cao 724 và lớp đỉnh 3 mm, thành phẩm tổng 727 mm. Thùng `3.8.02293` có chiều cao nguồn 850 mm, DIM `3E5DF3`; khe hai đầu đo được đều 61,5 mm. Với thành phẩm 700 mm, chiều cao thùng theo cùng khe là **823 mm**.

Biên nhận: `storage/validation-fixtures/dauphine-packaging/measured-envelope.json`; lặp lại bằng `python scripts/audit_dauphine_packing_envelope.py`. Nhận diện đã kiểm tra với block có vị trí chèn khác gốc; không so tọa độ local với tọa độ world.

Con số 823 chưa được áp dụng lên toàn bộ bản đóng gói. Xốp hai bên nguồn đo 745 và 743 mm, hình thùng/phối cảnh/tách rời chưa đủ binding. Không coi khe của một hình lắp là chứng nhận cho mọi vật tư đóng gói.

## Còn phải hoàn thành

- Mốc giữ chiều cao đã chốt: giữ đáy/chân, hạ mặt trên 27 mm. Kết quả áp dụng mới ở báo cáo liên kết phía trên.
- Liên kết phôi triển khai với mặt cắt sau uốn và quy tắc chiều dài/bend allowance khi đổi độ dày.
- Đồng bộ đủ 12 mã tấm laser, mọi hình cụm/phối cảnh/công đoạn và thùng/xốp Dauphine trong một revision.

Chưa thể tuyên bố tự sửa mọi DWG bất kỳ. Các kiểm tra mới mở rộng một nhóm hình học có bằng chứng nguồn; không giải bài toán lắp ghép hoặc độ bền tổng quát.
