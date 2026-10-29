# Phương án mở rộng sửa DWG mới — 14/10/2026

Đã bắt đầu triển khai: có bộ kiểm kê khả năng CAD, kiểm tra phạm vi trước apply, hồ sơ nguồn và gắn DIM/mốc có xác nhận để giải chuỗi/giữ khe hở, đồng bộ các chi tiết liên quan. **804 kiểm thử đạt**; hai DWG mẫu mới đã được duyệt/tải backup và ODA mở lại đo đúng. Bản Dauphine mới nhất vẫn là preview một phần. Chưa hoàn tất hợp đồng adapter CAD gốc, bộ ràng buộc tổng quát và các mốc nghiệm thu dưới đây. Giữ nguyên phần nhận diện/chọn khung đã được người dùng chấp nhận. [Bản triển khai mới và cách thử](source-parameter-links-2026-10-14.md).

## Mục tiêu có thể nghiệm thu

Người dùng tải DWG mới, chọn hình bản vẽ và nhập yêu cầu. Hệ thống kiểm kê khả năng xử lý, xác định chi tiết và phạm vi ảnh hưởng, giải các ràng buộc đủ dữ liệu, đồng bộ toàn bộ biểu diễn liên quan, rồi xuất một DWG được mở lại kiểm chứng. Quan hệ thiết kế thiếu hoặc có nhiều nghiệm phải được bổ sung bằng chọn mặt/mốc trên hình; lưu quyết định có bằng chứng để dùng tiếp.

Không có cơ sở bảo đảm tự sửa đúng 100% mọi DWG không có dữ liệu thiết kế. Một file 2D có thể không chứa quan hệ tiếp xúc, chiều sâu, hệ số uốn, tải trọng hoặc ứng dụng tạo đối tượng tùy biến. Phần mềm CAD gốc cũng không tự biết các thông tin này.

## Kiến trúc đích

DWG → kiểm kê đầy đủ → định danh chi tiết/công đoạn/hình chiếu → mô hình tham số nội bộ → đồ thị ràng buộc → kế hoạch có kiểm chứng → thực thi qua CAD adapter → tái tạo các hình/BOM/đóng gói → mở lại DWG → duyệt/tải.

1. **Kiểm kê khả năng xử lý file**: Model/Layout, đơn vị, block lồng, block động, DIM/association, proxy/custom classes, XREF và tài nguyên ngoài. Ghi rõ mỗi loại đọc được, sửa được, bảo toàn được hoặc cần ứng dụng gốc. Thiếu XREF phải báo đúng tài nguyên thiếu; không biến nó thành hình học rỗng mà vẫn báo hoàn tất.
2. **Định danh chi tiết**: gắn entity vào mã chi tiết, BOM gốc, công đoạn, hình chiếu và phiên bản. AI đọc ảnh/leader/ghi chú để đề xuất; DIM, topology, định nghĩa block và dữ liệu nguồn xác nhận. Tách biểu diễn một chi tiết khỏi instance vật lý và khỏi vật tư mua hàng. Số thứ tự thuộc từng BOM, không dùng chung toàn tài liệu.
3. **Mô hình tham số**: lưu chiều dài, dày, đường bao, lỗ, bán kính, mặt lắp, vị trí và nguồn chứng minh. File đầu vào vẫn là DWG 2D. Chi tiết phẳng dùng mô hình 2D; chỉ dựng thông tin 2.5D/không gian nội bộ khi các hình chiếu/DIM xác định được chiều sâu và hướng lắp. Không đo ảnh phối cảnh để tự đoán chiều sâu.
4. **Bộ giải ràng buộc**: giữ mặt ngoài/mặt giữa/đáy, tiếp xúc, khe hở, đồng tâm, lỗ lắp, đối xứng, khoảng cách và các giới hạn sản xuất. Phân biệt dư ràng buộc, thiếu ràng buộc, nhiều nghiệm và vô nghiệm. Sửa đồ thị con bị ảnh hưởng đến khi ổn định; báo xung đột thay vì nối các công thức tùy ý.
5. **Đồng bộ biểu diễn**: mọi hình đứng/cạnh/mặt cắt/Detail/phối cảnh/bản cắt của một chi tiết lấy cùng bộ tham số. Hình phối cảnh CAD được kiểm tra hệ trục và phép chiếu riêng; hình minh họa vẽ tay cần binding riêng, không coi là camera trực giao. Bảo toàn đường nét, ký hiệu, khung tên và lịch sử nguồn khi có thể.
6. **Công đoạn và đóng gói**: liên kết đầu ra công đoạn với vật tư/chi tiết đầu vào. Phôi uốn dùng tham số xưởng hoặc quy tắc nguồn đã xác nhận. Đóng gói dựa trên bao sản phẩm theo tư thế đóng, khe hở và các lớp đệm; phân biệt thùng tự thiết kế với mã thùng tiêu chuẩn mua sẵn.
7. **Thực thi/kiểm chứng**: snapshot bất biến, transaction, cô lập block dùng chung, phục hồi khi lỗi, cập nhật DIM/BOM, audit native và xuất DWG. Kiểm kê mọi biểu diễn bị ảnh hưởng: mỗi mục phải được sửa và kiểm tra hoặc có bằng chứng không chịu ảnh hưởng. Không dùng tỷ lệ confidence AI làm bằng chứng đầy đủ.

