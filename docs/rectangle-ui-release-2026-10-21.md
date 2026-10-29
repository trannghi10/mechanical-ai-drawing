# Bản hoàn thiện luồng MVP rectangle, 21/10/2026

Đã nối chức năng solver → DWG vào giao diện, tìm nhóm và xem trước, API local/cloud và lịch sử job. Phạm vi hoàn thiện là chữ nhật LWPOLYLINE bốn cạnh thẳng có đúng một DIM ngang liên kết vertex 0/1, giữ cạnh trái/chiều cao. Không coi đây là hoàn thành mục tiêu mọi DWG.

## Cách sử dụng

Mở CAD Studio, chọn file. Trong **Công cụ AutoCAD và chẩn đoán file → AutoCAD trên máy / Autodesk APS**, chọn provider rồi **Tìm nhóm chữ nhật trong file**. Công cụ dùng inspection đã lưu; nếu chưa có thì tạo inspection. Khi chọn APS, nút/nội dung chỉ rõ gửi bản sao CAD đến Autodesk. Không tự gửi CAD khi tải trang.

Chọn nhóm qua kích thước/layout và hình nguồn; nhập chiều rộng mới. Intent cố định là giữ cạnh trái và chiều cao. Bấm tạo DWG; theo dõi trạng thái hoặc đóng trang rồi mở lịch sử job. Sau ready, xem hai hình trước/sau và tải DWG. Phần này không ghi đè nguồn hoặc phê duyệt toàn sản phẩm. Chỉnh tiếp bằng cách nhập DWG kết quả thành tài liệu mới; đã có kiểm chuỗi trên cloud.

Thêm hướng dẫn tương ứng trong `/help#rectangle-stretch`. Luồng thao tác không yêu cầu gõ handle hoặc tự tạo JSON.

## Tìm nhóm và preview

Hai provider có endpoint GET trên `/documents/{document_id}/{provider}/jobs/{job_id}/rectangle-candidates` và `/rectangle-preview?polyline_handle=...&dimension_handle=...`.

Candidate discovery là chỉ đọc, dùng inventory/DXF đã được kiểm hash; kiểm source DWG hiện tại, đúng provider và trạng thái ready. Tối đa 100 nhóm và 20.000 DIM; trả scanned/unsupported/truncated. Không trộn selection của bản vẽ hiện tại với phạm vi toàn file: UI ghi rõ tìm toàn file và người dùng chọn đúng nhóm bằng hình. Không sửa hoặc tạo edit job trong discovery/preview.

DIM thiếu association, association không xác minh, nhiều reactor, nhóm không phải rectangle đúng thứ tự vertex hoặc không khớp DIM đều không được đề xuất. Kết quả candidate giữ edit_authorization=false và yêu cầu người dùng chọn target. Preview chỉ đọc đúng polyline/DIM từ DXF native, trả SVG với Cache-Control no-store, không dùng ảnh minh họa thay geometry nguồn.

Job mới lưu native_summary.rectangle_stretch_effects có chiều rộng nguồn/đích, dùng để xem lại sau reload. Job cũ trước tính năng vẫn có link DWG; không tự tạo bằng chứng summary mới cho chúng.

Giao diện chặn phản hồi muộn khi đổi file/provider/nhóm, chặn số không dương hoặc bằng kích thước nguồn và không tự apply khi tìm thấy candidate. Các job đang chạy vẫn được giữ trên server khi người dùng chuyển file.

## Native guard bổ sung

Writer native giờ chặn nếu block hiển thị DIM còn được DIM/INSERT khác sử dụng. Điều này bổ sung cho kiểm vùng ngoài nhóm sau save/reopen. Đã kiểm âm bằng mẫu có INSERT dùng chung DIM block: nhận đúng lỗi `Rectangle DIM visual block has another user`, không tạo DWG kết quả, source hash giữ nguyên.

