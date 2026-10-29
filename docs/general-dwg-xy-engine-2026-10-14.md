# Engine DWG dùng chung — quan hệ dịch chuyển X/Y

Phạm vi công việc là chức năng của dự án cho DWG người dùng tải lên. Không sửa thêm Dauphine hoặc file khách hàng trong đợt này. Bộ nhận diện/chọn khung được giữ nguyên.

## Thay đổi trong engine

- `graph/change_dependencies.py`: ghép các dịch chuyển vuông góc từ nhiều nguồn hoặc hai trục của cùng một nguồn. Tính theo thứ tự đồ thị, chuyển vector giữa các tọa độ instance, giữ OCS và kiểm tra lại thao tác trực tiếp. Quy tắc cũ giữ hành vi độc lập; quy tắc mới phải khai báo `composition=orthogonal`. Vòng lặp, quan hệ trùng, vector không vuông góc, sai layout, thiếu ma trận và kết quả bị sửa sai đều bị chặn.
- `graph/native_contacts.py`: bỏ giới hạn chỉ dịch một trục. Từ các mặt tiếp xúc native 2D và DIM đo thật, giải vị trí theo X/Y, cập nhật DIM cụm và tạo đủ quan hệ nguồn cho từng trục. Giữ hình dạng của chi tiết nhận khi chỉ cần dịch chuyển. Kiểm tra tiếp xúc, chồng lấn và sự đầy đủ của quy tắc trước apply/duyệt; báo cáo hình cụm không chứng nhận khi thiếu một quan hệ.
- Tích hợp vào luồng lập kế hoạch, lan truyền, validation, preview, duyệt và xuất sẵn có. Không cần model lớn hơn, mapping handle theo sản phẩm, liên kết tham số nhập thủ công hoặc công cụ trả phí cho nhóm cấu trúc này.

Đây là mở rộng bộ giải dùng chung, không phải thêm mapping cho một sản phẩm. Mã engine không dùng tên DWG, mã vật tư cố định hoặc handle fixture.

## Kiểm chứng chức năng

**840 kiểm thử Python đạt**, log `storage/validation-fixtures/pytest-general-xy-final.txt`. Các kiểm thử mới gồm nhiều nguồn dẫn động, hai trục của một nguồn, tọa độ quay, nguồn OCS, chuỗi kéo theo, block lồng nhau, POLYLINE cũ, thay đổi tỷ lệ kích thước, thiếu một quan hệ và thao tác bị sửa sai.

`scripts/verify_general_xy_dwg.py` tạo ba DWG mới với tên ngẫu nhiên để thử chức năng bằng API thật. File được upload và catalog/khung được đọc bình thường, không chèn danh mục khung hay mapping vào engine. Từ bản vẽ đã chọn, hai yêu cầu kích thước được xử lý cùng nhau; một chi tiết khác tự dịch cả hai trục theo các tiếp xúc nguồn.

| Cấu trúc | Kết quả sau sửa | Luồng hoàn tất |
| --- | --- | --- |
| LWPOLYLINE, nhiều khung | Chi tiết nhận tại (630; 130), DIM cụm 90 mm | Upload → sửa → preview → duyệt → tải DWG → ODA mở lại |
| POLYLINE cũ, kích thước ×2 | Chi tiết nhận tại (1260; 260), DIM cụm 180 mm | Như trên |
| Cụm block lồng nhau, kích thước ×0,5 | Chi tiết nhận tại (315; 65), DIM cụm 45 mm | Như trên |

Các BOM đổi đúng kích thước của hai chi tiết dẫn động; quy cách chi tiết chỉ dịch chuyển giữ nguyên. FreeCAD/OpenCASCADE kiểm tra các profile/lỗ đã sửa; nguồn không đổi. Cả ba DWG tải HTTP 200 và được đo lại sau chuyển đổi bằng ODA. Lượt kiểm thử nhỏ này mất khoảng 3,3–3,4 giây mỗi trường hợp; không dùng kết quả đó để cam kết tốc độ cho DWG lớn.

Biên nhận: `storage/validation-fixtures/general-xy-dwg-4bf549ff/receipts.json`. Đây là dữ liệu hồi quy tổng hợp chứng minh chức năng, không thay thế nghiệm thu các DWG sản xuất thực tế. Lặp lại bằng `python scripts/verify_general_xy_dwg.py` khi backend chạy cổng 8765.

## Phạm vi hiện tại và phần chưa hoàn thành

Bộ giải này cần chủ sở hữu chi tiết đã xác định, profile native 2D đo thật và mặt tiếp xúc có chiều dài trên cả hai biên. Bounding box chạm nhau hoặc cùng công đoạn chưa đủ để tự suy ra quan hệ cơ khí. Nó xử lý dịch chuyển hai trục; việc tự co/giãn mọi chi tiết nhận còn cần quy tắc kích thước/lắp ghép tương ứng. Quan hệ giữ khe hở đã xác nhận tiếp tục dùng bộ liên kết tham số chung.

Chưa chứng minh sửa đúng 100% mọi DWG. Block động/proxy/association chưa có adapter, hình thiếu chủ sở hữu hoặc mốc lắp và đường cong chưa có quan hệ xác định vẫn còn giới hạn. Mục tiêu phát triển tiếp là mở rộng các bộ giải và kiểm chứng theo cấu trúc CAD của file mới, không tiếp tục viết mapping riêng theo sản phẩm hoặc bỏ chốt kiểm tra để tạo file nhìn như đã sửa.