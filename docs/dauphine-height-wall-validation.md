# Dauphine: đồng bộ chiều cao và độ dày tấm ốp — 12/10/2026

Người dùng đã chốt giữ đáy/chân, hạ mặt trên 27 mm: thành phẩm 727 → 700 mm, khung tương ứng 724 → 697 mm. Lựa chọn được lưu theo hash nguồn trong `design-decisions-v1.json`. Bản kiểm chứng này mới sửa **tấm ốp cung và các bản chi tiết đi cùng**, chưa sửa toàn bộ khung/thành phẩm.

## DWG thật đã xuất và mở lại

- File xem trước: `storage/backups/Dauphine-PREVIEW-tam-op-cao697-day1.dwg`.
- Mã tấm ốp: `8.1.05417.258`; 66 thao tác CAD/BOM, nguồn giữ nguyên.
- Ba DIM chiều cao 724 → 697 mm; hình cạnh mỏng và hình chiếu cạnh cùng cao 697 mm. Hình cạnh mỏng dày 1 mm.
- Hai mặt cắt cung: R ngoài 406,5 giữ nguyên, R trong 405,5. DIM dày aligned trên cung đo thật 1 mm.
- Phôi có rãnh và bản cắt cùng cao 697 mm; bản cắt giữ vị trí định nghĩa native, khe trên thành 37 mm, khe dưới giữ 486 mm. Chưa tính lại chiều dài phôi theo uốn.
- 11 DIM góc được gắn lại vào các cạnh mới và tạo lại hình DIM; giữ nguyên góc nguồn. DIMASSOC bốn điểm của góc được kiểm tra trên endpoint thật, không tháo liên kết.
- BOM/quy cách tấm ốp thành `1x382x697x812`; ghi nguyên liệu 1×1220×2500 mm chờ cấp mã theo lựa chọn người dùng.
- SHA256 DWG: `14969ebcd7324c5a6434dd41e38f69f19c999c65fb386574460b5179a6bba0ca`.
- Biên nhận, plan, ảnh: `storage/validation-fixtures/dauphine-height-wall/2c37b0b3bdfe4bac9bbc0c6296901d25/`.
- Lặp lại: `python scripts/verify_dauphine_height_wall.py`.

Đây là **bản xem trước một phần, chưa duyệt**, không phải backup Dauphine hoàn chỉnh. Các handle cố định trong script chỉ đối chiếu đúng tài liệu kiểm chứng; engine không dùng handle Dauphine hardcode để sửa file khác.

## Cải tiến dùng chung

- Co/giãn đồng thời hai trục của cùng profile từ snapshot nguồn; kiểm tra kết quả không phụ thuộc thứ tự, giữ lỗ, phát hiện mâu thuẫn và phát ra một thao tác cuối cho mỗi entity.
- Ghép lệnh nhiều ý trên cùng chi tiết: tính lại geometry cùng nhau, ghép những trường số khác nhau trong BOM mà giữ nguyên chữ/format. Hai lệnh sửa trái nhau cùng trường vẫn bị chặn.
- Hình chiếu chữ nhật có DIM ngang nhưng thiếu DIM cao có thể theo hai mốc cao của hình chính khi cùng chi tiết/khung, căn thẳng hai đầu và quy cách BOM chứng minh chiều chung. Kích thước trung gian chỉ tồn tại trong engine, không tạo DIM giả vào CAD.
- Bản cắt không DIM được đồng bộ khi toàn bộ định nghĩa native ánh xạ một-một và cùng chủ sở hữu đã chứng minh; DIM khe hở chỉ theo những đỉnh CAD có chuyển động duy nhất.
- Nét trong kéo hết giữa hai đầu profile được sửa theo biên khi có chủ sở hữu nguồn duy nhất. Nét rời, cắt qua hoặc chưa rõ chủ sở hữu vẫn bị chặn.
- Nhận diện chuỗi công đoạn hàn → nhám → sơn qua mã/quy cách/sản phẩm/HDCV nguồn. Mã bulông 9.1… không bị nhầm thành sản phẩm. Đây là liên kết phạm vi, chưa tự chứng nhận hình học lắp ghép.
- Đọc đúng DIM aligned bằng khoảng cách Euclid kể cả khi thuộc tính angle nguồn bị thiếu/0. Hỗ trợ mặt cắt hai ARC và hai mép cắt hoặc hai ARC và sáu đoạn chân/mép.
- Nén chuỗi metadata lặp và format BOM có thể khôi phục chính xác; quy cách của các BOM liên quan còn được truy xuất theo table ref. Dữ liệu kiểm tra/sửa vẫn là toàn bộ nguồn. Context thực tế 72 khung còn đủ hơn 4k token đầu ra trong 32k.

## Chưa hoàn tất

Liên kết chiều cao của các thanh/tấm khác trong khung, hình cụm/phối cảnh, chiều dài triển khai sau uốn, toàn bộ 12 vật tư laser và thùng/xốp. Mục tiêu thùng 823 mm mới được đo từ khe nguồn, chưa có bản đóng gói hoàn chỉnh. Chưa thể khẳng định sửa mọi DWG bất kỳ.

Kiểm chứng cuối: 445 kiểm thử Python và 6 script JavaScript đạt; log `storage/validation-fixtures/pytest-height-stages-full-20261012.txt`. Context 28.264 token đầu vào, còn 4.248 token đầu ra trong 32k. Đã kiểm tra cả chữ trong block DIM sau mở lại: 1 mm và 11 góc 90°, tránh lỗi thư viện vẽ số chiếu 0,479 hoặc góc ngoài 270°.
