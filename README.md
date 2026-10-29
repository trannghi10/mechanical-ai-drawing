# CAD Studio · Mechanical AI Drawing

Ứng dụng nội bộ để đọc DWG/DXF, chọn bản vẽ theo hình, lập yêu cầu chỉnh sửa, đối chiếu và tải bản sửa DWG. File nguồn được giữ nguyên; bản sửa và lịch sử được lưu riêng.

Phạm vi người dùng chốt ngày 23/10: **DWG cơ khí 2D**. Mục tiêu là hiểu chi tiết/cụm và các hình biểu diễn trên toàn hồ sơ để sửa liên động đúng; không yêu cầu dựng hoặc chỉnh mô hình 3D.

[DWG Edit Confidence & Safety Gate — 23/10](docs/dwg-edit-confidence-safety-gate-2026-10-23.md): thêm quyết định thống nhất `AUTO`/`REVIEW`/`BLOCK` cho kế hoạch, revision, export và phát hành; mơ hồ chỉ chặn khi chạm chi tiết/geometry đang sửa. `AUTO` chỉ dành cho loại sửa có chứng nhận kỹ sư, hai benchmark nguồn độc lập, hash nguồn/DWG còn đúng và DWG toàn hồ sơ đã mở lại native; hiện chưa có chứng nhận sản xuất nào được cấp. Kiểm 29 ca chính sách và 436 ca revision/export liên quan đạt.

[Liên động bản chi tiết, hình lắp và DIM khe hở — 23/10](docs/linked-2d-clearances-2026-10-23.md): bổ sung quan hệ khe hở đo thật; bốn DWG mới đã qua tìm mã toàn file → sửa → xuất/mở lại AutoCAD, gồm hình xoay, LINE/polyline và Model/Layout riêng. Kiểm biên/lỗ, giữ tâm, DIM khe hở, BOM và nguồn. Hồi quy 2.206 bài Python đạt; nhóm cuối 208 bài và 16 script frontend đạt. Chưa đạt phạm vi mọi DWG 2D hoặc nghiệm thu toàn công ty.

[Quan hệ cơ khí trên DWG mới — 23/10](docs/generic-mechanical-relations-2026-10-23.md): thêm nhận dạng chi tiết vẽ rời qua BOM/leader/DIM, giải tiếp xúc phẳng và đồng bộ đường bao/lỗ/DIM/leader. Ba DWG mới độc lập (polyline, LINE xoay, polyline chung đỉnh) đã qua tải lên → tìm mã toàn file → revision → xuất/mở lại AutoCAD. Hồi quy 2.178 bài Python đạt; 16 script frontend đạt. Đây là lớp quan hệ 2D đã kiểm, chưa phải hiểu mọi ý đồ cơ khí hoặc nghiệm thu mọi DWG.

[Tài khoản, truy vết và điều kiện phát hành — 23/10](docs/company-accounts-release-review-2026-10-23.md): bốn vai trò, thu hồi phiên, nhật ký và người tạo xuyên suốt tác vụ nền đã kiểm trên SQLite/PostgreSQL và giao diện thử. Mỗi revision có trang đối chiếu điều kiện phát hành. Dauphine đã xuất toàn hồ sơ/mở lại độc lập sau bổ sung kiểm hash giữ nguồn cho bản xem trước. Chưa tạo quản trị viên thật, mở LAN hoặc bật chứng nhận/tự phát hành.

[Dauphine: sửa thành hộp trong block lồng](docs/dauphine-nested-wall-2026-10-22.md): tìm đúng mã toàn file, thử 1,2→1 mm, đồng bộ tiết diện/bốn đường trong hai block/DIM/hai BOM. DWG **toàn document** đã nhập lại độc lập, giữ chiều dài thật, đủ 23.116 đối tượng cấp layout và sáu OLE. Bản thử vẫn chưa hoàn tất quan hệ công đoạn/lắp ghép toàn sản phẩm. Truy cập dữ liệu web đã giới hạn cùng máy/cùng nguồn; nền tài khoản được bổ sung ngày 23/10, chưa mở LAN.

