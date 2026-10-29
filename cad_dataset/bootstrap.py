"""Dataset configuration and ten unbound acceptance tasks; no fabricated truth."""
from pathlib import Path
from cad_dataset.models import Record, GROUPS
from cad_dataset.store import ROOT,write_json

PUBLIC_SOURCES=[
 dict(id='autodesk_mechanical',name='Autodesk Mechanical Samples',url='https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/5FT67coP41xn6vjfEgyGQo.html',priority='very_high',formats=['DWG'],access='browser_verified_download_links',rights='pending',notes='HTTP trực tiếp trả 403 nhưng trình duyệt mở được trang và xác định 12 liên kết tải chính thức, gồm bốn mẫu ưu tiên. Trang liệt kê mẫu chưa xác nhận quyền dùng cho AI/huấn luyện/chia sẻ.'),
 dict(id='autodesk_autocad',name='Autodesk AutoCAD Samples',url='https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/6XGQklp3ZcBFqljLPjrnQ9.html',priority='very_high',formats=['DWG'],access='http_403',rights='pending',notes='Chưa tải file gốc từ trang này.'),
 dict(id='engineering_cad_drawings',name='EngineeringCADDrawings',url='https://github.com/david1203d/EngineeringCADDrawings',priority='high',formats=['DWG'],access='available',rights='readme_use_modify_only',notes='README cho dùng/sửa; không có LICENSE chuẩn. Chỉ dùng đánh giá nội bộ, giữ chờ quyền huấn luyện/phân phối.'),
 dict(id='forge_designautomation',name='Autodesk Design Automation',url='https://github.com/Autodesk-Forge/learn.forge.designautomation',priority='high',formats=['DWG'],access='http_404',rights='pending',notes='Liên kết người dùng cung cấp hiện trả 404; chưa gán giấy phép hay file từ repository khác.'),
 dict(id='ldm_example_cad',name='LDM Example CAD',url='https://ldm.kisski.de/en/dataset/example-cad',priority='medium',formats=['DWG'],access='certificate_error',rights='pending',notes='Trang được lập chỉ mục ghi CC-BY và nguồn Autodesk. Chứng thư máy chủ cũ lỗi; endpoint/resource TIB công bố hiện trả 503. Không tắt kiểm tra TLS.'),
 dict(id='cadquarry',name='CadQuarry',url='https://github.com/jacobjennings/CadQuarry',priority='high',formats=['STEP','PNG','JSON'],access='available',rights='CC0-1.0_generated_data',notes='Dữ liệu sinh: DATA_LICENSE CC0; mã bộ sinh: Apache-2.0. Chỉ thu artifact dữ liệu, không chạy mã tải về. STEP chưa phải DWG hay bản vẽ chế tạo được duyệt.'),
 dict(id='cadsy',name='Cadsy Technical Drawings',url='https://huggingface.co/datasets/cadsy/cad-technical-drawings',priority='high_for_recognition',formats=['STEP','PNG','JSON'],access='available',rights='Apache-2.0_sample_and_upstream_declared',notes='Nguồn công bố 65 STEP/130 ảnh tổng hợp. Có nguồn phía trước ADSKAILab/Zero-To-CAD-100k; giữ UUID và source_row. Không có DWG trong bộ này; nhãn nguồn chưa là nhãn kỹ sư nghiệm thu.'),
]

