# Quan hệ cơ khí trên DWG mới — 23/10/2026

Mục tiêu là đọc quan hệ từ từng hồ sơ mới người dùng tải lên. Không dùng tên file, mã vật tư, handle hoặc kích thước của các bản mẫu làm quy tắc sản phẩm. Phần vừa bổ sung giải được một lớp quan hệ lắp ghép phẳng có bằng chứng nguồn; **chưa hoàn thành khả năng hiểu mọi DWG hoặc nghiệm thu toàn công ty**.

Người dùng đã chốt phạm vi: **chỉ cần DWG cơ khí 2D, không yêu cầu 3D**. Các giới hạn liên quan mô hình 3D không phải hạng mục còn thiếu để nghiệm thu. Vẫn cần hiểu quan hệ cơ khí được thể hiện trong các hình vẽ 2D trên toàn hồ sơ.

Cập nhật tiếp: [đã bổ sung DIM khe hở và kiểm liên động giữa bản chi tiết/hình lắp ở nhiều khung hoặc Model/Layout](linked-2d-clearances-2026-10-23.md). Bốn DWG mới đã qua luồng web và nhập lại AutoCAD độc lập. Các số liệu dưới đây ghi nhận đợt trước khi mở rộng này.

## Thay đổi trong luồng sản phẩm

- Định danh chi tiết vẽ rời bằng chuỗi BOM cục bộ → STT → balloon/leader → đường bao kín → DIM đo thật. Đọc lại dòng BOM để kiểm chứng mã, tránh lấy STT ở cụm khác hoặc chỉ dựa trên hình giống nhau.
- Lập mô hình quan hệ trước khi có yêu cầu sửa: thành viên hình học, lỗ, DIM, mặt tiếp xúc và phương trình giữ tiếp xúc. AI lấy được quan hệ này qua trang dữ liệu nguồn; giao diện hiển thị các cặp chi tiết và khe đo được.
- Khi đổi kích thước một chi tiết có mốc giữ, giải chuyển vị của các chi tiết nhận theo các phương độc lập. Dịch đường bao, lỗ và DIM của chúng; đầu leader đi theo hình, balloon/STT giữ nguyên vị trí. DIM tổng được ánh xạ lại theo cạnh nguồn.
- Tái tạo và đối chiếu toàn bộ thao tác/ràng buộc trước thực thi. Thiếu thao tác, sửa sai hình hoặc bỏ ràng buộc sẽ bị từ chối. Hình chưa xác định quan hệ được kiểm như vật cản đứng yên; không tự coi là thành viên cần kéo.
- Sửa lỗi nhận dạng: hai polyline kín chung đỉnh/mặt vẫn là hai đường bao riêng. Mạng LINE phân nhánh chưa xác định được vòng kín duy nhất vẫn bị chặn.
- Sửa nhận diện tiêu đề tiếng Việt không dấu như `BAN VE LAP`; đổi phiên bản cache hồ sơ khi quy tắc khung thay đổi để không tái sử dụng danh mục cũ.

Mã chính: [bộ giải quan hệ vẽ rời](../graph/flat_contacts.py), [dịch hình học](../cad/rigid_translation.py), [đường bao kín](../cad/closed_profiles.py), [mô hình nguồn](../graph/design_model.py), [kiểm thử](../tests/test_flat_contacts.py).

## Kiểm chứng thực tế bằng AutoCAD local

Ba hồ sơ dưới đây là **DWG tổng hợp mới, mã/kích thước sinh độc lập**, không phải hồ sơ sản xuất của công ty. Mỗi ca đi qua: tạo DWG nguồn bằng AutoCAD → tải DWG mới lên website → yêu cầu tìm mã toàn file không chỉ định handle/khung → lập kế hoạch → revision → xuất toàn hồ sơ DWG → nhập lại bằng AutoCAD độc lập và đối chiếu hình học.

| Ca | Hình nguồn | Đổi chiều dài | Kết quả |
|---|---|---|---|
| 934 | Polyline, cụm ba chi tiết | 124,5 → 147,5 mm | Đạt lưu/mở lại và đo kiểm |
| 2147 | LINE rời, cụm xoay 27° | 86,5 → 109,5 mm | Đạt lưu/mở lại và đo kiểm |
| 9411 | Polyline chung đỉnh/mặt | 76,5 → 99,5 mm | Đạt lưu/mở lại và đo kiểm |

