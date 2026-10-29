# Lộ trình Mechanical AI Drawing

Ngày lập: 07/10/2026. Trạng thái: kế hoạch phát triển, chưa phải chức năng đã triển khai.

## 1. Mục tiêu và định nghĩa hoàn thành

Người dùng upload một DWG, hệ thống lập danh mục các bản vẽ logic trong file, người dùng chọn bản vẽ và nhập yêu cầu bằng tiếng Việt. AI tạo kế hoạch có cấu trúc; engine CAD áp dụng trên bản sao, cập nhật quan hệ phụ thuộc và BOM, kiểm tra, hiển thị khác biệt; người dùng duyệt đúng phiên bản rồi tải DWG mới.

Hoàn thành khi toàn bộ luồng chạy trên bộ DWG thực tế được thống nhất, file xuất mở được trong CAD đích, thay đổi đúng yêu cầu và không thay đổi đối tượng ngoài phạm vi cho phép. Không xem một demo DXF hoặc một câu trả lời AI là hoàn thành sản phẩm DWG.

## 2. Phạm vi phiên bản đầu

- Bản vẽ cơ khí 2D, một DWG mỗi lần; khai báo danh sách phiên bản DWG được hỗ trợ sau thử nghiệm.
- Nhận diện theo layout, khung tên, block và cụm hình học; người dùng xác nhận hoặc sửa vùng nhận diện.
- Một bản vẽ logic có thể gồm nhiều hình chiếu. Layout không mặc nhiên tương đương một chi tiết; layer không mặc nhiên tương đương một bản vẽ.
- Hỗ trợ ban đầu LINE, LWPOLYLINE, CIRCLE, ARC, TEXT, MTEXT, INSERT, ATTRIB và DIMENSION. Đối tượng khác được thống kê và giữ nguyên khi có thể; chặn thao tác nếu không thể bảo toàn.
- Thay đổi vật liệu, số lượng, thông tin chi tiết; sửa kích thước trên một số mẫu hình học có quy tắc được xác nhận.
- BOM từ bảng/attribute/text có nguồn rõ ràng; không suy đoán số lượng từ số hình chiếu.
- Chưa cam kết sửa tự động mọi DWG, tái dựng mô hình 3D, hoặc suy luận toàn bộ ràng buộc cơ khí từ hình học rời rạc.
- XREF/ảnh/font thiếu phải được báo rõ. Nếu cần tài nguyên ngoài DWG để xử lý đúng, yêu cầu bổ sung hoặc giới hạn chức năng; không coi upload một file là đã có toàn bộ dữ liệu.

## 3. Nguyên tắc bắt buộc

1. File gốc bất biến. Mỗi thao tác tạo revision mới, có khả năng quay lại.
2. AI trả ChangePlan theo schema, không chạy mã tùy ý do mô hình sinh ra.
3. CAD engine sửa entity thật. Sửa chữ số kích thước không đồng nghĩa sửa hình học.
4. Kế hoạch luôn gắn drawing_id, source_revision, entity references, đơn vị, giả định và bằng chứng nhận diện.
5. Phụ thuộc trong phạm vi được chọn có thể lan truyền theo rule đã xác nhận. Phụ thuộc sang bản vẽ khác phải xin mở rộng phạm vi trước khi áp dụng; mặc định chỉ hiển thị cảnh báo tác động.
6. Chỉnh block definition dùng chung có thể ảnh hưởng instance ngoài phạm vi. Phải kiểm tra và clone/điều chỉnh instance phù hợp hoặc đưa vào kế hoạch mở rộng phạm vi.
7. Quan hệ suy đoán không được tự động truyền thay đổi. Lưu loại quan hệ, nguồn, độ tin cậy và trạng thái xác nhận.
8. User duyệt revision đã preview và kiểm tra. Thay đổi tiếp theo làm mất hiệu lực duyệt cũ.
9. File DWG xuất phải được mở đọc lại và kiểm tra trước khi cung cấp tải xuống.

## 4. Kiến trúc đề xuất

Frontend web → FastAPI → hàng đợi tác vụ → CAD worker → kho file/revision + cơ sở dữ liệu.

Các module:
- File ingestion: upload, xác minh định dạng, giới hạn dung lượng, checksum, job status.
- CAD adapter: inspect/read/render/apply/export/reopen; che giấu khác biệt DXF và SDK DWG.
- Drawing discovery: layout, viewport, khung tên, vùng bản vẽ, thumbnail, điểm tin cậy.
- Semantic model: Drawing, View, Part, Feature, Dimension, Material, BOM và nguồn entity.
- AI planner: diễn giải yêu cầu dựa trên dữ liệu bản vẽ đã chọn; hỏi lại khi thiếu chi tiết, đơn vị hoặc thao tác mơ hồ.
- Dependency engine: tính affected set, phân loại phạm vi và thứ tự thực thi, xử lý vòng lặp/xung đột.
- CAD operations: các thao tác cho phép, có điều kiện trước/sau và log.
- BOM service: cập nhật bản ghi chuẩn và bảng CAD từ cùng một nguồn dữ liệu.
- Validation: hình học, quy tắc cơ khí đã cấu hình, BOM, phạm vi thay đổi, tính toàn vẹn file.
- Preview/review: trước/sau, overlay, danh sách thay đổi và duyệt revision.