[Mở rộng sửa kích thước trên nhiều DWG](docs/multi-dwg-size-rules-2026-10-22.md): bộ sửa hộp nhận hai thứ tự quy cách BOM, tiết diện polyline và hình xoay theo DIM thật. Hai DWG hồi quy khác kích thước/góc xoay đã qua API → revision → AutoCAD xuất → nhập lại độc lập, giữ hình ngoài/chiều dài, đồng bộ thành trong/DIM/BOM. 873 kiểm Python liên quan đạt. Corpus ba DWG công ty được audit riêng; năm chi tiết Dauphine còn thiếu bằng chứng nên chưa mở sửa.

[Kiểm thử DWG công ty](docs/company-dwg-validation-2026-10-22.md): MR-106 đã xuất **toàn hồ sơ**, nhập lại đo 15×15 mm, giữ tâm lỗ/hai BOM, đủ 2.199 đối tượng cấp layout và nội dung OLE; đã kiểm thêm một lượt lưu/mở. Luồng cục bộ ODA → AutoCAD khắc phục lỗi nhập DXF và chặn mất payload. LEG6949 mới đã nhập lại độc lập: thành hộp 2→1,2 mm, bas/DIM, 20 ô BOM và 329 thao tác hình chiếu; bốn khung cụm đạt mapping. Còn khung `43C2FE`, ba mã thiếu ràng buộc và bốn hình cụm MR-106. Chưa nghiệm thu toàn sản phẩm.

[Tìm chi tiết toàn file → sửa liên động → lưu/mở DWG](docs/whole-file-linked-edit-2026-10-22.md): đã nối yêu cầu không cần chọn khung, phân biệt STT trùng và kiểm hồ sơ cũ trước sửa. AutoCAD local kiểm chứng hai biên dạng/hai DIM 100→120 mm, PART-B dịch theo, DIM tổng 220 mm và BOM đồng bộ; DWG tải xuống đã được nhập lại độc lập để đo. Đây là ca tổng hợp đã kiểm, chưa phải nghiệm thu mọi DWG.

[Mechanical DWG Intelligence Dataset – V1](docs/mechanical-dataset-v1-2026-10-22.md): `/dataset` theo dõi 33 hồ sơ khởi tạo (20 DWG, 13 STEP), nguồn/quyền/hash, nhãn và trạng thái nghiệm thu. Có 12 DWG Autodesk chính thức, 4 DWG công khai đã mở local, 4 hồ sơ công ty giữ nội bộ và 378 nhãn ảnh đề xuất. **0/500 hồ sơ nghiệm thu; chưa huấn luyện model.** ZIP chỉ chứa cấu hình và 13 hồ sơ STEP được phép phân phối, không chứa DWG.

[Mục tiêu website dùng chung cho công ty và hồ sơ toàn bản vẽ — 22/10](docs/company-web-product-2026-10-22.md): đã bổ sung đọc mọi layout/instance, tra mã tới các khung liên quan, dữ liệu hình học/DIM phân trang và trạng thái bao phủ trong kế hoạch sửa. Đã kiểm trên bốn hồ sơ thực tế, 245.161 bản ghi; nguồn giữ nguyên. Người dùng chọn mạng nội bộ/VPN và tự phát hành loại sửa đã kiểm chứng. **Nền nhiều tài khoản, tự phát hành và hiểu đầy đủ quan hệ cơ khí vẫn chưa hoàn thành.**

[Luồng MVP trên giao diện đã hoàn thiện](docs/rectangle-ui-release-2026-10-21.md): tự tìm nhóm rectangle một DIM, nhập width giữ trái, xem trước/sau, lịch sử và tải DWG local/APS. Đã kiểm chuỗi cloud 100→120→140, chặn DIM visual dùng chung. [Trạng thái toàn dự án và phần chưa hoàn thành](docs/project-completion-status-2026-10-21.md): chưa đạt mục tiêu mọi DWG hoặc toàn sản phẩm Dauphine.

