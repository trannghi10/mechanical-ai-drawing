# Thành hộp trong block lồng — kiểm trên Dauphine thật, 22/10/2026

Đã sửa thêm một chi tiết trên DWG thực tế bằng bộ sửa chung: mã **8.1.05190.002**, thành hộp **1,2 → 1 mm**. Giá trị 1 mm là phép thử phát triển trong revision xem trước, chưa phải phương án vật liệu được kỹ sư phê duyệt. Không đụng đề xuất xốp chưa xác nhận.

Website tìm đúng mã từ toàn hồ sơ, không cần gửi handle/khung trong yêu cầu. Plan `9f1bf4e8efa149cba4cdf823711f94af`, job `61e4997b5ab642209475871db621c747`, compiler `checked_tube_wall`. Hệ thống vẫn chặn thực thi toàn yêu cầu do các quan hệ công đoạn/lắp ghép chưa đủ; đã dùng đúng API checked partial preview có sẵn.

## Phần được bổ sung

Đường thành trong thực sự có lớp Hidden, nằm trong hai block đặt ở tọa độ khác nhau. Bộ cũ chỉ nhận các LINE cấp layout nên bỏ sót. Bộ mới đưa từng entity vào tọa độ layout theo ma trận instance, kiểm tiết diện/đường thành/DIM, rồi trả thao tác về đúng đường dẫn và tọa độ cục bộ. Writer tiếp tục cô lập definition để bảo vệ các instance khác. Không có nhánh theo tên file/mã/handle trong quy tắc hình học.

DIM độ dày gắn vào đỉnh polyline tiết diện cũng được hỗ trợ khi tọa độ nguồn chứng minh binding. Không thay số DIM bằng text cố định. Các DIM ghi số cố định vẫn không được dùng làm số đo thật.

Quy cách BOM dùng chiều dài danh nghĩa 347,5 mm, nhưng hình đo thật là 347,5003629724961 mm. Bộ đối chiếu mới dùng độ chính xác thập phân native đã ghi trong DIM để kiểm tên quy cách; không nới một dung sai chung cho mọi hình. Số đo thật và tọa độ thật tiếp tục giữ nguyên. Độ làm tròn không biết, tỷ lệ DIM khác 1, DIM literal hoặc nominal không khớp số hiển thị vẫn bị từ chối.

Khi sao chép hình chữ của hai bảng native, phát hiện extension dictionary rỗng do AutoCAD tạo. Đã thêm bảo toàn đúng DICTIONARY rỗng, hard-owned, owner đúng entity, đúng cấu trúc tag đã nhận diện. Clone giữ dictionary và remap owner/handle; không xóa dictionary để vượt kiểm. Dictionary có nội dung, reactor, XDATA, owner sai hoặc dictionary lồng vẫn không được mở theo quy tắc này. Kiểm cấu trúc tiếp tục chạy sau ghi và sau native round-trip.

## DWG kết quả đã được nhập lại độc lập

Revision `cea85585ac9240eaab6ec1ceb7e1ed0e`, xuất **toàn document** qua AutoCAD local. Toàn file được giữ lại nhưng thay đổi cơ khí chỉ bao phủ các quan hệ đã chứng minh; hai khái niệm này không được gộp thành hoàn thành toàn sản phẩm.

| Đối chứng trên DWG tải xuống, nhập lại độc lập | Kết quả |
|---|---|
| Polyline tiết diện ngoài | Giữ nguyên 14×14 mm |
| Polyline trong | Thành bốn phía 1 mm |
| Bốn LINE bên trong hai block | Tọa độ sau sửa đúng, giữ đường ngoài |
| DIM độ dày | Đo thật 1 mm |
| Hai DIM chiều dài | Cùng giữ đúng 347,5003629724961 mm; nominal vẫn 347,5 |
| Hai ô BOM native | `14x14x1.2x347.5` → `14x14x1x347.5` |
| Chữ BOM/ghi chú liên quan | Khớp thao tác đã kiểm |
| Thành viên không sửa trong hai block hình | 14 thành viên giữ nguyên |
| Inventory toàn document cấp layout | Đủ 23.116 đối tượng, handle/loại/layout khớp |
| Đối chứng ngoài các root được sửa | 21.851 đối tượng đạt; không đồng nghĩa mọi thuộc tính của mọi loại đều được kiểm |
| OLE | Sáu payload/metadata/XDATA giữ nguyên |
| DWG và DXF gốc | SHA-256 giữ nguyên |

Nguồn DWG SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`. Kết quả SHA-256 `a28800b134664beee65145da59e917291decfe2ba3a6b1f8d3fd36e0c700c0ef`. Document nhập lại độc lập `df3ce521453846f6a0a5372473efac66`.

- [DWG đầy đủ, bản thử](../storage/validation-fixtures/dauphine-wall-evidence-2026-10-22/native-61e4997b5ab6/after.dwg).
- [Receipt và toàn bộ kết quả đo](../storage/validation-fixtures/dauphine-wall-evidence-2026-10-22/native-61e4997b5ab6/run.json).
- [Dữ liệu/ảnh nguồn năm chi tiết](../storage/validation-fixtures/dauphine-wall-evidence-2026-10-22/evidence.json).
- [Corpus sau khi đọc block lồng](../storage/validation-fixtures/dauphine-wall-evidence-2026-10-22/tube-corpus-nested.json).

Corpus mới có hai chi tiết đạt lập kế hoạch hình học (LEG6949 và một Dauphine), bốn chi tiết Dauphine còn bị chặn: hai hình dùng DIM literal và hai hình cắt khuyết/xiên chưa đủ binding thành trong. Đây không phải thêm hai file công ty mới. Ba mã LEG6949 thiếu quan hệ, hình công đoạn/đóng gói Dauphine, cơ chế nhiều tài khoản và tự phát hành toàn công ty vẫn chưa hoàn thành.

## Giữ dữ liệu nội bộ

Người dùng không cung cấp đường dẫn kho DWG công ty vì dữ liệu nội bộ. Tiếp tục phát triển với tài liệu đã có và ca tổng hợp; không cần chuyển kho DWG cho dịch vụ ngoài. Các phép CAD trong báo cáo chạy bằng AutoCAD/ODA cục bộ, AI cấu hình local-only, `cloud_used=false`, `production_release=false`, `engineer_accepted=false`.

Đã mở rộng chốt cùng máy/cùng nguồn từ thao tác ghi sang cả đọc danh mục, preview và download; bỏ CORS wildcard và kiểm Host để tránh website khác truy cập CAD qua trình duyệt. HTTP thật kiểm đọc local 200, Origin ngoài 403, Host ngoài 403. Cơ chế này dành cho triển khai loopback hiện tại, không thay cho đăng nhập/phân quyền khi mở mạng nội bộ/VPN.

Kiểm trước chạy toàn suite: 952 bài Python liên quan đạt; thêm nhóm kiểm truy cập và xuất 182 bài đạt (có phần trùng, không cộng thành tổng). 13 script frontend đạt. Sau đó suite cơ sở đạt 2.142 bài, kiểm bổ sung ARC đạt riêng; suite nền tài khoản ngày 23/10 đạt 2.155 bài. [Đợt kiểm tiếp theo](company-accounts-release-review-2026-10-23.md) bổ sung 121 bài liên quan sau sửa mới và 15 script frontend; các số có phần trùng, không cộng thành tổng.
