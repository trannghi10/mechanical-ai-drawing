# Tài khoản, truy vết và điều kiện phát hành — 23/10/2026

Đã nạp bản cập nhật vào web cục bộ. Phần này hoàn thiện nền tài khoản và kiểm tra điều kiện của từng revision; chưa mở LAN/VPN, chưa chứng nhận loại sửa và chưa tự phát hành bản sản xuất.

## Chức năng đã triển khai

- `/accounts`: thiết lập quản trị viên đầu tiên, đăng nhập/đăng xuất, đổi mật khẩu, thêm/khóa tài khoản và đổi vai trò. Bốn vai trò: chỉ xem, nhân viên chỉnh sửa, kỹ sư phê duyệt, quản trị viên. Sau khi thiết lập lần đầu, các API bản vẽ yêu cầu đăng nhập.
- Mật khẩu dùng PBKDF2-SHA256; session lưu hash token, hết hạn sau 12 giờ. Khóa tài khoản, đổi vai trò hoặc mật khẩu thu hồi các phiên cũ; lưu lại thông tin không thay đổi không làm mất phiên. Chặn khóa quản trị viên hoạt động cuối cùng. Giới hạn đăng nhập sai được lưu trong database.
- Vai trò được kiểm tại server. Nhân viên không duyệt được revision; kỹ sư/quản trị viên vẫn phải qua các chốt kiểm cơ khí hiện có. Trạng thái database cơ bản được chia sẻ, thông tin kết nối chi tiết dành cho quản trị viên.
- Nhật ký lưu các thao tác ghi được phép, mã yêu cầu và kết quả HTTP, cùng các sự kiện đăng nhập. Không lưu mật khẩu/token hoặc nội dung bản vẽ trong nhật ký này. Bản ghi bắt đầu phải được lưu trước khi chạy thao tác; database lỗi thì không thực hiện thao tác. GET và các yêu cầu bị từ chối ở lớp phân quyền chưa được ghi đầy đủ vào nhật ký.
- Người tạo và người cập nhật được giữ trong hồ sơ upload, kế hoạch, chỉ mục toàn file, revision, lịch sử undo/redo và tác vụ xuất/native khi có đăng nhập. Thông tin đi theo worker; mở lại hoặc theo dõi tác vụ không chuyển người tạo sang người đang xem. Hồ sơ cũ thiếu người tạo không được suy diễn tên người tạo.
- Tác vụ native tiếp tục sau gián đoạn dùng người tạo đã lưu. Worker luôn trả lại context sau khi chạy hoặc lỗi, tránh lẫn người dùng giữa hai tác vụ.
- Luồng `apply-checked-preview` bổ sung kiểm hash DXF làm việc và file DWG/DXF gốc từ trước đến sau xử lý. Nếu nguồn đổi giữa chừng, không chấp nhận revision. Bản xem trước vẫn bị chặn duyệt/phát hành khi chưa đủ quan hệ.
- Mỗi revision hình học có liên kết **Kiểm tra điều kiện phát hành**. Trang đối chiếu: hình học/phiên bản nguồn, giữ nguyên gốc, phạm vi liên quan, phê duyệt đúng hash, lưu/mở lại DWG toàn hồ sơ và chứng nhận loại sửa. Bản xuất selection không được coi là DWG toàn hồ sơ. Báo cáo không thay đổi CAD, không tự duyệt và không cấp chứng nhận.

## Kiểm chứng

1. Toàn bộ suite cơ sở sau thay đổi truy vết worker: **2.155 bài Python đạt**. Sau các thay đổi tiếp theo về điều kiện phát hành, giữ nguồn của checked preview và trạng thái database theo vai trò: **121 bài liên quan đạt**. Hai nhóm có phần trùng, không cộng thành tổng. Log: `storage/validation-fixtures/pytest-company-accounts-2026-10-23.txt` và `pytest-accounts-release-final-2026-10-23.txt`.
2. **15 script frontend đạt**, gồm đăng nhập/thiết lập, vai trò, chuyển hướng an toàn, trạng thái bận/lỗi, hiển thị chữ CAD bằng text và trang điều kiện phát hành chỉ đọc. Log: `storage/validation-fixtures/frontend-accounts-release-2026-10-23.txt`.
3. PostgreSQL thật: sáu nhóm kiểm về thiết lập, phân quyền, người tạo upload/nhật ký, thu hồi phiên, phiên qua kết nối mới, quản trị viên cuối cùng và giới hạn đăng nhập. Chỉ dùng schema thử duy nhất, đã xóa schema thử; không tạo/sửa tài khoản thật. Receipt: `storage/validation-fixtures/cad_accounts_check_124828ada973470b95b5b1b83f223a74/verification.json`. Lệnh: `python scripts/verify_accounts_postgres.py`.
4. Trình duyệt thật: đăng nhập tài khoản thử đã được người dùng cho phép, xem danh sách thành viên/nhật ký rồi đăng xuất. Môi trường thử không chứa bản vẽ công ty. Ảnh: `storage/validation-fixtures/accounts-ui-28bd4c585e94/admin-2026-10-23.jpg`.
5. HTTP thật trên bốn revision của ba hồ sơ công ty: mọi revision đều bị chặn tự phát hành. Dauphine và MR-106 có artifact DWG toàn hồ sơ mở lại còn đúng hash; LEG6949 selection không đạt tiêu chí toàn hồ sơ. Nguồn gốc giữ nguyên. Receipt: `storage/validation-fixtures/release-review-2026-10-23/company-checks.json`; chạy lại bằng `python scripts/verify_release_review_live.py`.

