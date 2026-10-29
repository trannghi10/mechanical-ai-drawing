# Kiểm thử trên DWG công ty — 22/10/2026

Đã tạo bản sao nguyên byte từ DWG công ty, nhập lại bằng AutoCAD local 2027, tìm chi tiết qua hồ sơ toàn file và thử sửa qua API. Không tạo bản vẽ tổng hợp để thay thế dữ liệu thật. Không gửi CAD lên cloud, không duyệt sản xuất, không đổi DWG gốc.

Thư mục bằng chứng: `storage/validation-fixtures/company-whole-file-37ce7a8a4478`.

Cập nhật tiếp: [Dauphine — thành hộp trong block lồng](dauphine-nested-wall-2026-10-22.md) đã sửa thử 1,2→1 mm và nhập lại DWG đầy đủ độc lập; đủ 23.116 đối tượng cấp layout, giữ chiều dài thật và sáu OLE. Phạm vi quan hệ cơ khí vẫn là partial preview, chưa nghiệm thu toàn sản phẩm.

## MR-106: đã xuất toàn hồ sơ và mở lại độc lập

Nguồn: `9.1.07588(MR-106)-ver00.dwg`, 58.479.136 byte. SHA-256 `0b33a8e2561621f341d7693b6c1386bcfb9b3e141cdcc3ef038bcfd928f3c99b`. Nhập mới thành document `adca0491043c4105aeced9b94ca779be`, không dùng lại DWG tổng hợp hoặc sửa trên bản nguồn cũ.

Yêu cầu đã có xác nhận trước đó: mã `8.1.05940.126`, cả hai DIM thực tế về 15 mm và giữ tâm lỗ. Quyết định nguồn được ghi ở `design-decisions-v1.json` của document MR-106 cũ; không tự lấy 20 mm danh nghĩa trong BOM làm số đo hình học, không chuyển các quyết định mơ hồ của Dauphine sang đây.

API nhận yêu cầu với `whole_document=true`, không gửi ID khung. Hệ thống tự tìm đúng bản chi tiết `frame_40C7A5_404569` trong 20 khung và mở rộng danh mục đối chiếu sang 8 khung. Plan `4af911c1edea4a4084d3e1635c481513`, revision `fefe2e74f4a947a591ad90bb212b6095`.

| Kiểm tra sau tải DWG và nhập lại độc lập | Kết quả |
|---|---|
| Hai DIM đo thật | 20,2 → 15 mm |
| Biên dạng thực, đo tọa độ sau transform qua block lồng | 15 × 15 mm |
| Hai tâm lỗ/bán kính nguồn | Giữ nguyên, kiểm cả tọa độ WCS |
| Hai ô BOM native | `3x20x20` → `3x15x15` |
| Nhận lại mã từ DWG đã mở lại | Đúng `8.1.05940.126`, BOM mới và khung chi tiết |
| Kiểm tra mặt/lỗ | Hai mặt qua FreeCAD/OpenCASCADE đạt |
| Đối tượng không sửa trên bản toàn hồ sơ | 2.070 đối tượng kiểm đạt |
| Đối tượng cấp layout giữ lại | Đủ 2.199, không loại đối tượng ngoài khung sửa |
| Nội dung OLE nhúng | 10 payload nguyên byte; ba placeholder rỗng được kiểm riêng |
| DWG và DXF nguồn | SHA-256 giữ nguyên |

Các tên block ẩn `*U...` có thể được AutoCAD đánh số lại. Đối chứng chỉ chấp nhận đổi tên khi cùng block-record handle, cùng tập handle thành viên và cùng hình học/thuộc tính, kiểm đệ quy cả block lồng. Không bỏ qua mọi thay đổi block. Có kiểm âm: thêm thành viên hoặc thay tọa độ phải bị từ chối.

**Phạm vi kết quả mới:** đã xuất toàn document, không cắt khung; tập handle/loại/layout 2.199 đối tượng khớp nguồn. 2.070 đối tượng ngoài thao tác sửa qua đối chứng hình học/chữ/placement. Toàn bộ bảng được exporter kiểm dữ liệu native. OLE được đối chứng riêng cả payload, metadata và XDATA. Còn 9 ATTDEF, 52 LEADER, 2 ARC_DIMENSION và 6 DIM loại ngoài snapshot của bộ đối chứng độc lập chưa được gọi là đã kiểm đầy đủ mọi tính chất. Pixel hiển thị OLE và kích hoạt ứng dụng nhúng chưa kiểm.

