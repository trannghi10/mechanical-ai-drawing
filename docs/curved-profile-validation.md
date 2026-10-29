# Đường bao cong và hình chiếu cùng định nghĩa — 12/10/2026

## Chức năng đã triển khai

- `cad/curved_profiles.py` đọc đường bao kín từ LINE/ARC hoặc LWPOLYLINE có bulge, kiểm tra giao nhau bằng hình học giải tích. Bản CAD xuất vẫn giữ ARC/bulge; không biến cung thành đoạn thẳng. Lấy mẫu chỉ phục vụ kiểm tra vùng bên trong và hiển thị.
- `cad/measured_features.py` gắn DIM với đúng điểm đo trên đường bao sau chuyển tọa độ. Nhận diện cực trị cung theo trục DIM, kể cả block quay 30°, 90° hoặc tỷ lệ đều. Mã chi tiết cần tên/thuộc tính native hoặc khung chi tiết có chủ sở hữu duy nhất từ nguồn.
- `cad/parametric.py` co/giãn các cạnh nối thẳng song song trục DIM; hai đầu cong dịch nguyên khối, giữ bán kính/bulge. Lỗ giữ đường kính và khoảng cách tới đầu gần nhất. DIM bán kính đi theo cung/lỗ, kể cả DIM nằm ngoài block. Chặn cung đi qua vùng co/giãn, cạnh đảo chiều, lỗ chạm biên, cạnh trùng/tự giao và nét không rõ chủ sở hữu cắt qua profile.
- `graph/measured_views.py` mở rộng recipe sang hình chiếu của cùng mã chi tiết khi **toàn bộ định nghĩa cục bộ** có ánh xạ một-một và điểm đo DIM tương ứng. Hỗ trợ block vô danh, bản sao đổi handle, quay/tỷ lệ đều và DIM đảo hai đầu. Khác lỗ, khác mã, không rõ chủ sở hữu hoặc DIM trùng không đủ bằng chứng để tự nhận là cùng hình chiếu. Đây không phải quy tắc suy phối cảnh hay tiếp xúc giữa hai mã khác nhau.
- Bộ kiểm tra kế hoạch lưu tự tính lại hình chiếu nhận. Bỏ thao tác hình học hoặc DIM của hình chiếu nhận bị chặn. Luồng AI diễn giải lệnh tự nhiên dùng cùng bộ biên dịch kiểm chứng, không tự cấp quyền cho hình chiếu khác.
- `/cad/capabilities` công bố rõ hỗ trợ và giới hạn. Bộ nhận diện khung/vùng gạch đỏ không thay đổi. Không thêm model/dịch vụ trả phí.

## DWG xuất và đọc lại

Chạy:

```powershell
python scripts/verify_curved_backup.py
python scripts/verify_curved_backup.py --polyline
```

Hai trường hợp đi qua upload DWG, lập kế hoạch, tạo revision, kiểm tra phạm vi, xuất DWG bằng ODA và mở lại. Profile dài 100 → 76 mm, block quay 30°/tỷ lệ 0,5; bán kính cung 10 mm, lỗ R2, DIM và BOM đúng. Có DIM bán kính bên ngoài block ở cả hai trường hợp. Hash DWG/DXF nguồn không đổi; các bản kiểm thử chưa duyệt.

| Loại | Biên nhận trong `storage/validation-fixtures/curved-backup/` | SHA256 DWG |
|---|---|---|
| LINE + ARC | `6bcf9095931245ca89ef3ec25de5c6fc/receipt.json` | `f9b6b24c5339d2f7950fc3f946999fcc4275c99759a3057d38ac3d6df8dc49c3` |
| Polyline có bulge | `32fc3ef4793f4c91b66596b6ccc396c8/receipt.json` | `d7d3d1f0ec9d41f27b9c883a3f864777b3e3c4548bbbbe5ee8786ae9a35834cc` |

Đây là **fixture kiểm thử**, không phải backup Dauphine. Kiểm thử hình chiếu vô danh, bản sao đổi handle và DIM nhận nằm trong `tests/test_measured_views.py`; các ca này xác nhận sửa/đọc lại DXF.

## Audit Dauphine nguồn

`python scripts/audit_curved_features.py` chỉ đọc nguồn, không tạo bản sửa:

- 61 phạm vi, 32.614 entity; 97 profile gắn DIM, trong đó 17 profile có cung.
- 7 cặp hình chiếu có cùng định nghĩa nguồn và DIM tương ứng. Chỉ số này xác nhận phép đối chiếu nguồn, không chứng nhận mọi kích thước của các profile đều co/giãn được.
- Biên nhận: `storage/validation-fixtures/curved-source-audit-34ee84f35e1a44fb81c56044397a0fff.json`; `source_unchanged=true`, `complete_backup=false`.
- Audit context yêu cầu hai ý: 27.152 token đầu vào, còn 5.360 token đầu ra trong runtime 32k; các lựa chọn thành phẩm 700 mm, khung 697 mm và tấm 1 mm chờ cấp mã vẫn được giữ. Biên nhận `storage/validation-fixtures/dauphine-compound-token-audit.json`.

**Chưa hoàn tất:** backup đầy đủ Dauphine; liên kết phối cảnh, biến dạng ellipse/spline tùy ý, mốc tiếp xúc chưa có bằng chứng, quan hệ uốn/phôi cần bend allowance và hình đóng gói rời. DWG 2D không luôn chứa ràng buộc thiết kế để suy ra duy nhất các quan hệ đó. Thêm model không tự chứng minh được các ràng buộc còn thiếu; engine vẫn cần quy tắc và kiểm tra nguồn tương ứng.

## Kiểm chứng hệ thống

400 kiểm thử Python đạt, log `storage/validation-fixtures/pytest-curved-views-full-20261012.txt`; 6 script JavaScript đạt. Backend PID 20300 đã nạp mã mới, `/health` và `/cad/capabilities` trả 200; DWG export bật. Chưa có cơ sở tuyên bố tự sửa mọi DWG bất kỳ.
