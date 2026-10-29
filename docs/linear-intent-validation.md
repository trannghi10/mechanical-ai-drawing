# Hiểu yêu cầu, lưu lựa chọn và sửa đúng hướng — cập nhật 20/10/2026

## Tiếp tục 20/10: nhiều mặt, khe hở nguồn và đệm khác bề rộng

- `projected_profiles` nhận nhiều mặt trong cùng INSERT khi mỗi mặt có đường bao kín thẳng, ít nhất hai lỗ và cùng danh tính BOM được chứng minh. Phân vùng lỗ/DIM theo từng mặt, đối chiếu toàn bộ và kiểm tra chuyển động tại đỉnh/mép chung. Tất cả mặt phải khớp đúng một lần, DIM chung phải cho cùng thao tác; thiếu một mặt, cạnh lạ, lỗ sai, phần che khuất hoặc mép tách sau sửa không được cấp quyền đồng bộ root. Đây là các mặt phẳng đã có hình nguồn tương ứng, chưa tái dựng chiều sâu hoặc liên kết 3D ẩn.
- `native_span_fits`/`native_series_fits` hiểu yêu cầu hoặc câu trả lời rõ ràng **“giữ khe hở nguồn”**. Có thể giữ khoảng trống đo từ hai mặt thẳng song song của các chi tiết native đã định danh dù không có DIM riêng cho khe hở. Vẫn cần các mốc giữ và DIM chi tiết đủ nghiệm; kiểm tra đoạn mặt tiếp xúc, mặt phẳng, không có vật tư xen giữa. DIM nguồn mâu thuẫn/ghi đè hoặc nhiều ứng viên không được thay bằng suy đoán hình học. Quy tắc được tái lập từ yêu cầu khi tạo/duyệt bản sửa, lưu `clearance_policy`, và được giữ khi mở rộng sang bản gia công. Không có yêu cầu giữ khe hở thì không tự thêm chính sách này.
- `packing_top_layers` nối lớp đệm/lót khác bề rộng qua đoạn tiếp xúc thực, giữ chiều dày, vị trí tương đối và hai khe hở với sản phẩm/thùng. HATCH theo toàn đường bao; DIM có cả hai gốc đo trên góc lớp đệm và chuyển động không mâu thuẫn được dịch cùng. DIM chỉ có một đầu gắn lớp đệm, khác mặt phẳng hoặc ghi đè chưa được tự nhận quyền sửa. Đệm bên, góc V và phối cảnh chưa gắn vẫn giữ trạng thái chưa hoàn chỉnh.

**DWG tổng hợp mới qua website và AutoCAD thật (không phải file khách):**

| Trường hợp | Bằng chứng | Mở lại file tải về |
| --- | --- | --- |
| Hai mặt trong block xoay/phóng | `projected-face-9ea9e883/receipt.json`; document `6cf517830ef24c03992d426ee186c1ca`, revision `42953efece854be6ae228718532abcde` | Hai mặt, bốn lỗ, hai DIM 100 → 85 mm; giữ mép chung. HTTP 200, backend AutoCAD, hash nguồn không đổi. |
| Khe hở không ghi DIM | `mount-gap-4d35f8e2/receipt.json`; document `d20d3cc484b143ea88ccb27c413add37`, revision `efb40f2dd028465f9d3f1e5296596f20` | Các chiều cao 80/110/110 mm, khe hở 2 mm, tổng 302 mm. Đo mặt thực sau biến đổi, không dùng điểm chèn block làm mặt lắp. HTTP 200, nguồn không đổi. |

Chạy lại bằng `python scripts/verify_general_dwg_workflow.py --projected-multiface` và `--source-mount-gap`. Các tài liệu thử được ẩn khỏi thư viện mặc định; không tự duyệt sản xuất. Ảnh mặt sau sửa: `storage/validation-fixtures/projected-face-9ea9e883/after.png`.

**Kiểm tra lại nguồn thực tế:** `multiface-customer-audit-2026-10-20.json` ghi MR-106 chưa có cặp mặt hợp lệ, Dauphine có một ứng viên nhưng chưa khớp mặt nhận. Đệm/lót 3.8.01309 và 3.8.01280 của Dauphine vẫn có tiếp xúc đã kiểm tra, không có giao hình mới trong phần đã gắn; không phát sinh thao tác bổ sung cho bản cũ. Hai nguồn DXF giữ nguyên hash. Vì vậy **đợt này chưa tạo backup toàn Dauphine và chưa chứng nhận sửa đúng mọi DWG**.

