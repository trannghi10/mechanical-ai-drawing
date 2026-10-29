# Inventory native có reactor và extension dictionary

Cập nhật tiếp theo: [đã xử lý point reference lồng của DIM 3DFA20](dimassoc-perpendicular-2026-10-21.md), kiểm chỉ đọc bốn DIMASSOC và sửa/xuất CAD trên mẫu tổng hợp. Các ghi nhận unsupported dưới đây mô tả trạng thái trước thay đổi đó. Hai action native của toàn nhóm thực tế vẫn cần adapter riêng.

Inventory AutoCAD bổ sung `persistent_reactor_handles` và `extension_dictionary_handle` trên từng entity được liệt kê. Danh sách reactor live được sắp xếp ổn định; không coi metadata thiếu ở artifact cũ là danh sách rỗng. Đây chỉ là topology qua các trường này, không phải toàn bộ quan hệ native hoặc quan hệ lắp ghép.

`aps_context.attach` đưa cả entity chỉ có reactor vào native facts, giữ nguyên cờ review_only của context và ràng buộc hash/owner/path hiện có. `native_topology_available` chỉ true khi tất cả entity trong inventory có hai trường mới; artifact cũ trả false. Metadata không cấp quyền sửa hoặc suy ra nhóm cơ khí.

Lõi CenterMark dùng inventory này trong snapshot trước/sau, nên kiểm tra ngoài nhóm nay bao gồm cả handle reactor và extension dictionary, bên cạnh các thuộc tính đã liệt kê trước đó.

## Mẫu polyline và sáu DIM thực tế

Native inspection job `ea4b1d186ca4453e9db9cd06c55ef263`, nguồn bản sao `51ec94944c4443b19fb8d5bd7930a6dd`, chọn `3DFA1C`, `3DFA24`, `3DFA29`: 28 node/67 cạnh, không lỗi/truncated. Polyline `3DFA1C` có sáu reactor; kiểm trực tiếp DXF cùng job và DXF native-import trước đó đều có đủ sáu:

- DIMASSOC `3DFA1F`, `3DFA22`, `3DFA27`, `3DFA2C`, qua dictionary sở hữu đến các DIM `3DFA1D`, `3DFA20`, `3DFA25`, `3DFA2A`.
- Geom dependency `3E032B` thuộc action `3E0329`, body `AcDbAssocRotatedDimActionBody`, DIM đích `3DFA24`.
- Geom dependency `3E0331` thuộc action `3E032F`, cùng loại body, DIM đích `3DFA29`.

Các association đều tham chiếu polyline; đây là dữ liệu để phát triển adapter đóng nhóm polyline + sáu DIM, chưa phải bằng chứng cho phép sửa nhóm này. Không áp dụng bản sửa lên chi tiết thật hoặc xác nhận mating từ các liên kết annotation.

Đọc point binding từ DXF: DIM `3DFA1D`, `3DFA25`, `3DFA2A` trả `verified_source_points` về `3DFA1C`; DIM `3DFA20` trả `unsupported_source_points`, lý do `DIMASSOC thiếu/thừa point reference`. Không coi việc thấy handle polyline trong object là đủ để cho phép sửa. Dữ liệu tại `group-discovery.json` trong thư mục kiểm chứng dưới đây.

## Đối chiếu readback

`cad/native_topology.py` và `scripts/audit_native_readback_topology.py` đối chiếu type/owner, tập reactor và extension dictionary của inventory với DXF cùng job, qua artifact đã kiểm integrity.

Kết quả `storage/validation-fixtures/native-topology-polyline-dim-2026-10-21/topology-comparison.json`:

- 39.917 entity được kiểm, không thiếu metadata.
- Không có khác biệt trong tập reactor.
- Có 10 khác biệt extension dictionary, tất cả là ACAD_TABLE. Native inventory ghi null; DXF có thêm dictionary với duy nhất entry `ACAD_XREC_ROUNDTRIP` loại XRECORD.

Báo cáo vẫn giữ trạng thái `listed_topology_differs`, liệt kê từng handle và entry; không tự bỏ qua các khác biệt, không kết luận mất liên kết hoặc coi đây là quyền sửa bảng. Không dùng bảng thống kê gộp theo loại reactor thay cho kiểm từng entity.

## Kiểm chứng CAD sau khi tăng điều kiện đối chiếu

Plugin build/check AutoCAD 2027 đạt, runtime key `54e40ef469b56b030efe8b6d07cc8ef3bc858812577dcaea046bd33cf090dfae`.

Nhóm hai CenterMark, hai vector khác nhau, đã qua HTTP production và kiểm topology mới trước/sau:

- Inspection `cea6d54e98f7485abcbb0f18328e41a7`.
- Edit `9e1dcf2f3b2c42dc9ddffc2cc2bc1261`.
- DWG SHA-256 `f9e30f32edcbfa2c9d14b1f8158e748f7371386225f88443a4d555edb7ef981d`.
- 39.913 entry ngoài nhóm được giữ trong dung sai, bao gồm reactor/dictionary handles; lưu/mở lại DWG, evaluate ổn định và DXF độc lập đạt.
- Receipt `storage/validation-fixtures/centermark-topology-regression-2026-10-21/receipt.json`.

Nguồn giữ SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`; không tạo revision khách. Chưa có adapter sửa polyline kèm cả sáu DIM trong mẫu này. Đề xuất tấm xốp tiếp tục chưa xác nhận.

**171 bài** topology/CenterMark/export jobs đạt, 12,59 giây. Bộ so sánh kiểm metadata cũ, entity bị xóa, reactor dư/thiếu và dictionary không khớp; entity đã bị xóa trong entitydb cũng được báo khác biệt thay vì làm hỏng lượt audit. Native context có kiểm thử riêng cho facts chỉ có reactor và cờ legacy topology unavailable. Không chạy lại toàn bộ 1.741 bài trong lượt chỉ bổ sung metadata/audit này.
