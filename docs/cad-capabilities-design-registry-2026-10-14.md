# Kiểm kê khả năng CAD và hồ sơ chi tiết — 14/10/2026

Đã triển khai phần đầu của phương án mở rộng cho DWG mới. Đây là chức năng kiểm kê và chuẩn hóa dữ liệu nguồn, **chưa hoàn thành sửa đúng mọi DWG hoặc backup toàn sản phẩm Dauphine**. Không đổi thuật toán nhận diện/chọn khung, model AI, khóa API hoặc công cụ trả phí.

## Cập nhật 16/10: cụm theo BOM và STT cục bộ

### Quy tắc đọc mặc định cho các DWG mới

Đã đưa quy ước người dùng xác nhận vào `rules/mechanical_bom.py`, hồ sơ `mechanical-bom-assemblies-v1`. Đây là hướng dẫn có cấu trúc được nạp vào mỗi lượt lập kế hoạch, không phải huấn luyện lại trọng số. Áp dụng chung cho native/Ollama và các provider cloud khi được chủ động chọn; không đổi cấu hình model hoặc gửi dữ liệu ra cloud.

Thứ tự bắt buộc trong hướng dẫn: BOM đang chọn/mã chi tiết → cụm cha–con/nhóm được bao phủ → STT/leader cục bộ → hình có chủ sở hữu/DIM thật → mặt lắp/khe hở/mốc giữ đã xác minh → các hình gia công/BOM/đóng gói chịu ảnh hưởng → kiểm tra bản sửa. Ví dụ nhận dạng chỉ dùng ký hiệu minh họa, không cung cấp kích thước hoặc mã vật tư để sao chép sang file khác.

Sửa luồng chia trang CPU để AI truy xuất được cấu trúc mới: `assemblies`, `assembly_members`, `products`, `balloons`, `assembly_chunks`. Hỗ trợ `assembly_id`, `part_number`, `target_id`, `part_code` và con trỏ offset. Ưu tiên BOM đang chọn; trường lớn lấy theo mảnh JSON để không mất thành viên. Trang metadata không cấp quyền sửa hình học; ô BOM và nét CAD vẫn cần ref nguồn. Hồ sơ đọc được lưu trong design model và kế hoạch mới; các quan hệ số đã xác nhận vẫn lưu riêng theo hash CAD hiện có.

**1.173 kiểm thử Python đạt.** Bài kiểm tra bằng model qwen3-vl:4b-instruct thật, chạy nội bộ, phân biệt STT 1 của BOM tổng với STT 1 của BOM con: trả đúng `PLATE-B` / `BOM-CHILD` và không xác nhận rigid attachment chỉ từ đồng cụm. Bài tổng hợp nhỏ dùng 550 input tokens, 11,52 giây; đây không phải thời gian xử lý DWG sản xuất. Receipt `storage/validation-fixtures/mechanical-profile-native-lesson-2026-10-16.json`.

API thật trên #3D337A nhận hồ sơ mặc định; trang CPU ưu tiên đúng BOM #3D2DE4, 2.685 byte, giữ nguồn 1.433 entities tại server và 9 nhóm/75 dòng thành viên trong graph. Hash CAD không đổi. Receipt `storage/validation-fixtures/mechanical-profile-live-2026-10-16.json`; hồi quy `storage/validation-fixtures/pytest-mechanical-profile-release-2026-10-16.txt`. Tải lại trang và phân tích lại yêu cầu để dùng hồ sơ mới; kế hoạch đã lưu không tự trở thành bản sửa hoàn chỉnh.

Quy tắc đọc và bài nhận dạng đúng chưa chứng minh suy được mọi mặt lắp, phương trình, hình phối cảnh hoặc backup toàn Dauphine. Không dùng thống kê này làm nghiệm thu sửa mọi DWG.

