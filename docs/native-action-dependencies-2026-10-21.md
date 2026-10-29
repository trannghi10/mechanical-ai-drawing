# Đọc dependency trực tiếp của associative action

Native inspector đã bổ sung `AssocAction.GetDependencies(true,true)` cho từng action không phải `AssocNetwork`, tạo cạnh `native:Dependency`. Giới hạn 128 dependency/action, 256 node và depth 6 vẫn áp dụng; vượt giới hạn hoặc lỗi được báo partial. Không mở rộng shared network thành toàn bộ action. Đây là đọc dữ liệu, không evaluate hoặc cấp quyền sửa.

Graph mới có `action_dependency_limit=128`. Khi có metadata này, bộ nhận diện CenterMark yêu cầu tập dependency được action liệt kê khớp đúng hai dependency đang sở hữu hình nguồn và dấu tâm. Graph có dependency dư, thiếu hoặc mâu thuẫn không tạo ứng viên. Artifact cũ chưa có metadata vẫn dùng cơ chế kiểm graph cũ và native preflight bắt buộc; không cấp quyền mới từ dữ liệu cũ.

## Phân biệt cung tròn đồng tâm và nguồn thực tế

Rà inventory nguồn tìm thấy 61 cặp vị trí ARC–INSERT trùng tâm. Đây chỉ là các vị trí hình học, không phải 61 liên kết đã xác nhận. Chọn ba ARC và năm INSERT để đọc native: job cuối `482cd7f80fe045feb3e4555772fd5e86`, nguồn bản sao `51ec94944c4443b19fb8d5bd7930a6dd`. Inspector nhận 38 node/81 cạnh, không lỗi/truncated. Bản inspector trước chưa đọc GetDependencies chỉ nhận 28 node/51 cạnh ở cùng tập root.

Các action của năm dấu tâm đều tham chiếu CIRCLE, không tham chiếu ba ARC đã chọn:

| Dấu tâm | Action | Hình nguồn thực tế | Bán kính CAD |
|---|---|---|---:|
| 3B2DCC | 3B2DD8 | CIRCLE 3B2DCB | 25 |
| 3C7A4B | 3C7AA3 | CIRCLE 3C7A44 | 4 |
| 3C7A4C | 3C7B26 | CIRCLE 3C7A41 | 4 |
| 3C7A54 | 3C7B2B | CIRCLE 3C7A53 | 5 |
| 3C7A5B | 3C7B30 | CIRCLE 3C7A5A | 5 |

ARC roots: `3B2DC6`, `3C7A4E`, `3C7A55`. Ví dụ ARC `3B2DC6` có R15,875, nhưng dấu tâm đồng vị trí `3B2DCC` thuộc CIRCLE R25. Không mở adapter ARC từ bằng chứng đồng tâm này. Không suy rộng kết quả của ba ARC sang toàn bộ 61 ứng viên.

Inventory, receipt và kiểm tra ràng buộc: `storage/validation-fixtures/arc-centermark-expanded-final-2026-10-21/`, đặc biệt `binding-verification.json`. Kiểm tra xác nhận mỗi action có đúng hai dependency, đích là một CIRCLE và một INSERT; không đích nào là ba ARC root. Hash bản sao và DWG khách gốc đều giữ `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.

## Kiểm chứng sửa và hồi quy

Cặp mới CIRCLE `3B2DCB`–mark `3B2DCC` đã qua job production trên bản sao, delta CAD `[-1.5,0.75,0]`, giữ bán kính R25 và association:

- Inspection `eeab51d7d110424ca3bb6050a76a324e`.
- Edit `219a11a23fab44778c701a6b68c7cf65`.
- DWG SHA-256 `28dca181b60837dabe7d8f8c5697367c00a70923f23fcfb3e9d65ce9c9109f14`.
- Receipt `storage/validation-fixtures/native-centermark-job-d331fa8f/receipt.json`.

Đã kiểm persisted state trước evaluate trên DWG mở lại, ổn định sau evaluate, đối chiếu inventory ngoài mục tiêu và DXF độc lập qua bộ nhận kết quả chuẩn. Đây là cặp thứ 12 có bằng chứng trên cùng DWG, ngoài 11 cặp của khung `3B3987`; không phải xác nhận dịch cả cụm.

Plugin cuối build và host check AutoCAD 2027 đạt với runtime key `cdd3cdb5a479cf876be129723f65b25cf5c6a50703ac4a2bb1a32a286c2bbc75`. **160 bài** CenterMark/export jobs đạt, 11,64 giây, gồm kiểm dependency action dư/thiếu. Chưa xác nhận hỗ trợ sửa ARC gắn CenterMark, nested mark hoặc mọi DWG. Đề xuất tấm xốp vẫn chưa xác nhận.

Hồi quy HTTP theo vùng chọn trên plugin cuối cũng đạt: inspection `839a6b422b10459f9f38616ca6da7531` giữ 11 cặp hợp lệ của khung; native edit `5109ba2192bc452cb4d3b5dd66416ba1` xuất/mở lại và đọc DXF độc lập đạt, DWG SHA-256 `9cc399c34fdce357a6ee8b43ad18a854e890d76341175541d22dff469a12f0d3`. Sai tâm nguồn vẫn nhận 422. Receipt: `storage/validation-fixtures/native-action-selection-regression-2026-10-21/receipt.json`.