**Kiểm thử cuối:** 1.477 bài Python đạt trong 230,81 giây (`pytest-multiface-final-2026-10-20.txt`), giữ 19 module; bảy script frontend đạt. Thêm sáu bài tập trung cuối về cùng mặt phẳng và báo cáo đối chiếu đạt (`pytest-multiface-coplanar-final-2026-10-20.txt`). Backend đã nạp mã mới; health/help và hai đường tải DWG trả HTTP 200, hash tải khớp receipt. Hướng dẫn mới tại `/help#mount-gap-projections`.

## Cập nhật 20/10: mặt vẽ nghiêng và mũi tên mặt lắp cho file mới

`graph/projected_profiles.py` đối chiếu một mặt chi tiết phẳng có biên dạng LWPOLYLINE thẳng, khép kín và ít nhất hai lỗ CIRCLE với một mặt vẽ nghiêng có lỗ ELLIPSE. Toàn bộ đỉnh, tâm lỗ và ma trận conic phải khớp cùng một phép biến đổi affine duy nhất. Mã phải đến từ tên/thuộc tính native hoặc chuỗi BOM cục bộ → STT → leader → một vùng vật liệu duy nhất. Không lấy tên file/handle mẫu hoặc chỉ kích thước giống nhau làm danh tính.

Mặt nhận được giữ phép chiếu nguồn; đỉnh, tâm lỗ, elip, DIM linear/aligned có hiệu chỉnh đo thật và mô tả trùng văn bản nguồn cập nhật theo recipe nguồn đã kiểm chứng. Hình xoay/phóng trong instance khác vẫn dùng hệ tọa độ cục bộ. Bỏ thao tác, sửa sai tâm/biên dạng, mã mâu thuẫn, đối chiếu đối xứng nhiều nghiệm, thiếu lỗ, cung elip không kín, thêm hình chưa gắn hoặc DIM ghi đè/sai hệ số không được cấp quyền đồng bộ. Mặt đã gắn vẫn hiện trong báo cáo khi phần còn lại của khung chưa đủ điều kiện hoàn chỉnh.

Đây là **phép chiếu của mặt phẳng có bằng chứng**, không phải tự suy chiều sâu 3D, bản uốn hoặc hình cụm hàn từ nét vẽ bất kỳ. HATCH, spline và mặt bị che/cắt còn cần adapter tương ứng; nhiều đường bao chỉ được hỗ trợ theo quy tắc kiểm tra đầy đủ nhiều mặt ở cập nhật phía trên. Ký hiệu STT giúp định danh nhưng không tự chứng minh mặt lắp.

`graph/native_contacts.py` nối mũi tên ngoài block với mặt chi tiết khi BOM/leader và profile nguồn xác định được đúng chủ sở hữu. Với đầu mũi tên nằm trên cạnh, nội suy vị trí theo đúng đoạn cạnh sau sửa; với đầu nằm trong vật liệu chỉ theo chuyển động tịnh tiến cứng đã kiểm chứng. Giữ vòng STT/chữ và các đỉnh leader còn lại tại vị trí nguồn. Có kiểm tra cụm xoay 23°, LINE/LEADER, đầu trên cạnh và trong vật liệu; thiếu thao tác mũi tên không qua validation. Việc này không tạo tiếp xúc mới từ ký hiệu.

Đóng gói: `carton_height_text` sửa đúng trường thứ ba L×W×H sau khi hình đo/BOM chứng minh vai trò chiều cao. Thùng có dài/rộng/cao bằng nhau không còn bị sửa tất cả số trùng nhau hoặc bị chặn chỉ vì trùng giá trị. Giữ ký hiệu định dạng MTEXT, số lớp và chỉ tiêu LBS. Nhiều quy cách trong cùng ô hoặc không xác định được đúng trường vẫn bị chặn.

**Kiểm chứng end-to-end hai DWG mới độc lập, mã ngẫu nhiên:**

