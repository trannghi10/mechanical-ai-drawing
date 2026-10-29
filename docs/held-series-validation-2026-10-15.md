# Đồng bộ chuỗi chi tiết khi một vách thay đổi — 15/10/2026

Đã mở rộng engine dùng chung cho DWG mới: khi một chi tiết thay đổi và người dùng yêu cầu giữ kích thước ngoài cụm, engine tính lại cả chuỗi chi tiết cùng loại nằm giữa hai mặt lắp. Không dùng tên file, mã sản phẩm hoặc handle riêng của khách hàng. Không đổi phần nhận diện/chọn khung, nhà cung cấp AI hay cấu hình bảo mật.

## Phần đã triển khai

- Hỗ trợ 2–32 chi tiết nối tiếp có định nghĩa CAD tương đương hoàn toàn, cùng tham số DIM nguồn. Một mặt dẫn động thay đổi; mặt đối diện được giữ theo DIM tổng thật và yêu cầu của người dùng.
- Tính kích thước chung từ khoảng lắp còn lại, hệ số DIM và các khe hở nguồn. Cập nhật đường bao, lỗ, DIM, vị trí từng instance, bản chi tiết và BOM; giữ số lượng vật tư.
- Hỗ trợ profile có rãnh, POLYLINE cũ, block lồng và xoay theo hệ trục đo thật. Không coi số đo ghi đè là bằng chứng giữ kích thước.
- Kiểm tra lại binding, phương trình, DIM tổng, mốc giữ, hình/DIM/BOM và chuyển vị của từng thanh trước apply/duyệt. Thiếu một recipe, một thanh hoặc đổi sai mặt giữ đều bị từ chối.
- Dùng chung chứng minh mốc ngoài cho bộ giải một chi tiết và bộ giải chuỗi, tránh hai cách kiểm tra khác nhau.

Ví dụ, sau khi chọn cụm có DIM/BOM phù hợp:

```text
Mã [mã chi tiết] độ dày từ 2 thành 1.2 mm, giữ dưới; giữ kích thước ngoài cụm
```

Mốc dưới/trên phải phù hợp với hướng đo và ý định thiết kế của bản vẽ. Nếu không có yêu cầu giữ ngoài, engine không tự áp đặt mốc này; các quy tắc dịch chuyển theo tiếp xúc vẫn được kiểm tra riêng.

Mã chính: `graph/native_series_fits.py`, `graph/native_span_fits.py`. Hồi quy được thêm vào file kiểm thử hiện có, không tăng số file `test_*.py` (vẫn 19 file).

## Kiểm chứng qua DWG và API thật

`scripts/verify_native_series_dwg.py --one-wall` tạo file mới, chuyển sang DWG bằng ODA, upload với tên ngẫu nhiên và dùng bộ nhận diện bình thường. Không cung cấp mapping hoặc liên kết tham số thủ công cho engine. Các file tổng hợp được ẩn khỏi danh mục tài liệu khách hàng ngay sau upload theo hash nguồn.

| Trường hợp | Kết quả mở lại DWG | Nghiệm thu |
| --- | --- | --- |
| Vách 100 → 80, hai thanh nhận | Mỗi thanh 100 → 110 mm, giữ ngoài 400 mm | Duyệt, tải HTTP 200, ODA mở lại; 4,025 giây |
| Vách 100 → 120, bốn thanh có rãnh/POLYLINE cũ | Mỗi thanh 100 → 95 mm, giữ ngoài 600 mm | Như trên; 4,493 giây |
| Vách phía đối diện 100 → 80, khe hở 2 mm | Hai thanh 100 → 110 mm, giữ ngoài 402 mm và khe hở | Như trên; 4,173 giây |
| Độ dày vách 2 → 1,2 | Hai thanh 100 → 100,4 mm, giữ ngoài 302 mm | Như trên; 5,153 giây |
| Các hình rời cùng nằm trong block cụm/công đoạn, chưa rõ vai trò | Chưa chứng minh được mọi occurrence của mặt giữ | Không cho duyệt/thực thi; apply trả HTTP 422 |

Bốn bản đã xuất được kiểm tra vị trí từng thanh, hình/lỗ, DIM tổng, khe hở, BOM và quantity sau ODA mở lại. Kiểm tra profile bằng FreeCAD đạt. Bảng công đoạn phân biệt đúng chi tiết thay đổi và mặt giữ nguyên đã có chứng minh. Nguồn không đổi. Các thời gian trên là của fixture nhỏ trên máy hiện tại, không phải cam kết tốc độ cho mọi file.

Biên nhận, ID kế hoạch/bản sửa, hash DWG và đường dẫn backup: `storage/validation-fixtures/native-series-dwg-8b8708de/receipts.json`.

**994 kiểm thử Python đạt**, gồm 20 trường hợp mới về tăng/giảm, đổi dày, hai phía dẫn động, block xoay/lồng, rãnh, khe hở, BOM/quantity, nguồn không đổi và từ chối thiếu/sai chứng cứ. Log: `storage/validation-fixtures/pytest-held-series-final-2026-10-15.txt`. Backend đã nạp mã mới; `/health`, `/ai/status`, `/cad/capabilities` trả HTTP 200.

## Phạm vi chưa hoàn tất

Đây là mở rộng một lớp quan hệ lắp ghép dùng chung, **chưa phải khả năng sửa đúng mọi DWG**. Cùng mã vật tư không đủ để chia mức thay đổi cho các chi tiết khác hình hoặc khác tham số; chuỗi có nhánh, thiếu DIM thật/mặt lắp hoặc hình chưa rõ vai trò vẫn cần bổ sung ràng buộc. Block động, proxy association và các quan hệ thiết kế còn thiếu vẫn có giới hạn.

Đợt này không chỉnh file khách hàng. **Backup toàn Dauphine chưa hoàn chỉnh**; bản xem trước gần nhất vẫn là revision `c75fb805`. Các liên kết/hình cụm/đóng gói còn thiếu được liệt kê trong `docs/native-dimensions-and-dauphine-2026-10-15.md`. DWG tổng hợp đã kiểm chứng không thay thế nghiệm thu sản phẩm đó.