**Lỗi xuất đã được xử lý trong luồng local:** `DxfIn` trực tiếp lỗi ở `read_source` ngay cả với DXF chưa sửa. Ba OLE rỗng thiếu header là dấu hiệu phân biệt. Thử chỉ thêm header giúp nhập được nhưng làm mất payload OLE khác; kết quả này đã bị chặn và job tải cũ được đánh dấu failed. Luồng hiện dùng ODA cục bộ chuyển nguyên DXF sang DWG, tắt audit/repair, sau đó AutoCAD lưu/mở native. Chốt kiểm từ chối trước sao chép kết quả nếu mất payload/metadata/XDATA hoặc đổi inventory. Mười OLE có nội dung giữ nguyên byte; ba placeholder có wrapper rỗng 128 byte. ODA chỉ dùng nội bộ, không gửi cloud. Receipt ghi rõ chuỗi converter và hash.

**Chưa đạt đồng bộ toàn sản phẩm:** bốn khung công đoạn/phối cảnh vẫn `unverified_projection_mapping`; xuất đủ hồ sơ không tự chứng minh chúng đã được sửa đúng. `complete_product_backup=false`, không duyệt sản xuất.

- [DWG toàn hồ sơ MR-106](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/mr106-document-after.dwg).
- [Kết quả nhập lại độc lập](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/mr106-verification.json).
- [Đối chứng ngoài thao tác sửa](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/mr106-outside-audit.json).
- DWG toàn hồ sơ SHA-256: `4d05cb784dfc87e7dbb9be04a7e67a910be90a8ad6d9c1663738d66eb0e3dc3c`.
- Document mở lại độc lập: `fd314057bbcb44378a1c134e2bdc00dd`.
- [Bản cắt trước đó](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/mr106-selection-after.dwg) và [receipt riêng](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/mr106-selection-verification.json) vẫn được giữ, không nhầm với bản toàn hồ sơ.

## LEG6949: đã lưu/mở và đo kiểm phần sửa có bằng chứng

Nguồn: `9.1.08326(LEG6949)-ver03.original.dwg`, 17.875.648 byte. SHA-256 `c4c7c634b155558d745800357d194bd250e060960e8393e43190dc8b519614d7`. Bản sao native: `349a82dab3824d2b8b8082eae9ee9af0`, tự nhận 54 khung và tìm đúng mã hộp `8.1.07011.002`.

Yêu cầu thử: thành hộp 2 → 1,2 mm, giữ kích thước ngoài/chiều dài, đối chiếu bas lắp trong theo khe hở nguồn. Engine đã tính được thay đổi hộp, các bas và bố trí phôi nhưng còn ba mã thiếu ràng buộc: `3.1.00766`, `8.1.07013.121`, `9.1.05415`. Toàn yêu cầu chưa được cho thực thi. Phần có đủ bằng chứng được thử bằng luồng checked preview riêng, không xác nhận giả các quan hệ còn thiếu.

Lượt apply preview đầu bị chặn ở DIMASSOC `43800F`, DIM `43800D`: số đo vẫn 2 mm nhưng cả hai điểm gắn trên cạnh phải dịch 0,4 mm khi bas dài ra. Giữ nguyên tọa độ DIM chỉ vì số đo không đổi làm liên kết native sai. Đã bổ sung đồng bộ theo endpoint/midpoint/center được chứng minh từ nguồn, không tìm cạnh gần nhất và không gỡ DIMASSOC. Nếu điểm native làm số đo khác kích thước được yêu cầu hoặc nằm trong vùng chỉ xem thì vẫn chặn.

Revision `04552a94e8294965bd45403ea7b72c17` đã xuất DWG bằng AutoCAD, tải xuống và nhập lại độc lập thành document `a69ddb3090d642668fb71ceffe1b32a4`. Receipt đo kiểm độc lập đạt:

