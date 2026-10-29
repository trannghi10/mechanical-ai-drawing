# Kiểm chứng thêm chín cặp CenterMark thực tế

Chín cặp mới tìm thấy trong khung `3B3987` đã được dịch riêng qua API production, xuất DWG, mở lại, kiểm persisted state trước evaluate và đọc DXF độc lập. Tất cả chín job ready; không có job thất bại. Cộng với hai cặp đã kiểm chứng trước, hiện có bằng chứng cho 11 cặp của khung này trên cùng nguồn Dauphine.

Đây là kiểm chứng trên bản sao native-import `51ec94944c4443b19fb8d5bd7930a6dd`, không phải chỉnh vị trí thiết kế sản phẩm. Inspection dependency `14697ba4627d4970990a17960f7df3b7`; mọi lệnh gắn với context chọn khung và hash DWG nguồn `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`.

| Circle | Dấu tâm | Bán kính CAD | Góc dấu tâm | Delta X/Y CAD | Job |
|---|---|---:|---:|---|---|
| 3D4AE9 | 3D4AF4 | 4 | 0° | 0,125 / −0,25 | b1f6e5b9a2794def87685349d9629601 |
| 3D4AEC | 3D4AF3 | 4 | 0° | 0,25 / −0,25 | 122cbf155e9f4daebb7c76bea0a61c55 |
| 3D4AF0 | 3D4AF5 | 4 | 0° | 0,375 / −0,25 | 095b46ba58c84fbbab11f512b36327ba |
| 3D4AFB | 3D4AFC | 5 | 90° | 0,5 / −0,25 | 1e49487d4abb4ee2b2371ec230abacae |
| 3D4B02 | 3D4B03 | 5 | 90° | 0,625 / −0,25 | ce236e93772c4cd2910ee133abffc577 |
| 3D4B09 | 3D4B0A | 5 | 90° | 0,75 / −0,25 | da535cd90263496c82bbe7f7340d8f57 |
| 3D4B10 | 3D4B11 | 5 | 90° | 0,875 / −0,25 | aaadc757566040b8899bd325c0550724 |
| 3D4BF0 | 3D4BF1 | 5 | 90° | 1 / −0,25 | 4ada77e1ea9140179be3d3f646ace83e |
| 3D4C18 | 3D4C19 | 5 | 90° | 1,125 / −0,25 | 7d551eb705444d2a90690b38ff5ca0bc |

Mỗi job đối chiếu 39.915 entry inventory ngoài cặp mục tiêu trong dung sai 1e−7, giữ tập handle, bán kính và thuộc tính được inventory liệt kê. Đây không phải đối chiếu nhị phân mọi thuộc tính của toàn bộ native database. Các cặp đều là circle XY ở layout và dấu tâm static scale `[1,1,1]`; không suy rộng sang nested CenterMark, normal nghiêng hoặc block scale khác.

## Artifact và cách lặp lại

`storage/validation-fixtures/centermark-population-2026-10-21/started.json` lưu tập cặp trước khi chạy; `progress.json` lưu từng job ID ngay sau khi gửi và từng kết quả terminal. `receipt.json` ghi chín SHA-256 DWG đầu ra và số entry đã đối chiếu. Artifact chuẩn của mỗi job ở `storage/documents/51ec94944c4443b19fb8d5bd7930a6dd/aps-jobs/JOB_ID/result/`.

`scripts/audit_centermark_population.py` dùng API context, dependency candidates và native-edits; mỗi cặp là một job với vector thử riêng, không tạo revision hoặc xác nhận mating. Nếu quan sát quá thời gian, script dừng và giữ ID để kiểm tra tiếp; không tự khởi động lại job không rõ trạng thái. Không ghi đè thư mục audit đã tồn tại.

`scripts/verify_centermark_population_artifacts.py` kiểm lại artifact đã lưu qua cơ chế integrity của job, hash commands/receipt/output, tập cặp, nguồn hiện tại và đọc DXF độc lập. **9/9 đạt**; kết quả ở `artifact-verification.json`.

Các vector chỉ phục vụ phát triển adapter. Chưa dịch cả cụm sản phẩm, chưa đồng bộ các chi tiết xung quanh, chưa hoàn thành backup toàn Dauphine hoặc hỗ trợ mọi DWG. Đề xuất tấm xốp giữ nguyên trạng thái chưa xác nhận.