[Probe stretch nhóm polyline sáu DIM](docs/polyline-six-dim-stretch-probe-2026-10-21.md): solver đã kéo rộng 905→925 mm và thu 905→885 mm trên bản sao DWG thực, giữ bốn DIMASSOC/hai native action và vượt qua save/reopen. Hai đầu DIM thiếu liên kết vẫn là giả định thử nghiệm; chưa phát hành thành operation sửa khách hàng.

[Bằng chứng native vertex](docs/native-vertex-binding-proof-2026-10-21.md): đã chứng minh 8/12 đầu DIM từ nguồn và thử để native action tự cập nhật đầu DIM có vertex binding; hai chiều kéo đạt kiểm 54/54 primitive sau mở lại. Bốn đầu còn thiếu bằng chứng vẫn được báo rõ.

[Sửa thử liên kết DIM và đối chứng ngoài nhóm](docs/dimension-relationship-repair-2026-10-21.md): hai đầu DIMASSOC được gắn lại trên bản sao và tự cập nhật khi kéo ±10 mm; 15 bbox khác biệt đã kiểm bằng no-op control và dữ liệu DXF/OLE. Chưa phát hành bản sửa khách hàng hoặc xác nhận pixel hiển thị OLE/dung sai.

[Màn hình xem xét liên kết DIM](docs/native-revision-release-2026-10-22.md): `/relationship-review` lập/lưu/mở lại đề xuất, xem hình nhóm, tạo revision legacy hoặc native trong phạm vi đã kiểm chứng, undo/redo và tải DWG bản sửa để kiểm tra. Nguồn được giữ nguyên; chưa phát hành bản sản xuất đầy đủ.

[API rectangle stretch trên local và APS](docs/rectangle-stretch-aps-2026-10-21.md): đã chạy 100→120 mm qua AutoCAD local 2027 và APS AutoCAD 2025, giữ cạnh trái/DIMASSOC/chữ DIM sau lưu/mở lại. HTTP thật tải DWG khớp hash, retry dùng lại job, nguồn sai hash bị chặn; 179 kiểm liên quan đạt. Alias rectangle_mvp đã được đăng ký sau chấp thuận người dùng; alias cloud mặc định giữ nguyên. Chưa hỗ trợ stretch DWG tổng quát.

[MVP solver → geometry DWG 100→120 mm](docs/point-binding-mvp-2026-10-21.md): đã chạy AICAD_EXPORT_POINTS → binding → solver → AICAD_APPLY_POINTS, giữ cạnh trái, DIMASSOC và chữ DIM sau lưu/mở lại bằng AutoCAD 2027. Hai kiểm âm native đạt; 42 kiểm Python liên quan đạt. Chưa kiểm AutoCAD 2026 hoặc APS Automation cho operation này.

[Bộ giải phi tuyến điểm 2D](docs/nonlinear-point-solver-2026-10-21.md): đã có khoảng cách, góc, song song/vuông góc và tiếp tuyến đường vô hạn–tròn bán kính cố định; 32 kiểm liên quan đạt. Chỉ trả đề xuất nghiệm cục bộ đủ hạng và đạt residual; chưa tích hợp stretch DWG hoặc bulge.

[Kiến thức DOF/stretch và solver affine 2D](docs/dof-stretch-knowledge-2026-10-21.md): đã kiểm chứng hạng, DOF, ràng buộc dư và mâu thuẫn trên mẫu tổng hợp; 19 bài kiểm liên quan đạt. Chưa phải GCS phi tuyến hoặc stretch DWG tổng quát.

[Yêu cầu sáu hạng mục và đồ thị quan hệ đề xuất](docs/mechanical-relationships-roadmap-2026-10-21.md): đã bắt đầu bộ quan sát hình học có residual trên phạm vi chọn, 8 kiểm thử đạt. Quan sát chưa xác nhận không cấp quyền sửa; chưa tính DOF hoặc giải stretch chung.

