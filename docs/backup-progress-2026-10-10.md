# DWG 2D — tiến độ kiểm chứng ngày 10/10/2026

**Đã có DWG xem trước mới; chưa phải backup đồng bộ hoàn chỉnh.** Chỉ dùng dữ liệu 2D có sẵn, không yêu cầu file 3D và không gửi CAD lên dịch vụ ngoài.

## Bổ sung lắp khung v3

DWG mới: `storage/backups/LEG6949-PREVIEW-lap-khung-v3.dwg`, **18.421.261 byte**, DWG 2018. Plan `1a66c229c8974eb6a0389425ed5f98e4`, revision `a10d894e9657460dbf708e5d907c533b`, **39.572 thao tác**, chưa duyệt. File gốc không đổi.

- Bas 3 trong hình hàn phóng to: dựng lại 53 entity native gồm biên bo R3,8, lỗ Ø10,5, thành trong minh họa R2,8 và sáu đoạn ký hiệu hàn. Hàn giữ chiều dài/pitch, dịch theo mép bas; không kéo giãn vòng tròn hàn. Các đường phía sau lỗ được cắt lại bằng giao điểm elip; giữ tâm lỗ và hai mặt dày 2 mm.
- Hai khung công đoạn bổ sung 18 cạnh hình chiếu: bas đáy dài 57,2/rộng 27,2; bas 2 dài 11,4/rộng 27,2; bas 4 dài 444,5; thành trái vốn minh họa 3 mm được đưa về 1,2.
- Engine thêm 12 LINE native riêng cho bas ở các vị trí bản nguồn gộp nét với thành hộp. Thêm cạnh ràng buộc khung kín, style nguồn cùng layout, phạm vi chọn, tọa độ hữu hạn và hash nguồn; không ghi lại toàn bộ DXF. Entity gốc, bảng và definition ngoài phạm vi được giữ nguyên. DWG mở lại phải giữ handle, owner, layer và geometry của mọi cạnh mới.
- Audit thực tế sau DWG → DXF: **224 thao tác hình chiếu**, **17 DIM** và **12 chiều dài cạnh lắp** đạt; **41 bảng native**, **1.343 CIRCLE nguồn giữ nguyên**, **30 CIRCLE ký hiệu hàn được dịch có binding rõ ràng và giữ bán kính**. Không dùng quy tắc gần nhau để di chuyển lỗ gia công.
- **243 kiểm thử Python đạt**; JavaScript đạt. HTTP tải DWG trả 200 và trùng byte với backup; SHA-256 DWG `5936d1cc8ddee97352b8d2407d9e0d1275c4a6e4cfe03b7fbc8240ca0381088b`.
- FreeCAD vẫn chỉ kiểm tra ba solid và lắp tiết diện bas 3, chưa kiểm tra toàn bộ cụm hoặc độ bền.

**V3 vẫn chưa phải backup hoàn chỉnh.** Khung `43BD0D` còn bas 1/mối hàn ở bậc, các hình cụm cắt đoạn và một số cạnh ống trong hình đáy. Khung `43BF49` còn hình cụm đã hàn và Detail C. Không thêm hai khung này vào `complete_sheets`, không duyệt hoặc bỏ chặn xuất cuối. Mốc giữ bas 1 vẫn chờ lựa chọn của người dùng; v3 giữ dài 45 mm, chưa tự áp phương án dịch 0,8 hay tăng dài 45,8.

