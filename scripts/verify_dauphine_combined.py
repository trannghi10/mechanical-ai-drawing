"""Publish a checked customer preview through the normal revision/export gates.

The remaining assembly/forming/foam work is preserved as blocking review.
"""
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding='utf8')
from verify_dauphine_laser_group import context
from backend.services import catalog_service as storage
from backend.services.compound_planner import compile_bundle
from backend.services.change_service import validate_plan
from graph.packaging_fit import synchronize, review as packing_review
from graph.drawing_sync import assembly_sync_review
from backend.services.curved_wall_service import review as forming_review
from cad.edit_engine import digest


def main():
    started = time.monotonic()
    source, c = context()
    document_id = '34ee84f35e1a44fb81c56044397a0fff'
    request = ('Mã 8.1.05417.258 chiều cao từ 724 thành 697 mm, giữ đáy; '
        'Tất cả liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1 mm')
    print('Compiling source-measured height and all 12 laser parts', flush=True)
    plan, audit = compile_bundle(c, request)
    assert plan is not None and not plan.questions, audit
    print('Synchronizing measured packing envelope', flush=True)
    plan = synchronize(plan, c)
    validate_plan(plan, c)
    assembly = assembly_sync_review(plan, c)
    packing = packing_review(plan, c)
    forming = forming_review(plan, c)
    pending = ['Còn liên kết hình cụm, chiều cao các chi tiết lắp bên trong và các khung công đoạn chưa đồng bộ đầy đủ.',
        'Còn các lớp đệm/hình tách rời đóng gói.']
    if any(r['status']!='verified_source_calibrated_blank' for r in forming):pending.append('Còn kiểm chứng phôi uốn.')
    plan_id = uuid.uuid4().hex
    full = plan.model_copy(deep=True)
    full.questions = pending
    full.operations = []
    proposal = dict(id=plan_id, document_id=document_id, status='proposal_only', request=request,
        customer_goal='Thành phẩm Dauphine 700 mm; khung 697 mm, giữ đáy; mọi tấm laser 1,5 → 1 mm; đóng gói vừa sản phẩm.',
        source_hash=c['source_hash'], targets=c['targets'], target_ids=[t['id'] for t in c['targets']],
        root_target_ids=c['root_target_ids'], root_bom_refs=c['root_bom_refs'], review_only_ids=[], scope_links=[],
        impact_graph=c['part_graph'], request_review=audit, provider='checked_cad', model='source_geometry',
        planner='checked_atomic_compound', plan=full.model_dump(), execution_available=False,
        checked_preview_plan=plan.model_dump(), preview_execution_available=True,
        packaging_review=packing, forming_review=forming, drawing_sync=assembly,
        message='Bản xem trước có các thao tác CAD đã kiểm chứng; chưa phải backup hoàn chỉnh toàn sản phẩm.')
    folder = storage.folder(document_id)
    storage.write_json(folder/'change-plans'/(plan_id+'.json'), proposal)
    return export_checked_preview(document_id, plan_id, source, c, plan, audit, assembly, packing, forming, started)


def export_checked_preview(document_id, plan_id, source, c, plan, audit, assembly, packing, forming, started,
                           backup_name='Dauphine-PREVIEW-12tam-laser1-cao697-thung823.dwg'):
    # Run the same independent kernel, source/hash, and download gates as UI.
    os.environ['CAD_AUTO_PRE_EXPORT'] = '0'
    from backend.services.checked_preview_service import apply
    print('Applying checked partial revision and independent FreeCAD verification', flush=True)
    revision = apply(document_id, plan_id)
    from backend.services.export_jobs import start, status, download
    print('Exporting and validating DWG roundtrip', flush=True)
    job = start(document_id, revision['id'], format='dwg', scope='selection', preview=True)
    while job['status'] in ('queued', 'running'):
        time.sleep(1)
        job = status(document_id, revision['id'], job['id'])
    assert job['status'] == 'ready', job
    dwg, name = download(document_id, revision['id'], job['id'])
    target = Path('storage/backups')/backup_name
    shutil.copy2(dwg, target)
    assert digest(target) == digest(dwg)
    from backend.services.revision_service import revision_preview, approve
    svg = revision_preview(document_id, revision['id'], '3E5E8C')
    try:
        approve(document_id, revision['id'])
    except ValueError as error:
        approval_block = str(error)
    else:
        raise AssertionError('A partial customer preview must not be approved as complete')
    out = Path('storage/validation-fixtures/dauphine-combined')/revision['id']
    out.mkdir(parents=True, exist_ok=True)
    (out/'packing-after.svg').write_text(svg, encoding='utf8')
    from cad.vision import rasterize_svg
    (out/'packing-after.png').write_bytes(rasterize_svg(svg, width=1500))
    receipt = dict(document_id=document_id, plan_id=plan_id, revision_id=revision['id'], job=job,
        dwg=str(target.resolve()), dwg_hash=digest(target), source_unchanged=digest(source) == c['source_hash'],
        source_hash=c['source_hash'], complete_product_backup=False, complete_packaging=False,
        changed_entities=len(plan.operations), edited_part_codes=sorted({r.part_code for r in plan.resize_recipes}),
        curved_sections=len(plan.curved_wall_recipes), measured_dimensions=len(plan.resize_recipes),
        source_frame_count=len(c['targets']), parsed_entities=len(c['entities']), request_review=audit,
        drawing_sync=assembly, packaging_review=packing, forming_review=forming,
        independent_kernel=revision['solid_validation'], partial_approval_block=approval_block,
        elapsed_seconds=round(time.monotonic()-started, 3))
    storage.write_json(out/'receipt.json', receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('drawing_sync', 'packaging_review', 'forming_review', 'request_review', 'independent_kernel')},
        ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 2:
        from backend.services.change_service import DrawingChangePlan
        started = time.monotonic()
        source, c = context()
        doc = '34ee84f35e1a44fb81c56044397a0fff'
        proposal = json.loads((storage.folder(doc)/'change-plans'/(sys.argv[1]+'.json')).read_text(encoding='utf8'))
        export_checked_preview(doc, proposal['id'], source, c, DrawingChangePlan.model_validate(proposal['checked_preview_plan']),
            proposal['request_review'], proposal['drawing_sync'], proposal['packaging_review'], proposal['forming_review'], started)
    else:
        main()