Mỗi ca giữ đầu dưới; hai chi tiết nhận dịch 23 mm trong hệ trục cụm. Đã kiểm đường bao, lỗ, DIM riêng, DIM tổng, đầu leader, vị trí balloon, đối tượng ngoài nhóm và hash nguồn. Ca 9411 có DIM tổng sau sửa 187,5 mm; hai DIM riêng 55 mm và 33 mm giữ nguyên. Tất cả chạy cục bộ, không dùng cloud; chưa cấp chứng nhận hoặc phát hành sản xuất.

- [Manifest và kết quả đo](../storage/validation-fixtures/unseen-loose-relations-2026-10-23/run.json)
- [Mô hình nguồn: ba chi tiết, hai tiếp xúc](../storage/validation-fixtures/unseen-loose-relations-2026-10-23/source-mechanical-model.json)
- [DWG nguồn ca 9411](../storage/validation-fixtures/unseen-loose-relations-2026-10-23/9411/unseen-input.dwg) / [DWG sau sửa](../storage/validation-fixtures/unseen-loose-relations-2026-10-23/9411/after.dwg)
- [Hình trước sửa](../storage/validation-fixtures/unseen-loose-relations-2026-10-23/before.png) / [hình sau sửa](../storage/validation-fixtures/unseen-loose-relations-2026-10-23/after.png)
- [Ảnh giao diện đọc quan hệ từ DWG mới](../storage/validation-fixtures/unseen-loose-relations-2026-10-23/mechanical-model-ui.jpg)
- [Script kiểm chứng có checkpoint](../scripts/verify_unseen_loose_relations.py)

## Hồi quy

- Lượt toàn bộ Python cuối: **2.178 passed**, 2.777 cảnh báo chủ yếu từ thư viện parsing, 495,56 giây. [Log](../storage/validation-fixtures/pytest-mechanical-relations-final-2026-10-23.txt).
- Sau các bổ sung cuối cho metadata/giao diện: nhóm liên quan **204 passed** và nhóm trang dữ liệu **120 passed**; đây là các lượt có phần trùng nhau, không cộng thành tổng. [Log liên quan](../storage/validation-fixtures/pytest-relations-final-focused-2026-10-23.txt), [log trang dữ liệu](../storage/validation-fixtures/pytest-relations-pages-2026-10-23.txt).
- **16 script frontend đạt**, gồm đếm/hiển thị quan hệ và xử lý tên CAD an toàn. [Log](../storage/validation-fixtures/frontend-loose-relations-final-2026-10-23.txt).
- Các kiểm âm chặn quan hệ thiếu bằng chứng, BOM không khớp, thay đổi bị sửa lệch, ràng buộc bị bỏ và va chạm vật cản; kiểm dương có hình xoay, co/ngắn và polyline chung đỉnh.

Các lượt thử ban đầu đã phát hiện lỗi khung/cache và lỗi kiểm thử; số liệu ở trên là sau khi sửa. Không coi các lượt lỗi ban đầu là bằng chứng thành công.

## Phạm vi còn thiếu

Adapter mới cần đường bao thẳng kín, mặt phẳng XY, đơn vị mm, DIM tuyến tính phù hợp và chuỗi định danh cục bộ đủ bằng chứng. Chưa giải tổng quát block động, XREF, proxy, hình cong hoặc mạng LINE chung cạnh phân nhánh; các adapter cũ có phạm vi riêng.

Các hạng mục còn thiếu trong phạm vi 2D là định danh cùng một chi tiết giữa nhiều hình chiếu/khung/layout, đọc nét khuất và ký hiệu lắp/dung sai khi có ảnh hưởng tới yêu cầu sửa, xác định mốc giữ/khe hở và phạm vi tác động qua hình tổng, hình chi tiết, công đoạn và đóng gói. Các liên kết này cần bằng chứng và ca kiểm chứng độc lập trước khi được cấp quyền sửa; chỉ trùng vị trí hoặc giống hình chưa đủ.

Mô hình hiện giữ `mechanical_3d_intent_verified=false` như thông tin phạm vi, không phải điều kiện nghiệm thu cần đạt. `complete_design_understanding=false` vẫn phản ánh các quan hệ 2D toàn hồ sơ chưa bao phủ đầy đủ.

Không thay đổi quyết định chưa xác nhận về tấm xốp Dauphine. Không truy cập thêm kho dữ liệu riêng của công ty; ba DWG này bổ sung bằng chứng kỹ thuật, chưa thay thế nghiệm thu trên dữ liệu sản xuất.