## Công cụ và chi phí

- Giữ **ezdxf + ODA File Converter + FreeCAD/OpenCASCADE + AI nội bộ** làm nền cho hình học 2D tiêu chuẩn. ODA File Converter miễn phí là bộ chuyển đổi; không có nghĩa đã sở hữu ODA Drawings SDK.
- Mở rộng FreeCAD từ kiểm tra mặt sang giải sketch/ràng buộc trong các cấu trúc được hỗ trợ. Phải viết adapter ánh xạ nguồn, đơn vị, topology và vòng đời solver; không có chức năng một lệnh tự hiểu mọi bản vẽ lắp.
- Tạo giao diện **CAD adapter** thống nhất. Adapter hiện tại dùng DXF; adapter bổ sung chạy plugin trong AutoCAD đã được cấp phép để chỉnh tham số block động và tái tính liên kết được hỗ trợ. Kiểm tra khả năng thật trên file mẫu trước khi chọn host.
- Trong các thư mục cài đặt đã kiểm tra trên máy có FreeCAD 1.1, ODA và DWG TrueView 2025; chưa thấy bản AutoCAD đầy đủ ở đó. TrueView không thay thế môi trường lập trình sửa bản vẽ AutoCAD.
- Nếu không có CAD host đã được cấp phép, hướng SDK thương mại cần ngân sách riêng. ODA Drawings SDK có khả năng đánh giá block động nhưng SDK được cấp phép theo gói thành viên; không đưa bản dùng thử vào kiến trúc sản xuất miễn phí.
- Proxy/custom objects có thể cần Object Enabler hoặc ứng dụng tạo ra chúng. Có native API không đồng nghĩa mọi lớp proxy đều chỉnh sửa được.
- AI đảm nhận hiểu yêu cầu, đọc hình và đề xuất ràng buộc có nguồn. Bộ giải và CAD adapter tính tọa độ/sửa DWG. Trước mắt không cần thêm nhiều model; chỉ đánh giá đổi model sau khi có bộ dữ liệu kiểm thử và xác định lỗi thuộc nhận thức, không phải thiếu ràng buộc/CAD API.

## Thứ tự thực hiện và điều kiện đạt

