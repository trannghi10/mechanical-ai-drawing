# AutoCAD 2027 trên máy — 16/10/2026

Đã thêm bộ chạy AutoCAD Core Console cho luồng upload → đọc native → sửa theo phạm vi → DWG xem trước → mở lại kiểm tra. Bộ chạy này dùng plugin .NET và PostgreSQL hiện có, không cần APS credentials. AI vẫn là thành phần riêng: AutoCAD thực thi CAD, engine/AI xác định yêu cầu và liên kết thiết kế.

Đã nối yêu cầu với tham số block động dạng số, mã lựa chọn, visibility và flip; AutoCAD tự cập nhật các quan hệ được định nghĩa trong block. [Cách dùng, năm trường hợp native đã kiểm chứng và giới hạn](native-dynamic-editing-2026-10-16.md).

## Đã cài và kích hoạt — cập nhật 16/10/2026

AutoCAD 2027 được tìm thấy tại `D:\AutoCAD 2027\accoreconsole.exe`, SDK 26.0.118.0. Đã build theo DLL thực trên máy, chạy native check đạt và bật **CAD_READ_BACKEND=autocad, CAD_DWG_BACKEND=autocad**. Backend đã nạp cấu hình; upload mới và xuất DWG dùng AutoCAD local, không gọi APS. Database PostgreSQL và cấu hình AI được giữ.

Đã sửa những lỗi chỉ xuất hiện khi chạy thật:

- Nhận diện AutoCAD cài trên ổ khác qua `AcadLocation` trong registry; ưu tiên đường dẫn cấu hình tường minh.
- Nạp DLL bằng NETLOAD với đường dẫn đầy đủ trong script. Core Console thực tế không nạp bundle qua `/al` như dự kiến. Profile tác vụ cách ly chỉ tin cậy thư mục plugin đã kiểm hash, giữ `SECURELOAD=2`.
- Đọc DIM nhập từ DXF cần quyền ghi cache trên database bản sao; không cấp quyền ghi nguồn. Dictionary native dùng enumerator của API, tránh lỗi ép `DictionaryEntry` thành `DBDictionaryEntry`.
- Khôi phục `WorkingDatabase` trước khi dispose bản mở lại. Xác nhận bỏ thay đổi **bootstrap trắng tạm** khi QUIT, dùng stdin đóng; lệnh N trước đây hủy QUIT và có thể gây access violation ở server nền.
- Ghi log bước xử lý, lỗi plugin và mã thoát. Nếu engine thoát lỗi, archive được cách ly dưới `failed-result.zip`, không có link tải kết quả thành công.
- Giải phóng `DBDictionaryEnumerator` trong transaction, trước khi database bị đóng. Sau sửa, hai native check liên tiếp (bốn tiến trình AutoCAD) có dictionary đều đạt. Lỗi `coreclr.dll` từng xuất hiện với cả runtime hệ thống và portable; không coi thay runtime đơn thuần là cách sửa lỗi tài nguyên native.
- AutoCAD 2027 dùng bộ .NET 10.0.13 portable đã chuẩn bị; root/phiên bản/hash coreclr và hostfxr được gắn vào receipt. Môi trường chỉ áp dụng cho tiến trình CAD, không đổi runtime Windows; cập nhật runtime cần build/check lại.

Native smoke test đã kiểm tra đọc extension dictionary, sửa text có điều kiện, DWG save/readback, hình và DIM 100 mm, nguồn bất biến. Receipt hiện hành: `storage/autocad-host-check.json`.

Đã kiểm chứng qua API thật:

| Trường hợp tổng hợp độc lập | Kết quả |
|---|---|
| Block lồng ba tầng, biên NURBS | 140 → 123 mm; giữ đường kính lỗ; duyệt, tải DWG và mở lại đo đúng |
| Công đoạn và chi tiết lắp giữa hai mặt, ba cấu trúc | Tự tính chiều dài chi tiết liên quan 120 / 100,8 / 120 mm; giữ khoảng ngoài 300 mm, đồng bộ hình/BOM; duyệt và tải DWG đạt |
| DIMASSOC midpoint | Chiều cao 100 → 80 mm; DIM phụ 40 mm; BOM và liên kết native giữ đúng sau tải/mở lại |

Các luồng tổng hợp được sinh từ fixture, không sửa khách hàng; ODA chỉ dùng tạo đầu vào thử và đo chéo file tải về. Backend đọc/xuất trong các luồng này là AutoCAD.

