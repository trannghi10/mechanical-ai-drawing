# Hai đầu DIM native: kết quả sửa thử ngày 22/10/2026

**Cập nhật mới nhất:** adapter ObjectARX đã biên dịch và sửa đủ tham chiếu hai DIM trên bản sao; giữ action native B, qua lưu/mở lại và 8/8 phép kéo A/B ±10 mm. Xem [báo cáo adapter trực tiếp](native-point-reference-adapter-2026-10-22.md). Các kết luận “chưa tạo được” dưới đây mô tả các phương pháp cũ trước khi có bridge C++; các cờ cũ vẫn bị khóa, chưa tích hợp bridge vào revision.

**Chưa tạo được bản DWG hợp lệ sửa đủ hai đầu A.** Các phép thử đều chạy trên bản sao; không phát hành revision mới từ các kết quả không đạt. Nhánh thay đổi native head đã bị khóa trong CLI và native command để không đi vào luồng sản phẩm.

## Phạm vi

Nguồn document `51ec94944c4443b19fb8d5bd7930a6dd`, polyline `3DFA1C`. Hai điểm cần xử lý là `3DFA24/defpoint2` (ứng viên vertex 1) và `3DFA29/defpoint2` (ứng viên vertex 0). Native dependency/OwnedParams hiện chỉ chứng minh đầu B lần lượt ở vertex 2 và 7. Các phép kéo ±10 mm ngày 21/10 xác nhận đầu A không đi theo ứng viên. Tọa độ trùng nhau không được tự nâng thành liên kết thiết kế đã xác nhận.

## Các kết quả đáng chú ý

| Hướng thử | Kết quả thực tế | Bằng chứng dưới `storage/validation-fixtures/` |
|---|---|---|
| DIMREASSOCIATE, giữ action cũ | Lệnh có thể xóa action/dependency native hoặc làm hai điểm đo trùng nhau; bị chặn | `relationship-repair-e08034d0`, `relationship-repair-f37fbf89` |
| Tháo native rồi chuyển sang DIMASSOC | Có bản giữ nguyên điểm đo, số đo và qua save/reopen/inventory; đọc độc lập chỉ có một đầu liên kết, nên không được chấp nhận | worker `storage/acwork/relationship-repair-762f7fe8`; các bản thử tiếp theo vẫn thiếu một đầu |
| Chọn trên cạnh, ẩn DIM lân cận/đang chọn, tạm DIMASSOC=2 | Có thể gắn đầu A đúng nhưng đầu B bị mất hoặc không được duy trì sau regen/save; bộ kiểm đầy đủ hai điểm từ chối | `relationship-repair-7ce473e6` và các worker được lưu riêng |
| Vá đúng hai DIMASSOC trong DXF rồi nhập toàn file | Bản vá DXF đọc được đủ hai điểm, nhưng AutoCAD lỗi native khi nhập toàn bộ file; không có DWG đạt kiểm | `native-headlink-de547e04`, return code 3221225477 |
| Khôi phục native B sau gắn A | AutoCAD từ chối thao tác với `eCannotBeErasedByCaller`; không tạo DWG kết quả | `relationship-repair-0aad6c21` |

Thử DXF toàn file và mã clone chưa hỗ trợ đã được loại khỏi mã thực thi. Không bỏ qua lỗi, không hạ kiểm số đo/vertex/reactor để làm một bản thử đạt. Cách khôi phục bị từ chối là hạn chế của thao tác đã thử với adapter hiện tại, không phải bằng chứng rằng mọi cách sửa bằng ObjectARX đều không thể thực hiện.

## Phần đã bổ sung

- `cad/native_head_repairs.py`: lập hai đề xuất có ràng buộc về hash nguồn, dependency, cây tham số, ứng viên đầu A duy nhất và đầu B đã chứng minh. Luôn giữ `design_intent_confirmed=false`.
- Kiểm thử planner cho nguồn cũ/sai hash, thiếu cây tham số, báo cáo partial và điểm B không phù hợp.
- Chế độ challenge đầu A có kiểm save/reopen đã được chuẩn bị nhưng chưa có bản migration đủ điều kiện để chạy thành công; không báo đó là kiểm chứng đã đạt.
- Các cờ `--native-heads`, `--migrate-native-to-dimassoc`, `--restore-native-b` hiện bị từ chối trước khi chạy sửa. Native command cũng có guard tương ứng. Luồng API revision chỉ gọi adapter legacy đã kiểm chứng.

## Kiểm hồi quy và bảo toàn

