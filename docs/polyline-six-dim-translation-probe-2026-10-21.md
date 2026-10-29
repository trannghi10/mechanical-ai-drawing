# Probe dịch polyline cùng sáu DIM thực tế

Đã kiểm chứng dịch cứng nhóm polyline `3DFA1C` cùng sáu DIM trên bản sao Dauphine bằng AutoCAD 2027. Đây là probe phát triển, chưa có action production hoặc quyền sửa kích thước của nhóm.

Nhóm gồm DIM `3DFA1D`, `3DFA20`, `3DFA24`, `3DFA25`, `3DFA29`, `3DFA2A`: bốn DIMASSOC đã xác minh điểm nguồn và hai action `3E0329`, `3E032F` có body `AcDbAssocRotatedDimActionBody`. Probe yêu cầu đúng sáu reactor, dictionary/owner đúng và dependency action khớp polyline cùng DIM. Tất cả được kiểm trước sửa.

## Bằng chứng CAD

- Delta `[5,-3,0]`: `storage/validation-fixtures/native-poly-dim-probe-5ee187cd/`, DWG SHA-256 `1b924c3ba7c9847f9ec2e4e7759c870d27e1bc14f21b1664304ecd33ff31e6f0`. Đối chiếu visual bổ sung tại `visual-verification.json`.
- Delta `[-2.5,4,0]`: `storage/validation-fixtures/native-poly-dim-probe-e53dfd7b/`, SHA-256 `74bfa0f8d25cb9713d0e612a38826b7e67e9abdc6e0668af4ede3148c4d5217e`. Receipt có kiểm visual từng DIM.

Cả hai lưu/mở lại DWG, kiểm trạng thái trước evaluate, evaluate lại hai action và kiểm mọi DIM sau evaluate. Điểm đo, điểm đường DIM, vị trí chữ, góc, style và normal phải dịch đúng/giữ nguyên theo phép dịch. Readback DXF độc lập kiểm polyline, bốn source binding DIMASSOC, sáu số đo và chữ DIM. Các số đo vẫn 905/905/625/140/625/140 (làm tròn theo chữ nguồn).

39.856 entry inventory ngoài nhóm và ngoài 54 primitive thuộc block hiển thị DIM được đối chiếu theo snapshot và dung sai hiện có. Việc loại 54 primitive khỏi inventory chung chỉ sau kiểm block không có người dùng ngoài nhóm; chúng được đối chiếu riêng bằng hình học, style, nội dung chữ và độ trong suốt hiển thị. Cả 54 primitive khớp phép dịch trong hai lượt.

AutoCAD regen thêm transparency BYBLOCK thay cho thuộc tính không ghi (BYLAYER). Bộ so sánh không bỏ qua thuộc tính này: giải quyết độ trong suốt theo layer/parent DIM rồi so giá trị hiển thị. MTEXT được so nội dung `entity.text` riêng vì `dxfattribs()` không chứa toàn bộ nội dung. Kiểm thử làm sai chữ hoặc transparency thực tế đều bị chặn. Không tuyên bố serialization thuộc tính kế thừa giữ nguyên byte; bằng chứng visual là độ trong suốt được giải quyết tại thời điểm kiểm.

Lượt đầu `native-poly-dim-probe-81e17155` thất bại trước dịch do ép kiểu enumerator dictionary sai. Đã sửa dùng `GetEnumerator()` như native inspector; không cấp receipt thành công cho lượt lỗi.

## Mã và phạm vi

`autodesk/MechanicalCad/PolylineDimensionProbe.cs` cung cấp lệnh cố định `MECHANICALPOLYDIMPROBE`; không được gọi bởi endpoint production `MECHANICALCAD`. `scripts/probe_native_polyline_dimensions.py` đọc bốn binding từ DXF, kiểm hash nguồn, chạy bản sao riêng, đọc lại DXF và kiểm visuals bằng `cad/dimension_visuals.py`. Plugin build/check đạt, runtime key `62a71f4d1deda1fec54fdec8bf2e8161c63c045a5858c774a5bf74b6953bd606`.

Nguồn khách giữ SHA-256 `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`; không tạo customer revision. Chỉ chứng minh dịch cứng nhóm cụ thể với tám vertex thẳng XY và sáu DIM nói trên. Chưa kiểm chứng stretch/đổi kích thước, chưa nối luồng API/revision, chưa đồng bộ BOM hoặc chi tiết xung quanh. Capability production của nguồn vẫn chưa được mở. Đề xuất tấm xốp vẫn chưa xác nhận.

Kiểm thử geometry, DIM visuals, nested perpendicular và export jobs: **310 bài đạt**, 223 warning thư viện, 41,64 giây; log `storage/validation-fixtures/pytest-poly-dim-probe-2026-10-21.txt`. Không dùng kết quả này thay cho kiểm CAD thật nêu trên hoặc tuyên bố toàn bộ dự án đã hoàn thành.

## Chỉnh lần hai trên DWG đầu ra

Đã nhập DWG `74bfa0f8...` của lượt delta `[-2.5,4,0]` thành tài liệu native riêng `b6b63eec23894cd4a8192a456062a1fb`, import job `4c11074c317c4ddf81cdf57f1f6d3c59`. Hash file original của tài liệu mới khớp chính xác hash DWG đầu ra lượt trước. Sau đó chạy probe delta ngược `[2.5,-4,0]` trên tài liệu mới.

