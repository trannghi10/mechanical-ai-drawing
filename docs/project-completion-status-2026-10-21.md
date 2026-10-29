# Trạng thái hoàn thành dự án, 21/10/2026

Cập nhật 22/10: [adapter native đã tích hợp revision/undo, PostgreSQL phục hồi](native-revision-release-2026-10-22.md). Hai đầu DIM `3DFA24`, `3DFA29` đã sửa tham chiếu trên revision riêng, giữ native B, qua 12 phép kéo và save/reopen; HTTP undo/redo/download/restart đạt. Các nhánh thử cũ chưa đạt vẫn bị khóa. Các mục ngày 21/10 bên dưới là trạng thái lịch sử; chưa khẳng định hỗ trợ mọi DWG hay hoàn chỉnh toàn sản phẩm.

## Phần đã hoàn thiện để dùng trong phạm vi đã kiểm

Đã có trang `/relationship-review` và API lưu/mở lại đề xuất sửa liên kết DIM, gắn hash nguồn/inspection/artifact/plan và preview nhóm sáu DIM. Đã kiểm HTTP thực, stale source/plan/artifact và logic giao diện. Chưa nối thực thi/revision/phát hành DWG từ trang này. Xem `relationship-review-release-2026-10-21.md`.

Luồng MVP rectangle đã có giao diện tìm/chọn nhóm, ý đồ giữ cạnh trái rõ ràng, point binding và solver, native writer/DIM sync, save/reopen, kiểm DXF độc lập, API local/APS, preview trước/sau, lịch sử job và tải DWG. Đã chạy local AutoCAD 2027 và APS AutoCAD 2025; cloud có chuỗi sửa 100→120→140 mm. Xem `rectangle-ui-release-2026-10-21.md`.

Các adapter đã có từ trước vẫn giữ phạm vi riêng cho hình học, DIM/BOM và liên kết được kiểm chứng. Không gộp kết quả của nhiều adapter thành cam kết sửa được mọi DWG hoặc đồng bộ toàn sản phẩm.

## Điều kiện để có thể tuyên bố hoàn thành mục tiêu ban đầu

| Hạng mục | Hiện trạng | Còn phải đạt |
|---|---|---|
| Quan hệ cơ khí | Native/DIMASSOC và các quy tắc có bằng chứng; geometric candidate; solver affine/phi tuyến trên mô hình điểm | Ghép bằng chứng vào intent/version, xử lý các liên kết thiếu dữ liệu và phân biệt ràng buộc cần giữ trên nhiều cấu trúc thực tế |
| Stretch | Rectangle một DIM dùng được; nhóm polyline–6 DIM có probe stretch 905→925/885 mm đạt save/reopen và 54/54 primitive; 8/12 đầu DIM có bằng chứng nguồn, chế độ native auto giữ/cập nhật hai đầu đã có vertex binding | Chứng minh 2 đầu native còn lại và 2 đầu thiếu liên kết, tích hợp operation; LINE writer theo binding, polyline bất kỳ/bulge và kiểm nghiệm nhánh/đảo hình |
| Đồng bộ sản phẩm | Nhiều quy tắc DIM/BOM/hình chiếu được kiểm riêng | Bao phủ toàn hình chiếu, chi tiết trong, công đoạn và đóng gói; backup toàn Dauphine còn thiếu |
| Đối tượng nâng cao | Một số block động/native đã hỗ trợ | Block động phức tạp, proxy/object enabler và các quan hệ native còn thiếu adapter |
| Sản phẩm sử dụng | MVP rectangle có UI/API/job history/download, source giữ nguyên | Tích hợp revision/undo/redo hình học cho operation mới, chỉnh tiếp ngay trong workspace, lựa chọn nhiều nhóm và thao tác còn thiếu |
| Chất lượng | Bộ test rộng, native round-trip và iterative cloud sample | Corpus DWG đa dạng có quyền sử dụng, regression theo loại, audit/database integrity và kiểm riêng AutoCAD 2026 nếu yêu cầu |

Audit riêng adapter rectangle trên Dauphine quét 1.221 DIM nhưng chưa có nhóm phù hợp; do đó không có cơ sở coi dự án trên Dauphine hoặc mục tiêu mọi DWG đã hoàn thành.

Đề xuất xốp được người dùng giữ ở trạng thái chưa xác nhận vẫn chỉ là đề xuất. Không dùng yêu cầu “hoàn thành dự án” để suy ra mã vật tư/điểm giữ hoặc biến liên kết chưa có bằng chứng thành xác nhận.

## Ưu tiên tiếp theo

Đã sửa thử hai đầu DIMASSOC thiếu liên kết trên bản sao; 15 bbox ngoài nhóm được tái hiện bằng no-op control và đối chiếu nội dung DXF/OLE. Hai DIM mới tự cập nhật 140→150 và 140→130 mm sau save/reopen, đối chứng chưa sửa không cập nhật. Bản đề xuất có 10/12 đầu có bằng chứng; nguồn khách hàng vẫn giữ nguyên 8/12. Chưa kiểm pixel hiển thị dung sai/OLE, hai đầu native còn thiếu và ý đồ toàn sản phẩm chưa xác nhận. Xem `dimension-relationship-repair-2026-10-21.md`.

Nhóm polyline–nhiều DIM đã có bằng chứng stretch cục bộ, kiểm từng primitive và hai native vertex binding, xem `polyline-six-dim-stretch-probe-2026-10-21.md` và `native-vertex-binding-proof-2026-10-21.md`. Tiếp theo đọc ý đồ/đầu DIM còn thiếu, tích hợp revision/preview và xem tác động đa hình chiếu/BOM. Các cấu trúc và DWG chưa hỗ trợ tiếp tục được báo rõ, không cố sửa chỉ để tăng tỷ lệ bao phủ.