[Mở bản v3 công đoạn 2](http://127.0.0.1:8765/explorer?document=baf461e9c2764a5ba9000a48772f846c&revision=a10d894e9657460dbf708e5d907c533b&target=43BD0D).

## Bổ sung đối chiếu và thứ tự vật tư

- Giao diện có bảng STT/mã vật tư/quy cách trước và sau. STT theo BOM gốc; không đổi số balloon. Cụm tổng mặc định hiện đủ 9 vật tư theo STT 1–9, trong đó 5 vật tư thay đổi; có nút chỉ hiện các dòng đã sửa.
- Mỗi vật tư chỉ hiện một dòng trong bảng so sánh, không lặp theo số vị trí cập nhật. Phần đề xuất chi tiết cũng gom theo STT số tự nhiên (1, 2, …, 10).
- “Xem thay đổi” mở vùng hình học native trên bản chi tiết gia công. Chữ kích thước được ẩn riêng trong vùng phóng để không che nét; bản vẽ đầy đủ vẫn giữ toàn bộ DIM/BOM.
- “Trước sửa / Sau sửa / Chồng nét thay đổi” dùng cùng vùng và cùng tỷ lệ CAD. Đỏ là nét cũ, xanh là nét mới, xám giữ nguyên. Màu này chỉ phục vụ đối chiếu trên trình duyệt, không ghi vào DWG sản xuất.
- Đối chiếu kiểm tra hash nguồn và bản sửa trước khi render; bảng kê thay đổi được đối chiếu lại ô native. Xem một vùng phóng không được tính là đã duyệt toàn bộ khung.
- Bản SVG được lưu theo hash để chuyển trước/sau nhanh hơn. Không thay đổi thuật toán nhận diện khung hoặc loại khung gạch đỏ.
- Kiểm thử sau bổ sung: **234 kiểm thử Python đạt**, JavaScript kiểm tra thứ tự STT/gom dòng/tô đủ con số đạt. Đối chiếu 5 chi tiết × 3 chế độ trả SVG qua HTTP; kết quả lưu `storage/validation-fixtures/current-comparison-http-check.json`.
- Ảnh trình duyệt kiểm tra: `storage/validation-fixtures/material-order-browser.png`, `storage/validation-fixtures/wall-change-browser.png`.
- Lần này bổ sung giao diện và đối chiếu; không đổi hình học DWG v2 hoặc tuyên bố hai khung lắp còn thiếu đã hoàn tất.

## File thực tế

- `storage/backups/LEG6949-PREVIEW-2D-hop1.2-bas-congdoan-v2.dwg`: 18.421.571 byte, DWG 2018 (`AC1032`).
- Document `baf461e9c2764a5ba9000a48772f846c`.
- Plan `3408278880b044a1b998af6c0fb161e7`: 39.499 thao tác.
- Revision `73a40bc4084c4ebbb0adc946f76261e7`, chưa duyệt.
- [Mở xem trước](http://127.0.0.1:8765/explorer?document=baf461e9c2764a5ba9000a48772f846c&revision=73a40bc4084c4ebbb0adc946f76261e7&target=43C372).

File gốc giữ nguyên. SHA-256 DXF nguồn: `3f1c8d90be4d3e8d858b15abfd017f17ae20c2dd323863e2af63fe983685662b`.

## Phần bổ sung đã thực thi và đọc lại từ DWG

| Hình | Đã sửa/kiểm tra | Còn thiếu |
| --- | --- | --- |
| `43C372`, cụm tổng | Thành trong hộp; cạnh bas 4 rộng 27,2 mm được tách khỏi cạnh thành hộp; giữ lỗ | Chưa xác nhận toàn bộ lắp/độ bền |
| `43BC13`, công đoạn 1 | Bas 4 ở hình chiếu và phối cảnh; DIM 27,2 và nửa bề rộng đo thật | Chưa xác nhận toàn bộ lắp/độ bền |
| `43BD0D`, công đoạn 2 | Hộp tách, bas 1 và bas 3 tách, mặt cắt R5/R3,8, ba thành trong, DIM dày 1,2; Detail B tỉ lệ 3:1 | Bas trong hình chiếu dọc; hai hình cụm cắt đoạn và hình phóng to mối hàn bas 1/3 |
| `43BF49`, công đoạn 3 | Hộp tách, bas 2 tách, bas 4 tách rộng 27,2/dài 444,5; mặt cắt và ba thành trong, DIM dày 1,2 | Các bas trong hình chiếu dọc, hình cụm đã hàn và Detail C |

Có **151 thao tác hình chiếu/đường dẫn** được đối chiếu lại trên entity native sau DWG → DXF, tăng từ 59 của lần trước. Hai mũi tên LEADER gắn với cạnh dịch chuyển cũng được cập nhật; đầu vòng tròn số chi tiết giữ nguyên. Hình bas tách dùng DIM/BOM chi tiết để sửa lại các hình minh họa nguồn: bas 2 nguồn minh họa dài 15 mm, trong khi DIM chi tiết gốc là 10,6 mm và kích thước mới là 11,4 mm. Không dùng số đo pixel.

Hệ chiếu kiểm tra ma trận trực giao, tọa độ điểm nguồn và metric cung elip. Độ sâu/mặt phẳng của điểm được đăng ký từ CAD; ma trận ảnh không tự chứng minh độ sâu. Bas bo được dựng lại đường thẳng, cung và tiếp tuyến; giữ tâm lỗ, lỗ bas 3 minh họa sửa về Ø10,5 theo bản chi tiết. Detail B giữ đường tròn biên phóng to và tính lại giao điểm đường thành trong với biên đó.

Các góc ngoài minh họa khác góc gia công được phân biệt: hình hộp tách dùng R4 ngoài, nên góc trong minh họa thành R2,8 khi thành 1,2; mặt cắt gia công R5 ngoài/R3,8 trong giữ theo CAD có DIM. Bas bo gia công và hình tách mới dùng R3,8.

## BOM, gia công và kiểm tra

Giữ các thay đổi đã kiểm chứng ở bản trước: hộp 1,2×30×60×571,5; bas 1 là 2×27,2×45; bas 2 là 2×11,4×27,2; bas 3 là 2×27,2×57,2; bas 4 là 2×27,2×444,5. Góc bo bas 1/2/3 R3,8. Bốn BOM và bốn bản cắt đồng bộ; số phôi lần lượt 2465/8240/1960/286, tấm 1250×3000 không đổi.

Audit độc lập đo **17 DIM native**, bề rộng bas 4 trong block cụm tổng **27,200000 mm**, chiều dài bas 4 tách **444,500000 mm**. Audit đi theo handle mới của block được tách riêng sau sửa, không đọc nhầm definition nguồn chưa dùng. Cả **41 bảng native** và **1.373 CIRCLE nguồn** được bảo toàn. FreeCAD/OpenCASCADE kiểm tra ba solid; bas 3 nằm trong tiết diện hộp, phần giao nhau **0 mm³**. Kiểm tra này chưa xác nhận mọi vị trí lắp hoặc mối hàn.

Sửa lỗi chọn nguồn kiểm tra: các mặt cắt hộp trên bản công đoạn có BOM nhiều chi tiết không được chọn thay bản chi tiết gia công. Có regression kiểm tra trường hợp hai mặt cắt cùng kích thước và cùng được sửa.

**228 kiểm thử Python đạt**; kiểm tra JavaScript về vừa khung/gom thay đổi đạt. Giao diện đã mở revision mới, hiển thị một bản vẽ công đoạn tại một thời điểm. Nút tải DWG trả HTTP 200; byte nhận từ API trùng hoàn toàn file backup. Xuất cuối trả HTTP 422 khi chưa duyệt. Ảnh kiểm tra: `storage/validation-fixtures/backup-2D-congdoan-v2-browser.png`.

Báo cáo máy đọc:

- `storage/validation-fixtures/current-preview-state.json`
- `storage/validation-fixtures/current-preview-measurements.json`
- `storage/validation-fixtures/current-preview-http-check.json`
- `storage/validation-fixtures/rounded-companion-backup-check.json`

## Điều kiện còn phải giải quyết

Hai khung công đoạn `43BD0D`/`43BF49` vẫn chưa hoàn tất. Không được bỏ chặn duyệt cuối chỉ vì mặt cắt, BOM và bản cắt đã đúng. Phải gắn từng bas vào mặt lắp của các hình cắt đoạn/phóng lớn, dịch đường hàn theo cạnh mới và kiểm tra chéo các hình chiếu.

Đã gửi câu hỏi chốt mốc giữ của **bas 1 tại bậc hộp**: giữ đầu bas ở mốc 47 mm và tăng dài 45 → 45,8 mm để tiếp xúc thành trong mới, hoặc giữ dài 45 mm rồi dịch bas 0,8 mm. Đây là hai phương án bố trí cần chốt trước khi dựng lại hình lắp và mối hàn; **DWG xem trước hiện vẫn giữ bas dài 45 mm**, chưa áp một trong hai phương án. Không tự coi người dùng im lặng là đã chọn.

Adapter hiện ràng buộc SHA-256 của mẫu LEG6949. Toán chiếu và engine chỉnh CAD có thể tái sử dụng, nhưng file khác cần bằng chứng sở hữu chi tiết, mặt lắp và mốc giữ riêng. Chưa có bộ tự giải mọi DWG 2D hoặc đảm bảo chất lượng chịu lực của mọi thay đổi.
