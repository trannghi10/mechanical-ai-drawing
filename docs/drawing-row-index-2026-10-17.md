# Nhận diện nhóm cụm và chi tiết trong toàn DWG — 17/10/2026

## Quy ước được người dùng xác nhận

Nhãn khoanh tròn C1, C2… ngoài khung chỉ nhóm cụm theo hàng. Nhãn số như 16, 17, 18 chỉ nhóm bản vẽ của một chi tiết. Những khung cùng hàng có thể là hình chiếu hoặc công đoạn khác nhau. Tên, mã vật tư, BOM, ký hiệu STT và hướng dẫn gia công trong từng khung phải được đối chiếu trước khi sửa.

## Đã triển khai

- `cad/row_groups.py` quét chú thích qua mọi layout và các cấp INSERT được đặt; giữ đường dẫn instance, tọa độ thật, nhãn/vòng tròn, đường dẫn ký hiệu và đầu mút. Kiểm kê cả định nghĩa block chưa đặt, nhưng không gán tọa độ definition thành một chi tiết thực tế.
- Nhãn ngoài khung được nối với chuỗi khung cùng hàng; tách theo layout, nhãn bắt đầu nhóm mới, khoảng ngắt lớn và mã sản phẩm được ghi rõ. Nhóm chồng lấn được đánh dấu mơ hồ. Khung bị gạch bỏ hoặc loại khỏi phạm vi không được đưa vào nhóm.
- Dùng tâm bounding box chữ để nhận diện nhãn trong vòng tròn, tránh bỏ sót chữ C2/C3/C4 có điểm chèn sát mép vòng.
- Đọc TEXT, MTEXT, ATTRIB, chú thích MULTILEADER dạng MTEXT và leader; lưu toàn bộ chữ trong từng khung, mô tả công đoạn và ref của ghi chú. Nội dung CAD luôn là dữ liệu nguồn, không phải lệnh thực thi.
- Ký hiệu bên trong nhóm được khớp với BOM cục bộ. Có thể dùng BOM của khung cùng hàng trong một cụm để đối chiếu hình công đoạn kế tiếp. Một hàng của chi tiết riêng không thừa hưởng STT bất kỳ từ BOM tổng. STT trùng hoặc mơ hồ không được ép thành mã duy nhất.
- Chỉ mục được tạo khi mở file trên giao diện và trước bước lập kế hoạch sửa; cache theo hash nguồn và cấu hình nhận diện/loại bỏ. Hai yêu cầu đồng thời dùng lại chỉ mục sau khi tác vụ đầu hoàn tất.
- Nhóm hàng giúp mở rộng phạm vi kiểm tra công đoạn/hình liên quan. Nó không tạo quan hệ rigid attachment, mốc giữ hay công thức co giãn.
- AI nội bộ có các trang `row_groups`, `row_frames`, `row_markers`, `row_bindings`, `row_chunks`. Dữ liệu đầy đủ giữ trên server, truy xuất theo `row_group_id`, không nhồi toàn bộ chữ/tọa độ vào context 8k. Các trang giữ con trỏ và hỗ trợ tái tạo trường lớn đầy đủ.

## Cách xem

Mở ứng dụng, nhấn Ctrl+F5, mở **Cấu trúc cụm và chi tiết trong toàn file**. Cụm được xếp trước, có ảnh từng khung, **Mô tả / công đoạn** và bảng ký hiệu → mã vật tư. Nút **Mở khung** mở đúng CAD để đối chiếu; giữ phạm vi yêu cầu hiện tại.

API: `GET /documents/{document_id}/row-groups`. Hồ sơ thiết kế và đồ thị ảnh hưởng cũng mang chỉ mục này. Các nút tạo/tải DWG và điều kiện duyệt hoàn chỉnh tiếp tục dùng luồng hiện có.

## Bằng chứng thực tế

Đã chạy trên Dauphine, LEG6949, MR-106 và Sample_recover. Hash DWG/DXF nguồn được đối chiếu trước/sau và không thay đổi. Receipt: `storage/validation-fixtures/document-rows-multi-file-2026-10-17.json`.