| Nhận diện mặt nhận | Document / revision | Kết quả mở lại DWG |
| --- | --- | --- |
| Thuộc tính mã chi tiết native | `1328536838944ab7bc52bfc80accadb9` / `a97128c8df1748038e3aae5345a6503b` | Hình nguồn và DIM mặt nghiêng 100→85 mm; hai lỗ elip theo đúng mặt nguồn |
| Block không có mã, STT `01` + leader + BOM cục bộ | `b1267dee1f564dfc9bf8dac65816249e` / `ea1b086086e9408b9726138e151ea067` | Cùng kết quả 85 mm; không gán mã theo hình giống hoặc tên block |

Hai trường hợp qua upload thật → lập kế hoạch → bản sao → AutoCAD xuất DWG → tải HTTP 200 → mở lại qua ODA và đo kiểm; nguồn DWG không đổi. Receipts/file tải trong `storage/validation-fixtures/projected-face-65db4b46/` và `projected-face-0ad94901/`; ảnh mặt đã sửa `projected-face-0ad94901/after.png`. Đây là **DWG tổng hợp để kiểm chứng luồng mới**, không phải chứng nhận bản vẽ sản xuất khách hàng. Trường hợp STT vẫn giữ trạng thái khung chưa hoàn chỉnh vì ký hiệu/hình còn lại chưa được chứng nhận; không tự duyệt.

Lặp lại qua `python scripts/verify_general_dwg_workflow.py --projected-face` hoặc `--projected-face-balloon`. Các tài liệu thử được đánh dấu synthetic/auxiliary, không đưa vào danh sách file làm việc mặc định.

**Kiểm tra trên nguồn khách hàng:** trong phạm vi kế hoạch đang có, MR-106 không có mặt đáp ứng điều kiện adapter mới, Dauphine có một mặt ứng viên nhưng không có cặp đối chiếu được chứng minh. Không tạo thêm sửa đổi hoặc gỡ chặn toàn sản phẩm cho hai file này. Hash nguồn giữ nguyên; receipt `storage/validation-fixtures/projected-faces-customer-audit-2026-10-20.json` ghi cả kết quả không tìm được. Còn mặt lắp thiếu bằng chứng, hình cụm hàn/phối cảnh nhiều mặt, phần trong và đóng gói chưa đồng bộ đầy đủ. **Chưa đạt mọi DWG hoặc backup toàn Dauphine.**

Toàn bộ **1.443 kiểm thử Python đạt** (197,60 giây, 19 module), bảy script frontend đạt; 34 bài tập trung chạy lại sau bổ sung báo cáo từng mặt. Logs: `pytest-planar-projections-release-2026-10-20.txt`, `pytest-planar-projections-final-focused-2026-10-20.txt`, `frontend-planar-projections-2026-10-20.txt` trong `storage/validation-fixtures/`.

## Cập nhật 20/10: liên kết hình cụm/đệm theo nguồn, không theo tên file

- Bảng cụm và chọn chi tiết dùng chung quy tắc STT số: `7`, `07`, `007` đối chiếu trong đúng bảng đã chọn; `C1`/`C01` vẫn tách biệt. Nếu hai dòng trong cùng bảng va chạm sau chuẩn hóa, cụm bị đánh dấu mơ hồ, không được tự nhận là bản chính đầy đủ. Graph 31, cấu trúc cụm 4.
- Đệm bên không còn phụ thuộc hình bằng phải nằm phía trên hình cạnh. Cần hai DIM thật, quy cách/số lượng BOM, trục đăng ký hình, mặt đỡ dưới và mặt lót trên. Các bản chi tiết đệm cùng mã được đối chiếu đầy đủ trước khi lan truyền, kể cả hình clone, xoay và tỷ lệ khác; thiếu một hình nhận hoặc biên dạng khác vẫn chặn binding đó. Báo cáo hiển thị số hình chi tiết đã xác minh.
- HATCH của thân/nắp trong hình bao đóng gói được gắn bằng toàn bộ đường bao nguồn, không dùng bounding box. Khi sửa, nét gạch mặt cắt đi cùng đường bao; HATCH có association không hỗ trợ, nhiều boundary hoặc boundary trùng/mâu thuẫn không được đoán. Đồng bộ block cùng mã hỗ trợ snapshot HATCH, giữ pattern riêng của từng hình và instance ngoài phạm vi. Part Map nâng 5, hồ sơ thiết kế 18 để bỏ đối chiếu cũ.
- DIM thùng phải có đầu đo chạm góc thật, đúng hai mặt phẳng chiều cao và hệ số DIM đơn vị; không lấy số đo cùng chiều cao ở nơi khác. Cho phép đầu còn lại có offset gióng nguồn, như chính DWG Dauphine; không yêu cầu người dùng sửa cách trình bày CAD.

