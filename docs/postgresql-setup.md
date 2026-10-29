# PostgreSQL cho Mechanical AI Drawing — 16/10/2026

Đã tạo database `mechanical_ai_drawing` trên PostgreSQL 18 tại `127.0.0.1:5432`, với role ứng dụng `mechanical_ai_app`. Role không có superuser, tạo database, tạo role, replication hoặc bypass RLS. `DATABASE_URL` của tài khoản ứng dụng đã được lưu trong `.env`; không đưa URL chứa mật khẩu vào chat hoặc repository.

Đã cài `psycopg`/`psycopg-binary` 3.3.6 cho Python backend. SQLite `storage/aps.sqlite3`, file CAD và các bản sửa cũ được giữ nguyên. Chuyển sang PostgreSQL không gọi APS hoặc gửi DWG ra ngoài.

## Lưu những gì

| Bảng | Nội dung |
|---|---|
| `cad_documents` | Tài liệu, tên file, trạng thái, hash và vị trí nguồn |
| `cad_revisions` | Phiên bản sửa, kế hoạch, hash output/approval, cờ hoàn chỉnh |
| `cad_files` | Đường dẫn tương đối, SHA-256, kích thước, loại nguồn/revision/DWG preview/backup |
| `aps_jobs` | Tác vụ APS, trạng thái và payload JSONB |
| `aps_artifacts` | File kết quả APS, hash và kích thước |
| `schema_migrations` | Phiên bản schema |

DWG/DXF vẫn nằm trong `storage/documents`, không nhét file lớn vào database. Sao lưu database phải đi kèm sao lưu kho file. Cờ preview/hoàn chỉnh lấy từ receipt hiện có; database không duyệt thay cho engine hoặc người dùng.

Khi thiết lập: đã lập chỉ mục **112 tài liệu, 139 revision, 387 file**. SQLite hiện có **0 APS jobs**, vì chưa có tác vụ cloud thật. Index bao gồm các upload/lịch sử còn trong kho, kể cả tài liệu thử cũ; đây không phải số sản phẩm đã nghiệm thu.

## Vận hành

### Xem kết nối trong ứng dụng và pgAdmin

Backend hiện đã kết nối PostgreSQL; không cần tạo lại database hoặc thay mật khẩu. Trên Explorer, bấm **PostgreSQL · đã kết nối** ở góc trên để mở thông tin kết nối và số tài liệu/phiên bản. Có nút **Kiểm tra lại kết nối**. Trang kiểm tra trực tiếp: `http://127.0.0.1:8765/database/status` (`backend=postgresql`, `ready=true`). API không trả mật khẩu hoặc DATABASE_URL.

Trong pgAdmin, chọn **Servers → Register → Server**, đặt tên ở tab General, rồi điền tab Connection:

| Trường | Giá trị trên máy này |
|---|---|
| Name (General) | Mechanical AI |
| Host name/address | `127.0.0.1` |
| Port | `5432` |
| Maintenance database | `mechanical_ai_drawing` |
| Username | `mechanical_ai_app` |
| Password | Mật khẩu ứng dụng trong `DATABASE_URL` của `.env` |

