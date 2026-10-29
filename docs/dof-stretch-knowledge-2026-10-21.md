# Kiến thức DOF và stretch dùng cho dự án

Ngày tổng hợp: 21/10/2026. Nguồn yêu cầu: tài liệu người dùng về quan hệ cơ khí, GCS và generalized stretch. Tài liệu này là tri thức tham khảo cùng mô hình thử nghiệm; việc thêm tài liệu không đồng nghĩa đã fine-tune mô hình hoặc có thể chỉnh mọi DWG.

## 1. Sửa các kết luận dễ dẫn đến chỉnh sai

**DOF không bằng số biến trừ số ràng buộc ghi trong JSON.** Một ràng buộc có thể sinh nhiều phương trình vô hướng; các phương trình có thể phụ thuộc nhau. Với mô hình tuyến tính đã định nghĩa `A x = b`, số chiều không gian nghiệm nếu nhất quán là `n - rank(A)`. Với hệ không nhất quán, nullity vẫn tính được nhưng không phải số bậc tự do của một trạng thái cơ khí khả thi. DOF không âm; số đếm âm thường cho thấy cách đếm sơ bộ không áp dụng được. Không dùng Laman như tiêu chuẩn phổ quát cho mọi hỗn hợp điểm, đường, tròn, tiếp tuyến và ràng buộc suy biến.

**Ràng buộc dư không đồng nghĩa mâu thuẫn.** Hai phương trình cùng bắt chiều rộng bằng 150 mm có thể phụ thuộc nhưng nhất quán; bắt cùng chiều rộng bằng cả 150 và 160 mm là xung đột. Phải kiểm residual và hạng, không tự xóa ràng buộc. Báo số phương trình phụ thuộc không có nghĩa đã xác định được constraint nào có thể bỏ.

**DOF bằng 0 không phải nguồn quyền sửa.** Nó chỉ nói mô hình đang phân tích đã khống chế đủ biến theo các giả thiết đó. Hình có thể đổi khi người dùng thay ràng buộc kích thước. Một mô hình thiếu ràng buộc cũng không tự cho phép phần mềm chọn tùy ý một nghiệm.

