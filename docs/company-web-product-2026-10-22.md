# Sản phẩm web cho công ty — 22/10/2026

Phạm vi được người dùng chốt thêm ngày 23/10: **chỉ cần bản vẽ cơ khí 2D trong DWG; không yêu cầu dựng, hiểu hoặc chỉnh mô hình 3D**. Tiêu chí hoàn thành phần cơ khí là đọc toàn hồ sơ 2D, xác định đúng chi tiết/cụm và quan hệ giữa các hình biểu diễn, rồi sửa liên động và kiểm chứng DWG sau lưu/mở lại. Không lấy năng lực 3D làm điều kiện nghiệm thu.

Cập nhật quan hệ cơ khí 23/10: [bộ giải dùng chung cho các chi tiết vẽ rời và mặt tiếp xúc 2D](generic-mechanical-relations-2026-10-23.md) đã chạy trên ba DWG mới qua tải lên, sửa liên động và lưu/mở lại AutoCAD. Chưa hoàn thành hiểu toàn hồ sơ 2D hoặc nghiệm thu toàn công ty.

Cập nhật 23/10: [đã bổ sung nền tài khoản, vai trò, truy vết worker và trang điều kiện phát hành](company-accounts-release-review-2026-10-23.md), kiểm SQLite/PostgreSQL và chạy lại DWG Dauphine thực tế. Triển khai LAN/VPN và chứng nhận/tự phát hành vẫn chưa hoàn tất. Các mô tả dưới đây ghi nhận mốc 22/10.

Mục tiêu do người dùng xác nhận: nhân viên cơ khí dùng website chung, đưa nhiều hồ sơ DWG khác nhau vào mỗi ngày; hệ thống đọc toàn hồ sơ, định vị cụm và các bản chi tiết, hiểu yêu cầu thay đổi và kiểm chứng các chi tiết liên quan trước khi trả DWG. Không lấy một bản mẫu hoặc nhóm tám đỉnh/sáu DIM làm tiêu chí hoàn thành dự án.

Hai quyết định đã được người dùng chốt ngày 22/10:

- Triển khai mạng nội bộ/VPN trước.
- Cho phép tự phát hành với các loại sửa đã kiểm chứng. Đây là yêu cầu sản phẩm; chưa phải xác nhận mọi quan hệ còn mơ hồ hoặc mọi bản sửa cũ đã đủ điều kiện phát hành.

## Phần vừa triển khai

Cập nhật tiếp: [đã nối tìm chi tiết toàn file vào luồng sửa liên động và lưu/mở lại DWG](whole-file-linked-edit-2026-10-22.md). Website nhận yêu cầu không cần chọn khung; STT trùng hiển thị ứng viên có mã/khung nguồn. Ca tổng hợp PART-A 100→120 mm đã đồng bộ hai hình, DIM, BOM, dịch PART-B, cập nhật DIM tổng 220 mm và được mở DWG độc lập để đo lại. Kết quả giới hạn ở trường hợp đã kiểm, chưa thay cho lớp hiểu cơ khí tổng quát hay nghiệm thu công ty.

Website tự lập **Hồ sơ toàn bản vẽ** khi mở tài liệu. Tác vụ đọc độc lập với khung đang chọn; đọc mọi layout và các instance block lồng, gồm hình nằm ngoài khung và vùng loại khỏi phạm vi sửa. Từng bản ghi giữ handle, đường dẫn instance, hệ tọa độ và ma trận tới layout; geometry có tọa độ nguồn, không dùng hình render để đo thay CAD.

Nét trong block hiển thị DIM/bảng được đánh dấu chú thích, tránh tính thành chi tiết cơ khí mới. DIM tọa độ và polyline 3D được đọc dưới dạng thuộc tính/đỉnh native chỉ đọc; không vì đọc được mà cấp quyền sửa. Sửa lỗi đọc DIM không có `actual_measurement` lưu sẵn.

Danh mục toàn file nối mã BOM tới các khung tổng, khung chi tiết và instance có mã đã được engine nguồn xác định. Tra mã/mô tả/vật liệu/STT xét toàn danh mục; nút mở chỉ chọn đúng khung nguồn, không tự nhận hình trong khung đã có quan hệ lắp ghép. STT vẫn giữ theo từng bảng kê. Hình trùng nhau không tự được gán cùng mã.

Có API tác vụ chạy nền, trạng thái chờ/đang đọc/hoàn tất/lỗi, dữ liệu phân trang và bộ lọc layout/loại/text/handle. Mỗi trang có SHA-256; nguồn, danh mục khung, vùng loại, liên kết tham số và quyết định hình học thay đổi sẽ làm hồ sơ cũ mất hiệu lực. Tác vụ gián đoạn khi server khởi động lại được báo lỗi và có thể đọc lại. Kế hoạch sửa lưu `document_reading` và gửi trạng thái bao phủ đã kiểm tra vào ngữ cảnh lập kế hoạch; hồ sơ này không tự mở rộng quyền sửa.

XREF, block thiếu, tham chiếu vòng, giới hạn độ sâu/số bản ghi và MINSERT chưa mở từng vị trí được báo là nhánh chưa đọc đủ. Định nghĩa block chưa đặt được kiểm kê riêng. Nội dung proxy/OLE chưa giải mã không được gọi là đã hiểu đầy đủ.

## Bằng chứng trên nhiều hồ sơ

Kiểm tra qua HTTP thật trên DXF đã đọc từ bốn DWG hiện có; không chạy sửa mới trên khách hàng trong đợt này.

