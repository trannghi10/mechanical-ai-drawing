# Thử dịch CenterMark bằng AutoCAD native — 21/10/2026

Cập nhật tiếp theo: action đã được nối vào hợp đồng job local và kiểm chứng qua bộ xử lý production; xem [bằng chứng production](native-centermark-production-2026-10-21.md). Các đoạn dưới mô tả trạng thái và phạm vi của probe ở thời điểm thử nghiệm.

Đã kiểm chứng được phép dịch đường tròn và dấu tâm liên kết trên hai cặp thực tế của Detail C, trong các bản sao kiểm chứng cách ly. AutoCAD cập nhật dấu tâm qua đúng action CenterMark; không tháo association hoặc thay dấu tâm bằng nét rời.

Đây là probe phát triển adapter. Chưa đưa phép dịch này vào NativeOperation, apply/export của bản sửa khách hoặc UI. Chưa áp phương án giữ hai khe của cụm hộp–chốt, chưa tạo revision khách và không dùng các DWG thử nghiệm này làm backup sản phẩm.

## Hai phép thử đạt

| Đường tròn / dấu tâm | Vector dịch trong đơn vị CAD nguồn | Artifact |
| --- | --- | --- |
| `3B7FF1` / `3B7FF2` | (+3; −2; 0) | `storage/validation-fixtures/native-center-probe-91d64c8c/` |
| `3B7FD1` / `3B7FD6` | (−4; +1,25; 0) | `storage/validation-fixtures/native-center-probe-bfdc7716/` |

Mỗi thư mục có `center-probe-receipt.json`, DWG và DXF đã mở lại, dữ liệu sai khác inventory và log. Cả hai đạt:

- Đường tròn XY trong layout có đúng một geometric dependency; action body đúng AcDbCenterMarkActionBody, hai dependency trỏ chính xác đường tròn và block dấu tâm tĩnh cùng owner.
- Tâm nguồn và vị trí dấu tâm khớp nhau; sau dịch đều đúng cùng vector. Bán kính, pháp tuyến, owner, block tham chiếu, rotation/scale và các thuộc tính được inventory ghi lại giữ nguyên ngoài phần center/position và bbox dẫn xuất.
- Action được cập nhật bằng callback của Associative Framework và có trạng thái IsUpToDateAssocStatus.
- DWG được lưu, mở lại, kiểm tra đúng cặp dependency và evaluate action lần hai. Hình vẫn đúng, không nhảy trở lại vị trí cũ.
- 39.915 entry inventory ngoài cặp mục tiêu được đối chiếu; tập handle không đổi. Đây là kiểm tra các thuộc tính inventory được liệt kê, không phải so sánh mọi trường nhị phân của mọi đối tượng native.
- DXF xuất được ezdxf đọc độc lập và xác nhận tâm, vị trí, bán kính và reactor.

DWG SHA-256 lần lượt `509235aef6ba9acae94ae83616879685c63a8fd8e1e308af2c6180eb443d15ec` và `bd259d344e6c759d405a5bc0b245ffb1d53c9d9daa91de95ee2c218d5d9e4783`.