Đã đọc native Dauphine gốc bằng AutoCAD: **1.457 block definitions, 39.917 entities**, 1.226 DIM và 10 bảng native, không cảnh báo inventory, nguồn SHA-256 giữ nguyên. Thời gian khoảng 17 giây. Đây là kiểm chứng đọc, không phải backup toàn sản phẩm. Báo cáo: `storage/validation-fixtures/autocad-dauphine-read-2026-10-16.json`.

MR-106 gốc cũng đọc đạt: **469 block definitions, 10.067 entities**, không cảnh báo inventory và giữ hash nguồn. File `Sample_recover.dwg` được AutoCAD xác định `eDwgNeedsRecovery`, không báo nhầm lỗi kết nối AI.

Đã nhập một bản sao MR-106 qua API AutoCAD native, không thay bản cũ: danh mục 348 mục, 20 khung. Đã tải SVG và kiểm tra ảnh khung chi tiết có hình, DIM 2.900/50/3 cùng ghi chú và khung tên rõ trên nền trắng. Các khung tên mẫu trống cũng tồn tại trong nguồn; không thay bộ nhận diện khung để bỏ chúng. Bản kiểm chứng được đánh dấu auxiliary để không làm rối danh sách tài liệu. Báo cáo `storage/validation-fixtures/autocad-live-import-and-recovery-api-2026-10-16.json`; ảnh `autocad-mr106-native-detail.png` trong cùng thư mục.

### DWG cần phục hồi

Đã thêm **Tạo bản DWG phục hồi** trong mục CAD native khi chọn AutoCAD trên máy. API `POST /documents/{id}/autocad/recover` dùng `AppContextRecoverDocument` trên bản sao riêng; xuất DWG, mở lại lấy inventory và receipt `source_recovered=true`, `recovery_review_required=true`. Không tự sửa dữ liệu nguồn, không tự chuyển ODA/cloud hoặc duyệt thành backup thiết kế.

Kết quả Sample thực tế: đã tạo candidate, đọc lại **1.044 block definitions, 13.105 entities**, nguồn không đổi. Có thể tải file tên `RECOVERY-REVIEW-....dwg`; đối chiếu nội dung rồi mới upload làm đầu vào mới. Phục hồi có thể loại dữ liệu hỏng, nên bản này không tự chứng minh toàn bộ hình đã bảo toàn. [Autodesk mô tả RECOVER](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Core/files/GUID-78F5B1AB-583F-410F-85DA-6D03768832C8.htm).

Receipt thực tế: `storage/validation-fixtures/autocad-recovery-native-2026-10-16.json`. Cờ phục hồi bị thiếu/sai sẽ bị chặn tải kết quả thành công; backend chỉ hỗ trợ recovery qua AutoCAD local và nguồn DWG.

Kiểm chứng cuối: **1.115 kiểm thử Python đạt** trong 198,50 giây, vẫn 19 module test. Log `storage/validation-fixtures/pytest-autocad-final-release-2026-10-16.txt`; 7 script frontend đạt, script native bổ sung kiểm tra nút phục hồi và lựa chọn local/cloud. Các số ở mục chuẩn bị phía dưới là kết quả trước khi cài AutoCAD.

Các file đã upload trước khi chuyển backend giữ nguyên lịch sử. Để phân tích bằng dữ liệu native mới, trong mục CAD native chọn **AutoCAD trên máy → Mở bản sao bằng AutoCAD trên máy**, hoặc upload file mới. Không ghi đè bản cũ.

Chưa bảo đảm tự sửa đúng mọi DWG: các quan hệ thiết kế thiếu bằng chứng, proxy cần object enabler và tham số block động chưa kiểm chứng trên file thực vẫn cần xử lý theo trường hợp. Chưa nghiệm thu backup toàn Dauphine.

## Đã chuẩn bị

- .NET SDK 10.0.402 portable trong `storage/tools/dotnet10`; đã đối chiếu SHA-512 của gói tải từ Microsoft. Không đổi .NET của hệ điều hành.
- Plugin local đã biên dịch bằng bộ API tham chiếu Autodesk `AutoCAD.NET.Core/26.0.0` và `AutoCAD.NET.Model/26.0.0`, không lỗi/cảnh báo. Kết quả ở `autodesk/local/preflight-2027`; đây là kiểm tra biên dịch, chưa phải kiểm chứng chạy AutoCAD.
- Adapter tự nhận diện `acad.exe`, `accoreconsole.exe`, SDK và phiên bản .NET; kiểm tra hash plugin/manifest/engine trước tác vụ. Không nhận TrueView/LT thay cho AutoCAD đầy đủ.
- Mỗi tác vụ dùng bản sao riêng, lệnh plugin cố định và JSON thao tác có giới hạn; không chạy AutoLISP hoặc mã người dùng nhập. Có timeout, log, chống chạy lại mù tác vụ bị gián đoạn. Workdir ngắn để tránh lỗi Windows MAX_PATH.
- Bản DWG trắng dùng khởi động đã được tạo bằng ODA từ DXF tổng hợp, không dùng tài liệu khách hàng. Khi chạy tác vụ local, adapter không gọi ODA hoặc APS.
- Luồng đọc, xuất và tải DWG có lựa chọn backend `autocad`; giao diện CAD native có lựa chọn **AutoCAD trên máy / APS cloud**. Kết quả native vẫn qua kiểm tra nguồn/hash, DIM, BOM và điều kiện duyệt hiện có.
- Tác vụ và artifact local lưu cùng PostgreSQL, phân biệt `provider=autocad`. Không thay nguồn và lịch sử bản sửa cũ.

