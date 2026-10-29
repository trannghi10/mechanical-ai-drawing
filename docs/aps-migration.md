# Chuyển CAD backend sang Autodesk Platform Services

## Đã kết nối và chạy thật — 20/10/2026

Credentials đã được kiểm tra trực tiếp với Autodesk; đã tạo bucket private, đăng ký AppBundle/Activity và kiểm tra hợp đồng khởi chạy. `APS_CLOUD_ENABLED=1`; mặc định đọc/xuất vẫn là `autocad` trên máy, AI vẫn nội bộ. Để chủ động dùng cloud, mở **Công cụ AutoCAD và chẩn đoán file → Autodesk APS · cloud** rồi dùng nút đọc hoặc mở bản sao bằng APS. Khi chọn APS, bản sao CAD/lệnh sẽ được gửi Autodesk; các file nội bộ chưa được dùng trong lượt kiểm chứng này.

Hai API đã hoạt động với DWG tổng hợp:

- **Model Derivative:** manifest và metadata HTTP 200, translation `success`, có hai khung nhìn.
- **AutoCAD Automation:** đọc native và extension dictionary, sửa TEXT đúng handle/owner/phạm vi, lưu DWG rồi mở lại. Lượt lưu hình mới giữ LINE và DIM **80 mm**. File DWG tải qua website trả HTTP 200, 15.008 byte, khớp SHA-256; ODA mở lại độc lập cũng đo hình/DIM 80 mm và thấy TEXT đã sửa.
- Nguồn DWG/DXF giữ nguyên. Document tổng hợp `3a1a5835f2614c2cb587e294f4ea011a` được ẩn khỏi thư viện mặc định. Ba workitem kiểm chứng thành công; lần đầu thất bại ở tham chiếu AppBundle đã được lưu báo cáo và sửa, không tự gửi lại tác vụ có trạng thái chưa rõ.

Lỗi phát hiện khi chạy thật: chỉ mục `$(appbundles[...].path)` dùng tên ngắn **MechanicalCad**; nickname/alias đầy đủ chỉ đặt trong danh sách `appbundles`. `setup_aps.py check` nay đối chiếu cả command line, script, tham số và dependency, tránh báo sẵn sàng chỉ vì token/engine đúng. Plugin cloud hiện nhắm AutoCAD 2025/.NET 8 và đã chạy được trên engine đó; AutoCAD local vẫn là 2027. Object Enabler Plant 3D 2027 cài trên máy chưa được đóng gói trong bundle cloud.

Bằng chứng: `storage/aps-cloud-check.json`, `storage/validation-fixtures/aps-live-2026-10-20/website-check.json`, `derivative.json`, `independent-readback.json`, `downloaded-backup.dwg` và `smoke-run.log`. API `/aps/status` hiện `configured=true`, `live_verified=true`; bằng chứng gắn config/bundle/hash nguồn và kết quả, không phải kiểm tra mạng liên tục. Không trả credentials ra trình duyệt.

Chạy lại (dùng tối đa ba workitem APS, áp dụng hạn mức/chi phí tài khoản):

```powershell
python -X utf8 scripts/setup_aps.py check
python -X utf8 scripts/setup_aps.py smoke
```

`smoke` tự tạo dữ liệu tổng hợp, từ chối tài liệu khách hàng khi dùng `--document`. Kiểm thử liên quan cuối: **235 bài Python đạt**, bảy script frontend đạt; vẫn 19 module kiểm thử. Log `storage/validation-fixtures/aps-live-2026-10-20/pytest-final.txt`.

**Đây là nghiệm thu kết nối/động cơ CAD và bản sao tổng hợp, chưa hoàn thành backup toàn Dauphine hoặc suy luận/sửa đúng mọi DWG.** Những quan hệ lắp ghép, phối cảnh, proxy và đóng gói thiếu bằng chứng vẫn giữ điều kiện kiểm chứng trước xuất hoàn chỉnh.

## Cách dùng trên website

Xem hướng dẫn trong website: **Hướng dẫn sử dụng → AutoCAD / APS** (`/help#aps`).

1. Tải DWG mới, chọn khung cần sửa.
2. Mở **Công cụ AutoCAD và chẩn đoán file → AutoCAD trên máy / Autodesk APS**.
3. Chọn APS và bấm **Kiểm tra kết nối APS**; thao tác này không gửi CAD/chạy workitem.
4. Muốn đọc lại bằng cloud, bấm **Mở bản sao bằng APS (gửi Autodesk)**. Nguồn/lịch sử cũ giữ nguyên.
5. Chọn khung của bản sao, nhập yêu cầu và mốc giữ; phân tích, tạo bản sửa, đối chiếu rồi tải DWG. Với tham số block động, dùng nút đọc tham số và áp dụng; tải kết quả trong danh sách tác vụ native.