| Kiểm tra trên DWG đã mở lại | Kết quả |
|---|---|
| Bốn cặp cung trong/ngoài tiết diện hộp | Thành 2 → 1,2 mm; cung ngoài giữ nguyên |
| Hình/DIM bas lắp trong | 25,6 → 27,2; 45 → 45,8; 10,6 → 11,4; 55,6 → 57,2 mm |
| DIM native `43800D`, `438084`, `4380FA` | Vẫn 2 mm, cả hai điểm gắn bám đúng cạnh mới theo DIMASSOC |
| Ô BOM native | 20 ô khớp quy cách hộp và bốn bas sau sửa |
| Nhận lại mã từ toàn DWG kết quả | Đúng `8.1.07011.002`, thành hộp mới 1,2 mm |
| Đối chứng ngoài thao tác sửa trong phần giữ lại | 2.468 đối tượng đạt |
| DWG/DXF nguồn và bản sao đầu vào | Hash giữ nguyên |

**Phạm vi:** đây là checked partial preview theo các khung đã chọn, không phải toàn hồ sơ hoặc toàn yêu cầu. Khi xuất đã loại 88.775 đối tượng cấp layout ngoài phạm vi; chín thành viên block cũng nằm trong danh sách loại đã kiểm. 16 block khung được cô lập bằng mapping handle, từng thành viên giữ lại được đối chiếu hình học/chữ/thuộc tính; không coi tên block khác là lỗi hoặc bỏ qua toàn bộ block. Ba HATCH, 10 MULTILEADER, 20 LEADER và một bảng ngoài các ô sửa chưa được bộ đối chứng độc lập kiểm toàn bộ tính chất. Năm khung hình cụm vẫn `unverified_projection_mapping`; ba mã thiếu ràng buộc vẫn chặn thực thi toàn yêu cầu.

- [DWG LEG6949 theo phạm vi sửa](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/leg6949-selection-after.dwg).
- [Receipt mở lại và đo độc lập](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/leg6949-verification.json).
- [Đối chứng ngoài thao tác sửa](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/leg6949-outside-audit.json).
- SHA-256 DWG kết quả: `ccd3e06be0c78f78ebfae22e393ed4feffd66a94776a9359fd6e538c818c8521`.

### LEG6949: bổ sung hình chiếu trên bản đọc AutoCAD

Đã tìm nguyên nhân các mapping cũ không chạy trên bản đọc native mới: mapping gắn SHA DXF do bộ chuyển đổi cũ tạo. Hai document thực sự chứa cùng DWG byte-for-byte. Đã đối chiếu 377 tham chiếu CAD dùng trong adapter, gồm handle/path, owner, geometry, thuộc tính và đơn vị; chỉ sau đối chiếu mới đăng ký biến thể đọc nguồn. Registry gắn cả SHA template lẫn SHA DXF và DWG; thay template hoặc nguồn khác làm mất hiệu lực bằng chứng. Đây là khôi phục binding đã kiểm trên đúng nguồn, không phải tự suy luận mọi hình chiếu mới.

26 snapshot elip cũ thiếu trường extrusion; đã bổ sung từ CAD nguồn sau khi kiểm mọi trường đã lưu còn khớp. Không bỏ trường extrusion khỏi bộ kiểm để làm kế hoạch qua.

Plan mới `c77bd7efc40541a49a89b3a11268df16`, revision `56fb8ab223f449b19436d0647539ea9a`: 41.913 thao tác, trong đó 329 thao tác hình chiếu/cạnh lắp đã được đo lại từ DXF sau AutoCAD lưu/mở DWG. Bao gồm phối cảnh tách hộp, bas, mép lỗ bị che, đoạn hàn, mũi tên leader và các cạnh bổ sung có ràng buộc nguồn. Bốn khung `43BC13`, `43BD0D`, `43BF49`, `43C372` đạt mapping; khung `43C2FE` vẫn chưa đạt. 20 ô BOM, thành hộp 1,2 mm và DIMASSOC tiếp tục qua kiểm.

- [DWG LEG6949 mới có hình chiếu liên động](../storage/validation-fixtures/company-native-projections-b981bdb1ba61/leg6949-selection-after.dwg).
- [Đo kiểm sau native save/reopen](../storage/validation-fixtures/company-native-projections-b981bdb1ba61/leg6949-native-readback-verification.json).
- [Bằng chứng còn thiếu của ba mã](../storage/validation-fixtures/company-native-projections-b981bdb1ba61/remaining-relationships.json).
- SHA-256 DWG mới: `ddfbe30fe1df2648803329c01b513b8521122075f5f20e958dc738f77c3f16fd`.