Lượt thứ hai đạt toàn bộ kiểm native/DXF/visual; artifact `storage/validation-fixtures/native-poly-dim-probe-db625d21/`, DWG SHA-256 `8eba59658b5c9c10ee8596f5c00a4cae5456b052b653d1cdea3fe9c69323456f`.

`scripts/verify_poly_dim_return.py` đối chiếu chuỗi hash hai lượt, tổng vector bằng 0, tập DIM/action không đổi, rồi đọc DXF cuối so với native readback nguồn ban đầu. Polyline, snapshot sáu DIM, số đo, reactor, bốn DIMASSOC source binding và 54 primitive hiển thị đều trở về đúng trong dung sai 1e−6. Receipt `storage/validation-fixtures/poly-dim-second-edit-2026-10-21/return-verification.json`. Đây là kiểm chuỗi hai lần chỉnh/lưu trên bản sao, không phải đồng nhất nhị phân toàn database hoặc chứng minh liên kết với chi tiết xung quanh. Không thay đổi production adapter hay cấp quyền stretch.


## Tự phát hiện nhóm từ bằng chứng native

`cad/native_polyline_dimensions.py` và `scripts/audit_native_polyline_dimensions.py` tự tìm sáu DIM từ polyline được yêu cầu kiểm tra, không truyền sẵn danh sách DIM. Bộ đọc kiểm reactor native/DXF, ownership dictionary, bốn binding DIMASSOC đã xác minh, hai action cùng body/dependency và layout. Chỉ nhận hình tám đỉnh thẳng XY thuộc phạm vi probe hiện tại. Inventory thiếu, bị cắt, trùng handle, sai body/source/owner hoặc thừa dependency đều bị từ chối.

Đã chạy với inventory native job `ea4b1d186ca4453e9db9cd06c55ef263` và DXF readback cùng job: tìm đúng `3DFA1D,3DFA20,3DFA24,3DFA25,3DFA29,3DFA2A`. Receipt có hash hai đầu vào tại `storage/validation-fixtures/poly-dim-discovery-2026-10-21/discovery.json`. Hash chỉ định danh artifact được đưa vào, không tự chứng minh artifact thuộc DWG hiện tại. Khi nối luồng sửa vẫn phải chạy native preflight trên bản DWG nguồn. Chưa nối vào API production.

Kiểm thử bộ phát hiện và visual: **13 đạt, 7 warning, 13,63 giây**; gồm 10 trường hợp làm hỏng bằng chứng, một lượt phát hiện thật và hai kiểm visual. Fixture thật được bỏ qua nếu môi trường kiểm thử không có dữ liệu lưu này.

Hai kiểm native âm cũng đạt: `native-poly-dim-probe-09e60ad1` thiếu một DIMASSOC và `native-poly-dim-probe-f1226ff2` trỏ nhầm DIM. AutoCAD trả đúng lỗi preflight, không tạo DWG/DXF/receipt thành công, hash nguồn giữ nguyên. Chúng xác minh chặn đúng hai lỗi cụ thể; không chứng minh mọi lỗi liên kết đều đã bao phủ.


## Luồng tự phát hiện → native preflight → chỉnh/lưu/readback

Công cụ probe nhận thêm `--inspection-job`. Job phải là inspect, hash nguồn phải bằng hash `original.dwg` hiện tại; inventory và DXF được lấy qua `aps_jobs.artifact` để kiểm trạng thái, hash nguồn và hash artifact. Không dùng catalog DXF thay cho DXF cùng job trong chế độ này. Sau phát hiện, bốn binding được đối chiếu lại; danh sách sáu DIM và hai action được gửi cho plugin. Native preflight đối chiếu chính xác hai tập này với database vừa mở trước mutation. Receipt và DXF readback cuối vẫn kiểm độc lập như trước.

Chạy thực tế với job `ea4b1d186ca4453e9db9cd06c55ef263`, polyline `3DFA1C`, delta `[3,2,0]`: đạt. Artifact `storage/validation-fixtures/native-poly-dim-probe-a3791527/`, DWG SHA-256 `0581da2de32dd3de37568a29ee295bdba60a77dc7a443ce82edb1d1c9acff68a`. Receipt xác nhận discovery_verified, independent_dxf_readback, lưu/mở lại/evaluate ổn định, sáu DIM và 54 primitive visual. Nguồn giữ nguyên; không tạo customer revision.

Hai kiểm âm native mới: `native-poly-dim-probe-b7c6304b` cố ý thiếu một DIM trong danh sách phát hiện, và `native-poly-dim-probe-62bdec7f` cố ý thiếu một action. Cả hai trả đúng lỗi đối chiếu trước mutation, không tạo DWG/DXF hoặc receipt thành công.

Plugin build/check đạt với runtime key `8520a0f8192a5de6bd3fce6975686ec80a92bbb124d9148ecb2bbc20b09a0f61`. Bộ kiểm Python liên quan đạt **16 bài, 7 warning, 19,75 giây**; thêm kiểm job sai mode/hash bị từ chối trước đọc artifact và kiểm dùng đúng hai artifact được xác thực. Đây vẫn là công cụ thử nghiệm trên bản sao; chưa đưa operation vào API chỉnh sửa chính thức, chưa hỗ trợ stretch hoặc chứng minh quan hệ với BOM/chi tiết xung quanh.

Lệnh tái lập:

```powershell
python scripts/probe_native_polyline_dimensions.py 51ec94944c4443b19fb8d5bd7930a6dd 3DFA1C --inspection-job ea4b1d186ca4453e9db9cd06c55ef263 --dx 3 --dy 2
```
