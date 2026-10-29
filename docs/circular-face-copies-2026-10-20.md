# Đồng bộ mặt cong ARC/CIRCLE native — 20/10/2026

Bổ sung thực thi cho mặt cong đích dùng ARC và lỗ CIRCLE, khi toàn bộ biên và lỗ chứng minh duy nhất một phép đồng dạng với mặt nguồn có mã BOM. Hỗ trợ xoay, đổi tỷ lệ và phản chiếu; giữ kiểu đối tượng native, mặt phẳng, chiều cung và vị trí lỗ. Phép chiếu không đều tiếp tục dùng ELLIPSE. Không suy quan hệ từ tên file hoặc handle cố định.

Trước đây bộ đối chiếu đã tìm được các mặt này nhưng bộ sinh thao tác chỉ nhận ELLIPSE nên không thực thi đồng bộ. Nay bán kính, tâm, góc đầu/cuối và lỗ thay đổi theo đúng phép gắn nguồn; kiểm tra lại toàn mặt sau sửa. Thiếu nét, sai mã, lỗ sai, phép gắn mơ hồ, đổi Z hoặc nguồn thao tác cũ vẫn bị từ chối.

## Bằng chứng DWG

DWG tổng hợp mới `UNSEEN-CURVE-b5882d24` qua upload website → phân tích → sửa → duyệt → AutoCAD xuất → tải HTTP 200 → ODA mở lại đo kiểm. Mặt đích có tỷ lệ 1,7, xoay 37 độ, phản chiếu và dịch gốc trong block.

- Độ dày nguồn: 8 → 6 mm, bán kính ngoài giữ 50 mm, bán kính trong 42 → 44 mm.
- Hình đích giữ hai ARC: bán kính 74,8 và 85 mm; hai lỗ CIRCLE bán kính 1,7 và 2,21 mm.
- Toàn bộ biên/lỗ sau mở lại vẫn có đúng một phép gắn; BOM và ghi chú đổi cùng độ dày. Hash file gốc giữ nguyên.
- Receipt: `storage/validation-fixtures/curved-projection-b5882d24/receipt.json`.
- DWG: `storage/validation-fixtures/curved-projection-b5882d24/download/curved-face-backup.dwg`.
- SHA-256: `a5177b5edea602553dc40c16f2401028125d07386340f080ca26bba6d6cc996d`.
- Lặp lại: `python scripts/verify_general_dwg_workflow.py --circular-projection --approve`.

Lượt đầu trong sandbox bị chặn tạo khóa registry hồ sơ AutoCAD; chạy backend bằng tài khoản Windows ngoài sandbox đã thành công, không thay bộ xử lý hoặc gửi CAD lên cloud.

## Kiểm thử và phạm vi còn thiếu

Hồi quy toàn bộ đạt **1.622 bài Python**, 254,22 giây, 1.273 cảnh báo thư viện. 16 bài tập trung đạt, gồm hai trường hợp ARC phản chiếu/không phản chiếu và các trường hợp ELLIPSE trước đó. Hai bài bổ sung chạy riêng đạt về thay tâm/bán kính lỗ CIRCLE, mở lại DXF và từ chối bán kính nguồn đích sai. Log riêng: `storage/validation-fixtures/pytest-circular-bores-2026-10-20.txt`. Log hồi quy toàn bộ: `storage/validation-fixtures/pytest-circular-projection-2026-10-20.txt`.

Audit lại phạm vi production của Dauphine: chưa tìm được mặt cong kín đủ điều kiện hoặc liên kết mới. Nguồn giữ nguyên hash. Receipt: `storage/validation-fixtures/circular-projection-customer-audit-2026-10-20.json`.

Phối cảnh C4 bị che nét, mặt lắp cạnh cung Detail C và các lớp đệm chưa gắn đủ vẫn chưa hoàn thành. Kết quả này mở rộng một nhóm DWG được hỗ trợ; chưa nghiệm thu toàn Dauphine hoặc mọi DWG.