Dauphine có 1.457 block definitions, 1.392 INSERT được đặt (gồm lồng), 39.917 entities trong definitions và 45.007 lượt entity trong cây đặt. Các con số có cách đếm khác nhau. Chỉ mục nhận 25 nhóm và 119 ký hiệu khoanh tròn:

| Nhóm | Khung đang dùng | Đối chiếu trong nhóm |
|---|---:|---|
| C1 | 2 | STT 8/9/10 → ba mã trong BOM cụm |
| C2 | 2 | STT 11/12/13 → ba mã trong BOM cụm |
| C3 | 2 | STT 13/14/15 → ba mã trong BOM cụm |
| C4 | 3 | Hai ký hiệu → hai mã trong BOM cụm |
| 16 | 4 | Cùng mã 8.1.05417.258 |
| 17 | 2 | Khung gạch bỏ không được lấy |
| 18 | 2 | Khung gạch bỏ không được lấy |

LEG6949 có hai nhóm hàng nhận diện được. MR-106 và Sample_recover chưa có nhóm hàng ngoài khung được xác nhận theo bộ nhận diện này; các BOM/khung vẫn được đọc bằng luồng hiện có. Không báo số 0 thành bằng chứng đã hiểu cấu trúc của chúng.

Ảnh giao diện: `storage/validation-fixtures/document-row-groups-ui-2026-10-17.png`. Kiểm tra trình duyệt xác nhận ảnh C1 tải được, bảng STT/BOM đúng và nút mở khung #3AAABC giữ yêu cầu cho #3D337A.

Model `qwen3-vl:4b-instruct` nội bộ thật đã đọc metadata C1 và trả đúng hai khung, STT 8/9/10 → 8.1.06126.196 / 8.1.06127.196 / 8.1.06128.196; không suy rigid attachment từ đồng cụm. Thời gian đo 18,92 giây. Đây là kiểm tra đọc metadata, không phải kiểm chứng sửa hình học. Receipt `storage/validation-fixtures/document-rows-native-ai-2026-10-17.json`.

Bộ cuối đạt **1.204/1.204 kiểm thử Python**, 7 script frontend đạt. Log `storage/validation-fixtures/pytest-document-rows-final-2026-10-17.txt`. Kiểm thử có block lồng sâu, vòng lặp, layer ẩn, nhãn lặp, sản phẩm khác, khung gạch bỏ, STT cục bộ, MULTILEADER và phân trang/tái tạo ghi chú dài trong ngân sách model.

## Giới hạn

### Bước kế tiếp: nối leader với hình học nguồn

Hồ sơ CAD bổ sung `leader_profile_bindings`: đối chiếu BOM trong nhóm, chữ STT, vòng tròn và LEADER/LINE nguồn trong cùng khung/layout. Đầu còn lại được kiểm tra với đường bao kín và DIM thật sau khi chuyển về tọa độ layout. Đường bao chưa có DIM cũng tham gia kiểm tra trùng; không chọn hình gần nhất. Nét thẳng rời được định vị riêng bằng khoảng cách điểm–đoạn chính xác. Nguồn khác hash, STT mơ hồ, nhiều đường bao, nhiều đầu mút hoặc mã native khác BOM không được coi là chuỗi xác nhận. Liên kết cong chỉ là ứng viên để kiểm tra chính xác thêm.

Trong hồ sơ CAD, mở **STT → leader → hình CAD** để xem trạng thái và mở khung tương ứng. AI nội bộ lấy trang `leader_profiles` theo khung, nhóm, mã hoặc STT; các tọa độ và thực thể nguồn vẫn truy xuất riêng. Kết quả này chưa xác lập chủ sở hữu cơ khí, mặt tiếp xúc hoặc quyền tự sửa. Các gate sửa/duyệt backup được giữ.

Trên C1–C4 Dauphine (chín khung), nhận 18 biên dạng có DIM nhưng cả 11 ký hiệu đã khớp BOM vẫn chưa nối được tới đường bao/DIM hoặc nét thẳng chính xác. Không dùng kết quả thử tổng hợp để tuyên bố đã sửa được các cụm này. Receipt `storage/validation-fixtures/leader-profiles-dauphine-2026-10-17.json`, nguồn không đổi.