Stack khởi đầu: giữ Python/FastAPI, Pydantic, NetworkX và ezdxf hiện có; frontend React/TypeScript; SQLite cho thử nghiệm một người dùng. Khi chạy nhiều người dùng chuyển PostgreSQL, hàng đợi worker và kho object theo nhu cầu. CAD chuyển đổi/render phải chạy ngoài request HTTP, có timeout và giới hạn tài nguyên.

## 5. Quyết định công nghệ DWG

PoC có thể dùng DWG → DXF → ezdxf → DXF → DWG như converter hiện tại, nhưng phải kiểm tra tổn thất dữ liệu trên DWG thực tế. Không xem round-trip là mặc nhiên bảo toàn dynamic block, custom object hoặc association.

Trước khi triển khai production, so sánh ODA Drawings SDK và Autodesk RealDWG về khả năng đọc/ghi, nền tảng triển khai, license, hỗ trợ đối tượng và chi phí. Chọn theo kết quả thử nghiệm và điều khoản sử dụng thực tế. Giữ CAD adapter để thay engine không làm lại toàn hệ thống.

Nguồn chính thức:
- https://ezdxf.readthedocs.io/en/stable/introduction.html
- https://www.opendesign.com/products/drawings
- https://forge.autodesk.com/developer/overview/realdwg-api

## 6. Hiện trạng mã nguồn

- backend/main.py: chỉ có root và health, chưa có API nghiệp vụ.
- cad/converter.py: gọi converter ngoài; cần cấu hình đường dẫn, timeout, job isolation và xác minh output.
- cad/reader.py: đọc DXF, modelspace/layer/block; chưa xử lý danh mục layout/viewport và bản vẽ logic.
- cad/entities.py: trích xuất một số entity; thiếu handle, ownership, units, bounding box, transform block, attribute, dimension và thông tin liên kết cần để sửa.
- graph/dependency_graph.py: quan hệ có hướng và descendants; thiếu semantics, bằng chứng, trạng thái xác nhận, cycle policy và scope guard.
- backend/services/ai_service.py: chưa triển khai.
- backend/models: có mô hình sơ bộ; cần Document/Revision/DrawingRegion/View/EntityRef/Operation/ValidationReport/Approval.
- rules/dimension_rules.py và các thư mục frontend/bom/preview/storage/tests chưa có triển khai trong danh sách file nguồn đã kiểm tra.

## 7. Lộ trình triển khai và cổng nghiệm thu

| Giai đoạn | Đầu ra | Điều kiện chuyển bước | Ước lượng |
|---|---|---|---|
| 0. Chốt dữ liệu và phạm vi | 10–20 DWG đại diện, bộ kết quả kỳ vọng, chọn loại thay đổi đầu tiên | Có file nhiều bản vẽ, block dùng chung, BOM, kích thước và ca lỗi; thống nhất CAD đích | 1 tuần |
| 1. Nền CAD và round-trip | Upload, job, adapter, inventory entity/layout, xuất DWG chưa sửa | Mở lại được, đối chiếu hình học/text/layer/block/units; đánh dấu trường hợp không hỗ trợ | 1–2 tuần |
| 2. Danh mục và chọn bản vẽ | Thumbnail, vùng bản vẽ, tên/số hiệu, sửa vùng thủ công | Tất cả vùng trong bộ nghiệm thu được nhận diện hoặc được user sửa; lựa chọn có entity scope rõ ràng | 2 tuần |
| 3. Chỉnh sửa xác định | 3–5 thao tác CAD có rule, revision và diff | Hình học cùng annotation cập nhật đúng; không sửa entity ngoài phạm vi | 2 tuần |
| 4. AI lập kế hoạch | Yêu cầu tiếng Việt → ChangePlan; xác nhận chỗ mơ hồ | Schema hợp lệ, không dùng ID không tồn tại, không thực thi yêu cầu ngoài tập thao tác | 1–2 tuần |
| 5. Dependency và BOM | Quan hệ có nguồn, impact report, cập nhật BOM | Lan truyền đúng rule; chặn vòng lặp không giải được; bản vẽ ngoài scope không tự bị sửa | 2–3 tuần |
| 6. Validation, preview, duyệt, xuất | Trước/sau, lỗi/cảnh báo, duyệt revision, DWG mới | Lỗi nghiêm trọng chặn export; duyệt cũ bị vô hiệu khi revision đổi; DWG xuất mở lại thành công | 2 tuần |
| 7. Pilot và phát hành | Chạy file thực, auth, backup, vận hành, tài liệu | Nghiệm thu end-to-end, phục hồi được, cô lập dữ liệu người dùng, license phù hợp | 2–3 tuần |