Bản mới `ddfbe...` đã được tải rồi nhập lại bằng AutoCAD thành document độc lập `ccfbbc557d704cf481af906c113b987f`. [Receipt nhập lại độc lập](../storage/validation-fixtures/company-native-projections-b981bdb1ba61/leg6949-verification.json) đạt: hình học, DIM, 20 ô BOM, 329 thao tác hình chiếu, DIMASSOC và đối chứng ngoài vùng sửa. Sáu DIM follower giữ đúng số đo cũ trong khi điểm gắn đi theo hình; ba DIM bổ sung có số đo hiển thị 1 mm do tỷ lệ nguồn, không phải mất cập nhật. Phạm vi vẫn là partial preview, các quan hệ chưa đủ bằng chứng chưa được duyệt.

MR-106 cũng đã qua [lượt lưu/mở lặp](../storage/validation-fixtures/company-whole-file-37ce7a8a4478/mr106-repeat-save-open.json) từ DXF đã có đủ header OLE: policy 3, 13 đối tượng OLE giữ nguyên payload/metadata/XDATA, bảng native khớp và 2.081 đối tượng ngoài vùng sửa kiểm đạt. Máy chủ đã nạp bản cập nhật mới. Lượt này kiểm khả năng lưu tiếp bản kết quả, không thêm phạm vi đồng bộ cơ khí.

Các mã còn chặn toàn yêu cầu:

| Mã | Bằng chứng đã có | Chưa đủ để sửa |
|---|---|---|
| `3.1.00766` | Ống nối ren 6.3, phi 9,5 × 12; bốn hàng BOM | Chưa gắn duy nhất hình học, mặt lắp, mốc giữ và chuyển động |
| `8.1.07013.121` | Mã cụm sơn và liên kết công đoạn hàn/nhám | Chưa chứng minh hình học và phạm vi tác động ở công đoạn sơn/khung `43C2FE` |
| `9.1.05415` | Tán rút M1/4 × 15 D9,9; bốn hàng BOM | Chưa gắn duy nhất hình học tán, lỗ/mặt tiếp xúc và quy tắc giữ/dịch |

Đợt kiểm luồng công ty trước đó đạt **722 bài Python**; nhóm kiểm bổ sung runner đạt 42 bài. Đợt mở rộng bộ sửa nhiều DWG sau đó đạt **873 bài Python liên quan**, có báo cáo riêng trong multi-dwg-size-rules-2026-10-22.md. Đây không phải toàn bộ suite hoặc nghiệm thu kỹ sư. Nguồn MR-106 và LEG6949 vẫn khớp SHA ban đầu.

## Các sửa đổi phát hiện từ kiểm thử thực tế

- “Sửa cả hai chiều” và cơ sở DIM/BOM là phần giải nghĩa của yêu cầu kích thước, không bị tách thành lệnh khác.
- “Giữ kích thước ngoài và chiều dài” không bị hiểu thành một lệnh đổi chiều dài; nhận được cách viết “độ dày hộp từ 2 thành 1,2”.
- Ghi nhớ lựa chọn hai chiều/DIM đặt trong `linear-decisions-v1.json` cho luồng toàn file. Việc nhớ lựa chọn không làm chính hồ sơ vừa đọc bị lỗi thời; quyết định hình học/cuboid vẫn nằm trong tệp có kiểm thay đổi nguồn. Cache mới chỉ được nạp cho đúng SHA và chỉ nhận lựa chọn linear_resize.
- DIMASSOC phải theo cạnh dù số đo giữ nguyên. Bộ kiểm nguồn và kiểm sau ghi tiếp tục được giữ.
- Bộ kiểm thử công ty bắt buộc CAD nhập/xuất local và AI local, từ chối cấu hình chuyển sang cloud.
- DXF chứa OLE được chuyển qua ODA cục bộ rồi AutoCAD lưu/mở và kiểm nguyên payload, metadata, XDATA trước khi sao chép artifact. Bao phủ cả DXF đọc lại từ DWG đã lưu; bản xuất cache thiếu bằng chứng bảo toàn OLE bị từ chối.

Các kết quả là kiểm hình học/nguồn trong phạm vi đã nêu, chưa phải nghiệm thu kỹ sư, chưa chứng nhận cơ tính hoặc tự phát hành toàn công ty. Lựa chọn xốp `3.8.01312 / 745→718` vẫn chưa được xác nhận và không được dùng làm ca sửa trong đợt này.
