# Khối đen che số đo trong preview MR-106 — 17/10/2026

## Nguyên nhân đã xác minh

Khung `frame_4065C1_404569` của tài liệu MR-106 `1c7d831296ff402bb1a838479063a99d` đang dùng `sheet-v4-*.svg` cũ. Ảnh này được tạo khi nền che chữ MTEXT bị ép thành đen bởi ColorPolicy.BLACK. Bản vá nền trắng hiện có đã dựng đúng ảnh mới, nhưng cache vẫn giữ ảnh lỗi vì tên cache không gắn phiên bản renderer. Các khối này là nền che chú thích/kích thước, không phải biên dạng vật liệu.

Đối chiếu SVG cùng khung: cache cũ có 235 path tô đen; dựng mới có 222 path tô đen và **13 path nền trắng**. 392 path nét kỹ thuật khác giữ số lượng. Đã xem trực quan các số Ø914, Ø908, 36°, 38, 3 và 20 hiển thị đúng vị trí; không xóa hàng loạt những vùng tô đen thật trong CAD.

## Đã sửa

- Phiên bản renderer riêng `RENDER_VERSION=5`; cache khung/block gắn phiên bản này, SHA-256 DXF đang đọc và dữ liệu vùng xem. Đổi nguồn nhập hoặc crop cùng ID cũng không dùng lại ảnh cũ.
- Cache bản sửa và Before/After cũng gắn phiên bản renderer. Ghi SVG bằng file tạm rồi đổi tên; tác vụ lỗi không công bố cache dở dang. Tên cache bản sửa/file tạm ngắn để giữ tương thích đường dẫn Windows dài.
- Các route SVG trả `Cache-Control: no-cache`; URL xem nguồn/bản sửa/đối chiếu trên frontend đã đổi phiên bản. Ảnh cũ đã nằm trong blob của trang mở trước đó cần tải lại trang hoặc mở lại bản vẽ.
- Không thay đổi bộ nhận diện khung, hình học, DIM, BOM, DXF hoặc DWG nguồn; không xuất bản sửa sản phẩm trong lượt xử lý preview này.

## Kiểm chứng

20 khung MR-106, gồm 17 bản vẽ và 3 khung mẫu, đều trả HTTP 200 qua API localhost; dựng lại toàn bộ 11,36 giây trong lượt này. Trình duyệt mở đúng preview mới và xem toàn màn hình không còn các mảng đen che số đo trong ảnh người dùng báo; không ghi nhận lỗi JavaScript trong lượt kiểm tra.

SHA-256 trước/sau giữ nguyên:

- DWG: `0b33a8e2561621f341d7693b6c1386bcfb9b3e141cdcc3ef038bcfd928f3c99b`
- DXF: `424aeca538a55220e3735fb04b91ee8de872a73b89bc23cf9a4d05e5b41a708a`

1.280 kiểm thử Python toàn bộ, 120 kiểm thử CAD I/O/revision và 7 script frontend đạt. Bổ sung kiểm tra nền MTEXT trắng nhưng giữ SOLID đen thật, không dùng cache cũ, thay renderer/nguồn/crop, ghi cache nguyên tử và ảnh bản sửa. Vẫn 19 module kiểm thử.

Bằng chứng:

- `storage/validation-fixtures/black-mask-preview-fix-2026-10-17.json`
- `storage/validation-fixtures/black-mask-cached-before-2026-10-17.png`
- `storage/validation-fixtures/black-mask-corrected-2026-10-17.png`
- `storage/validation-fixtures/black-mask-fixed-browser-2026-10-17.jpg`
- `storage/validation-fixtures/pytest-preview-cache-2026-10-17.txt`
- `storage/validation-fixtures/pytest-preview-fix-full-2026-10-17.txt`