**Stretch có thể đổi góc cạnh.** Khi một đầu cạnh được dịch và đầu kia giữ, hướng cạnh nói chung thay đổi. Nếu yêu cầu giữ góc, yêu cầu đó phải có trong hệ ràng buộc và được kiểm sau giải. Một đoạn cắt qua cửa sổ nhưng cả hai đầu đều ngoài không tự sinh một đỉnh ở giao điểm để kéo. Cửa sổ cũng cần chỉ rõ hệ tọa độ và quy tắc xử lý điểm trên biên. Autodesk mô tả chọn crossing có đầu mút/đỉnh bên trong; đối tượng hoàn toàn trong crossing được move. [Nguồn Autodesk](https://help.autodesk.com/cloudhelp/2018/ENU/AutoCAD-Core/files/GUID-1632A4D6-FAA4-4EA3-B133-098F88CC2766.htm).

**Không sửa chữ DIM để giả lập phép đo mới.** Sau đổi geometry phải cập nhật/giữ source binding, điểm đo, DIM line/text position, native action và regen/readback. Chữ ghi đè phải được phát hiện và xử lý riêng. Kết quả hình đúng nhưng DIM mất liên kết chưa đạt yêu cầu.

## 2. Thuật toán phù hợp từng phạm vi

### Mô hình affine 2D đầu tiên

Biến là tọa độ XY của từng point ID, tất cả theo mm. Các loại hiện có:

| Loại | Phương trình |
|---|---|
| fixed(P, x0, y0) | xP=x0; yP=y0 |
| horizontal(P,Q) | yQ-yP=0 |
| vertical(P,Q) | xQ-xP=0 |
| coincident(P,Q) | xQ-xP=0; yQ-yP=0 |
| dx(P,Q,d) | xQ-xP=d có dấu |
| dy(P,Q,d) | yQ-yP=d có dấu |

Đây là ràng buộc điểm, không phải bộ hiểu LINE/CIRCLE native tổng quát. `dx`/`dy` là khoảng cách có hướng theo trục, không phải chiều dài Euclid. Mỗi ràng buộc phải có ID riêng và trạng thái explicit/confirmed/native do lớp gọi cung cấp; candidate hình học bị từ chối. Các nhãn này chưa thay thế cơ chế kiểm bằng chứng theo hash hoặc quyền chỉnh trong ứng dụng.

Mã dùng `numpy.linalg.lstsq` để giải hiệu chỉnh `A Δx = b - A x0`, lấy hạng với `rank_rcond=1e-12`, rồi tính lại residual từng phương trình, ngưỡng mặc định 1e-7 mm. NumPy mô tả least-squares hỗ trợ hệ thiếu/đủ/thừa phương trình và trả hạng, singular values; ngưỡng rcond quyết định singular values được coi bằng 0. [Nguồn NumPy lstsq](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html). Không nghịch đảo ma trận trực tiếp; không dùng phần tử `residuals` rỗng của thư viện để kết luận nghiệm đúng.

Quy trình: kiểm đầu vào → dựng A/b → giải → kiểm residual → phân loại inconsistent/underconstrained/fully_constrained. Chỉ trả `proposed_points` khi nhất quán và DOF=0. Hệ thiếu hoặc xung đột không trả geometry được chọn tùy ý. Tất cả kết quả đều `edit_authorization=false`.

### Phạm vi phi tuyến còn phải xây dựng

Khoảng cách Euclid, góc, tiếp tuyến và các tiếp xúc không affine cần mô hình riêng, Jacobian và xử lý cấu hình suy biến. `n-rank(J)` chỉ là phân tích chuyển động vi phân tại cấu hình đó, không tự chứng minh chuyển động hữu hạn hoặc nghiệm duy nhất toàn cục. Cần xét scaling, anchor, nghiệm/nhánh và vùng khả thi.

Không dùng công thức `J^-1 F` như yêu cầu tổng quát: J thường không vuông hoặc thiếu hạng. Khi xây solver phi tuyến cần phương pháp bước lặp có kiểm giảm residual và xử lý thiếu hạng. SVD cung cấp singular values và cơ sở phục vụ phân tích hạng, không tự giải quyết ý đồ thiết kế. [Nguồn NumPy SVD](https://numpy.org/doc/stable/reference/generated/numpy.linalg.svd.html).

## 3. Kiểm lại ví dụ người dùng

Bốn điểm chữ nhật tạo 8 biến. Các ràng buộc trong ví dụ: cố định v1 (2 phương trình), ngang v1-v2 (1), đứng v2-v3 (1), chiều rộng v1-v2 (1). Hạng của mô hình này là 5, còn 3 DOF. Tọa độ v4 chưa bị khống chế và chiều cao chưa xác định. Vì vậy expected_output 150×50 không suy ra duy nhất từ constraints đó; trường `allowed_stretch_directions` cũng chưa được viết thành phương trình.

Mô hình bổ sung đủ: cố định v1=(0,0); bốn cạnh ngang/đứng; dx(v1,v2)=150; dy(v1,v4)=50. Mô hình có rank=8, DOF=0 và cho (0,0),(150,0),(150,50),(0,50). Việc bổ sung được thực hiện trong mẫu tổng hợp rõ ràng, không tự gán các giả thiết này vào bản vẽ khách hàng.

## 4. Mã, dữ liệu và kết quả

- `graph/linear_point_constraints.py`: phân tích mô hình affine có giới hạn 64 điểm/256 constraint records; chưa tích hợp DWG/native/API.
- `scripts/solve_linear_point_model.py`: nhận JSON schema_version=1, units=mm, xuất kết quả; không ghi CAD.
- `tests/test_linear_point_constraints.py`: 11 trường hợp gồm rectangle, mẫu thiếu DOF, dư nhất quán, mâu thuẫn, không ràng buộc, coincident và đầu vào không hợp lệ.
- `storage/validation-fixtures/linear-point-constraints-2026-10-21/rectangle-model.json`: mẫu dữ liệu tường minh kèm expected points.
- `verification.json` cùng thư mục: kết quả đủ/thiếu/dư/xung đột; `cli-result.json`: kết quả chạy CLI mẫu.

Bộ kiểm tuyến tính và geometric candidates: 19 đạt, 7 warning thư viện, 0,40 giây. CLI mẫu đạt rank 8, DOF 0, residual lớn nhất khoảng 3,83e-14 mm. Chỉ là xác minh số học trên dữ liệu tổng hợp, chưa phải kiểm stretch DWG hoặc native round-trip.

Lệnh sử dụng:

```powershell
python scripts/solve_linear_point_model.py storage/validation-fixtures/linear-point-constraints-2026-10-21/rectangle-model.json --output storage/validation-fixtures/linear-point-constraints-2026-10-21/cli-result.json
```

## 5. Điều kiện tiếp theo trước chỉnh DWG

Liên kết point IDs với handle/vertex/source version; thu thập constraint thật và xác nhận cần thiết; định nghĩa điểm giữ và target dimension; kiểm nguồn ban đầu có thỏa constraints; giải và kiểm residual, self-intersection/cạnh suy biến/hướng; kiểm tác động qua toàn nhóm; thực hiện trên bản sao native; lưu, mở lại, evaluate, đối chiếu DIM/BOM có liên quan và vùng không sửa; nhập lại bản đã sửa để kiểm lần chỉnh tiếp. Không tự dùng candidate gần nhau làm constraint. Chưa mở quyền sửa nhóm sáu DIM hoặc đề xuất xốp chưa xác nhận bằng bộ giải mới.