| Mốc | Sản phẩm bàn giao | Điều kiện đạt |
|---|---|---|
| 1 | Bộ phân loại khả năng CAD và hợp đồng adapter | File mới có danh sách đối tượng/tài nguyên/khả năng thực tế; đối tượng không hỗ trợ không bị mất âm thầm |
| 2 | Mô hình chi tiết và các hình biểu diễn dùng chung | Mã/BOM/instance/công đoạn có provenance; người dùng chọn mặt/mốc để giải trường hợp mơ hồ |
| 3 | Solver và thư viện quan hệ kỹ thuật | Bộ thử hộp–bas, ba tầng, lỗ, khe hở, tấm cong, uốn, đóng gói; phát hiện thiếu/xung đột, giữ các đại lượng nguồn |
| 4 | Tái tạo hình và adapter CAD gốc | Các hình liên quan cùng bộ tham số; thử block động/association/custom classes riêng nếu có host hỗ trợ |
| 5 | Dauphine toàn sản phẩm | Hình cạnh/phối cảnh C4, Detail C, công đoạn và toàn bộ đóng gói đều có bằng chứng cập nhật; mở lại chính DWG tải xuống và được kỹ sư duyệt |
| 6 | Nghiệm thu file mới | Đề xuất ít nhất 30 DWG sản xuất đa dạng, trong đó 10 file giữ riêng đến nghiệm thu; không thêm nhánh theo tên file/handle để làm các file giữ riêng vượt kiểm tra |

804 unit/integration tests hiện tại không thay thế 30 DWG sản xuất được kỹ sư kiểm chứng. Bộ file phải có đáp án và tiêu chí đo/BOM/bao phủ hình trước khi chạy. Kết quả đo, file lỗi và trạng thái chưa hỗ trợ phải được báo cùng kết quả thành công; không cam kết một tỷ lệ tự động hóa chưa đo được.

## Hiệu năng và giao diện

- Index và cache theo hash nguồn; tái dùng cây block, BOM và topology.
- AI truy xuất từng vùng/chi tiết cần thiết; dữ liệu đầy đủ vẫn ở server, không nhồi toàn bộ vector vào prompt.
- Giải và dựng preview theo đồ thị con bị ảnh hưởng; kiểm tra lại toàn bộ phạm vi ảnh hưởng trước xuất cuối.
- Đo riêng đọc file, AI, giải ràng buộc, apply, dựng preview, chuyển đổi và mở lại DWG. Bản xem trước Dauphine gần nhất cần khoảng 215 giây đến bước xuất kiểm chứng; đây là baseline cần giảm, không phải cam kết tốc độ cho file khác.
- Chạy nền có tiến độ/hủy/khôi phục, dùng một worker cho mỗi tài liệu. Giao diện chỉ hiện bản người dùng chọn; các mục liên quan nằm trong phần đối chiếu.
- Quan hệ được người dùng xác nhận lưu theo tài liệu/hash. Chỉ đưa vào thư viện quy tắc dùng chung sau khi tổng quát hóa và kiểm thử trên sản phẩm khác; không tự áp lựa chọn của Dauphine sang DWG mới.

## Nguồn chính thức đã đối chiếu

- [ODA File Converter miễn phí và chức năng chuyển đổi](https://www.opendesign.com/guestfiles/oda_file_converter)
- [ODA Drawings SDK: dynamic blocks evaluation](https://www.opendesign.com/datasheets/2025/en/Drawings%20Datasheet.pdf)
- [Giấy phép/gói thành viên SDK của ODA](https://www.opendesign.com/pricing?language=en)
- [AutoCAD Dynamic Block API](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-DevGuide/files/GUID-81D407FB-5C58-4197-A8DE-83A10F13091E.htm)
- [Custom objects, proxy và Object Enablers](https://help.autodesk.com/cloudhelp/2025/ENG/AutoCAD-Core/files/GUID-6515268E-3D71-4CBC-8D3C-2059CFAA4E38.htm)
- [FreeCAD: kernel, parametric model và Sketcher solver](https://www.freecad.org/features.php)
- [Giới hạn các lớp chưa ổn định trong LibreDWG](https://www.gnu.org/software/libredwg/manual/html_node/CLASSES.html)