[Probe polyline–sáu DIM native](docs/polyline-six-dim-translation-probe-2026-10-21.md): hai hướng dịch cứng trên bản sao thực tế đã xuất/mở lại DWG, giữ sáu DIM, hai action và 54 primitive hiển thị. 310 bài kiểm thử liên quan đạt. Chưa nối production hoặc xác nhận đổi kích thước nhóm.

Luồng thử nghiệm đã tự tìm nhóm từ inspection có kiểm hash, đối chiếu nhóm lần nữa bằng native preflight rồi dịch/lưu/mở lại DWG thành công; 16 kiểm thử liên quan đạt. Hai danh sách phát hiện bị cố ý làm sai đều bị chặn trước khi tạo DWG. Chưa nối API production.

DWG đầu ra của probe đã được nhập lại và chỉnh lần hai với vector ngược: hình, sáu DIM và 54 primitive hiển thị trở về đúng nguồn ban đầu. Bằng chứng chuỗi hash và đối chiếu độc lập nằm trong cùng tài liệu probe.

[DIMASSOC perpendicular lồng nhau](docs/dimassoc-perpendicular-2026-10-21.md): đã phân tích đúng last point của DIM thực tế và kiểm chứng sửa 90,5 → 95 mm trên mẫu tổng hợp qua xuất/mở lại DWG, giữ snap và source binding. Toàn nhóm polyline–sáu DIM thực tế vẫn chưa được mở sửa.

[Inventory topology native](docs/native-topology-inventory-2026-10-21.md): kiểm thêm reactor và extension dictionary khi đối chiếu CenterMark; nhóm hai cặp vẫn xuất/mở lại CAD đạt. Audit 39.917 entity cho thấy reactor native/DXF khớp, còn 10 khác biệt dictionary ACAD_TABLE được giữ rõ trong báo cáo. Đã xác định nhóm polyline + sáu DIM để phát triển adapter tiếp theo.

[Dịch nhóm CenterMark](docs/native-centermark-batch-2026-10-21.md): nhóm 2 cặp dùng độ dịch riêng và nhóm 11 cặp dùng chung độ dịch đã xuất/mở lại một DWG chung, đọc DXF độc lập và đối chiếu ngoài nhóm. Giao diện cho chọn nhiều cặp; toàn bộ 1.741 bài kiểm thử đạt. Chưa phải dịch toàn cụm cơ khí.

[Đọc dependency của action native](docs/native-action-dependencies-2026-10-21.md): lần từ dấu tâm đến đúng hình nguồn, phân biệt ARC đồng tâm với CIRCLE thực sự được tham chiếu. Thêm một cặp Circle–CenterMark kiểm chứng, nâng tổng lên 12 cặp trên cùng DWG; chưa xác nhận adapter ARC.

[Dịch CenterMark qua job native](docs/native-centermark-production-2026-10-21.md): 11 cặp trong một khung thực tế đã có bằng chứng dịch riêng, lưu/mở lại DWG và đọc DXF độc lập; native preflight chặn action sai. [Chín cặp kiểm chứng bổ sung](docs/centermark-population-2026-10-21.md) đều đạt kiểm lại artifact đã lưu. Công cụ AutoCAD có form tìm/chọn cặp và nhập độ dịch X/Y. Chưa xác nhận dịch cả cụm sản phẩm; form chưa kiểm trực quan trình duyệt.

[Đọc dependency dấu tâm bằng AutoCAD gốc](docs/native-centermark-dependencies-2026-10-21.md): xác định hai cặp CenterMark thực tế trong Detail C, đọc lớp native thay cho proxy DXF. Chưa cấp quyền dịch cụm; 140 bài export/native jobs và kiểm chứng AutoCAD đạt.

[Đề xuất khoảng hở Detail C](docs/detail-c-clearance-proposal-2026-10-21.md): đo CAD nguồn, đối chiếu tiết diện BOM và tính phương án giữ hai khe; chưa thực thi khi thiếu liên kết cả cụm hộp–chốt.

