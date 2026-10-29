# Màn hình và API xem xét liên kết DIM, 21/10/2026

Đã tích hợp bước lập hồ sơ đề xuất vào backend và giao diện local. Người dùng có thể xem hai liên kết cần gắn lại, đỉnh nguồn, hình polyline/sáu DIM và mở lại hồ sơ bằng URL. Đây là bước review có lưu trạng thái, chưa phải luồng thực thi/phát hành DWG.

## Đã kiểm trên backend đang chạy

URL local:

`http://127.0.0.1:8765/relationship-review?document=51ec94944c4443b19fb8d5bd7930a6dd&proposal=f1cf1b3653bf40caa4bdd53ef9d9439d`

Hồ sơ thực `f1cf1b3653bf40caa4bdd53ef9d9439d` có hai đề xuất cho `3DFA25` và `3DFA2A`, nguồn SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`, scope fingerprint `ba16c9e82825667d407c643feb5532ce53a74cd9b2b41c4bfc63d9b2d236c847`. HTTP POST thành công, GET hồ sơ/preview/trang HTML thành công; preview SVG 9.211 byte. Bằng chứng ở `storage/validation-fixtures/relationship-review-release-2026-10-21/http-verification.json` và `preview.svg`.

## Hành vi

- POST `/documents/{id}/autocad/relationship-proposals`: chỉ nhận inspection ID, polyline handle và source hash. Cần job local đã ready, mode inspect, hash đúng file hiện tại và topology được đọc đầy đủ. Chặn các trường thực thi ngoài schema.
- Lưu JSON trong `storage/documents/{id}/relationship-proposals/{proposal_id}.json`; fingerprint gắn plan, tài liệu, inspection và hash của inventory/DXF. Đây là kiểm toàn vẹn nội bộ, không phải chữ ký mật mã chống người có quyền sửa toàn workspace.
- GET hồ sơ và preview đều kiểm lại nguồn, artifact hashes và fingerprint; không trả hồ sơ cũ như kết quả hợp lệ khi nguồn thay đổi.
- Preview là hình nguồn. Gắn lại liên kết chưa làm thay đổi tọa độ nên không có ảnh hình học sau sửa giả lập.
- `release_gate.allowed=false`, `edit_authorization=false`, `design_intent_confirmed=false`. Không tự gọi AutoCAD hoặc APS khi lập hồ sơ. Các phép sửa thử và challenge đã được kiểm ở runner riêng, xem `dimension-relationship-repair-2026-10-21.md`.

Trang `/relationship-review` có nhập thông tin nguồn, bảng đầu A/B theo vertex, hình xem trước, trạng thái, liên kết hồ sơ JSON và khôi phục hồ sơ từ URL. Đã thêm đường dẫn từ `/help`.

## Validation

`tests/test_relationship_repair_service.py`: **6 passed, 7 warnings**. Gồm persist/reopen/preview, stale source, inventory đổi, plan sửa, release flag bị đổi, HTTP schema và provider. Một lần đầu 1 failed/22 passed do tuple/list khác nhau sau JSON round-trip; đã chuẩn hóa plan và chạy lại cả 6 test service đều đạt. 17 test planner/CFB/OLE đã qua ở lượt trước, không chạy lại toàn suite trong lượt này.

`node scripts/verify_frontend_relationship_review.js`: đạt luồng submit, bảng đỉnh, preview URL, khôi phục nút, lỗi stale nguồn và xác nhận không gửi native-edit request. Đây là kiểm logic DOM giả lập, chưa phải kiểm giao diện bằng trình duyệt hoặc visual QA. Backend local PID 4056 được khởi động lại sau khi xác minh đúng tiến trình cũ.

## Chưa hoàn thành toàn dự án

Chưa nối thực thi sửa liên kết vào managed job/revision/undo và tải DWG từ màn hình này. Chưa kiểm pixel hiển thị dung sai/OLE sau no-op save. Hai đầu A của native DIM vẫn chưa có binding nguồn được chứng minh. Chưa bao phủ block động phức tạp/proxy, ý đồ cơ khí hoặc đồng bộ toàn sản phẩm Dauphine. Không dùng màn hình này để tuyên bố sửa được mọi DWG.

Bước tiếp theo là managed job cho phép sửa thử và gắn các báo cáo control/challenge vào cùng revision, có trạng thái kiểm chứng rõ ràng; mở phát hành chỉ sau khi các điều kiện cần thiết của đúng nhóm sửa đã đạt.