TASKS=[
 ('linear_length','Đổi chiều dài chi tiết từ 100 thành 120 mm, giữ cạnh trái.',['geometry_length_120','left_datum_unchanged','bound_dimension_120','unaffected_geometry_unchanged']),
 ('plate_two_axes','Đổi tấm 100×60 thành 120×70 mm, giữ tâm lỗ và chiều dày.',['two_true_dimensions','hole_centers_unchanged','thickness_unchanged','bom_updated']),
 ('shaft_and_bore','Đổi đường kính trục từ 20 thành 22 mm; đồng bộ bạc lắp theo khe hở đã xác nhận.',['shaft_diameter','bore_diameter','confirmed_clearance','coaxiality']),
 ('hole_pitch','Đổi khoảng cách hai lỗ từ 40 thành 50 mm, giữ tâm nhóm lỗ.',['pitch_50','group_center_unchanged','diameters_unchanged']),
 ('wall_thickness','Đổi chiều dày hộp từ 2 thành 3 mm, giữ kích thước ngoài.',['outside_unchanged','inside_dimensions','mating_parts','bom_thickness']),
 ('multi_view','Rút ngắn thanh 20 mm; đồng bộ mọi hình chiếu và hình lắp đã gắn mã.',['all_proven_views','related_dimensions','assembly_fit','bom']),
 ('local_bom_number','Sửa chi tiết số 7 của cụm A; giữ chi tiết số 7 thuộc cụm B.',['local_bom_identity','assembly_B_unchanged']),
 ('ambiguous_datum','Tăng chiều dài chi tiết 20 mm, chưa chỉ định mốc giữ.',['clarification_required','no_geometry_written']),
 ('units_and_scale','Đổi kích thước thật thành 120 mm trên hình có tỷ lệ hoặc đơn vị khác mm.',['native_units','dimension_scale','world_geometry','no_text_only_edit']),
 ('missing_relationship','Sửa cụm có XREF/proxy hoặc liên kết lắp còn thiếu bằng chứng.',['missing_scope_reported','no_unproven_release','original_unchanged']),
]


def initialize(root=ROOT):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    write_json(root/'sources.json',dict(checked_on='2026-10-22',public_sources=PUBLIC_SOURCES,
        internal_source=dict(id='company_internal',rights='internal evaluation only; never exported by starter pack')))
    write_json(root/'targets.json',dict(target_dossiers=500,groups=[dict(id=k,name=v,target=50) for k,v in GROUPS.items()],
        counting_policy='Unique engineering-reviewed DWG dossiers, deduplicated by content and product lineage. STEP, layouts, previews and variants do not inflate the 500 target.'))
    write_json(root/'record.schema.json',Record.model_json_schema())
    write_json(root/'edit-task-templates.json',dict(ground_truth=False,templates=[dict(id=key,request_vi=text,
        status='unbound_template',record_id=None,engineer_review='pending',expected_checks=checks) for key,text,checks in TASKS]))
    (root/'README.md').write_text('''# Mechanical DWG Intelligence Dataset – V1

Mục tiêu: 500 hồ sơ DWG, 10 nhóm × 50. Đây là chỉ tiêu; xem status.json để biết số thật.

- records/: mỗi hồ sơ có CAD gốc, nguồn, revision/commit, SHA-256, giấy phép, dòng sản phẩm và split.
- assets/: file gốc và các artifact tải về/kiểm chứng; không tự chạy Python/CadQuery từ bên ngoài.
- source-evidence/: bản chụp metadata, giấy phép và lỗi truy cập nguồn.
- record.schema.json: nhãn hình chiếu/DIM/mã/BOM/mốc, quan hệ, ca sửa tiếng Việt, before/after và review.
- edit-task-templates.json: 10 mẫu nhiệm vụ CHƯA gắn đối tượng, CHƯA có đáp án kỹ sư; không tính là benchmark đã đạt.
- history/: hồ sơ cũ khi bổ sung dữ liệu, không ghi đè CAD gốc.

Trạng thái độc lập: tải file → kiểm chữ ký → đọc CAD native → gắn nhãn có bằng chứng → kỹ sư duyệt → lưu/mở DWG sau sửa và đối chiếu.
Nhãn Cadsy chỉ được nhập thành đề xuất có nguồn. STEP hợp lệ ở mức chữ ký không đồng nghĩa đã kiểm B-rep hoặc chuyển thành DWG.
Không trộn cùng sản phẩm, biến thể, hình chiếu, before/after, CAD trùng hash hoặc cùng UUID nguồn vào train/validation/test khác nhau.
Mọi split khởi tạo là unassigned; chưa tự tạo dữ liệu huấn luyện hay tinh chỉnh model.
Hồ sơ công ty chỉ tham chiếu file trong kho nội bộ, không tải lên dịch vụ ngoài và không đưa vào ZIP.
ZIP starter chỉ lấy cấu hình và dữ liệu bên ngoài có quyền phân phối được ghi rõ; không chứa record nội bộ hoặc DWG đang chờ quyền phân phối.

Lệnh từ thư mục dự án:
python -m scripts.dataset_v1 init
python -m scripts.dataset_v1 collect
python -m scripts.dataset_v1 register-company
python -m scripts.dataset_v1 inspect-dwg
python -m scripts.dataset_v1 audit
python -m scripts.dataset_v1 pack
''',encoding='utf8')
    return root