| Hồ sơ | Bản ghi theo vị trí đặt | Khung | Mã BOM | DIM | Giới hạn đọc còn lại |
|---|---:|---:|---:|---:|---|
| Dauphine | 56.814 | 71 | 46 | 1.221 | 6 OLE chỉ metadata |
| MR-106 | 14.507 | 20 | 12 | 224 | 13 OLE chỉ metadata |
| Sample_recover | 11.671 | 23 | 0 | 349 | Chưa nhận diện BOM đủ bằng chứng |
| LEG6949 | 162.169 | 54 | 25 | 668 | 4 OLE chỉ metadata |

Tổng 245.161 bản ghi, 493 trang dữ liệu khớp hash; bốn tác vụ hoàn tất, không có nhánh traversal bị bỏ qua trong phạm vi DXF. Bản ghi gồm chú thích, nét DIM và instance lặp; **không phải số chi tiết cơ khí**. Đọc hết dữ liệu DXF chưa chứng minh DWG native không có phần chưa hỗ trợ, cũng chưa chứng minh hiểu mọi quan hệ cơ khí.

Bốn DWG gốc giữ nguyên SHA-256. Dữ liệu khách hàng không gửi cloud. Receipt: `storage/validation-fixtures/document-atlas-2026-10-22/verification.json`; chạy lại bằng `python -m scripts.verify_document_atlas_live` khi server đang mở.

Kiểm thử đợt này: 213 bài CAD I/O, hồ sơ toàn file, context/planning/jobs và 223 bài assembly/revision đạt; tổng **436 bài liên quan**. 11 script `verify_frontend*.js` đạt, gồm kiểm mới về tìm toàn danh mục, phân trang, text CAD, nguồn cũ, chuyển file và bảo vệ khi đang sửa. Đây không phải kết quả chạy lại toàn bộ test suite. Giao diện thật được kiểm tra thêm bằng trình duyệt.

## Những điều còn phải hoàn thành để nghiệm thu dùng chung

| Hạng mục | Điều kiện nghiệm thu |
|---|---|
| Đọc và hiểu toàn hồ sơ | Đối chiếu dữ liệu native với kết quả đọc; AI xem ảnh tổng và ảnh chi tiết theo nhiều mức; định danh vai trò hình tổng/chi tiết/công đoạn, chỉ rõ phần chưa đọc hoặc mâu thuẫn. Chỉ mục vừa thêm là nền dữ liệu, chưa hoàn tất lớp hiểu này. |
| Quan hệ cơ khí toàn file | Mỗi liên kết cùng chi tiết, hình chiếu, đo kích thước, mặt lắp, khe hở, công đoạn và đóng gói có bằng chứng nguồn riêng. Tính đủ phạm vi tác động khi một chi tiết đổi; quan hệ thiếu bằng chứng phải được giải quyết thay vì bỏ qua. |
| Hiểu yêu cầu sửa | Nhận đúng chi tiết và hình từ yêu cầu toàn file; giải quyết trùng STT, mã, đơn vị, chiều sửa, mốc giữ và phiên bản. Không cần nhân viên tự biết handle hoặc tọa độ. |
| Sửa DWG đa dạng | Mở rộng adapter/solver theo loại hình học thực tế, block động và liên kết native; giữ các đối tượng ngoài phạm vi; không chỉ sửa số text DIM. |
| Tự phát hành đã kiểm chứng | Danh mục loại sửa được chứng nhận gắn với phiên bản adapter, điều kiện áp dụng và bộ kiểm DWG độc lập. Mỗi lần chạy vẫn phải đạt kiểm hình học, DIM, BOM, toàn bộ tác động liên quan, lưu/mở lại và hash nguồn/phiên bản. Loại chưa chứng nhận hoặc tác động chưa đầy đủ giữ dạng đề xuất. Chưa triển khai cơ chế chứng nhận/tự phát hành này. |
| Website nhiều nhân viên | Đăng nhập, vai trò, thư viện chia sẻ, chủ sở hữu tác vụ, chống hai người ghi đè cùng phiên bản, nhật ký người thực hiện, hạn mức hàng đợi, backup/khôi phục PostgreSQL và file. Hiện server vẫn chỉ nghe loopback, chưa mở mạng nội bộ. |
| Vận hành nội bộ/VPN | Cài dịch vụ, cấu hình host/proxy/chứng thư theo hạ tầng công ty, quản lý quyền và cấu hình, giám sát hàng đợi, giới hạn worker/giấy phép CAD, thử phục hồi và tải đồng thời. Chưa nghiệm thu triển khai toàn công ty. |
| Bộ nghiệm thu đại diện | Nhiều hồ sơ độc lập và yêu cầu thay đổi có đáp án kỹ sư; đo sửa đúng, liên kết bị bỏ sót, từ chối đúng và thời gian xử lý. Bốn lượt đọc ở trên chưa thay thế bài kiểm sửa liên động trên nhiều sản phẩm. |

Ưu tiên tiếp theo: mở rộng việc hiểu mô tả và truy xuất ảnh/hình học ngoài khung đang chọn, rồi kiểm tra đồ thị tác động trên nhiều hồ sơ độc lập có đáp án kỹ sư. Luồng tìm mã/STT từ chỉ mục toàn file đã được nối và kiểm chứng trên một ca sửa liên động. Song song với phần cơ khí cần hoàn thành nền đăng nhập, phiên bản dùng chung và tiêu chí tự phát hành trước khi mở website trong mạng công ty.

Lựa chọn mã xốp 3.8.01312 / 745→718 vẫn chưa được người dùng xác nhận; yêu cầu tự phát hành loại đã kiểm chứng không thay thế xác nhận ý đồ còn thiếu đó. Các bản sửa và undo/redo native trước đây được giữ nguyên.