DWG nguồn giữ SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`. Vector thử là đơn vị CAD của hình nguồn, không phải quyết định khoảng dịch vật lý của sản phẩm.

## Các kiểm tra phát hiện vấn đề

Lượt đánh giá riêng ban đầu thiếu callback bắt buộc theo tài liệu SDK local nên dấu tâm không đi theo; đã sửa dùng `AssocManager.GlobalEvaluationMultiCallback()`. Phương án evaluate toàn network chỉ là thử nghiệm trung gian, không được giữ trong probe cuối.

Đối chiếu byte chuỗi JSON ban đầu báo khác biệt ở cực trị ellipse rất nhỏ và tên block DIM anonymous. Dữ liệu sai khác chứng minh tên *D được AutoCAD đánh số lại khi SaveAs. Probe cuối giữ nguyên đối chiếu owner/BTR handle và thêm `dimension_block_handle` trên DIM, chỉ không so tên *D tạm. Số thực được đối chiếu bằng dung sai tuyệt đối 1e−7; chuỗi, tập trường, số phần tử và các handle vẫn phải khớp. Hai lượt cuối đều có 23 entry sai khác do độ chính xác số, không có sai khác vượt dung sai sau đối chiếu handle.

Inventory bổ sung normal của CIRCLE/ARC/ELLIPSE và start/end parameter của ELLIPSE để đối chiếu hình học rõ hơn. Không dùng bbox để thay cho các tham số này.

Đường tròn `3B7F86` không có dependency bị chặn đúng trước khi tạo kết quả đạt. Bằng chứng âm: `storage/validation-fixtures/native-center-probe-326658e8/probe-summary.json`. Các probe không đạt không được cấp receipt thành công; CLI trả lỗi trừ trường hợp âm đã chỉ rõ `--expect-rejected` và khớp đúng lý do dự kiến.

## Mã và kiểm chứng hồi quy

`MECHANICALCENTERPROBE` trong `autodesk/MechanicalCad/Commands.cs` chỉ đọc contract cố định `center-probe.json` và bản sao `input.cad`; script `scripts/probe_native_centermark.py` tạo workspace riêng, kiểm hash nguồn, không sửa tài liệu gốc. Endpoint production vẫn chỉ chạy MECHANICALCAD và chưa cho phép action dịch CenterMark.

Lặp lại: `python scripts/probe_native_centermark.py DOCUMENT_ID CIRCLE_HANDLE --dx DX --dy DY`. Đây là phép kiểm chứng phát triển adapter, không phải thao tác sửa bản vẽ khách trên website.

Plugin cuối build và `setup_autocad.py check` đạt trên AutoCAD 2027: runtime key `e071b03d50fcb8cfd3e4bdbfdf731cbd0d776c5ae5c9a8c0c711d74ce576cb4a`. Luồng nạp native, dictionary, text edit có giới hạn, geometry/DIM 100 mm, lưu/mở lại DWG và giữ nguồn đều đạt. **140 bài export/native jobs đạt**, 10,38 giây (`storage/validation-fixtures/pytest-native-centermark-probe-2026-10-21.txt`).

Bước còn thiếu: đưa adapter đã kiểm chứng vào hợp đồng thao tác có scope/hash, đối chiếu dependency và ảnh hưởng trước/sau trong luồng revision; đồng thời xác định danh tính và mốc dịch cả cụm hộp–chốt. Đề xuất tấm xốp riêng tiếp tục chưa xác nhận. Chưa hoàn thành backup toàn Dauphine hoặc sửa mọi DWG.

## Kiểm tra trạng thái đã lưu trước đánh giá lại

Probe được siết thêm: ngay sau mở DWG, trước khi gọi Evaluate, action phải sẵn ở trạng thái IsUpToDate và tâm đường tròn, vị trí dấu tâm, bán kính phải đúng. Như vậy đánh giá lại không thể che giấu một bản lưu chưa cập nhật. Sau đó vẫn đánh giá lại và kiểm tra ổn định như trước. CLI yêu cầu cả hai bằng chứng trong receipt.

Hai cặp đều đạt trên AutoCAD 2027 với runtime key `d588e6b2d7cfadcc9eba22416371e3903df8a9284b60ff58edbbefcd6b49aed3`:

- `3B7FF1` / `3B7FF2`: `storage/validation-fixtures/native-center-probe-7a171542/center-probe-receipt.json`; DWG SHA-256 `a8763e1cb4434eb08f384f556293f07a32839c3b14a48b80605d6583056289c5`.
- `3B7FD1` / `3B7FD6`: `storage/validation-fixtures/native-center-probe-3ddd1346/center-probe-receipt.json`; DWG SHA-256 `f6ece9a802509844a5a6334745d9f50d921bd8615c3ee9ae3462732bbaaa291f`.

Mỗi lượt đối chiếu 39.915 entry inventory ngoài mục tiêu, đọc DXF độc lập đạt, nguồn giữ nguyên và không tạo revision khách hàng. Kiểm tra host sau build cũng đạt đầy đủ các bước native load, dictionary, sửa text, geometry/DIM 100 mm và lưu/mở lại. Đây vẫn là probe phát triển, chưa phải action production.

## Nhận diện ứng viên từ inspection

`cad/native_centermark.py` nhận diện cặp dựa trên reactor hai chiều, geometric dependency, hai dependency cùng action và đúng CenterMark action body. Cả hai entity phải nằm trong requested roots, cùng layout owner và đồng tâm. Inventory partial, có lỗi hoặc truncated bị từ chối. Đây là bằng chứng giới hạn từ các quan hệ được inspector liệt kê; không chứng minh action không có tham chiếu chưa được liệt kê, và vẫn bắt buộc native preflight trước khi sửa.

API đọc `GET /documents/{document_id}/autocad/jobs/{job_id}/centermark-candidates` chỉ nhận inspection local đã ready, kiểm hash original DWG hiện tại và đọc artifact đã được kiểm integrity. Trả inspection ID, source hash và các handle cần ràng buộc cho thao tác tương lai; luôn trả `edit_authorization=false`, `complete_mechanical_group=false`. Không thực thi sửa, tạo revision hay xác nhận mating. Dữ liệu inspection Dauphine đã nhận diện đúng hai cặp trên. Action dịch production vẫn chưa được mở.