**Kiểm chứng file thực tế:** lập lại yêu cầu đã lưu của Dauphine thành plan `612029d39d9c46cca8922ec062fe2a5a`, revision `4e64546ecf13482e866cd6556eee5e9a`. Kế hoạch cũ bị từ chối khi thao tác không còn khớp bộ tính hiện tại; không bỏ qua đối chiếu để dùng lại. Bản mới xuất bằng AutoCAD, mở lại đạt `validated_roundtrip`. API tải trả HTTP 200, 2.452.599 byte, hash file tải trùng file xuất; DWG/DXF nguồn giữ nguyên hash. Trong khung đóng gói đo được: sản phẩm 727→700, thùng 850→823; đệm `3.8.01312` 745→718, hình cạnh còn lại giữ chênh lệch/khe hở nguồn; hai lớp lót trên dịch −27 mm. Receipt và file tải tại `storage/validation-fixtures/packaging-backup/4e64546ecf13482e866cd6556eee5e9a/`; ảnh `packaging-after-2026-10-20.png`.

**Đây vẫn là preview một phần**, không phải backup toàn sản phẩm: còn các hình cụm/phối cảnh, một số mô tả nguồn và lớp đóng gói chưa gắn đủ. Kiểm tra công đoạn còn thiếu mặt lắp/mốc giữ cho `8.1.05060.013`, `8.1.05190.002`, `8.1.05191.002`, `8.1.05192.002`. Nhận diện STT, đồng dạng hình hoặc cùng công đoạn không tự chứng minh các ràng buộc này. Không khẳng định đã sửa đúng mọi DWG.

**1.409 kiểm thử Python đạt**, 197,40 giây, vẫn 19 module; bảy script frontend đạt. Log toàn bộ: `storage/validation-fixtures/pytest-packaging-release-2026-10-20.txt`. Có kiểm tra bản chi tiết đệm xoay/phóng, bố trí hình bằng phía dưới, khác biên dạng, DIM sai đầu đo, HATCH thân/nắp, giữ pattern và instance ngoài phạm vi.

Công cụ kiểm chứng dùng được cho file khách hàng khác, không gắn ID/tên MR-106/Dauphine trong thuật toán:

```powershell
python scripts/verify_packaging_backup.py --document <document_id> --plan <plan_id>
```

Lệnh chạy lại kiểm tra kế hoạch hiện tại, tạo revision riêng, xuất và mở DWG lại, lưu receipt; không tự duyệt sản xuất và không sửa nguồn. Kế hoạch cũ sai phải phân tích lại trước. CLI tắt riêng tác vụ xuất nền trong lúc tự xuất để tránh chuyển đổi hai lần. Khi chạy thử trong sandbox, AutoCAD từng bị chặn tạo profile Registry; chạy lại riêng bước xuất với quyền phù hợp thành công, không cần thay đổi bản quyền/cấu hình CAD của người dùng.

## Cập nhật 20/10: kiểm chứng trên DWG sản xuất thật

Phát hiện lỗi đọc liên kết trên MR-106: bộ lập chỉ mục chỉ theo STT bên trong các hàng có nhãn ngoài khung (C1, 16…). File không có nhãn hàng vẫn quét được chữ/circle nhưng không tạo chuỗi BOM → STT → leader → vùng hình. Thêm `frame_groups` riêng cho khung chưa thuộc hàng, có ký hiệu/leader và phạm vi khung duy nhất. Không gom các khung theo khoảng cách hoặc lấy số từ BOM toàn file. `07` đối chiếu được với `7` trong BOM cục bộ; `C01` vẫn khác `C1`, và hai mã khác nhau cùng STT sau chuẩn hóa vẫn mơ hồ.