Tổng dự kiến 13–17 tuần cho nhóm nhỏ có năng lực backend/frontend và CAD, với phạm vi 2D hẹp và dữ liệu mẫu sẵn. Đây là ước lượng lập kế hoạch, phải cập nhật sau giai đoạn 0–1; phụ thuộc SDK và cấu trúc DWG có thể thay đổi đáng kể thời gian.

Ưu tiên làm luồng chỉnh sửa xác định trước khi tích hợp AI để chứng minh engine có thể sửa đúng. Không phát triển Dependency Engine đầy đủ khi chưa xác định được part/feature và nguồn quan hệ.

## 8. API và vòng đời tối thiểu

- POST /documents: upload và tạo job.
- GET /jobs/{id}: tiến độ/lỗi.
- GET /documents/{id}/drawings: danh mục vùng bản vẽ.
- PATCH /drawings/{id}/region: user sửa phạm vi nhận diện.
- POST /drawings/{id}/change-plans: yêu cầu + source revision → kế hoạch/clarification.
- POST /change-plans/{id}/apply: áp dụng kế hoạch vào revision mới; kiểm tra quyền phạm vi.
- GET /revisions/{id}/validation và /preview: báo cáo cùng ảnh/diff.
- POST /revisions/{id}/approve: lưu người duyệt và revision hash.
- POST /revisions/{id}/exports: tạo DWG từ revision đã duyệt và validation hợp lệ.

Vòng đời: uploaded → inspecting → indexed → selected → planned → applied → validated → preview_ready → approved → exporting → exported. Có failed/needs_clarification/needs_scope_approval theo từng bước. Validation lỗi phải quay lại sửa trước khi duyệt. Export có kiểm tra sau ghi riêng.

## 9. Mô hình dữ liệu cần bổ sung

Document: file gốc, checksum, định dạng, units, CAD version và tài nguyên ngoài.
Revision: parent, hash, thao tác, thời điểm, người thao tác, trạng thái.
DrawingRegion: layout, polygon/bbox, entity membership, view references, khung tên, confidence.
EntityRef: document/revision + handle + block instance path; không chỉ dựa vào tọa độ hoặc handle xuyên qua chuyển đổi không kiểm chứng.
Part/Feature: mã chi tiết, hình học, kích thước, vật liệu, số lượng, nguồn và mức xác nhận.
Dependency: source/target, loại, rule, evidence, confidence, confirmed.
ChangePlan: yêu cầu, target scope, operation whitelist, preconditions, expected effects, ảnh hưởng ngoài scope.
BOMItem: part_id, quantity/unit/material, source cells/entities và revision.
ValidationReport/Approval/ExportArtifact: kết quả, revision hash và audit trail.

## 10. Validation và kiểm thử

- Đơn vị và phép biến đổi tọa độ/block đúng; không tự mặc định mm khi không có bằng chứng.
- Các kích thước hình học và annotation thống nhất; phân biệt measured dimension với text override.
- Rule lắp ghép chỉ kiểm tra khi có quy tắc và dữ liệu được xác nhận, không tuyên bố đảm bảo kỹ thuật từ ảnh xem trước.
- BOM khớp mã, vật liệu, số lượng theo semantic model và nguồn đã xác nhận.
- Diff ngoài phạm vi cho phép bằng không về semantics; không so sánh byte toàn file vì writer có thể thay serialization.
- Ca bắt buộc: nhiều layout, nhiều khung trong modelspace, nhiều hình chiếu, block lồng/dùng chung, DIMENSION override, thiếu units, BOM không rõ, XREF thiếu, file lỗi và converter timeout.
- Ca thay đổi: vật liệu, kích thước hình học, cập nhật BOM, tác động qua bản vẽ khác, dependency cycle, hai kế hoạch trên revision cũ, export trước duyệt.
- Sau ghi DWG: đọc lại, đối chiếu nội dung, render lại và mở trong CAD đích tại nghiệm thu.
- Xác định giới hạn dung lượng/entity và thời gian xử lý theo benchmark giai đoạn 1; không cam kết hiệu năng khi chưa đo.

## 11. Công việc nên thực hiện ngay

1. Thu DWG mẫu và yêu cầu sửa mẫu, lập expected results.
2. Chọn một vertical slice: upload một DWG có nhiều khung → chọn một khung → sửa vật liệu → cập nhật BOM → preview → duyệt → xuất DWG.
3. Kiểm chứng DWG round-trip và quyết định engine trước khi mở rộng thao tác kích thước.
4. Bổ sung document/revision/entity reference và scope guard vào nền hiện tại.
5. Xây upload/job/inventory và giao diện chọn vùng; sau đó hoàn thiện vertical slice.

Quyết định đầu vào còn cần người dùng: DWG cơ khí 2D hay có 3D; CAD dùng để nghiệm thu; cách tổ chức bản vẽ (layout/khung/block); ba yêu cầu thay đổi thường gặp nhất; BOM hiện nằm ở đâu; nhu cầu chạy nội bộ/offline hay cloud; khả năng sử dụng SDK thương mại. Có thể tiếp tục nền tảng theo giả định 2D, chạy nội bộ và giữ engine adapter trong khi chờ các câu trả lời.