**Dropdown chỉ chọn bộ xử lý cho các công cụ native trong mục này.** Tải file mới và xuất revision thông thường vẫn theo `CAD_READ_BACKEND` / `CAD_DWG_BACKEND` trên server; trạng thái giao diện ghi rõ hai cấu hình đó. Chuyển cả luồng sang APS cần đặt cả hai thành `aps` trong `.env` và khởi động lại backend. Đổi cấu hình này làm file CAD mới/đầu ra được gửi Autodesk, không thay AI provider. Không cần đăng ký lại bundle hoặc điền lại API key trên máy này.

## Luồng xử lý đã tích hợp

Luồng đã tích hợp: tải DWG vào kho → AutoCAD Automation đọc native, tạo inventory và DXF đối chiếu → chọn khung như trước → AI/engine lập kế hoạch và tạo revision → xuất phạm vi chọn → AutoCAD Automation lưu DWG 2018, mở lại và xuất DXF đối chiếu → kiểm tra hình học/DIM/BOM/liên kết native → tải file. Khi chọn backend đọc APS, không dùng ODA để mở DWG đầu vào. Python tiếp tục phân tích ngữ nghĩa/hiển thị/kiểm chứng trên DXF native; APS không thay thế logic liên kết.

File cũ có thể dùng **Mở bản sao bằng APS (gửi Autodesk)**: tạo tài liệu mới, giữ nguyên nguồn và lịch sử sửa cũ. Nếu tài liệu đã nhập bằng APS đang dở, nút này tiếp tục tác vụ cũ; không gửi lại workitem đã được ghi nhận. **Đọc toàn bộ DWG bằng APS** chỉ lấy inventory, không tự thay nguồn đang làm việc. Chỉ native context khớp hash DXF readback và đường owner/handle được ghép vào dữ liệu phân tích.

Kết nối và plugin đã được kiểm chứng trên cloud như phần đầu. Các bước dưới dành cho triển khai trên máy/tài khoản khác. Chuyển engine không tự hoàn tất liên kết cơ khí của Dauphine hay bảo đảm sửa đúng mọi DWG.

## Những gì cần chuẩn bị

1. Tài khoản Autodesk, APS Developer Hub/app có quyền dùng **Automation**, **Model Derivative** và **Data Management/OSS**, cùng hạn mức hoặc phương thức thanh toán phù hợp. Kiểm tra điều khoản dữ liệu nội bộ trước khi bật cloud.
2. `Client ID`, `Client Secret`: chỉ điền vào `.env` ở máy server. Không gửi secret trong chat, frontend hoặc kho mã.
3. Khi chuyển sang máy khác: **.NET SDK 8** và hai DLL `AcDbMgd.dll`, `AcCoreMgd.dll` đúng phiên bản **ObjectARX SDK/AutoCAD 2025 chính thức**. Máy hiện tại đã có SDK portable và DLL Autodesk trong TrueView. Không cần mua AutoCAD desktop chỉ để gọi APS, nhưng phải có SDK đúng ABI và kiểm chứng plugin trên cloud. Bản nguồn hiện nhắm engine `Autodesk.AutoCAD+25_0`; không tự đổi sang engine mới vì .NET/SDK có thể khác.