- Plugin build và `setup_autocad.py check` đạt; runtime key `c3aa24cc65f966d4410d8b62e16d7466d71b68f1ddd676f0f4e4bbf34bcaf274`.
- 16 test tập trung đạt, 7 warnings: native head planner, legacy repair planner, revision/undo và native action review. Không chạy lại toàn suite.
- Chạy lại adapter legacy trên DWG thực: `relationship-repair-49dd4475` đạt `validated_relationship_repair_proposal`, lưu/mở lại và kiểm hai liên kết legacy; nguồn giữ nguyên.
- Revision hiện có `fc3037b7d2bc4588ad3c0df9b15e2494` vẫn `ready` và đang được chọn. Hồ sơ kiểm HTTP/hash: `storage/validation-fixtures/native-head-repair-2026-10-22/preservation-verification.json`.
- SHA-256 nguồn vẫn `cc4077e145edd4982232c2ffea4acb2e4fb8854146968a4a4b3d5f91566d5178`. Backend local đã được mở lại, PID 18872.

## Còn phải làm

Cần adapter tạo/chỉnh trực tiếp tham chiếu điểm native hoặc DIMASSOC có đủ hai đầu, không phụ thuộc bắt điểm hiển thị và không nhập lại toàn bộ file có OLE/proxy. Sau đó phải chứng minh đồng thời: đầu A mới theo đúng vertex; đầu B cũ vẫn bám đúng vertex; đủ hai điểm sau save/reopen; đồ họa DIM và các đối tượng ngoài nhóm được bảo toàn. Chỉ khi đạt các kiểm này mới tích hợp vào revision. Hiện hai đầu native vẫn chưa được sửa hoàn chỉnh.

## Kiểm tra khả năng xây adapter trực tiếp

Cập nhật sau khi người dùng tải SDK: đã tìm thấy `Downloads/objectarx-for-autocad-2027-win-64bit.exe` và giải nén thành công vào `storage/tools/objectarx2027/CDROM1`. SDK có `dbdimassoc.h`, `dbdimptref.h` và thư viện x64; không có header hai lớp action body/osnap parameter chuyên biệt đang cần. Nhận định thiếu SDK bên dưới là trạng thái trước lần tải này.

Đã thêm mã bridge thử nghiệm tại `autodesk/NativePointReference`, script build và smoke test tổng hợp. C++ **chưa biên dịch/chưa chạy** do chưa có MSVC 14.44. Plugin managed mới build/check đạt, runtime key `109c2040209aeb7638a52b6ad3ef092f49d303748360b0c17976dea48b346fe2`; điều này chỉ xác nhận plugin managed, không xác nhận bridge native. Bộ cài Microsoft chính thức bị kẹt tải catalog; đã tải được catalog local, nhưng Windows từ chối dừng đúng tiến trình setup để chạy lại (`Access is denied`). Cần hoàn tất/hủy bộ cài bằng quyền quản trị. Hai đầu DIM native vẫn chưa được sửa và không tạo revision khách hàng mới.

Đã kiểm tra lại môi trường: thư mục Visual Studio 18 không có bộ biên dịch C++; không tìm thấy header/library ObjectARX 2027 trong bộ cài AutoCAD hoặc workspace. Có .NET SDK và assembly managed để xây plugin hiện tại, nhưng chúng không cung cấp setter chuyên biệt cho `AcDbAssocRotatedDimActionBody`. Chưa thêm một adapter native chưa biên dịch vào luồng revision.

API công khai cần đánh giá tiếp là `AcDbDimAssoc::setPointRef` và `setPointRefReactor` với `AcDbOsnapPointRef`. Đây là API DIMASSOC, **chưa chứng minh** thay được tham chiếu A trong action native hoặc có thể cùng tồn tại với action B. Không coi việc tìm được API này là sửa thành công.

Theo [yêu cầu SDK chính thức](https://aps.autodesk.com/developer/overview/objectarx-autocad-sdk), AutoCAD 2027 dùng ObjectARX 2027, Visual Studio 2026 18.0 với VC tools 14.44.35207 và .NET 10. [Trang cấp SDK](https://aps.autodesk.com/developer/overview/autocad-objectarx-sdk-licensing) yêu cầu chấp nhận điều khoản và xác minh người dùng. Cần người dùng hoàn tất bước tải SDK chính thức; chưa tải hoặc cài SDK trong phiên này.

Khi có SDK/toolchain: trước hết kiểm tra header có API chỉnh reference của action body hay không; nếu chỉ có DIMASSOC, thử trên mẫu tổng hợp rồi bản sao nguồn với transaction rollback. Phải giữ nguyên B/action/dependency, kiểm A và B bằng các phép kéo độc lập, lưu/mở lại kiểm lần nữa và đối chiếu ngoài nhóm trước khi cho phép tạo revision.