[Bảo toàn HATCH cùng DIMASSOC](docs/preserved-hatch-dimassoc-2026-10-21.md): sao chép nguyên nhóm HATCH–biên–DIM và các đối tượng sở hữu khi sửa đối tượng độc lập; giữ binding qua AutoCAD xuất/mở lại. Chưa cấp quyền sửa thành viên của nhóm.

[Bảo toàn HATCH liên kết nội bộ](docs/preserved-hatch-associations-2026-10-21.md): giữ nguyên nhóm HATCH–biên–reactor khi sửa đối tượng khác trong block, gồm biên chữ TEXT/MTEXT; đã qua AutoCAD xuất/mở lại. Nhóm có DIMASSOC còn bị chặn.

[Bảo toàn HATCH nghiêng khi sửa block](docs/preserved-ocs-hatch-2026-10-21.md): sửa hình được hỗ trợ trong block có HATCH đảo mặt/nghiêng và bulge; giữ nguyên HATCH qua AutoCAD xuất/mở lại, kiểm tra đường bao và mặt phẳng.

[Gắn hình hộp thiếu mã và mốc giữ](docs/confirmed-cuboid-links-2026-10-21.md): đối chiếu hình CAD, chọn DIM/mốc và lưu xác nhận theo file; kiểm tra lại cạnh, BOM, nét nối và phạm vi trước sửa. DWG tổng hợp đã qua AutoCAD/mở lại; đề xuất tấm xốp Dauphine được giữ ở trạng thái chưa xác nhận theo lựa chọn người dùng.

[Hình hộp chiếu trực giao theo ba kích thước](docs/metric-cuboid-projections-2026-10-20.md): sửa hình có đủ cạnh và mã nguồn khi giữ tâm, đồng bộ DIM/BOM/ghi chú; DWG mới đã qua AutoCAD và mở lại. Đọc thêm hai hình đóng gói Dauphine; hình bị che hoặc thiếu mã vẫn chưa cấp quyền sửa.

[Đồng bộ bản sao mặt cong ARC/CIRCLE](docs/circular-face-copies-2026-10-20.md): bổ sung mặt xoay, đổi tỷ lệ và phản chiếu có toàn biên/lỗ được chứng minh; DWG mới đã xuất AutoCAD và mở lại đo kiểm. Audit Dauphine chưa có thêm liên kết đủ điều kiện.

[Đồng bộ mặt cong vẽ nghiêng](docs/analytic-curved-projections-2026-10-20.md): đối chiếu toàn bộ biên cung/nét và các lỗ, giữ cung elip native; DWG mới đã qua website, AutoCAD xuất và mở lại đo kiểm. Chưa áp dụng cho phối cảnh bị che nét hoặc thiếu mặt lắp.

Liên kết hình đứng/hình cạnh cụm: dùng DIM chiều rộng, các mặt tấm và chuỗi cao độ CAD để đồng bộ những hình đã chứng minh; giữ tiết diện thanh, căn lề chữ và đầu leader Detail. Quy tắc dùng chung theo cấu trúc nguồn, không dựa vào tên file. Phối cảnh hoặc mặt lắp chưa đủ dữ liệu vẫn được liệt kê riêng; không được coi một hình đã sửa là cả sản phẩm hoàn chỉnh.

Kiểm chứng mới: [sửa hai DIM thực tế của tấm, giữ tâm lỗ và đồng bộ hình cạnh/BOM](docs/plate-size-validation.md). Có DWG xem trước đã xuất và mở lại đo kiểm; chưa hoàn thành backup toàn sản phẩm hoặc hỗ trợ mọi DWG.

[Đã bổ sung ghi nhớ lựa chọn theo file/DIM và sửa tấm một hoặc hai hướng](docs/linear-intent-validation.md): phân tích lại không hỏi lặp lựa chọn đã chốt; vẫn biên dịch và kiểm tra CAD từ nguồn. Hai DWG mới độc lập đã xuất và mở lại đo kiểm.

## Mở dự án

Lệnh ngắn gọn:
```powershell
.\run
```
hoặc chạy bằng Python:
```powershell
python -m backend.main
```