- Mỗi BOM đã xác minh là một nhóm nguồn, gắn với table ref, layout, instance path và khung chứa. Từ hai dòng chi tiết trở lên được phân loại `assembly_bom`; một dòng có số lượng lớn vẫn là `part_bom`. Giữ STT, mã, mô tả và số lượng riêng cho từng BOM.
- Mã cụm xuất hiện trong BOM cấp trên xác lập quan hệ cụm cha–con. Tên block/thuộc tính mã đã xác minh hoặc mã cụm trong khung tên giúp xác định chủ sở hữu. Không suy quan hệ chỉ từ hai nhóm dùng chung một chi tiết.
- BOM tổng liệt kê phẳng được đối chiếu với các nhóm cùng mã sản phẩm: `covered_assembly_ids` chỉ ra những nhóm có tập thành viên nằm trong BOM đó. Đây là bằng chứng bao phủ dữ liệu, không tự gán hình học của các chi tiết cho một owner hay coi chúng là liên kết cứng.
- Tìm ứng viên bản vẽ tổng bằng độ bao phủ chi tiết lá sau khi mở các cụm con. Đóng gói là miền riêng. Hai BOM cùng đầy đủ được báo `ambiguous_main`, cần đối chiếu bản chính thức. Hỗ trợ cả nhãn mã sản phẩm/mã cụm tiếng Anh/Việt ngoài mẫu mã 9.x.
- Nối ký hiệu STT với đúng BOM theo scope, layout và thứ bậc instance. Số trùng trong các cụm khác nhau không được nhập thành một chi tiết. Nếu hai BOM cùng phù hợp hoặc STT trùng trong một BOM, báo mơ hồ. Vòng tròn/leader vẫn là bằng chứng cần đối chiếu, không tự chứng minh contour/mặt lắp.
- Đọc ACAD_TABLE lồng trong block với ref/mirror ref đầy đủ và vị trí qua ma trận instance; giữ việc loại khung gạch bỏ. Bảng nét kẻ lồng giữ thêm tên/thuộc tính container để định vị cụm.
- Khi sửa một mã, đồ thị đưa các thành viên cùng cây cụm vào phạm vi kiểm tra. `assembly_candidate_codes` được tách khỏi các mã đã có quan hệ ảnh hưởng; các khung chỉ dùng đối chiếu vẫn ở chế độ review. STT/cùng BOM không tạo phương trình co giãn. Prompt nhận cấu trúc rút gọn, không thêm toàn bộ vector hay cell vào model.

Giao diện: **Kiểm tra dữ liệu bản vẽ → Hồ sơ chi tiết và hình biểu diễn → Lập hồ sơ CAD đã chọn**. Phần **Cụm chi tiết theo bảng kê** có bảng thành viên, ứng viên bản vẽ tổng và nút **Xem khung cụm**. Mở khung đối chiếu giữ nguyên bản vẽ đang áp dụng yêu cầu. Hướng dẫn trong ứng dụng tại `/help#assemblies`.

**Kiểm chứng cuối: 1.163 kiểm thử Python và 8 script frontend đạt**, giữ 19 module kiểm thử. Hai DWG tổng hợp vẫn qua AutoCAD nhập/xuất → duyệt → tải HTTP 200 → ODA mở lại đo đúng và kiểm tra BOM, nguồn bất biến (`storage/validation-fixtures/parameter-links-dwg-88651a80/receipts.json`).

Trên Dauphine, graph đọc được 9 BOM; khi chọn #3D337A, hồ sơ hiển thị 28 mã chi tiết và 7 nhóm cụm gồm nhóm tổng cùng 6 nhóm được bao phủ. Có hai ứng viên BOM tổng nên không tự chọn bản chính thức. Trình duyệt đã mở đúng khung #39B233 và giữ yêu cầu ở #3D337A; không có lỗi JavaScript trong lượt kiểm tra. Nguồn giữ nguyên hash. Receipt: `storage/validation-fixtures/assembly-dauphine-read-2026-10-16.json`; ảnh: `storage/validation-fixtures/assembly-ui-2026-10-16.png`; hồi quy: `storage/validation-fixtures/pytest-assembly-release-2026-10-16.txt`.

Đây là phần nhận diện cấu trúc cụm và phạm vi liên quan. Hồ sơ của khung BOM được chọn chưa gắn được biên dạng có DIM thật; 35 khung chi tiết vẫn cần mapping đo được. Chưa hoàn tất mọi liên kết lắp/chiếu/uốn/đóng gói, backup toàn Dauphine hoặc sửa đúng mọi DWG.

## Đã triển khai

- `cad/capabilities.py` kiểm kê thực thể trong các layout và định nghĩa block; đếm mỗi định nghĩa một lần, giữ số lượng layout riêng. Phân loại có adapter nhưng cần ràng buộc, chỉ đọc và cần CAD host/adapter riêng. Đọc tên lớp/object, XREF và tài nguyên ngoài; không tự mở đường dẫn tài nguyên ngoài từ file tải lên.
- Nhận diện block động, block tham chiếu vòng, proxy, extension dictionary và association chưa hỗ trợ. Phạm vi sửa xét đầy đủ đường dẫn block cha. Kiểm tra lại trực tiếp nguồn ngay trước apply, kể cả khi bên gọi không đưa metadata khả năng CAD.
- Các đối tượng chưa hỗ trợ ngoài phạm vi thao tác không tự chặn chi tiết khác. Giữ ngoại lệ đã kiểm chứng: dịch nguyên instance có dictionary tĩnh được bảo toàn; sửa DIMASSOC/metadata roundtrip vẫn qua các bộ kiểm tra chuyên biệt hiện có. Phân loại không cấp quyền bỏ qua kiểm tra hình học, clone, BOM hoặc liên kết.
- `graph/design_model.py` tạo hồ sơ nguồn theo mã vật tư: giữ các dòng BOM/cell/số thứ tự cục bộ, hình biểu diễn có DIM thật, instance/frame tọa độ, công đoạn và bằng chứng. Không gom số thứ tự giống nhau ở các bảng thành cùng chi tiết. Mâu thuẫn quy cách, hình chưa gắn DIM, chủ sở hữu mơ hồ và ghi chú liên kết chưa có quy tắc đều được báo rõ.
- Hồ sơ có hash nguồn và phạm vi; từ chối graph thuộc nguồn khác. Snapshot được lưu theo hash nguồn, phạm vi, phiên bản và cache nhận diện. Không đưa toàn bộ chỉ mục khả năng/hồ sơ vào prompt: AI chỉ nhận tóm tắt; hình học đầy đủ và danh sách kiểm tra vẫn ở server.