Bảng đề xuất trên giao diện đã rút còn hai cột, chỉ hiển thị quy cách đổi; mô tả đầy đủ và ghi chú nằm trong một mục mở rộng dưới bảng. Những trường hợp không thể rút gọn mà giữ nguyên nghĩa vẫn hiển thị toàn nội dung. Ảnh `storage/validation-fixtures/compact-proposals-ui-2026-10-17.png`.

Chưa thể suy ra đầy đủ chủ sở hữu từng nét hình học chỉ từ một vòng tròn, một leader hay cùng hàng. Đầu mút leader là bằng chứng để tiếp tục gắn hình; mặt lắp, khe hở, mốc giữ, hình cong/phối cảnh và công nghệ uốn vẫn phải được kiểm chứng. Proxy hoặc MULTILEADER chứa block chưa có binding được báo rõ; không âm thầm coi là đã đọc đủ. Đợt này không sửa hình học DWG khách hàng và không tạo backup toàn Dauphine.

AutoCAD 2027 và các thư viện CAD/AI nội bộ đang có đủ cho phần chỉ mục này; chưa cần cài thêm ứng dụng hoặc mua API.

Kiểm tra sau bước đối chiếu leader/giao diện: **1.212 kiểm thử Python đạt**, 7 script frontend đạt; log `storage/validation-fixtures/pytest-leader-profiles-ui-final-2026-10-17.txt`. Các trường hợp mới gồm block quay/tỷ lệ, đầu leader nằm trong hình nhưng không chạm biên, đường bao chồng chưa có DIM, nét rời, nguồn khác hash và không tự nâng liên kết chú thích thành quyền sửa.

## Cập nhật tiếp: mũi tên chỉ vào vùng vật liệu

Bộ đọc kiểm tra cả đầu mũi tên nằm bên trong đường bao, không chỉ chạm biên. Đường cong được định vị bằng locator có chặn sai số; điểm sát dải sai số vẫn chưa được xác nhận. Khung giấy, bảng và lỗ tròn được loại khỏi vùng vật liệu. Các vùng chồng nhau, mã mâu thuẫn hoặc nhiều đầu mũi tên vẫn bị chặn gán chủ sở hữu.

Khi vùng **thẳng, kín**, có **DIM đo thật** và **dòng BOM native/graphic được đọc lại duy nhất**, chuỗi nguồn có thể cấp quyền sở hữu riêng đường bao đó (`local_bom_leader_profile`). Quyền này chưa xác lập tiếp xúc, khe hở, mốc giữ hay quan hệ giữa các hình chiếu. Khi sửa chiều dài, engine giữ nhãn ngoài và cập nhật riêng đầu mũi tên theo hình. Chỉ mục chữ kiểm tra lại tâm glyph trong vòng tròn bằng tọa độ native. Khung có BOM nhiều thành viên không được dùng tên cả cụm làm mã của mọi hình con.

Dauphine C1–C4 hiện định vị **9/11 ký hiệu**: 6 vùng cong chưa có DIM gắn hình và 3 vùng thẳng gắn được mã/DIM. Hai ký hiệu 19/20 ở C4 chưa có vùng kín phù hợp. Source hash không đổi; đây chưa phải sửa toàn cụm hay backup hoàn chỉnh. Receipt `storage/validation-fixtures/leader-interior-dauphine-2026-10-17.json` thay cho trạng thái 11 chưa nối được của bước trước.

File thử riêng có nhãn C1, BOM, STT, LEADER và block chưa mang mã đã được đọc bằng parser thật, sửa 100 → 76 mm, xuất bằng AutoCAD rồi mở lại. Hình, DIM và BOM đều 76 mm; đầu mũi tên theo hình, điểm nhãn ngoài và dòng BOM khác giữ nguyên. DWG nguồn thử và receipt nằm trong `storage/validation-fixtures/balloon-interior-native-2026-10-17/`; không dùng file này thay backup Dauphine. Bộ kiểm thử cuối **1.219 Python và 7 script frontend đạt**, vẫn 19 module test.
