# Mechanical DWG Intelligence Dataset – V1 — 22/10/2026

Đã triển khai bộ dữ liệu vào dự án, gồm sổ hồ sơ, schema nhãn/quan hệ/ca sửa, bộ thu thập, kiểm nguồn/hash/giấy phép, kiểm rò rỉ split, nhập CAD local và màn hình `/dataset`. **500 hồ sơ là chỉ tiêu, chưa thu thập hoặc nghiệm thu đủ 500 hồ sơ.**

## Đợt dữ liệu đầu

| Nguồn | Hồ sơ đã đăng ký | Nội dung / trạng thái |
|---|---:|---|
| Autodesk Mechanical Samples | 12 | DWG gốc từ các liên kết chính thức; đã kiểm chữ ký/hash. Giữ cách ly chờ xác minh quyền dùng cho AI, benchmark và phân phối. Chưa chạy nhập native trên các file này. |
| EngineeringCADDrawings | 4 | DWG đã mở bằng AutoCAD local trên bản sao, đọc DXF, nguồn giữ nguyên. README cho dùng/sửa nhưng chưa có LICENSE chuẩn; chỉ ghi nhận đánh giá nội bộ, chưa cho huấn luyện/chia sẻ. |
| CadQuarry | 10 | STEP cùng params/meta thuộc 10 family; dữ liệu sinh theo DATA_LICENSE CC0-1.0. Chưa kiểm B-rep, chưa chuyển thành DWG. Không tải/chạy chương trình Python của nguồn. |
| Cadsy | 3 | 3 STEP, 6 ảnh ISO/ASME, 6 file nhãn nguồn và UUID/source_row. Nguồn công bố Apache-2.0 cho sample và nguồn phía trước; giữ bản giấy phép/dataset card. |
| Công ty | 4 | Tham chiếu các file đã có trong kho nội bộ, không sao chép ra gói phân phối. Quyền đánh giá cục bộ; không tự suy quyền huấn luyện hoặc chia sẻ. |
| **Tổng** | **33** | **20 DWG gốc khác nhau và 13 STEP**. |

Có **378 nhãn ảnh Cadsy** được nhập thành đề xuất có bounding box nguồn. **0 quan hệ cơ khí đã gắn trong registry, 0 ca sửa có đáp án kỹ sư, 0 hồ sơ sẵn sàng huấn luyện, 0/500 hồ sơ nghiệm thu**. Không chạy huấn luyện hoặc tinh chỉnh model trong đợt này.

10 mẫu nhiệm vụ trong `edit-task-templates.json` chưa gắn đối tượng/đáp án. `annotation-queue.json` là hàng đợi 33 hồ sơ chờ kỹ sư; bốn mẫu Autodesk người dùng chỉ định được ưu tiên đầu. Đây không phải tác vụ đã gửi cho người khác, nhãn đã duyệt hoặc kết quả benchmark.

## Nguồn đã kiểm