Nguồn: [APS Automation](https://aps.autodesk.com/developer/overview/automation-api), [SDK và managed DLL](https://help.autodesk.com/cloudhelp/2025/PLK/OARX-DevGuide-Managed/files/GUID-8657D153-0120-4881-A3C8-E00ED139E0D3.htm), [thay đổi engine/.NET 2027](https://aps.autodesk.com/blog/end-autocad-2021-engine-new-autocad-2027-engine-released).

## Cấu hình

Giữ các cấu hình AI/ODA hiện có; bổ sung các dòng sau trong `.env`. Không sao chép đè toàn bộ `.env.example` lên `.env`.

```dotenv
CAD_DWG_BACKEND=aps
CAD_READ_BACKEND=aps
APS_CLOUD_ENABLED=0
APS_CLIENT_ID=
APS_CLIENT_SECRET=
APS_BUCKET_KEY=ten-bucket-duy-nhat-cua-cong-ty
APS_ACTIVITY_ID=
APS_REGION=us-east
APS_ENGINE=Autodesk.AutoCAD+25_0
```

`CAD_DWG_BACKEND` độc lập với `AI_PROVIDER`: có thể dùng AI nội bộ để lập kế hoạch, nhưng AutoCAD cloud vẫn nhận file CAD khi xuất bằng APS. `CAD_READ_BACKEND` chọn bộ đọc file mới; nếu bỏ trống, nó theo `CAD_DWG_BACKEND`. Màn hình tải file đổi nhãn để báo rõ việc gửi Autodesk. `APS_CLOUD_ENABLED=0` chặn mọi tác vụ cloud; không âm thầm chuyển sang ODA nếu APS cấu hình sai. `oda` vẫn dùng được khi chủ động chọn lại backend đó.

Sau khi điền credentials, bật `APS_CLOUD_ENABLED=1`, rồi chạy từ PowerShell trong thư mục dự án:

```powershell
python scripts/setup_aps.py status
python scripts/setup_aps.py engines
powershell -ExecutionPolicy Bypass -File scripts/build-aps.ps1 -AutoCADManagedDir 'C:\Autodesk\ObjectARX2025\inc'
python scripts/setup_aps.py register
```

Máy hiện tại đã có bundle `autodesk/MechanicalCad.zip`. Nếu cần build lại bằng công cụ đã chuẩn bị:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-aps.ps1 -AutoCADManagedDir 'C:\Program Files\Autodesk\DWG TrueView 2025 - English' -DotnetPath '.\storage\tools\dotnet8\dotnet.exe'
```

Đường dẫn SDK là ví dụ, phải thay bằng nơi chứa hai DLL. `engines` đọc danh sách thật từ tài khoản. `register` tải bundle và tạo phiên bản/alias app + activity; không gửi DWG và không chạy tác vụ sửa CAD. Điền `APS_ACTIVITY_ID` được lệnh register trả về, ví dụ `nickname.MechanicalCad+dev`. Script không tự ghi secret hay cấu hình vào `.env`.

Lệnh `register` cũng khởi tạo bucket OSS private đã cấu hình. Sau đăng ký: `python scripts/setup_aps.py check` kiểm tra token, bucket và hợp đồng Activity bằng các lệnh đọc, không tải CAD hay chạy workitem. `check` đạt không thay thế smoke test file thật.

Hiện `.env` giữ backend AutoCAD trên máy. Chỉ đặt `CAD_READ_BACKEND=aps` và `CAD_DWG_BACKEND=aps` khi muốn chuyển luồng đọc/xuất mặc định sang cloud; bộ APS hiện đã đăng ký và kiểm chứng.

Khởi động lại backend:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Mở `http://127.0.0.1:8765/explorer`. Chọn file, mở **Công cụ AutoCAD và chẩn đoán file → AutoCAD trên máy / Autodesk APS**, chọn **Autodesk APS · cloud**, bấm **Đọc toàn bộ DWG bằng APS (gửi Autodesk)**. Sau khi kiểm tra native inventory trên một file nhỏ, thử sửa một DIM/chi tiết đã được engine hỗ trợ rồi tải DWG xem trước. Đối chiếu kết quả trong TrueView/phần mềm CAD trước khi đưa vào vận hành.

## Cơ sở dữ liệu và file

- Khi có `DATABASE_URL`, PostgreSQL lưu `aps_jobs` (JSONB), `aps_artifacts` và chỉ mục tài liệu/revision/file. Máy hiện đã chuyển sang PostgreSQL `mechanical_ai_drawing`; xem [cấu hình và vận hành](postgresql-setup.md). Khi bỏ trống URL, dùng lại `storage/aps.sqlite3`; không tự fallback nếu PostgreSQL cấu hình nhưng đang lỗi. Không lưu bearer token hay APS client secret trong job database.
- `storage/documents/<id>/aps-jobs/<job>/`: snapshot bất biến, commands, gói kết quả và receipt. DWG không nhét vào database BLOB. File nguồn và revision cũ được giữ.
- Kho OSS dùng policy `persistent`; dữ liệu vẫn được lưu trên Autodesk cho đến khi quản trị xóa. Hiện chưa có chức năng tự xóa cloud hoặc quota retention. Cần đưa retention/quota vào chính sách triển khai trước khi nhận số lượng lớn.
- Có thể đóng trang khi chạy. GET trạng thái tiếp tục theo dõi workitem đã gửi sau khi backend khởi động lại. Nếu server ngắt đúng lúc submit chưa ghi được workitem ID, tác vụ được chặn để kiểm tra thủ công, tránh gửi lại và bị tính phí hai lần.
- Đã có PostgreSQL và tài khoản ứng dụng riêng; chưa triển khai hàng đợi nhiều server hoặc hệ thống tài khoản/phân quyền web. Không công khai server này ra Internet. Endpoint cloud chỉ nhận thao tác cùng nguồn từ máy local. DB không thay thế sao lưu: sao lưu cả DB và thư mục artifact nhất quán.

## Plugin và hợp đồng lệnh

`autodesk/MechanicalCad` chạy headless qua Core API; không chạy mã Python/Lisp/C# do AI sinh. Chỉ nhận JSON schema cố định, kiểm tra source SHA-256, scope, handle, owner, loại entity, giá trị trước. Các adapter native hiện có: sửa text, ô bảng native và tham số block động tại layout. Block động nằm trong nhánh cha tĩnh được hỗ trợ nay có thể sửa bằng đường dẫn instance đầy đủ; engine clone riêng từng nhánh cha và ánh xạ handle mới trước khi áp dụng, giữ các nhánh không chọn. Cha động, XREF, thuộc tính cha hoặc association/proxy chưa có adapter vẫn bị chặn. Đã có bộ nhận diện yêu cầu tham số động được hỗ trợ; chưa tự lập được mọi kế hoạch tham số.

Giao diện mới: sau khi nhập bằng APS, chọn khung/block → **Đọc tham số bản vẽ đang chọn** → nhập giá trị mới cho các tham số số được phép sửa → **Áp dụng tham số và tạo DWG xem trước**. Tác vụ có nút **Xem hình sau sửa** và tải DWG. Plugin kiểm tra lại giá trị tham số sau khi mở lại DWG. Những thay đổi này vẫn là preview: chưa tự xác nhận BOM, các chi tiết tiếp xúc, toàn cụm hay đóng gói đều đúng. Mỗi bản sửa tham số được lập trên snapshot nguồn; chưa có thao tác tiếp tục sửa trên kết quả native trước đó.

DWG từ form tham số native là bản sao toàn file nguồn với các tham số được chọn đã đổi. Xuất riêng phạm vi/khung hiện thực hiện qua luồng revision đã kiểm chứng; chưa áp dụng bộ cắt phạm vi này cho kết quả chỉnh tham số native. Không gọi file native đó là backup hoàn chỉnh của cả sản phẩm.

Trong lúc chờ chuyển đổi APS, backend giải phóng khóa CAD dùng chung để các tác vụ xem bản vẽ khác tiếp tục hoạt động. Chỉ tạo phạm vi xuất và kiểm tra kết quả mới giữ khóa; approval và kiểm tra DIM/BOM hiện có vẫn chạy sau bước cloud.

Native inventory đọc block definitions, Model/Paper layouts, handles, layer, extents, text, bảng, kích thước đo, tham số block động, thuộc tính, một số geometry và tên record trong extension dictionary. Entity chưa có serializer chi tiết vẫn có type/handle/owner/extents; **không coi inventory này là biểu diễn đầy đủ mọi association/proxy/xref**. Xref cần đóng gói đủ và proxy cần object enabler thích hợp.

API:

- `GET /aps/status`: cấu hình thiếu gì, không trả secret. `configured` chỉ nghĩa cấu hình đủ cú pháp; `live_verified`/`verified_at` phản ánh smoke test tổng hợp đã đạt và còn khớp cấu hình, bundle, hash nguồn/kết quả.
- `POST /aps/connection`: kiểm tra trực tiếp token, Activity/engine/hợp đồng plugin và bucket bằng các lệnh đọc; không tải CAD, không tạo workitem, không trả credentials.
- `POST /documents/{doc}/aps/jobs`: đọc native toàn file + gửi Model Derivative.
- `POST /documents/{doc}/aps/import`: mở bản sao tài liệu cũ bằng APS; hoặc tiếp tục đọc nếu chính tài liệu này đang nhập bằng APS. Giữ nguyên nguồn/lịch sử cũ.
- `POST /documents/{doc}/aps/context`: lấy native facts cho `ids` đã chọn, ràng buộc bằng hash readback và owner path. Gửi `parameter_offset=0`, rồi dùng `next_parameter_offset` để đọc các trang 25 block có tham số. Prompt AI vẫn gọn; số DIM được hoãn không làm mất quyền sửa tham số đã xác định. Yêu cầu có #đường_dẫn_instance có thể truy xuất riêng occurrence ngoài trang đầu; không đoán các phần chưa đọc.
- `GET /documents/{doc}/aps/jobs[/{job}]`: lịch sử/trạng thái.
- `POST /documents/{doc}/aps/jobs/{job}/derivative`: kiểm tra lại manifest và danh sách view metadata, không tạo thêm translation job. Lỗi Viewer không làm mất kết quả CAD native đã kiểm tra.
- `GET /documents/{doc}/aps/jobs/{job}/files/{name}`: tải artifact khi source/output hash còn đúng.
- `GET /documents/{doc}/aps/jobs/{job}/preview/{target}`: SVG sau sửa cho đúng target của tác vụ, dựng từ DXF AutoCAD mở lại.
- `POST /documents/{doc}/aps/native-edits`: adapter lệnh native có `inspection_id`, `source_hash`, `ids` khung/block đã chọn và `operations`; chỉ nhận entity layout hoặc nhánh tĩnh lồng đã đọc, kiểm tra đủ owner-chain và nằm trong phạm vi. Chưa tự sinh lệnh này từ mọi yêu cầu ngôn ngữ tự nhiên.
- Các nút tải revision hiện có dùng AutoCAD Automation khi chọn backend `aps`, rồi chạy lại bộ kiểm tra xuất đang có; approval toàn sản phẩm vẫn phải đạt các kiểm tra cũ.

Model Derivative chủ yếu phục vụ Viewer/metadata. Không dùng objectId viewer thay native handle, không khẳng định metadata JSON chứa đủ hình học/ràng buộc chỉnh sửa. AutoCAD inventory và kết quả mở lại mới được dùng đối chiếu CAD. APS không phải giải pháp duy nhất và không tự suy ra ý đồ thiết kế thiếu trong DWG.

Tài liệu giao thức: [OSS signed upload](https://aps.autodesk.com/en/docs/data/v2/tutorials/app-managed-bucket), [Automation input/output OSS URN](https://aps.autodesk.com/blog/new-feature-support-direct-s3-migration-inputoutput-files-design-automation), [mẫu Autodesk app bundle/activity](https://github.com/autodesk-platform-services/aps-design-automation-nodejs). Chi phí phải kiểm tra theo gói APS hiện hành của tài khoản; không cam kết 2–3 giây/file hoặc áp dụng mặc định các mức phí trong đề xuất ban đầu.

## Phần còn cần nghiệm thu

Engine cloud đã chạy inspect, sửa TEXT, lưu/mở lại DWG tổng hợp. Cần nghiệm thu tham số động và toàn luồng revision/DIM/BOM trên tập DWG thực tế đủ đa dạng; mở rộng native geometry/association adapters, liên kết lắp ghép, đăng nhập và quản lý quota. Chuyển sang APS giải quyết động cơ CAD native; chưa thay cho các bước xác định quan hệ và kiểm tra kết cấu này.

## Lịch sử kiểm tra trước khi kết nối APS

Các trạng thái thiếu credentials/ODA dưới đây chỉ phản ánh thời điểm 15–16/10, đã được thay bằng kết quả 20/10 ở đầu tài liệu.

Kiểm tra cục bộ ngày 15/10/2026: **1.073 kiểm thử Python đạt**, gồm 35 kiểm thử trong module xuất file/APS; JavaScript tải file, điều hướng và tác vụ phân tích đạt. Log: `storage/validation-fixtures/pytest-aps-migration-2026-10-15.txt`; build: `storage/validation-fixtures/aps-plugin-build-2026-10-15.txt`. Những kết quả này không phải nghiệm thu APS thật hoặc backup Dauphine.

Đợt 16/10 bổ sung luồng import APS không phụ thuộc ODA, tiếp tục tác vụ sau restart, native context theo owner/hash, form tham số động, preview và metadata Viewer; script kiểm chứng giao diện `scripts/verify_frontend_aps.js`. Plugin được build lại trong `storage/validation-fixtures/aps-plugin-build-2026-10-16.txt` (0 lỗi, 3 cảnh báo tham chiếu framework). Log hồi quy cuối: `storage/validation-fixtures/pytest-aps-native-final-2026-10-16.txt`. Vẫn chưa có credentials nên chưa gửi tài liệu hoặc chạy CAD trên Autodesk thật.

Kết quả hồi quy cuối 16/10: **1.085 passed, 769 warnings, 153,72 giây**; bảy script frontend đạt. Backend mới PID tại thời điểm kiểm tra 14804, health `ok`, route JavaScript HTTP 200, backend đọc/xuất hiện vẫn `oda`, APS `configured=false` do thiếu bốn trường cấu hình. Các file khách hàng và lịch sử revision không bị chuyển đổi/ghi đè trong đợt nâng cấp này.