Chuỗi mới được dùng trong bộ gắn hình, Part Map và trang truy xuất AI; giao diện hiện các khung riêng cùng mã BOM tương ứng. Không dùng việc nhận đúng STT làm bằng chứng mặt lắp. Chỉ mục graph nâng lên 30, nguồn đo 6, Part Map 4, hồ sơ thiết kế 17 để bỏ cache cũ. Sửa thêm trạng thái chọn bản vẽ khi đổi file/nhập lại bằng AutoCAD: xóa banner, yêu cầu và vùng nhóm của file trước, không giữ khung cũ trên giao diện của file mới.

Đã chạy trên nguồn thực tế, không tạo geometry mẫu thay thế:

- **MR-106:** không có hàng ngoài khung; nay đọc bốn khung riêng và 15 chuỗi ký hiệu trong phạm vi sửa. Hai ký hiệu `07` được nối đúng mã `8.1.05940.126` từ hai BOM nguồn. Tuy nhiên leader của chúng nằm trong vùng chồng của hai vành ellipse, chưa xác định được đường bao bas trong hình cụm; không nhận vành lớn làm chi tiết 7. Còn 11 endpoint chưa gắn được. Receipt `storage/validation-fixtures/mr106-frame-callouts-2026-10-20.json`.
- **Dauphine:** giữ 25 nhóm hàng nguồn, nhận thêm sáu khung riêng. Trong phạm vi thực tế đã đọc 60 chuỗi: 16 vùng nội bộ, ba chuỗi có DIM, 25 endpoint chưa xác định, 14 chưa có BOM cục bộ tương ứng, hai vùng chồng. Ba biên dạng đo được gắn mã của `8.1.06128.196` và `8.1.06131.196`. Đây không phải xác nhận đầy đủ mặt lắp hoặc toàn bộ sản phẩm. Receipt `storage/validation-fixtures/dauphine-frame-callouts-2026-10-20.json`.

**Thử lại chính DWG MR-106 trên website qua AutoCAD:** bấm “Đọc lại bằng AutoCAD” tạo document mới `1925d8bc425c4e1f93937f6c85ee27d2`, đọc 469 định nghĩa block/10.067 đối tượng native. Nhập yêu cầu đã chốt của user: hai DIM 20,2 → 15 mm, giữ tâm lỗ. Kế hoạch `d0f5bf2b…`, revision `c1a8d641…` tạo bản mới; bấm nút tải thật đã lưu `C:/Users/nghi.tran/Downloads/PREVIEW-backup-c1a8d641.dwg`. Hash file tải trùng file xuất; mở lại DWG qua ODA đạt hai DIM 15 mm và hai BOM 3×15×15. DWG gốc và DXF native nhập lại giữ nguyên hash.

File minh chứng thực tế: `storage/validation-fixtures/mr106-native-frame-callouts-2026-10-20/download/actual.dwg`; kết quả đo/hash/trạng thái trong `receipt.json` cùng thư mục. **Revision này vẫn là xem trước một phần**, vì bốn khung cụm chưa được đồng bộ/kiểm chứng đầy đủ. Không phải backup toàn MR-106 hoặc toàn Dauphine và chưa nghiệm thu chức năng sửa mọi DWG.

Toàn bộ **1.392 kiểm thử Python đạt**, 242,76 giây, giữ 19 module (`pytest-frame-callouts-full-2026-10-20.txt`); bảy script giao diện đạt (`frontend-frame-callouts-2026-10-20.txt`). Backend đã nạp mã mới.

## Cập nhật 20/10: đồng bộ tấm qua nhiều hình đo được

Bộ sửa tấm không còn yêu cầu chỉ có một mặt tấm trong toàn phạm vi. Chọn hình nguồn theo khung người dùng chọn; sau đó dùng bộ đối chiếu định nghĩa native hoặc Part Map nguồn để xác minh các hình nhận. Tất cả mặt ứng viên cùng mã phải được phủ bằng recipe có đối chiếu đầy đủ đường bao/lỗ/đầu đo DIM. Hình cùng số đo nhưng khác biên dạng, thiếu mapping, chỉ mở để review hoặc chưa rõ hướng vẫn không được tự sửa. Với nhiều hình vuông cùng được chọn, yêu cầu chỉ một hướng DIM cần chọn đúng khung nguồn trước.