Mật khẩu ứng dụng là phần mật khẩu của URI `DATABASE_URL`, không phải `PG_ADMIN_PASSWORD` của tài khoản `postgres`. Chỉ xem/nhập trên máy; không gửi mật khẩu qua chat. Nếu URI dùng ký tự `%xx`, cần giải mã URL phần mật khẩu trước khi nhập. Cách điền các trường: [hướng dẫn chính thức pgAdmin](https://www.pgadmin.org/docs/pgadmin4/latest/server_dialog.html).

Sau khi kết nối, mở **Databases → mechanical_ai_drawing → Schemas → public → Tables**. Xem `cad_documents`, `cad_revisions`, `cad_files`. Trong Query Tool có thể chạy câu lệnh chỉ đọc:

```sql
SELECT current_database(), current_user;
SELECT id, filename, status FROM cad_documents ORDER BY updated_at DESC LIMIT 20;
SELECT document_id, id, status, complete_product_backup FROM cad_revisions ORDER BY updated_at DESC LIMIT 20;
```

Kiểm chứng live lần này: role ứng dụng không có quyền quản trị; JSONB tiếng Việt và quan hệ file đạt; bản ghi thử được rollback. Số liệu tại thời điểm kiểm tra: 92 tài liệu, 111 revision, 311 file trong chỉ mục, gồm cả lịch sử/thử. Receipt: `storage/validation-fixtures/postgresql-download-ui-live-2026-10-16.json`.

### Tạo và tải bản DWG đã sửa

Kiểm tra trình duyệt ngày 16/10: đã tải DWG xem trước Dauphine về Downloads và đối chiếu SHA-256 với receipt. Trên mẫu tổng hợp riêng, nút tạo/tải đã tạo revision mới `ce7c48ac`, xuất qua AutoCAD và tải được DWG 18.148 byte; DIM/BOM khi mở lại đạt 76/36/16 mm. PostgreSQL có cả revision và file `dwg_preview`. Bản mới chưa được người dùng duyệt, `complete_product_backup=0`; không thay thế backup toàn Dauphine. Bằng chứng trong `storage/validation-fixtures/dwg-create-ui-handoff-2026-10-16.json`. Bộ kiểm thử sau thay đổi đạt 1.175/1.175. Bảng trạng thái thực tế sau lượt kiểm tra: 92 tài liệu/112 revision, bao gồm dữ liệu thử/lịch sử.

Khu vực **Tạo và tải DWG đã sửa** nằm ngay dưới phần phân tích yêu cầu. Có thể **Mở bản sửa gần nhất** của đúng hình đang chọn hoặc **Chọn bản sửa đã lưu**. Khi có kế hoạch thực thi được, nút tạo/tải gọi đúng luồng tạo bản sao và kiểm tra CAD hiện có. Khi đã có revision, nút tải xuất DWG của revision đó. File sẵn sàng có đường dẫn tải màu xanh.

Nếu chưa có thao tác CAD hợp lệ hoặc bản sửa có lỗi hình học, nút sẽ bị khóa và hiển thị lý do. Nút **Duyệt và tải DWG backup hoàn chỉnh** vẫn bị khóa với bản một phần; tải preview không biến nó thành bản sản xuất.

```powershell
python scripts/setup_postgres.py status
python scripts/setup_postgres.py index
python scripts/verify_postgres.py
```

- `status`: kiểm tra backend, kết nối và số lượng; không in mật khẩu.
- `index`: đồng bộ lại metadata từ status/revision JSON và file đang có; không sửa CAD.
- `verify_postgres`: kiểm tra role, JSONB tiếng Việt, upsert và quan hệ artifact; các bản ghi tổng hợp được rollback.
- `python scripts/setup_postgres.py migrate`: nhập lịch sử APS SQLite còn thiếu, không ghi đè job PostgreSQL đang có; SQLite giữ nguyên.

Khi có tài liệu/revision mới, receipt JSON vẫn được ghi trước, sau đó index PostgreSQL được cập nhật. Nếu index lỗi, local receipt được giữ và log cảnh báo chung; chạy lại `index` khi kết nối phục hồi. APS job repository dùng PostgreSQL trực tiếp khi có `DATABASE_URL`, không âm thầm chuyển sang SQLite khi PostgreSQL hỏng.

Script `setup_postgres.py create` dành cho tạo mới/khôi phục việc thiết lập dở. Nó đọc `PG_ADMIN_USER`, `PG_ADMIN_PASSWORD`, `PGHOST`, `PGPORT` từ `.env`, tạo role và database riêng, tạo schema, migrate APS rồi index CAD. Không thay pg_hba.conf, không đổi mật khẩu role sẵn có, không xóa database hoặc đổi chủ sở hữu database khác. Có thể xóa dòng `PG_ADMIN_PASSWORD` khỏi `.env` sau khi thiết lập xong; backend chỉ cần `DATABASE_URL` của role ứng dụng.

## AutoCAD hay APS?

Với hướng web app hiện tại, **APS AutoCAD Automation là CAD backend chính được đề xuất**: xử lý DWG tự động trên cloud qua plugin, kết hợp Model Derivative cho dữ liệu xem/metadata. AutoCAD desktop là công cụ bổ trợ cho kỹ sư kiểm tra, chỉnh tay và debug plugin. Nếu công ty bắt buộc DWG không rời mạng nội bộ, chọn **AutoCAD đầy đủ trên Windows + .NET plugin** thay cho cloud; AutoCAD LT không hỗ trợ bộ .NET plugin này.

Nguồn: [Autodesk APS Automation](https://aps.autodesk.com/automation-apis), [giao diện lập trình AutoCAD/AutoCAD LT](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-LT-Customization/files/GUID-E6429154-36DF-4D84-8ABC-9FCA15B66158.htm), [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).

Database quản lý lưu trữ và phiên bản; AutoCAD/APS thực thi CAD; AI/engine xác định yêu cầu và quan hệ. Mua thêm một thành phần không tự hoàn tất khả năng sửa mọi DWG hoặc backup toàn Dauphine.

Kiểm chứng sau triển khai: **1.090 kiểm thử Python đạt** (166,65 giây), kiểm tra giao diện tải DWG/APS đạt; backend mới dùng PostgreSQL và health `ok`. Log `storage/validation-fixtures/pytest-postgresql-2026-10-16.txt`; kiểm chứng PostgreSQL thật `storage/validation-fixtures/postgresql-live-2026-10-16.json`. Các bài pytest luôn cô lập khỏi DATABASE_URL thật; smoke test live rollback các hàng tổng hợp.