## Giao diện và API

Mở lại trang Explorer để nạp giao diện mới:

1. Mở **Khả năng xử lý CAD của file này** dưới thông tin file. Xem số lượng, nguyên nhân cần adapter riêng và phân trang; có nút kiểm tra lại.
2. Chọn bản vẽ, mở **Hồ sơ chi tiết và hình biểu diễn**, bấm **Lập hồ sơ CAD đã chọn**. Bước này dùng dữ liệu CAD nguồn, không gọi model AI.

API dùng chung cho tài liệu mới:

- `GET /documents/{id}/cad-capabilities?offset=0&limit=30` (giới hạn tối đa 200).
- `POST /documents/{id}/design-model`, JSON `{"ids":["mã khung/block đã chọn"]}`; nhận từ 1 đến 4 mục hợp lệ, giống luồng đọc bản vẽ.

Kết quả cũ không được ghi đè giao diện khi đổi file hoặc đổi bản vẽ trong lúc yêu cầu đang chạy. Tên và ghi chú nguồn được hiển thị bằng text, không thực thi HTML từ tài liệu.

## Kiểm chứng

- **787 kiểm thử Python đạt**, gồm 21 kiểm thử mới về khả năng CAD và hồ sơ nguồn. Kiểm tra riêng hồ sơ sau bổ sung trường instance cũng đạt.
- 5 script kiểm tra JavaScript đạt: định dạng/fit/BOM, điều hướng, tải file, tiến trình phân tích, và các điều khiển kiểm kê/hồ sơ mới. Đây là kiểm tra logic giao diện; không thay thế nghiệm thu thị giác trong trình duyệt.
- Bộ kiểm kê chạy trên 4 tài liệu thực tế, hash nguồn không thay đổi:

| File | Đối tượng lưu trong layout/block | Định nghĩa block | Thời gian kiểm kê lạnh |
|---|---:|---:|---:|
| Dauphine | 41.578 | 1.457 | 5,508 giây |
| MR-106 | 10.750 | 469 | 7,059 giây |
| Sample_recover | 16.393 | 1.044 | 1,672 giây |
| LEG6949 | 122.642 | 1.468 | 17,127 giây |

Thời gian gồm đọc DXF nguồn trên máy này; không phải thời gian chỉnh sửa/xuất DWG. Kiểm kê thành công không chứng minh hiểu/sửa đúng toàn bộ thiết kế. API kiểm kê và hồ sơ đã thử trên Dauphine, MR-106 và Sample_recover; phạm vi thiếu mã/chủ sở hữu/DIM vẫn được trả về chưa xác định.

395 thao tác của kế hoạch xem trước Dauphine hiện tại vượt kiểm tra khả năng CAD mới. Không tạo thêm DWG trong đợt này; file xem trước vẫn là bản một phần đã đo kiểm trước đó, không đổi thành backup hoàn chỉnh.

Bằng chứng tại:

- `storage/validation-fixtures/pytest-design-registry-shipped.txt`
- `storage/validation-fixtures/cad-capabilities-real-documents.json`
- `storage/validation-fixtures/design-registry-api-real-documents-final.json`
- `scripts/verify_frontend_capabilities.js`

## Còn phải làm

- Chuyển hồ sơ sang bộ tham số/ràng buộc thực thi thống nhất và bổ sung thao tác chọn mặt/mốc trên hình. Hồ sơ hiện tại là chỉ mục nguồn; chưa tự giải quan hệ cơ khí thiếu bằng chứng.
- Tái tạo các hình chiếu/công đoạn/phối cảnh còn thiếu; hoàn tất C4, Detail C cong và toàn bộ đóng gói Dauphine, rồi mở lại đúng DWG tải xuống để nghiệm thu.
- Adapter CAD gốc cho tham số block động và proxy/association tùy biến; máy chưa có CAD host chỉnh sửa đã được xác minh. ODA File Converter vẫn chỉ đảm nhận chuyển đổi.
- Bộ nghiệm thu nhiều DWG sản xuất độc lập, có đáp án kỹ thuật. Bốn lần kiểm kê trên không thay thế bộ nghiệm thu chỉnh sửa toàn sản phẩm.