Mô tả trên các khung chi tiết đã xác minh được cập nhật cùng BOM; kế hoạch lưu bị bỏ bớt hình nhận không qua đối chiếu lại ý định. Sửa thêm quy tắc lỗ bậc: chữ Ø5 trong hình phóng phải được so với bán kính CAD sau áp dụng hệ số DIM native, không so trực tiếp với bán kính trên giấy. Không coi hai vòng tròn chồng nhau là lỗ bậc nếu thiếu DIM chứng minh.

Block vô danh không còn nhận mã của block giống hình đầu tiên tìm thấy. Muốn đồng bộ native cần bằng chứng sở hữu nguồn độc lập, cùng mã BOM và đối chiếu đầy đủ định nghĩa; các mã khác có hình giống nhau không được kéo theo.

Chạy `python scripts/verify_general_dwg_workflow.py --plate-linked-views`: hai DWG mới mã/STT ngẫu nhiên có hai khung chi tiết, hình nhận clone khác tên xoay 90°/tỷ lệ 2, BOM nằm ở khung thứ ba. Website tự lập graph sau upload:

| Trường hợp | Hình nguồn sau mở lại DWG | Hình nhận sau quy đổi tỷ lệ | BOM |
| --- | --- | --- | --- |
| Vuông 27,2×27,2 → 18×18 | 18×18 mm | 18×18 mm | 3×18×18 mm |
| Chữ nhật 40,2×30,2 → 32×30,2 | 32×30,2 mm | 32×30,2 mm | 3×30×32 mm |

Cả hai qua kiểm tra mặt độc lập, xuất/tải HTTP 200 và mở lại đo đúng. Nguồn và instance đối chứng ngoài ba khung giữ nguyên. Receipt: `storage/validation-fixtures/plate-intent-b9ee3585/receipts.json`; DWG trong `square/download/preview.dwg` và `rectangle/download/preview.dwg`. Đây là preview một phần của dữ liệu tổng hợp, không thay thế backup toàn sản phẩm khách hàng.

Kiểm chứng thêm luồng quan hệ giữa hai chi tiết bằng `scripts/verify_contact_dwg_workflow.py`: DWG tổng hợp mới có tiếp xúc biên thật và mốc giữ đáy. A cao 100 → 80 mm; B giữ dài 100 mm và dịch vị trí lắp 100 → 80 mm, ATTRIB đi theo 103 → 83 mm; DIM tổng 200 → 180 mm, BOM A đổi/B giữ nguyên. Đã qua xem trước → duyệt → tải DWG → mở lại; nguồn bất biến. Receipt: `storage/validation-fixtures/contact-workflow-c16a63c3/report.json`; file `download/checked-assembly-backup.dwg`. Việc duyệt chỉ áp dụng cụm tổng hợp này, không phải Dauphine.

Toàn bộ **1.384 kiểm thử đạt** trong 187,79 giây, giữ 19 module; log `storage/validation-fixtures/pytest-plate-linked-views-full-2026-10-20.txt`. Backend chạy mã mới trên cổng 8765. Chưa có bảo đảm sửa mọi DWG, proxy/block động phức tạp hoặc quan hệ cơ khí thiếu bằng chứng; backup toàn Dauphine chưa hoàn tất.

## Cập nhật 20/10: chọn khung chi tiết khi BOM nằm ở khung khác

Bộ hiểu yêu cầu trước đây chỉ lấy quy cách từ BOM trong khung người dùng chọn hoặc danh sách BOM gốc. Vì vậy, cùng một tấm có thể sửa được khi chọn bảng kê nhưng không vào được bộ sửa tấm khi chọn chính khung chi tiết riêng.

`selected_bom_rows` nay đi từ chủ sở hữu khung và biên dạng đo được tới đúng occurrence của bảng kê trong dữ liệu nguồn đã mở rộng. Đối chiếu ref bảng, STT, mô tả và khung nguồn của occurrence; không tìm STT trên toàn file. BOM cục bộ vẫn được ưu tiên. Thiếu bằng chứng, nhiều chủ sở hữu, BOM khác hoặc occurrence không còn khớp đều không được mượn quy cách. Bước này chỉ giải quyết danh tính/quy cách; không cấp mốc giữ hay bỏ qua kiểm tra lắp ghép.