Plugin local build/check đạt với runtime key `794c1e2359255ab795ccb57401690c36be4c7d8fd18bc108b235288e2fbe7ad8`. Gói cloud .NET 8 được build và cập nhật alias rectangle_mvp theo ủy quyền đã có; alias mặc định và gói cloud mặc định giữ nguyên. Gói trước được giữ tại `autodesk/MechanicalCad-rectangle-mvp-initial.zip`; manifest gói mới ở evidence `cloud-bundle.json`.

## Kiểm chứng thực tế

Evidence root: `storage/validation-fixtures/rectangle-ui-release-2026-10-21/`.

- HTTP thật local: tìm được nhóm nguồn, SVG trước/sau HTTP 200, tạo bản 100→125 mm, history summary đúng, tải DWG thành công. Job `6222df9a051c48e2816933a6681f55e9`. DWG `local-125.dwg`, SHA-256 `66d83ccf8222eb7a47a56034510494ab68ec194dedd269564c09e1adbef38e0c`. Proof `local-http-verification.json`.
- Cloud chỉnh lần hai: nhập chính output 120 mm từ lượt trước, đổi thành 140 mm qua API APS và mở lại. Document `c864933a6ea14ba085687c9779ab180c`, inspection `897a9903d0bc45dfa661d35414ae1769`, edit `f4f673b808c9432399318689f5d10170`. Output SHA-256 `d3b2895d2b41632fe9599c0fd6bf0e7cdbdf2b6598161110a65607d92b53280c`. Artifacts trong `cloud-second-edit/`.
- Proof `two-edit-verification.json`: chuỗi 100→120→140, output hash lượt một chính là source hash lượt hai; các tọa độ, chiều cao 50, cạnh trái, DIMASSOC handle/vertex và control LINE giữ đúng trong dung sai 1e-7. Chưa chứng minh mọi kiểu chỉnh lặp hoặc mọi database object.
- `reject-shared-visual/`: native negative guard đạt, không sửa nguồn.
- Node harness `verify_frontend_rectangle.js` và `verify_frontend_aps.js` đạt: startup không upload/edit, explicit target, local/cloud routing, pending job, comparison và stale document. Đây là kiểm hành vi bằng DOM harness; chưa có visual QA trên trình duyệt thật trong môi trường hiện tại.
- Toàn bộ suite trước kiểm DIM không association: **1.840 đạt, 2.731 warning thư viện, 365,47 giây**; log `pytest-full.txt`. Sau khi phát hiện và sửa trường hợp association=None trên Dauphine, thêm hai regression; tập discovery/rectangle/binding **39 đạt, 19 warning, 2,10 giây**. Không gọi số 1.842 là full suite đã chạy nếu chưa chạy lại toàn bộ sau hai test mới.

## Rà soát Dauphine thật

Chỉ đọc native copy `51ec94944c4443b19fb8d5bd7930a6dd`, inspection `daacc85086d44bb3afb76f277e7ade6f`. Quét 1.221 DIM, không có nhóm nào đáp ứng phạm vi rectangle một DIM của adapter mới, không truncated. Proof `dauphine-readonly-audit.json`. Việc này không nói rằng mọi chức năng trước đó đều không sửa được Dauphine; chỉ nói adapter rectangle mới chưa mở thêm nhóm trên file đó.

Audit ban đầu phát hiện DIM không association làm hàm nhận None; đã sửa discovery/preview báo không hỗ trợ thay vì lỗi AttributeError và thêm regression. Không đổi DWG khách hàng, không cấp quyền cho nhóm polyline–6 DIM hoặc đề xuất xốp chưa xác nhận.

## Bản đang phục vụ

Backend cuối đã nạp lại (PID 20268 lúc triển khai). HTTP root/module/hướng dẫn đều 200; Dauphine candidates trả 200 với danh sách rỗng đúng phạm vi; lịch sử cloud 120→140 và SVG trước/sau đều đọc được. Proof `deploy-verification.json`; SVG `cloud-before.svg` và `cloud-after.svg`. Mở `http://127.0.0.1:8765/` để dùng giao diện.
