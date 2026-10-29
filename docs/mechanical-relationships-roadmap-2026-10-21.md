# Phạm vi phát triển từ yêu cầu sáu hạng mục

Yêu cầu người dùng ngày 21/10/2026 được dùng làm định hướng triển khai, không phải xác nhận rằng các năng lực nêu trong yêu cầu đã tồn tại. Thứ tự ưu tiên: quan hệ và bằng chứng → stretch có ràng buộc → đưa adapter đã kiểm chứng vào luồng sử dụng → lan truyền đa hình chiếu/BOM/công đoạn/đóng gói. Mở rộng loại đối tượng và bộ DWG kiểm chứng thực hiện theo từng adapter trong quá trình này.

## Các nguyên tắc áp dụng

- Ngưỡng 0,01 mm / 0,5 độ là tham số đề xuất mặc định, không phải tiêu chuẩn chung. Hai đường song song gần nhau không tự chứng minh chúng trùng nhau hoặc thuộc cùng chi tiết. Đầu mút gần nhau cũng chưa chứng minh mối ghép cơ khí.
- Bậc tự do phụ thuộc mô hình, biến và hạng của hệ ràng buộc. Không dùng phép đếm cạnh đơn thuần. DOF lớn hơn 0 không cấp quyền sửa; điểm có DOF bằng 0 không thay thế thông tin chuẩn cố định do người thiết kế cung cấp.
- Chuỗi kích thước có thể bổ sung bằng chứng kiểm nhất quán; không tự xác nhận danh tính vật tư hoặc ý đồ lắp ghép. Không đồng nhất mọi phương trình kích thước với phân tích dung sai sản xuất khi chưa có dữ liệu dung sai.
- Stretch phải mô tả rõ đối tượng, cửa sổ/đỉnh được chọn, điểm giữ, kích thước đích và điều kiện sau sửa. Chọn solver theo mô hình thực tế; chưa áp dụng solver phi tuyến chung cho mọi DWG.
- Native constraints và quan hệ suy ra được lưu riêng cùng nguồn bằng chứng. Không tự gán parametric constraint vào DWG chỉ vì geometry gần nhau.
- Change propagation là đồ thị phụ thuộc có kiểm chu trình, thứ tự và xung đột; không gọi đó là dependency injection. Chỉ lan truyền qua liên kết có bằng chứng hoặc xác nhận còn hiệu lực theo hash phiên bản.
- Proxy thiếu decoder/object enabler được giữ nguyên và báo thiếu hỗ trợ. Explode là thao tác chuyển đổi có thể mất ngữ nghĩa; cần phạm vi riêng và đối chiếu, không làm mặc định.
- Không cần bắt đầu bằng fine-tuning. Trước hết cần schema quan hệ, thuật toán, fixture, quy trình kiểm chứng và dữ liệu được phép sử dụng. Dataset lớn không tự bảo đảm độ tin cậy tuyệt đối.

## Bước đầu đã triển khai

`graph/geometric_candidates.py` tạo đồ thị chỉ đọc trên tối đa 64 thực thể được chọn rõ, cùng hệ tọa độ layout, đơn vị millimeter được khai báo. Hiện hỗ trợ LINE phẳng không suy biến và CIRCLE normal +Z: song song, vuông góc, đầu mút gần trùng và đồng tâm. Mỗi cạnh ghi loại quan sát, sai số, `status=candidate`, `requires_design_confirmation=true`, `edit_authorization=false`. Đơn vị không rõ, chọn phần tử trong block hoặc trộn layout đều bị từ chối. Đối tượng ngoài phạm vi được ghi rõ unsupported. Không quét toàn DWG rồi kết luận cùng cụm; không tính DOF hoặc sửa file.

`scripts/audit_geometric_candidates.py` xuất JSON kèm hash nguồn và kiểm nguồn giữ nguyên. Đây là CLI phân tích DXF; muốn chạy từ DWG dùng DXF native readback đã kiểm chứng. Chưa có endpoint/UI hay liên kết tự động từ candidate vào kế hoạch sửa.

Kiểm thử bước này: 8 đạt, 7 warning thư viện, 0,38 giây. Bao gồm song song không bị coi là trùng đầu mút, residual điểm đo, đồng tâm cùng mặt phẳng, chặn đơn vị không phải mm, báo đối tượng không hỗ trợ, chặn block và trộn layout.

## Phần còn phải thực hiện

1. Hợp nhất bằng chứng native, DIMASSOC và candidate vào schema quan hệ có vòng đời xác nhận theo phiên bản; bổ sung tiếp tuyến, khoảng cách/góc, chuỗi kích thước và phân tích DOF trên mô hình được định nghĩa rõ.
2. Xây fixture stretch với điểm cố định; giải hệ ràng buộc, kiểm dư/thiếu ràng buộc và xung đột; kiểm native/DXF/visual sau lưu, mở lại và sửa tiếp trên nhiều DWG.
3. Tích hợp adapter polyline–DIM vào API/UI/revision với hash/preflight/readback hiện có. Đồ thị candidate không mở khóa capability production.
4. Mở rộng mạng đa hình chiếu, chi tiết, BOM và quy trình; mỗi liên kết cần nhận dạng nguồn/đích, đơn vị, biến đổi tọa độ và bằng chứng riêng. Không sửa hàng loạt theo tên hoặc vị trí tương tự đơn thuần.
5. Thêm adapter block động/proxy theo loại và runtime thực tế; giữ ngữ nghĩa và kiểm tác động bên ngoài phạm vi sửa.
6. Quản lý corpus có quyền sử dụng, manifest đơn vị/loại đối tượng/kết quả; chạy round-trip, iterative edit, đối chiếu vùng không sửa và kiểm database phù hợp. Chỉ công bố phạm vi đã kiểm chứng, không tuyên bố mọi DWG.

Đề xuất tấm xốp chưa được xác nhận vẫn giữ nguyên trạng thái; tài liệu yêu cầu này không thay thế xác nhận đó.

## Kiểm chạy trên dữ liệu thật

Đã chạy CLI với 16 LINE/CIRCLE đầu tiên trong Model của DXF native readback job `ea4b1d186ca4453e9db9cd06c55ef263`. Report `storage/validation-fixtures/geometric-candidates-2026-10-21/report.json` chứa 16 node và 91 quan sát candidate, có danh sách handle và hash nguồn. Chọn 16 phần tử theo thứ tự chỉ là kiểm công cụ, không phải lựa chọn một cụm cơ khí; nhiều cặp song song có thể ở xa nhau. Không có cạnh nào được xác nhận, không tạo bản sửa, nguồn giữ nguyên.
