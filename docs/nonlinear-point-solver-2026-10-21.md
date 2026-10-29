# Bộ giải phi tuyến 2D: phạm vi và bằng chứng

Ngày 21/10/2026. Đã đọc yêu cầu người dùng về non-linear solver, generalized stretch, bulge và JSON chữ nhật đủ ràng buộc. Triển khai đầu tiên là bộ giải mô hình điểm tường minh, chưa phải adapter stretch DWG.

## Thuật toán đã dùng

`graph/nonlinear_point_constraints.py` dùng SciPy `least_squares(method=trf, jac=3-point, loss=linear)`. Jacobian được xấp xỉ sai phân trung tâm ba điểm, chưa phải Jacobian giải tích. Chọn trust-region thay cho vòng Newton cập nhật toàn bước trong mẫu để có cơ chế điều khiển bước. Tài liệu SciPy mô tả thuật toán tìm cực tiểu cục bộ và phương án Jacobian này. Không coi optimizer.success là bằng chứng các phương trình đều thỏa. [Nguồn SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html).

Luồng: kiểm schema/tham chiếu/trạng thái → dựng residual có đơn vị → kiểm cấu hình nguồn không suy biến → giải có giới hạn → tính lại mọi residual → SVD Jacobian đã chuẩn hóa → phân loại. Cần đồng thời điều kiện dừng thành công, mọi residual trong ngưỡng và local_linearized_dof=0 mới trả proposed_points. Kết quả luôn edit_authorization=false, global_uniqueness_proven=false.

Hết max_nfev trả not_converged. Dừng tại cực tiểu nhưng residual vượt ngưỡng trả unsatisfied, không kết luận vô nghiệm toàn cục. Thiếu hạng trả locally_underconstrained. Các trạng thái này không trả geometry. Cấu hình ban đầu có vector hướng/độ dài bằng 0 bị từ chối; nếu gặp suy biến trong bước thử, trả degenerate_geometry thay vì tiếp tục dùng mẫu số bị kẹp giả tạo.

## Ràng buộc được hỗ trợ

Biến: tối đa 32 điểm XY theo mm; tối đa 128 constraint records, ID riêng. Trạng thái input phải explicit/confirmed/native, không nhận candidate. Nhãn trạng thái do caller đưa vào chưa thay thế kiểm bằng chứng hay quyền chỉnh sửa trên DWG.

- fixed: khóa XY một điểm; horizontal/vertical; dx/dy có dấu; coincident hai điểm.
- distance: `norm(Q-P)-L`, L>0. Dùng residual mm để tránh trộn trực tiếp sai số mm² của phương trình bình phương với sai số mm.
- angle: góc có hướng từ vector P1-P0 đến P3-P2; value là radian trong [-pi,pi], residual wrap chu kỳ 2pi.
- parallel/perpendicular: hai vector không suy biến; residual góc không định hướng có chu kỳ pi. Chúng không cố định chiều dài hoặc tự bảo đảm điểm không đảo thứ tự.
- tangent_line: ba point IDs gồm đầu đường a,b và tâm tròn c; value là bán kính cố định >0, side bắt buộc -1/+1. Residual là khoảng cách có dấu đến đường vô hạn trừ side×R. Chưa hỗ trợ tiếp xúc đoạn hữu hạn, bán kính biến thiên, tròn–tròn hoặc cung có giới hạn góc.

Mỗi phương trình ghi residual, đơn vị và tolerance. Mặc định khoảng cách 1e-7 mm, góc 1e-8 rad; chuẩn hóa theo tolerance trước tối ưu. Rank dùng rcond=1e-8 trên Jacobian đã chuẩn hóa, kết quả có singular values. Đây là hạng số tại nghiệm và phụ thuộc scaling/ngưỡng; không phải chứng minh đại số hoặc chuyển động hữu hạn. Không trộn ngưỡng góc và mm thành một tổng sai số không có quy ước đơn vị.

## Chữ nhật trong tài liệu người dùng

Mẫu mới đã bổ sung đủ quan hệ ngang, vuông góc, hai cặp song song, chiều rộng và chiều cao cùng anchor. Đã tạo mô hình tương đương theo schema nội bộ: anchor=(0,0), bottom horizontal, right perpendicular, top/left parallel, dx(a,b)=150, dy(b,c)=50. Chạy từ hình 100×50 cho ra (0,0),(150,0),(150,50),(0,50) trong dung sai, hạng Jacobian 8, DOF tuyến tính hóa 0.

Tên uppercase/entities/target_coordinate/current_value trong JSON đính kèm chưa được nhận trực tiếp bởi CLI; fixture đã chuyển đổi tường minh. Không chỉ tin trường dof_analysis.total_system_dof=0 do input khai báo. Nếu đổi DIM_X thì phải thay phương trình width mục tiêu thay vì giữ cả 100 và thêm 150 gây xung đột. Các dữ liệu này là mẫu tổng hợp, không phải nhận dạng tự động từ DWG khách hàng.

## Những phần stretch/bulge chưa được mở

Chưa tự sinh crossing window hoặc vector từ chữ DIM. Phải lấy hình học đo thật, hướng và anchor, không suy từ nhãn DIM. Các điểm trên biên cần quy ước chọn rõ; đoạn cắt cửa sổ không tự tạo đỉnh nội suy. Phần ngoài cửa sổ được giữ theo thao tác đã chọn không có nghĩa tất cả đều là datum cơ khí.

Bulge=tan(theta/4) chưa đủ để tính cung sau sửa: cần xác định giữ bán kính, góc ở tâm, tâm hay tiếp tuyến, cùng phía/nhánh cung. Cùng hai đầu mút có nhiều cung khả thi; nếu giữ bán kính R thì chord mới phải không vượt 2R. Không cập nhật bulge bằng một giá trị suy đoán. Chưa ghi polyline cung hay cập nhật native DIM/action từ bộ giải này.

## Kiểm chứng và dữ liệu tái lập

Mã: `graph/nonlinear_point_constraints.py`; CLI: `scripts/solve_nonlinear_point_model.py`. Thêm dependency `scipy>=1.15,<2`; phiên bản môi trường đã chạy 1.15.3.

`storage/validation-fixtures/nonlinear-point-constraints-2026-10-21/` chứa ba model/result: distance-angle, tangent-line, rectangle. Tất cả đạt local_solution và DOF tuyến tính hóa 0. Residual chuẩn hóa lớn nhất của mẫu rectangle khoảng 1,23e-8 (ngưỡng chấp nhận 1); không được gọi con số chuẩn hóa đó là mm.

13 kiểm thử nonlinear cộng 19 bài affine/geometric candidates: **32 đạt, 7 warning thư viện, 0,50 giây**. Kiểm thiếu ràng buộc, hai chiều dài mâu thuẫn, max_nfev=1, hướng suy biến, candidate, thiếu tangent side, giá trị âm/nonfinite, ID trùng và tham chiếu sai. Chưa có kiểm native round-trip DWG cho solver này. Không thay thế kết quả probe dịch nhóm polyline–6 DIM trước đó.

```powershell
python scripts/solve_nonlinear_point_model.py storage/validation-fixtures/nonlinear-point-constraints-2026-10-21/rectangle-model.json --output storage/validation-fixtures/nonlinear-point-constraints-2026-10-21/cli-result.json
```

Bước tiếp theo cần liên kết point/constraint với version/hash và vertex của DWG, kiểm source model, nghiệm nhánh/hướng, geometry tự cắt/cạnh suy biến, native binding cùng readback trước khi mở một phép stretch cụ thể. Không có customer revision được tạo; đề xuất xốp chưa xác nhận vẫn giữ nguyên.