- [Autodesk Mechanical Samples](https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/5FT67coP41xn6vjfEgyGQo.html): HTTP trực tiếp trả 403 nhưng trình duyệt mở được trang. Đã ghi nhận và tải 12 liên kết `download.autodesk.com`, gồm Drive_shaft, Gear Pump Subassy, GRIPPER ASSEMBLY NEW và Trolley_Structure. Tiêu đề trang ghi 2023, URL thư mục tải ghi 2020; registry giữ hash bytes làm phiên bản thực, không suy phiên bản DWG từ tên trang.
- [Autodesk AutoCAD Samples](https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/6XGQklp3ZcBFqljLPjrnQ9.html): lượt HTTP trực tiếp trả 403; chưa thu file từ nguồn này.
- [EngineeringCADDrawings](https://github.com/david1203d/EngineeringCADDrawings): commit `9eb40d9652f1e006c88eb200371f50041e331a6f`; bốn DWG được giữ đúng nguồn.
- [Forge repository người dùng cung cấp](https://github.com/Autodesk-Forge/learn.forge.designautomation): API hiện trả 404, chưa thu mẫu hoặc gán giấy phép từ repository khác.
- [LDM Example CAD](https://ldm.kisski.de/en/dataset/example-cad): host cũ lỗi chứng thư; endpoint/resource TIB được công bố trả 503 trong lần thử. Không tắt TLS. Trang được lập chỉ mục ghi CC-BY và nguồn Autodesk; chưa xem đây là xác minh quyền huấn luyện/chia sẻ cho file gốc.
- [CadQuarry](https://github.com/jacobjennings/CadQuarry): commit `543b067ea9e416bc2e9587cb8775e012480b70ee`; phân biệt [DATA_LICENSE](https://github.com/jacobjennings/CadQuarry/blob/543b067ea9e416bc2e9587cb8775e012480b70ee/DATA_LICENSE) cho dữ liệu sinh và giấy phép mã nguồn. Một lượt kiểm lại cây metadata bị ngắt tải; bản metadata đã tải thành công trước đó và commit/file hash được giữ nguyên.
- [Cadsy](https://huggingface.co/datasets/cadsy/cad-technical-drawings): revision `01a38048c5eaf09b777d7929df8e3c8a03e36965`; tải 3 trong số 65 model nguồn công bố. Giữ quan hệ nguồn [Zero-To-CAD-100k](https://huggingface.co/datasets/ADSKAILab/Zero-To-CAD-100k), không tách hai profile ISO/ASME thành hai hồ sơ độc lập.

Các trạng thái quyền là ghi nhận bằng chứng do nguồn công bố hoặc phạm vi nội bộ đã được cho phép; không phải kết luận pháp lý cho mọi mục đích. 12 DWG Autodesk chưa qua cổng quyền sử dụng; 4 DWG Engineering chưa được đưa vào training/ZIP. Các file này vẫn nằm trong kho cục bộ để xử lý bước xác minh tiếp theo.

## Chất lượng thực tế phát hiện

Bốn DWG EngineeringCADDrawings mở được nhưng kết quả đọc có **0 đối tượng DIMENSION native**. Không lấy chữ/nét kích thước nếu có làm bằng chứng đã có DIM liên kết. Các file vẫn có thể phục vụ đọc hình sau gắn nhãn, nhưng chưa là benchmark sửa DIM native. Bản đọc có lần lượt 138, 145, 229 và 175 thực thể theo vị trí đặt.

STEP được kiểm chữ ký Part 21; kiểm này không chứng minh B-rep hợp lệ, kích thước đúng ý đồ hoặc đã có bản vẽ chế tạo. Nhãn ảnh tổng hợp không tự trở thành liên kết DIM/vertex native hoặc đáp án kỹ sư. Mô hình dữ liệu cố tình giữ các trạng thái đó độc lập.

## Cấu trúc và sử dụng

Kho dữ liệu: `storage/datasets/mechanical-dwg-v1/`.

- `sources.json`, `source-audit.json`, `source-evidence/`: nguồn, commit, giấy phép, snapshot và lỗi truy cập.
- `targets.json`: 10 nhóm × 50, tách chỉ tiêu khỏi số nghiệm thu.
- `record.schema.json`, `records/`: CAD gốc, hash, nguồn, dòng sản phẩm, quyền, nhãn, quan hệ, ca sửa và review.
- `assets/`: CAD/STEP/ảnh/nhãn/params/meta và bản đọc native; không ghi đè CAD gốc.
- `history/`: hồ sơ cũ khi bổ sung metadata/nhãn, dùng hash phiên bản để tránh ghi đè âm thầm.
- `edit-task-templates.json`, `annotation-queue.json`: công việc chờ gắn dữ liệu và nghiệm thu.
- `native-ingestion-report.json`, `status.json`, `release-verification.json`: kết quả đọc/kiểm và bằng chứng phát hành starter.

Từ thư mục dự án:

```powershell
python -m scripts.dataset_v1 init
python -m scripts.dataset_v1 source-audit
python -m scripts.dataset_v1 collect
python -m scripts.dataset_v1 register-company
python -m scripts.dataset_v1 inspect-dwg
python -m scripts.dataset_v1 audit
python -m scripts.dataset_v1 pack
```

`collect` dùng metadata đã lưu hoặc kiểm nguồn khi thiếu. Các liên kết Autodesk được lấy từ snapshot quan sát trang chính thức; không đoán URL. Nhập native luôn chọn AutoCAD local, không dùng backend cloud mặc định. Tác vụ CAD chạy trong kho tài liệu với bản sao, snapshot nguồn và plugin hiện có. Hồ sơ dataset được đánh dấu phụ trợ để không làm đầy thư viện làm việc thường ngày.

Schema yêu cầu nhãn/quan hệ có bằng chứng, review có người thực hiện/thời điểm/báo cáo kỹ sư, ca lưu/mở DWG có after DWG và artifact kiểm chứng. Đây là hợp đồng dữ liệu, **chưa phải hệ thống đăng nhập/xác thực kỹ sư hoặc cơ chế tự phát hành sản xuất**. API trang dataset chỉ đọc; không có nút tự duyệt nhãn hoặc cấp phép training.

Mọi split đang `unassigned`. Bộ kiểm phát hiện cùng leakage group, lineage hoặc cùng bytes CAD trước/sau xuất hiện ở nhiều split. Còn cần kỹ sư xác định dòng sản phẩm/chủ sở hữu chung để ngăn biến thể và chi tiết của cùng cụm rò rỉ mà chỉ hash không phát hiện được.

## ZIP và bằng chứng kiểm tra

`mechanical-dwg-v1-starter.zip` chứa cấu hình/schema/10 task template và **13 hồ sơ STEP sinh có quyền phân phối đã ghi nhận**: 13 STEP, 6 PNG cùng nhãn/params/meta/giấy phép. Gói có 71 mục, khoảng 2,12 MB. **Không chứa DWG công ty, 12 DWG Autodesk chờ quyền hoặc 4 DWG Engineering chưa có quyền phân phối rõ. Vì vậy ZIP hiện không chứa DWG.**

Tải qua `/dataset/starter.zip` đã kiểm trên trình duyệt, so hash với gói gốc và kiểm từng asset trong ZIP. Tất cả 33 record qua kiểm file/hash; không phát hiện rò rỉ split. Bốn DWG công ty giữ nguyên hash, PostgreSQL đang kết nối. Không gửi CAD công ty ra cloud.

31 kiểm Python dataset đạt; 18 kiểm atlas đạt ở lượt tập trung liên quan. 12 script giao diện đạt, gồm kiểm mới về số mục tiêu/số nghiệm thu, nhãn chờ duyệt, training gate, text nguồn và phản hồi tìm kiếm cũ. Không chạy lại toàn bộ Python test suite của dự án. Giao diện thật đã kiểm số liệu, tìm kiếm và tải ZIP.

Tiếp theo cần hoàn thiện quyền dùng của các nguồn DWG, gắn nhãn trên các hồ sơ đại diện, tạo ca sửa liên động có đối tượng/mốc/đáp án thật, rồi kỹ sư đối chiếu before/after và báo cáo lưu/mở DWG. Chưa dùng số file tải về để chứng nhận engine sửa đúng mọi bản vẽ.