- Hoặc click đúp chuột vào file `run.bat` trong thư mục dự án.
- Giao diện: http://127.0.0.1:8765/
- Hướng dẫn sử dụng: http://127.0.0.1:8765/help
- AI native tự khởi động model đã cài khi một yêu cầu thực sự cần AI; có trạng thái nạp và nút hủy. `start-project.ps1` hoặc nút **Khởi động AI** dùng để nạp trước. Luồng hình học/tham số được engine nhận diện không cần gọi model. Không tự tải model hoặc chuyển sang cloud.
- Nếu `python` chưa có trên PATH, dùng đường dẫn Python đã cài trên máy.

## AutoCAD trên máy và APS

APS đã kết nối và kiểm chứng DWG tổng hợp. Mặc định đọc/xuất vẫn dùng AutoCAD trên máy. Trong **Công cụ AutoCAD và chẩn đoán file → AutoCAD trên máy / Autodesk APS**, chọn bộ xử lý, kiểm tra kết nối APS hoặc mở bản sao bằng APS. Dropdown chỉ đổi công cụ native; không tự đổi cấu hình tải/xuất của server. [Hướng dẫn từng bước trên website](http://127.0.0.1:8765/help#aps) · [Cấu hình và kết quả kiểm chứng](docs/aps-migration.md).

## Quy trình sử dụng

1. Upload DWG/DXF hoặc chọn tài liệu đã lưu. File thử/trùng được ẩn mặc định.
   Mở **Cấu trúc cụm và chi tiết trong toàn file** để xem nhóm theo nhãn ngoài khung (C1, C2, 16…), ảnh từng khung, hướng dẫn công đoạn và đối chiếu STT/BOM. Chỉ mục được tạo tự động; [cách đọc và giới hạn](docs/drawing-row-index-2026-10-17.md).
2. Chọn hình bản vẽ; hình CAD và ô yêu cầu hiển thị thành hai vùng. Có nút đổi bản vẽ và phóng to/vừa khung.
   Mở **Kiểm tra dữ liệu bản vẽ → Hồ sơ chi tiết và hình biểu diễn → Lập hồ sơ CAD đã chọn** để xem cụm/BOM, STT cục bộ, nhóm cụm được bao phủ và các ứng viên bản vẽ tổng.
3. Nhập số/mã chi tiết, giá trị mới và mốc giữ. Phân tích, đọc các thay đổi và phần còn thiếu.
4. Tạo bản sửa đủ dữ liệu, xem trước/sau và BOM. Tải DWG xem trước hoặc duyệt/xuất khi bản sửa đủ điều kiện.

Ngay dưới phần phân tích có **Tạo và tải DWG đã sửa**, **Mở bản sửa gần nhất** và **Chọn bản sửa đã lưu**. Bản một phần chỉ được tải dưới dạng xem trước. Bấm **PostgreSQL · đã kết nối** ở góc trên để xem trạng thái và [hướng dẫn mở pgAdmin](http://127.0.0.1:8765/help#database).

File cũ nhập qua ODA có nút **Đọc lại bằng AutoCAD**, tạo bản nhập riêng và giữ lịch sử trước đó. Công cụ native/chẩn đoán nằm trong phần thu gọn phía dưới.

## Trạng thái hiện tại

- AutoCAD 2027 trên máy thực hiện đọc/lưu DWG; PostgreSQL lưu chỉ mục và trạng thái. CAD nằm trong `storage/documents`.
- Đọc Model/Layout, block lồng, DIM, bảng vật tư và sửa các dạng hình học/liên kết có adapter và bằng chứng.
- Gắn thân block ẩn danh qua STT/leader/BOM để giải mặt lắp 2D, kể cả cụm xoay và thân nhận dịch chuyển không có DIM riêng. Đồng bộ mũi tên/DIM tổng, giữ quyền co/giãn theo số đo nguồn. [DWG và đối chiếu file thực tế](docs/assembly-mount-validation-2026-10-20.md).
- Nhận thêm thân cong có STT/BOM để đối chiếu toàn bộ body; hỗ trợ mặt phẳng vẽ nghiêng bằng nét rời, ít lỗ và nhiều mặt dùng chung cạnh khi phép gắn hình duy nhất. [Kết quả DWG và giới hạn trên file thực tế](docs/curved-split-projections-2026-10-20.md).
- Quy tắc cơ khí/BOM/STT áp dụng cho mỗi lượt phân tích file mới; AI đọc theo cây cụm và truy xuất thành viên qua các trang nguồn. `rules/mechanical_bom.py` chứa quy ước dùng chung; số đo/mốc/quy tắc lắp đã xác nhận vẫn thuộc đúng hash CAD.
- Sửa tham số block động trong layout hoặc nằm trong nhánh block tĩnh được hỗ trợ; cô lập đúng đường dẫn instance, giữ các nhánh dùng chung không được chọn. Hỗ trợ số, lookup, visibility và flip; mở lại DWG đối chiếu. Năm dạng native đã được kiểm chứng trên mẫu Autodesk khác.
- Có lịch sử bản sửa, trạng thái tác vụ, xem/tải DWG. Bản một phần vẫn được ghi rõ là xem trước.
- **Chưa bảo đảm sửa đúng mọi DWG hoặc backup toàn Dauphine.** Block có cha động/XREF hoặc association chưa hỗ trợ, proxy/object enabler, association riêng và quan hệ cơ khí thiếu bằng chứng còn giới hạn. Thao tác tham số không tự chứng minh mọi BOM/công đoạn/đóng gói đã đồng bộ.

## Các thư mục cần giữ

| Thư mục | Vai trò |
|---|---|
| `backend` | API, lập kế hoạch, lưu trữ, AutoCAD và database |
| `cad`, `bom` | Đọc/sửa/kiểm tra hình học và bảng kê |
| `graph` | Các adapter liên kết lắp ghép, công đoạn và đóng gói đang dùng |
| `frontend` | Giao diện, hướng dẫn và các nút xem/tải |
| `autodesk` | Plugin và receipt của AutoCAD; không xóa bundle đang chạy |
| `tests` | 19 module hồi quy đã gộp; giữ để kiểm tra chức năng |
| `scripts` | Cấu hình, kiểm chứng và dọn dữ liệu |
| `storage` | File gốc, bản sửa, runtime/model, kết quả và gói phục hồi |
| `docs` | Tài liệu kỹ thuật và bằng chứng triển khai trước đây |

`__pycache__`, `.pytest_cache` và output build là dữ liệu sinh lại; VS Code đã được cấu hình thu gọn chúng. Các module trong `graph` là mã chức năng, không phải file rác.

## Bảo trì

```powershell
python -m pytest -q
python scripts/cleanup_workspace.py
python scripts/cleanup_workspace.py --apply
```

Lệnh dọn mặc định chỉ báo cáo. `--apply` chỉ dọn mục đã xác định là sinh tạm/thử, giữ nguồn khách hàng và bằng chứng native hiện hành; tạo ZIP phục hồi có manifest/hash trước khi xóa khỏi thư mục làm việc. Không xóa `.env`, model, runtime AutoCAD hoặc các module chức năng. Gói phục hồi nằm trong `storage/archives`; sao lưu cả database và file CAD trước khi vận hành sản xuất.

## Tài liệu kỹ thuật

- [AutoCAD trên máy](docs/local-autocad-2027.md)
- [Tham số block động và giới hạn](docs/native-dynamic-editing-2026-10-16.md)
- [PostgreSQL](docs/postgresql-setup.md)
- [APS cloud — chỉ dùng khi chủ động cấu hình](docs/aps-migration.md)
- [Lịch sử trạng thái và kiểm chứng](docs/current-project-status.md)

Cấu hình trong `.env`; không đưa mật khẩu/API key vào ô yêu cầu CAD. Hiện tại đọc CAD dùng AutoCAD trên máy; không tự chuyển tài liệu sang cloud.