Chạy lại bằng `python scripts/verify_general_dwg_workflow.py --plate-intent --detail-scope`. Hai DWG tổng hợp mới với mã ngẫu nhiên được upload qua HTTP; website tự nhận diện khung và đồ thị, chọn khung chi tiết không có BOM:

| Trường hợp | Kích thước nguồn → sau mở lại DWG | BOM sau sửa | Kết quả |
| --- | --- | --- | --- |
| STT 23, tấm vuông | 27,2×27,2 → 18×18 mm | 3×18×18 mm | Hai hướng, tâm lỗ/R giữ nguyên |
| STT 29, tấm chữ nhật | 40,2×30,2 → 32×30,2 mm | 3×30×32 mm | Chỉ đổi chiều dài |

Cả hai tạo revision, xuất DWG, tải HTTP 200, mở lại đo đạt; nguồn và instance ngoài phạm vi không đổi. Mỗi trường hợp có mã/document mới; không tái sử dụng lựa chọn giữa file. Bản vuông chỉ dùng lại lựa chọn sau lần xác nhận trong chính document đó. Hai bản vẫn là preview một phần, không phải backup toàn sản phẩm.

Receipt: `storage/validation-fixtures/plate-intent-84b9b887/receipts.json`. File: `square/download/preview.dwg` và `rectangle/download/preview.dwg` trong cùng thư mục. Log: `detail-bom-workflow-2026-10-20.txt`. Nhóm parametric/planning/revision đạt 305 bài (`pytest-detail-bom-2026-10-20.txt`); toàn bộ đạt 1.361 bài trong 186,07 giây (`pytest-detail-bom-full-2026-10-20.txt`), giữ 19 module kiểm thử.

## Lỗi thực tế và cách sửa

User gõ lại "giảm chiều dài chi tiết số 7 thành 15" nhưng website hỏi lại BOM 20 mm hay DIM 20,2 mm, dù đã chốt DIM thực tế, cả hai hướng và tâm lỗ. Lựa chọn cũ chỉ nằm trong một kế hoạch riêng; lần phân tích mới không có các câu trả lời đó.

Nay kế hoạch tấm đã được kiểm tra lưu lựa chọn vào `design-decisions-v1.json` của document. Khóa gồm hash nguồn, root CAD/BOM, mã/STT/mô tả, DIM nguồn/hướng/chủ sở hữu, loại yêu cầu và đích. Một yêu cầu lặp phù hợp dùng lại lựa chọn; không mặc định áp dụng sang file, vật tư hoặc đích khác. CAD/BOM vẫn được đọc và biên dịch lại. Câu trả lời phủ định/mâu thuẫn bị chặn. Kế hoạch lưu lại còn được so với thao tác và recipe mong đợi từ chính yêu cầu khi thực thi hoặc duyệt.

Website hiện thông báo đã dùng lựa chọn trước. Không dùng việc ghi nhớ này để tự duyệt hình cụm chưa được xác minh.

## Mở rộng dùng cho file mới

- Chọn sửa riêng DIM ngang hoặc DIM đứng của tấm vuông; giữ nguyên hướng còn lại.
- Sửa chiều dài/rộng duy nhất trên mặt tấm chữ nhật khi DIM và quyền sở hữu đã gắn nguồn; giữ tâm lỗ được người dùng chỉ định.
- Quy cách BOM được sửa theo vai trò rộng/dài, giữ độ dày và các trường khác. Có hai số giống nhau không đồng nghĩa thay cả hai.
- Khi BOM và DIM nguồn bằng nhau, không hỏi thêm cách xử lý chênh lệch không tồn tại. Khi khác nhau thì cần basis đã nêu hoặc được xác nhận cho đúng nguồn.
- Không suy cơ tính/đối xứng hoặc quyền co hai hướng từ việc BOM ghi tấm vuông. Tâm giữ cần có yêu cầu rõ; chữ "tâm lỗ" trong mô tả không phải quyền di chuyển hình.
- Nút Xem thay đổi nhận cả STT và mã chi tiết trong manifest. Bản sửa mới tự mở khung chứa DIM/profile đã sửa nếu chỉ có một khung xác minh, thay vì để người dùng nhìn mãi khung BOM/hình cụm chưa đổi. Phạm vi yêu cầu và file gốc được giữ nguyên.

