# Bảo toàn nhóm HATCH và DIMASSOC — 21/10/2026

Engine đã mở rộng việc tạo block riêng khi HATCH và đường bao còn liên kết với DIMASSOC. Cả HATCH, đường bao, DIM, dictionary sở hữu và đối tượng DIMASSOC được giữ thành một nhóm không thay đổi. Chỉnh sửa đối tượng độc lập khác không còn bị chặn chỉ vì trong cùng block có nhóm này.

Đây là adapter bảo toàn liên kết, chưa cho phép co/giãn hoặc sửa thành viên của nhóm HATCH–DIMASSOC. Liên kết khác ngoài nhóm vẫn phải có adapter riêng.

## Bằng chứng nguồn và cách sao chép

`cad/dimension_preservation.py` mở toàn bộ liên kết DIMASSOC từ reactor của biên HATCH. Nó kiểm tra DIM cùng definition, dictionary chỉ chứa ACAD_DIMASSOC, owner hai chiều, reactor và các điểm nguồn được `source_binding` đo lại độc lập. Biên thiếu, owner khác, dictionary ngoài phạm vi, điểm đo không được chứng minh hoặc reactor lạ đều bị chặn.

`cad/block_isolation.py` đưa cả dictionary và DIMASSOC vào ánh xạ handle, rồi sao chép các tag gốc sang OBJECTS. Các đối tượng gốc không thay đổi. Mọi thao tác sửa HATCH, biên hoặc DIM trong nhóm đều bị từ chối ở adapter bảo toàn này.

Sau ghi và khi xuất, engine kiểm tra lại association_ref, source_refs, điểm đo native và handle HATCH/biên/reactor. Nó không coi hai đối tượng cùng hình học là cùng danh tính.

## DWG kiểm chứng

Lệnh `python scripts/verify_cuboid_projection.py --confirm-uncoded --dimassoc-hatch` đã qua website đọc DWG → xác nhận fixture → phân tích → sửa → xem trước → duyệt fixture → AutoCAD xuất → tải HTTP 200 → ODA mở lại.

- Hình hộp độc lập đổi 2×80×100 → 2×80×76 mm; DIM nguồn 100 → 76 mm và BOM đạt kích thước đích.
- Đỉnh đã chọn, đủ 9 LINE và camera trực giao được giữ.
- Trong cùng block, HATCH liên kết biên LWPOLYLINE và vùng chừa MTEXT. Biên LWPOLYLINE còn có DIM native đo 20 mm qua DIMASSOC. Nhóm này giữ nguyên hình học và toàn bộ liên kết sau tách block/xuất/mở lại.
- File gốc giữ hash. Ghi chú chưa có bằng chứng chủ sở hữu trong block hỗn hợp vẫn giữ nguyên; receipt ghi rõ `projected_note_verified=false`.
- Receipt: `storage/validation-fixtures/cuboid-projection-ade957f9/receipt.json`.
- DWG: `storage/validation-fixtures/cuboid-projection-ade957f9/download/cuboid-backup.dwg`.
- SHA-256: `1b3c329de2f45607a7ce2d1b5b5374ada3c16aeb93dd57e269d147296011df6b`.

Thư viện preview có thông báo copy DIMASSOC không hỗ trợ trong đối tượng dựng hình tạm. Kết quả CAD giao dịch dùng sao chép raw tag; biên nhận trên kiểm tra DIMASSOC còn tồn tại với đúng handle và binding trong DWG mở lại, không dùng preview làm bằng chứng giữ liên kết.

## Dauphine

Audit chỉ đọc `storage/validation-fixtures/hatch-dimassoc-dauphine-2026-10-21.json` xác nhận 15/15 HATCH association đủ điều kiện adapter bảo toàn nguyên nhóm. Trong definition từng bị chặn có bốn DIM và tám đối tượng sở hữu (dictionary/DIMASSOC) đã có ánh xạ nguồn rõ.

Số liệu này không chứng minh toàn bộ block được cô lập: definition còn có LEADER và reactor của chú thích cần adapter riêng. Đối chiếu tiếp cho thấy definition chứa bốn HATCH/DIMASSOC này không có INSERT hay ACAD_TABLE nào tham chiếu trong nguồn hiện tại; không coi nó là điểm chặn đang hoạt động trên các hình khách. Audit phân biệt số definition với số instance tham chiếu. Không tự tạo revision khách từ audit. Nguồn giữ hash `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af`.

Đề xuất tấm xốp vẫn chưa xác nhận theo quyết định người dùng; không lưu liên kết danh tính/mốc giữ. Backup toàn sản phẩm, phối cảnh bị che, mặt lắp thiếu dữ liệu và các loại đối tượng chưa có adapter vẫn chưa hoàn thành.

## Kiểm thử

39 bài HATCH tập trung đạt (`storage/validation-fixtures/pytest-hatch-dimassoc-focused-2026-10-21.txt`). Có kiểm tra biên mất/khác owner, reactor thiếu, dictionary lạ, cố sửa DIM và trường hợp hợp lệ giữ nguyên instance không chọn. Một fixture lỗi owner ban đầu bị thư viện chuẩn hóa khi lưu; bài test đã sửa để thực sự chuyển DIM sang layout khác trước khi kiểm tra từ chối.

Bộ kiểm thử toàn dự án cuối đạt **1.697 bài**, 244,49 giây. Log `storage/validation-fixtures/pytest-hatch-dimassoc-release-2026-10-21.txt`. Backend đã nạp adapter hiện tại.
