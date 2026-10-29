# Liên kết khung bao cụm và hình cạnh — 20/10/2026

Đợt này sửa luồng đọc mới từ nguồn, không chỉ dùng hồ sơ nhận diện cũ. Quy tắc trong `graph/confirmed_inner_panels.py` và `graph/core_stack_views.py` không chứa tên file hoặc mã Dauphine.

## Liên kết được bổ sung

- Bộ đọc vẫn không coi mọi hình trong khung có nhiều dòng BOM là một chi tiết. Khung bao cụm chỉ được nối riêng khi có lựa chọn lắp đã xác nhận theo hash nguồn, BOM công đoạn chứa đủ các tấm liên quan, liên kết công đoạn về BOM gốc, một nhóm native đầy đủ năm biên và các DIM thật khớp mặt lắp. Không cấp quyền sửa cho các hình con chưa rõ chủ sở hữu.
- Đồ thị ảnh hưởng giữ hash và nhận dạng tài liệu nguồn. Trước đây việc rút gọn đồ thị làm mất thông tin này.
- Hình cạnh chỉ nhận cao độ từ hình đứng khi cùng khung/BOM, DIM rộng trùng biên bao, có đủ bằng chứng sáu mặt nguồn và các nét đứng nối tầng. Giữ tiết diện thanh; không biến nét thành hộp chiếu vào vùng tấm thành độ dày tấm.
- Chữ đồng tâm với vòng tròn đi cùng tâm, giữ cả điểm chèn và điểm căn lề. Đầu leader Detail đi cùng vòng tròn, phần chữ và các đỉnh còn lại giữ chỗ.
- Báo cáo liệt kê từng hình đã kiểm chứng; không dùng một hình đạt để chứng nhận cả khung/cụm.

## Kiểm tra chung cho file khác

Các trường hợp trong hai module kiểm thử hiện có dùng mã sản phẩm khác, khung không mang tên mã chi tiết, BOM nhiều thành viên, nét rời, chữ căn giữa và leader ra ngoài biên. Thiếu BOM thành viên, công đoạn, hash, mặt đo thật, hoặc có mã sở hữu mâu thuẫn thì không sửa. Nét xiên chưa có quan hệ riêng không tự co giãn.

Bộ gắn hình dùng bao hình học bảo toàn để loại các nét chắc chắn ngoài vùng trước khi phân tích cung/NURBS. Không dùng hai đầu cung bulge làm bao; đường cong chưa có bao an toàn vẫn được phân tích đầy đủ. Không thay đổi độ chính xác đối chiếu hoặc xuất đường cong.

## Phạm vi nghiệm thu

Kịch bản `scripts/verify_dauphine_core_stage.py` dựng lại cùng phạm vi và chỉ mục nguồn như endpoint thực thi, biên dịch lại yêu cầu rồi đi qua bước tạo revision/xuất DWG của website. Kết quả và log nằm trong `storage/validation-fixtures/c4-mount-links-2026-10-20/`.

## DWG thực tế đã mở lại

Revision `ec352bb5bece4bf78cd6c50bbee82e8a`, kế hoạch `da06e34f11134530a55fec6bc4016cea`: **490 thao tác**, được tạo từ phạm vi production và chỉ mục đọc lại nguồn. AutoCAD đã xuất, mở lại và kiểm tra toàn bộ thao tác; script đối chiếu riêng **219 thao tác native** của cụm, công đoạn và Detail được hỗ trợ.

| Nội dung | Nguồn | Mở lại DWG |
| --- | ---: | ---: |
| Hình đứng C4 | 721 mm | 695 mm |
| Hình cạnh C4 | 721 mm | 695,00000000001 mm |
| Tấm giữa trong hình cạnh | 2 mm | 1 mm |
| Thanh số 4 trong BOM/bản cắt | 717 mm | 692 mm |
| Thanh số 5 trong BOM/bản cắt | 721 mm | 695 mm |

Hình cạnh có **96 thao tác được đối chiếu**, bao gồm chữ và leader. Khe hở thanh số 4 là 0,5 mm mỗi đầu. Bảy dòng BOM native và các DIM góc được kiểm tra; nguồn DWG/DXF giữ nguyên hash.

- [Mở hình C4 trên website](http://127.0.0.1:8765/explorer?doc=34ee84f35e1a44fb81c56044397a0fff&target=3ADF05&revision=ec352bb5bece4bf78cd6c50bbee82e8a).
- [Tải DWG xem trước](http://127.0.0.1:8765/documents/34ee84f35e1a44fb81c56044397a0fff/revisions/ec352bb5bece4bf78cd6c50bbee82e8a/exports/b85f2f44518045f5b7408598eb29cc85/download): HTTP 200, 2.428.122 byte; SHA-256 `9a2a28d8a040728f50cb1e441578a2b09b679b0bbc797fe1c4f285821df28b21`.
- Bản lưu: `storage/backups/Dauphine-PREVIEW-C4-dung-canh-2026-10-20.dwg`.
- Bằng chứng số đo/ảnh: `storage/validation-fixtures/dauphine-combined/ec352bb5bece4bf78cd6c50bbee82e8a/core-stage-readback.json`, `core-front-after.png`; kết quả tải `c4-mount-links-2026-10-20/website-download.json`.

Lần xuất đầu bị môi trường hạn chế chặn tạo registry hồ sơ AutoCAD, không phải bằng chứng lỗi bản quyền. Chạy lại bằng quyền tài khoản Windows bình thường đã thành công. Backend nạp mã mới và health HTTP 200; không đổi bộ xử lý mặc định hoặc gửi CAD lên cloud.

**Kiểm thử:** 1.582 bài Python toàn bộ đạt (226,64 giây); sau tối ưu vòng tra BOM, 33 bài tập trung đạt; bảy script frontend đạt. Vẫn giữ 19 module kiểm thử. Logs: `pytest-c4-stage-release-2026-10-20.txt`, `pytest-c4-stage-focused-final-2026-10-20.txt`.

**Chưa nghiệm thu backup toàn sản phẩm hoặc sửa đúng mọi DWG.** Phối cảnh C4, Detail C cong, các mặt lắp chưa đủ bằng chứng và một số lớp đóng gói vẫn cần liên kết riêng. File chưa đủ điều kiện chỉ được ghi là xem trước một phần.