## DWG thực tế chạy lại sau thay đổi giữ nguồn

Đã chạy lại kế hoạch tìm mã `8.1.05190.002` trên toàn file Dauphine: thành hộp **1,2 → 1 mm**, giữ ngoài **14 × 14 mm** và chiều dài đo thật **347,5003629724961 mm**; đồng bộ biên trong, bốn đường trong hai block lồng, DIM, hai BOM và ghi chú.

- Revision mới: `68a4f91c2fda4155928f8d83b596993d`.
- Xuất **toàn document**, tải DWG và nhập lại bằng AutoCAD local độc lập: đạt kiểm hình học, DIM, BOM, đối tượng ngoài phạm vi và nội dung OLE theo oracle hiện có.
- Đủ **23.116** đối tượng cấp layout; chiều dài thật và file gốc giữ nguyên. Nội dung OLE được kiểm, chưa xác nhận hình thức hiển thị giống hệt.
- Receipt: [run.json](../storage/validation-fixtures/dauphine-wall-accounts-2026-10-23/native-61e4997b5ab6/run.json).
- [DWG bản thử](../storage/validation-fixtures/dauphine-wall-accounts-2026-10-23/native-61e4997b5ab6/after.dwg).
- [Trang kiểm điều kiện](http://127.0.0.1:8765/release-review?document=51ec94944c4443b19fb8d5bd7930a6dd&revision=68a4f91c2fda4155928f8d83b596993d): **3/6 đạt** — hình học/nguồn, giữ gốc và native lưu/mở lại. Phạm vi cơ khí, phê duyệt và chứng nhận vẫn bị chặn.

Không dùng kết quả này làm xác nhận ý đồ cơ khí hoặc nghiệm thu kỹ sư. Ca xốp `3.8.01312 / 745 → 718` vẫn chưa được xác nhận và không được thực thi.

## Cách thiết lập tài khoản thật

Trên máy chủ, mở [Tài khoản](http://127.0.0.1:8765/accounts), tự nhập tài khoản/mật khẩu quản trị viên đầu tiên. Dự án không cấp mật khẩu quản trị mặc định và chưa tự tạo tài khoản thật. Sau thiết lập, marker `storage/accounts.enabled` và dữ liệu tài khoản PostgreSQL cùng cần được sao lưu. `CAD_REQUIRE_LOGIN=1` có thể yêu cầu đăng nhập ngay từ trước khi thiết lập; khi database không truy cập được thì không chuyển qua SQLite.

Thư viện hiện là thư viện dùng chung theo vai trò; chưa có phân quyền riêng từng phòng ban/tài liệu. Không dùng nút cấp vai trò kỹ sư làm bằng chứng người đó đã nghiệm thu một loại sửa.

## Phần còn lại để nghiệm thu công ty

- Hoàn thiện quan hệ cơ khí và các adapter còn thiếu; tiếp tục giải quyết bốn chi tiết Dauphine, ba mã/khung còn thiếu của LEG6949 và bốn hình cụm MR-106 bằng bằng chứng nguồn.
- Danh mục chứng nhận loại sửa theo phiên bản adapter, điều kiện áp dụng, phạm vi kích thước và đáp án kỹ sư. **Trang điều kiện vừa thêm chưa phải cơ chế chứng nhận hoặc tự phát hành**; hiện không có certificate được cấp tự động.
- Triển khai nội bộ/VPN theo host/proxy/TLS của công ty, tài khoản thật, thử nhiều nhân viên đồng thời, giám sát hàng đợi/giấy phép CAD, sao lưu và phục hồi PostgreSQL cùng file. Hiện vẫn chỉ nghe `127.0.0.1`.
- Bộ nghiệm thu có đáp án kỹ sư trên nhiều hồ sơ đại diện. Không yêu cầu người dùng cung cấp kho DWG nội bộ cho dịch vụ ngoài; tiếp tục với file đã được phép dùng và ca tổng hợp, kiểm nghiệm thu riêng tại công ty.