## Kiểm chứng

MR-106 document `1c7d831296ff402bb1a838479063a99d`: refine kế hoạch đang bị chặn `2535af51…` bằng lựa chọn đã có của người dùng; sau đó gọi API mới không kèm câu trả lời. Kế hoạch `82a88405…` thực thi được, không còn câu hỏi, dùng đúng lựa chọn nguồn, lập kế hoạch trong 3,67 giây. Receipt `storage/validation-fixtures/mr106-linear-memory-2026-10-17.json`.

Gõ lại nguyên yêu cầu từ trình duyệt cũng tự tạo bản sao `627d4f54…`, BOM 3×15×15 mm, có link DWG AutoCAD, không gửi CAD ra ngoài. Các hình cụm chưa đồng bộ vẫn làm bản sửa chỉ đủ điều kiện xem trước.

Hai DWG mới độc lập, mã và STT ngẫu nhiên, được tạo bằng script `scripts/verify_general_dwg_workflow.py --plate-intent`. Không chèn graph/quy tắc nhận diện sẵn vào document: website tự đọc hai khung BOM/chi tiết của file upload.

| Nguồn kiểm thử | Số đo sau mở DWG lại | BOM sau sửa | Kết quả |
| --- | --- | --- | --- |
| Tấm vuông 27,2×27,2, STT 23 | 18×18 mm | 3×18×18 mm | Giữ lỗ/R, dùng lại lựa chọn đúng nguồn, nguồn và instance ngoài không đổi |
| Tấm chữ nhật 40,2×30,2, STT 29 | 32×30,2 mm | 3×30×32 mm | Chỉ chiều dài đổi; chiều rộng và các instance ngoài giữ nguyên |

Hai file qua FreeCAD và endpoint tải HTTP 200. Receipt: `storage/validation-fixtures/plate-intent-a77564eb/receipts.json`; log `plate-intent-workflow-2026-10-17.txt`. Đây là tệp tổng hợp kiểm thử, không thay thế nghiệm thu sản phẩm thực tế.

Bộ toàn phần đạt 1.349 bài (`pytest-linear-intent-complete-2026-10-17.txt`); sau sửa vùng phóng toàn biên dạng, 304 bài liên quan đạt trên mã cuối (`pytest-linear-intent-final-2026-10-17.txt`). Giữ 19 module kiểm thử.

Bản sửa cuối `3aca2080488f494ea3cc98fbe0c3b660` đã qua bước đối chiếu ý định mới, tự chọn khung hình học `frame_40C7A5_404569`, xuất AutoCAD và mở lại đạt 15×15 mm. Receipt: `mr106-linear-memory-verified-2026-10-17.json`. Nút đối chiếu trả HTTP 200 và phóng toàn bộ biên dạng, không chỉ vùng DIM R2. Ảnh chồng nét: `mr106-linear-memory-comparison-2026-10-17.png`.

## Phần chưa hoàn tất

Không có bảo đảm tự sửa đúng mọi DWG. Hình không gắn được chủ sở hữu/mốc/hướng, block động/proxy/association chưa có adapter, hình cụm phối cảnh và quan hệ cơ khí thiếu nguồn vẫn phải được xử lý riêng. Backup toàn Dauphine và bốn khung cụm MR-106 chưa được nghiệm thu hoàn chỉnh. Các kết quả trên không tính độ bền hay chứng nhận sản xuất.

Bấm tải trực tiếp trên trình duyệt đã nhận `C:/Users/nghi.tran/Downloads/PREVIEW-backup-3aca2080.dwg`, hash trùng DWG AutoCAD đã kiểm chứng. Nút Xem thay đổi chi tiết 7 mở toàn biên dạng chồng nét, không lỗi JavaScript. Ảnh UI: `storage/validation-fixtures/mr106-linear-memory-ui-2026-10-17.png`.
