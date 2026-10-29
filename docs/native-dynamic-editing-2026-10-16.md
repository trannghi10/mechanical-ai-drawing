# Sửa block động bằng AutoCAD trên máy — 16/10/2026

Đã nối ô nhập yêu cầu với thao tác tham số native. Bộ xử lý lấy tên, kiểu, giá trị nguồn và lựa chọn của từng block trong file được upload; không dùng mã sản phẩm Dauphine để nhận diện. Đây là phần mở rộng khả năng sửa file mới, chưa phải cam kết sửa đúng mọi DWG hay backup toàn sản phẩm.

## Cách dùng

1. Mở lại trang Explorer để nạp giao diện mới. Upload DWG bằng backend **AutoCAD trên máy**. Với tài liệu đã nhập qua ODA, chọn **Mở bản sao bằng AutoCAD trên máy**; lịch sử cũ được giữ.
2. Chọn một block/bản vẽ. Mục AutoCAD có nút **Đọc tham số bản vẽ đang chọn**, hiển thị số hoặc danh sách lựa chọn lấy từ nguồn.
3. Có thể chỉnh trực tiếp tham số, hoặc nhập yêu cầu: `Tăng chiều dài lên 80 mm`, `Length từ 50 thành 80 mm`, `Part Number từ 626 thành 627`, `Side từ 0 thành 1`, `Weld Symbol từ Backing thành Fillet`. Tên/mã này chỉ là ví dụ; phải khớp tham số và lựa chọn trong file hiện tại. Ngăn cách nhiều yêu cầu bằng `;`.
4. Bấm phân tích rồi **Tạo DWG sau sửa tham số**. Mục AutoCAD tự mở để theo dõi, xem hình và tải DWG. Sau khi mở lại DWG, giao diện liệt kê cả các tham số được AutoCAD thay đổi kéo theo.

Không cần khởi động model AI/Ollama cho các yêu cầu tham số được bộ biên dịch này nhận diện. Yêu cầu hình học thông thường tiếp tục dùng engine hiện có. Bản sửa native được lưu riêng và liên kết tải được giữ trên server.

## Đã bổ sung

- Tham số số thực, trạng thái số nguyên Int16/Int32 và chuỗi có tập lựa chọn được định nghĩa trong block; hỗ trợ lookup/visibility/flip.
- Nhận tên tham số nguồn và một số tên Việt tương ứng: chiều dài, chiều rộng, chiều cao, độ dày, đường kính ngoài/lỗ, mã chi tiết, kích cỡ. Giá trị trước được lấy từ CAD khi yêu cầu chỉ ghi giá trị mới.
- Kiểm tra đơn vị theo CAD, giá trị trước, quyền sửa, lựa chọn được phép, hash nguồn, kết quả đọc native, phạm vi và chủ sở hữu. Từ chối yêu cầu trùng, không xác định duy nhất hoặc còn mệnh đề chưa xử lý; không thực thi riêng ý đầu.
- Kiểm tra giá trị AutoCAD nhận ngay sau thao tác và sau lưu/mở lại. Đối chiếu tham số và bbox của các block động ngoài phạm vi; không xuất kết quả nếu chúng thay đổi.
- Giữ kiểu native khi đặt giá trị. Dropdown số xử lý sai số dấu phẩy động để không tạo thay đổi giả.
- Hiện rõ khi ràng buộc native không nhận đúng yêu cầu. Ví dụ block mẫu nhận 70 khi yêu cầu 75 do bước nhảy của tham số: tác vụ bị từ chối, không có DWG tải thành công. Lỗi plugin được ghi và trả về để Core Console tiếp tục QUIT, không ném lỗi qua biên lệnh native.

## Kiểm chứng

Dùng **bản sao** `Sample/en-us/Dynamic Blocks/Mechanical - Metric.dwg` có sẵn trong AutoCAD 2027. File cài đặt và nguồn upload giữ nguyên hash. Chạy qua API thật: upload → chọn block → planning job → native edit → mở lại DWG → SVG HTTP 200 → tải DWG HTTP 200 → đo DXF từ DWG mở lại.

| Trường hợp | Kết quả kiểm chứng |
|---|---|
| Part Number 626 → 627 | Đường kính ngoài 19 → 22 mm; Width/Bore 6 → 7 mm; bảng tra cập nhật các tham số phụ thuộc |
| Length 50 → 80 mm | Hai cạnh thân bu lông đo được 80 mm; không dùng tổng bbox có đường tâm để thay thế chiều dài thân |
| Side 0 → 1 | Trạng thái Int16 và hình sau lật thay đổi |
| Weld Symbol Backing → Fillet | Trạng thái và phần hình đang hiển thị thay đổi; giữ/đọc đúng cờ Invisible của các nét ẩn |
| Size M10 → M12 | Mã kích cỡ và hình đai ốc thay đổi theo cấu hình nguồn |

Script kiểm chứng cũng đối chiếu hình học các block ngoài phạm vi. Thời gian các lượt thử khoảng 5–7 giây, không phải bảo đảm thời gian cho file lớn hoặc mọi máy.

- Bằng chứng native: `storage/validation-fixtures/autocad-dynamic-native-2026-10-16.json`.
- Toàn bộ 1.128 kiểm thử Python đạt trước bước bổ sung thông báo lỗi cuối; sau đó bộ adapter cuối đạt **93 kiểm thử**. Bảy script frontend đạt, gồm form tham số chuỗi/số nguyên, dropdown, chống kết quả cũ và link tải.
- Build và native check cuối đạt trên AutoCAD 2027/.NET 10, nguồn bất biến.
- Trường hợp tham số 75 bị nhận thành 70 đã kiểm tra riêng: thông báo chứa giá trị yêu cầu/thực nhận, không có link tải, Core Console thoát mã 0 và không tạo archive kết quả. Bằng chứng: `storage/validation-fixtures/autocad-dynamic-rejected-2026-10-16.json`.

Chạy lại kiểm chứng trên bản sao mẫu cài đặt:

```powershell
python scripts/verify_autocad_dynamic.py --sample 'D:\AutoCAD 2027\Sample\en-us\Dynamic Blocks\Mechanical - Metric.dwg'
```

## Giới hạn còn lại

Adapter native này sửa instance trực tiếp trong Model/Layout. Block động nằm trong định nghĩa dùng chung chưa có cơ chế cô lập từng đường dẫn instance. Chuỗi tự do không có lựa chọn nguồn, tham số phức tạp không được hỗ trợ, proxy cần object enabler và association riêng vẫn chưa được sửa tổng quát.

Đợt này nghiệm thu **AutoCAD trên máy**. APS cloud chưa có credentials/Activity mới được nghiệm thu; cần build và đăng ký phiên bản plugin mới trước khi dùng các kiểu tham số bổ sung trên cloud.

Quan hệ được AutoCAD thực thi là quan hệ **đã được tác giả định nghĩa trong block**. Nó không tự chứng minh BOM bên ngoài, mọi hình chiếu, chi tiết lắp, công đoạn hoặc đóng gói đã đồng bộ. Những nét không được tác giả gắn vào tham số có thể giữ nguyên; ví dụ đường tâm trong mẫu bu lông. Các ràng buộc này cần được gắn/kiểm tra riêng trước khi coi là backup hoàn chỉnh. **Backup toàn Dauphine và yêu cầu sửa đúng mọi DWG vẫn chưa hoàn thành.**
