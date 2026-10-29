# Xuất DWG theo nội dung đã chọn trong block chứa — 15/10/2026

**Cập nhật tiếp theo:** giới hạn shared definition cần các tập member khác nhau dưới đây đã được mở rộng cho block tĩnh bằng cô lập riêng khi xuất (chính sách 4). Xem [chức năng và bằng chứng mới](shared-instance-export-2026-10-15.md). Các giới hạn dynamic/proxy và liên kết chưa xác minh vẫn giữ nguyên.

Đã bổ sung tách nội dung khi xuất `selection`: các bản vẽ không chọn trong cùng block chứa không còn được giữ như những hình đang đặt trong file xuất. Bản sửa làm việc vẫn giữ các hình đó nguyên trạng. Bộ nhận diện/chọn khung không thay đổi.

## Cách xuất

Sau khi tạo bản sửa và xem trước, giữ lựa chọn **“Bản vẽ đã chọn và các khung liên quan được sửa”** trong mục **Phạm vi tệp tải**, rồi bấm tải DWG. Engine giữ các đối tượng nguồn đã chọn và những hình liên quan được sửa, kể cả chi tiết đã giãn/dịch ra ngoài bbox cũ. Không cắt đường nét theo một hình chữ nhật mới.

Nếu một definition dùng chung cần các tập nội dung khác nhau ở những instance vẫn giữ lại, engine hiện từ chối tách definition đó. Có thể chọn **“Toàn bộ tài liệu gốc kèm thay đổi”** để tải file đầy đủ. Không tự dùng phép union để lẫn các bản vẽ ngoài phạm vi vào một bản xuất được gọi là đã tách.

## Bảo toàn CAD

- Ánh xạ đường dẫn nguồn qua các block đã cô lập khi sửa; giữ đúng handle, tọa độ, layer, thuộc tính và chuỗi POLYLINE/VERTEX/SEQEND. Ánh xạ được dựng một lần cho cả phạm vi.
- Chỉ bỏ các member khỏi block tĩnh khi mọi placement còn giữ của definition đó yêu cầu cùng tập member. Giữ nguyên các definition/tài nguyên còn lại, không serialize lại bằng ezdxf toàn bộ TABLE hoặc đối tượng opaque.
- Giữ thứ tự vẽ `ACAD_SORTENTS` của các member còn lại và kiểm tra lại sau ODA. DIMASSOC vượt phạm vi, pointer tới member bị bỏ, block động/proxy hoặc dữ liệu native chưa có adapter sẽ bị chặn; không tháo association để ép xuất.
- Giữ trọn tài nguyên khung chia ô theo bằng chứng nguồn: một viền chữ nhật, đường kẻ/nét cắt giấy nằm trong dải mép, nhãn chữ/số vùng. Đối tượng có hình kỹ thuật bên trong không được nhận là khung chia ô. Quy tắc này không dùng tên block hoặc tên file riêng của Dauphine.
- Kiểm tra danh sách member của các block đã tách và sự vắng mặt của handle đã bỏ sau ghi DXF và sau DWG roundtrip. Chỉ bỏ qua member không còn thuộc phạm vi trong phép kiểm clone; mọi đối tượng đã sửa vẫn phải có mặt.
- Phiên bản phạm vi tăng lên **3**. Tạo file mới không dùng lại tác vụ xuất `selection` của phiên bản cũ. Bản tải cũ còn đúng hash vẫn đọc được; không xóa bản sửa hay backup cũ.

Tài nguyên/definition không còn được đặt vẫn có thể nằm trong file. Đây là xuất phần bản vẽ, **không phải chức năng purge dữ liệu bí mật**.

Mã chính: `cad/nested_scope_export.py`, `cad/scoped_export.py`, `backend/services/revision_service.py`, `backend/services/export_jobs.py`.

## Kiểm chứng

**1.026 kiểm thử Python đạt**, log `storage/validation-fixtures/pytest-nested-export-release-2026-10-15.txt`. Sau bổ sung nét cắt giấy ngoài viền, 36 kiểm tra revision/xuất phạm vi được chạy lại và đều đạt: `storage/validation-fixtures/pytest-nested-export-borders-final-2026-10-15.txt`. Vẫn có 19 file kiểm thử Python; các trường hợp mới được bổ sung vào file hiện có.

Ba DWG mới qua upload → chọn khung → sửa → preview → duyệt → tải → ODA mở lại, không cung cấp mapping thủ công cho engine:

| Trường hợp | File DWG tải xuống | Bản sửa làm việc | Thời gian fixture nhỏ |
| --- | --- | --- | --- |
| Hai khung trong block lồng | Chỉ khung chọn; DIM 100 → 80 mm, BOM đổi đúng | Bản bên cạnh và bản sao ngoài khung giữ 100 mm | 2,974 giây |
| Block xoay 90°, tỷ lệ 2, có SORTENTS | Như trên; giữ thứ tự vẽ và giải mốc giữ qua câu trả lời | Như trên | 3,048 giây |
| Block phản chiếu | Như trên; đúng hình, DIM và BOM | Như trên | 3,029 giây |

Biên nhận: `storage/validation-fixtures/source-scopes-dwg-bd4e417f/receipts.json`. Mỗi DWG được mở lại chỉ còn một khung được đặt; definition nguồn không cần đặt vẫn được giữ. FreeCAD kiểm tra profile đạt. Các thời gian là của fixture nhỏ, không phải cam kết cho mọi file.

Hai DWG hồi quy DIMASSOC cũng đã sửa/duyệt/tải/mở lại: trung điểm theo DIM phụ 50 → 40 mm và tâm lỗ theo DIM phụ 90 → 70 mm khi thân 100 → 80 mm. Liên kết native, nguồn và hình/lỗ được kiểm chứng. Biên nhận: `storage/validation-fixtures/native-snap-4cf7ff67/report.json`, `storage/validation-fixtures/native-snap-b591b73f/report.json`.

Đã thử xuất lại **bản xem trước Dauphine hiện có** `c75fb805` bằng chính sách mới và tải HTTP 200, header DWG `AC1032`, 2.231.055 byte. Hash nguồn và DXF làm việc không đổi. Biên nhận: `storage/validation-fixtures/dauphine-nested-export-preview-2026-10-15.json`. Không chỉnh thêm geometry của sản phẩm trong lượt này.

## Chưa hoàn tất

Chưa tách được các instance dùng chung definition nhưng cần các member khác nhau nếu chưa cô lập instance đó. Block động/proxy và liên kết native chưa có adapter vẫn cần CAD host/công cụ tương thích.

**Chưa hoàn thành sửa đúng mọi DWG hoặc backup toàn Dauphine.** Việc xuất được phạm vi không chứng minh các hình cụm, chi tiết lắp bên trong, phối cảnh/uốn và đóng gói chưa gắn đủ đã được đồng bộ. Các chốt duyệt toàn sản phẩm vẫn giữ nguyên.