## Sau khi cài xong

Mở AutoCAD 2027 một lần để đăng nhập/kích hoạt bản quyền, rồi đóng bản vẽ thử. Trong PowerShell tại thư mục dự án:

```powershell
cd D:\mechanical-ai-drawing
python scripts/setup_autocad.py status
python scripts/setup_autocad.py build
python scripts/setup_autocad.py check
python scripts/setup_autocad.py activate
```

Nếu Python không nằm trên PATH, dùng `C:\Users\nghi.tran\AppData\Local\Programs\Python\Python310\python.exe` thay `python`.

`build` biên dịch lại đúng SDK đã cài và tạo bundle/receipt. Nếu cài ở đường dẫn khác, dùng `python scripts/setup_autocad.py build --core "C:\duong-dan\accoreconsole.exe"`.

`check` chạy thật trên file tổng hợp: đọc DXF, lưu DWG, sửa text có kiểm tra nguồn/owner, mở lại DXF và đo LINE/DIM 100 mm; kiểm tra nguồn không bị đổi. File thử được đánh dấu auxiliary. Nó không nghiệm thu một sản phẩm thực.

`activate` chỉ đổi `CAD_READ_BACKEND` và `CAD_DWG_BACKEND` sau khi `check` đạt trên đúng engine/plugin. Khởi động lại backend sau đó. Cấu hình AI và APS được giữ nguyên; không cần Ollama cho bản thân bước thực thi AutoCAD.

Có thể kiểm tra trước việc biên dịch mà chưa cài AutoCAD bằng `python scripts/setup_autocad.py prebuild`. Lệnh này tải SDK tham chiếu từ NuGet, không tạo host receipt hoặc kích hoạt backend. Build production sau khi cài sử dụng DLL SDK của đúng AutoCAD trên máy.

## Tình trạng tại thời điểm chuẩn bị trước khi cài

Tại thời điểm chuẩn bị, máy chưa có AutoCAD đầy đủ; backend đọc/xuất vẫn dùng ODA. Chưa chạy `check` hoặc kích hoạt AutoCAD local. Cài AutoCAD xong còn phải kiểm chứng trên DWG thực, nhất là tham số động, DIM association và proxy của từng loại file.

AutoCAD không tự bổ sung liên kết lắp ghép còn thiếu hoặc thông số công nghệ của xưởng. Chưa nghiệm thu backup toàn Dauphine và chưa bảo đảm sửa đúng mọi DWG. Bản xem trước một phần vẫn không được đổi nhãn thành backup hoàn chỉnh.

## Kiểm chứng đợt này

**1.106 kiểm thử Python đạt** trong 255,10 giây; 7 script frontend đạt. Các bài local kiểm tra lựa chọn provider, không gọi APS/ODA khi chạy native local, phạm vi/nguồn bất biến, timeout, tác vụ gián đoạn và chặn kích hoạt trước native check. Những kiểm thử transport dùng host giả lập, không thay thế kiểm chứng AutoCAD thật.

Log Python: `storage/validation-fixtures/pytest-local-autocad-2026-10-16.txt`. Plugin 2027 prebuild: `autodesk/local/preflight-2027/build.log` (0 lỗi/0 cảnh báo). Nhánh plugin APS .NET 8 vẫn build đạt (3 cảnh báo framework cũ). Backend đã nạp; `/health`, `/database/status`, `/autocad/status` và JavaScript trả HTTP 200. PostgreSQL giữ 112 tài liệu/139 revision; AutoCAD local báo chưa cài, ODA tiếp tục đọc/xuất.

Tài liệu tham khảo: [API tham chiếu Autodesk 2027](https://www.nuget.org/packages/AutoCAD.NET.Core/26.0.0), [Drawing model API](https://www.nuget.org/packages/AutoCAD.NET.Model/26.0.0), [AutoCAD Core Console](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-to-use-the-AutoCAD-Core-Console.html).
