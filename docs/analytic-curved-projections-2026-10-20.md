# Đồng bộ mặt cong vẽ nghiêng — 20/10/2026

Engine đã bổ sung đối chiếu một mặt có biên LINE/ARC với hình vẽ nghiêng dùng LINE/ELLIPSE. Cả hai hình phải có mã chi tiết native khớp BOM nguồn, toàn bộ biên kín và mọi lỗ xác định được duy nhất một phép affine. Quy tắc đọc cấu trúc file mới, không chứa tên file hoặc handle sản phẩm cố định.

Khi sửa độ dày mặt cong, cung trong và đầu các đoạn nối được tính lại; hình nghiêng giữ dạng ELLIPSE native và các lỗ đi theo đúng phép chiếu. Kiểm tra lại toàn mặt sau sửa, quyền sở hữu, hash nguồn và xung đột thao tác trước khi thực thi. Lỗ elip được kiểm tra trong hệ tọa độ chuẩn hóa của chính elip, gồm sai số chặn của đường dùng định vị, tránh nhầm đường tròn bao với biên lỗ thực.

Chỉ nhận mặt kín đầy đủ trong block có mã; không dùng adapter này cho hình hở, nét bị che khuất, block chứa thêm nét chưa phân loại, DIM chưa gắn hoặc nhiều cách ghép hình. Đây là đối chiếu affine của mặt 2D, chưa phải suy dựng 3D hoặc giải quan hệ che khuất. Một mặt đã gắn không chứng minh toàn cụm đã sửa.

## DWG mới qua website và AutoCAD

File tổng hợp độc lập, mã `UNSEEN-CURVE-089795f2`, đã qua upload DWG → chọn khung → nhập yêu cầu → sửa → xem trước → duyệt → xuất AutoCAD → tải HTTP 200 → ODA mở lại đo kiểm.

| Nội dung | Nguồn | DWG tải xuống |
| --- | --- | --- |
| Độ dày | 8 mm | 6 mm |
| Bán kính ngoài | 50 mm | 50 mm |
| Bán kính trong | 42 mm | 44 mm |
| Hai lỗ | R1 / R1,3 | Giữ nguyên |
| Hình chiếu | Hai cung elip, hai lỗ elip | Đủ bốn ELLIPSE; khớp toàn mặt nguồn |
| BOM | Tấm cung 8×50×100 mm | Tấm cung 6×50×100 mm |

Nguồn được kiểm tra hash giữ nguyên. DWG kết quả SHA-256 `07ae8e7b4b96ff8c1d0bc2642c1a61e7fe73225414ba979f6081b7753383e759`.

- [Tải DWG kiểm chứng](http://127.0.0.1:8765/documents/c1ae8c4090e54e5c9179522383bab9b8/revisions/bc77a908d02a492385b44c8910aa369f/exports/0806066d38d94b87a0157cf9a095664e/download).
- [Mở bản sửa mẫu trên website](http://127.0.0.1:8765/explorer?doc=c1ae8c4090e54e5c9179522383bab9b8&revision=bc77a908d02a492385b44c8910aa369f).
- Bằng chứng: `storage/validation-fixtures/curved-projection-089795f2/receipt.json`, `plan.json`, `after.svg`, `after.png` và DWG/DXF mở lại. Ảnh PNG được tạo từ SVG xuất bản.
- Lặp kiểm chứng: `python scripts/verify_general_dwg_workflow.py --curved-projection --approve`. File thử được đánh dấu và ẩn khỏi thư viện tài liệu chính.

## Kiểm tra Dauphine thực tế

Đọc context production và kế hoạch đang dùng cho revision `ec352bb5bece4bf78cd6c50bbee82e8a`: adapter mới chưa tìm được cặp mặt cong kín đủ điều kiện. Phối cảnh C4 có các đường rời/cung elip bị che, không được tự nhận là mặt đầy đủ.

Detail C đã có năm thao tác kiểm chứng cho cung trong, chân nối và hai DIM 1,5 → 1 mm; phần còn thiếu là các chi tiết lắp cạnh cung và mốc tiếp xúc. Hình đứng/cạnh C4 đã có ở bản xem trước trước đó. Các mặt phối cảnh, mặt lắp và một số đệm đóng gói vẫn chưa hoàn chỉnh.

Audit: `storage/validation-fixtures/c4-mount-links-2026-10-20/curved-projection-customer-audit.json`. Hash DXF nguồn `489b241478f8ad569f5061ceb8b81147cbee51d300ddd7b1c8eef01da03dc8af` giữ nguyên. **Mẫu DWG ở trên không thay thế backup toàn Dauphine và không chứng minh sửa đúng mọi DWG.**

## Kiểm thử

1.596 bài Python toàn bộ đạt trong 240,01 giây; 14 bài tập trung và bảy script frontend đạt, giữ 19 module. Log toàn bộ: `storage/validation-fixtures/pytest-curved-projection-final-2026-10-20.txt`. Website health/help và tải DWG HTTP 200; hash tải khớp receipt. Backend đã nạp mã cuối.
