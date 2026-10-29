"""Multi-document CAD understanding, cross-file impact analysis, and batch revision service.

Allows users to inspect, understand, plan, and apply synchronized CAD changes
across multiple DWG files simultaneously.
"""
import os
import json
import time
import uuid
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from cad.catalog import CAD_LOCK, load_document
from cad.edit_engine import digest
from backend.services import document_atlas_service as atlas
from backend.services.document_request_service import resolve, prepare as prepare_atlas
from backend.services.change_service import plan_change
from backend.services.revision_service import export_dwg, read_revision, safe_id
from backend.services.export_jobs import start as start_export_job

DOC_STORAGE = Path("storage/documents")
PROJECT_PLANS_DIR = Path("storage/project-plans")
PROJECT_EXPORTS_DIR = Path("storage/project-exports")
PROJECT_PLANS_DIR.mkdir(parents=True, exist_ok=True)
PROJECT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def list_project_documents() -> List[Dict[str, Any]]:
    """List all ready DWG documents available for multi-file analysis."""
    documents = []
    if not DOC_STORAGE.exists():
        return documents

    for d in DOC_STORAGE.iterdir():
        if not d.is_dir():
            continue
        status_file = d / "status.json"
        if not status_file.exists():
            continue
        try:
            st = json.loads(status_file.read_text(encoding="utf-8"))
            if st.get("status") != "ready":
                continue

            dwg_file = d / "original.dwg"
            size_bytes = dwg_file.stat().st_size if dwg_file.exists() else 0

            # Count sheets and parts if indexed
            sheets_file = d / "sheets-v3.json"
            sheet_count = 0
            sheet_names = []
            if sheets_file.exists():
                try:
                    sdata = json.loads(sheets_file.read_text(encoding="utf-8"))
                    items = sdata.get("items", [])
                    sheet_count = len(items)
                    sheet_names = [it.get("name") or it.get("id") for it in items[:5]]
                except Exception:
                    pass

            part_graph_file = d / "part-graph-v1.json"
            part_count = 0
            if part_graph_file.exists():
                try:
                    pdata = json.loads(part_graph_file.read_text(encoding="utf-8"))
                    part_count = len(pdata.get("nodes", []))
                except Exception:
                    pass

            documents.append({
                "id": d.name,
                "filename": st.get("filename", d.name),
                "size_bytes": size_bytes,
                "sheet_count": sheet_count,
                "part_count": part_count,
                "sample_sheets": sheet_names,
                "modified_time": st.get("modified", time.time())
            })
        except Exception:
            pass

    return sorted(documents, key=lambda x: x["filename"])


def analyze_document_for_request(document_id: str, request_text: str) -> Dict[str, Any]:
    """Inspect a single document to determine if it is affected by the user's request."""
    doc_path = DOC_STORAGE / document_id
    status_file = doc_path / "status.json"
    if not status_file.exists():
        return {"status": "error", "message": "Tài liệu không tồn tại."}

    st = json.loads(status_file.read_text(encoding="utf-8"))
    filename = st.get("filename", document_id)

    # 1. Quick sheet text search for high-confidence match
    sheets_file = doc_path / "sheets-v3.json"
    matching_sheets = []
    if sheets_file.exists():
        try:
            sdata = json.loads(sheets_file.read_text(encoding="utf-8"))
            req_words = [w.lower() for w in request_text.split() if len(w) > 2]
            for s in sdata.get("items", []):
                sname = (s.get("name") or "").lower()
                stexts = " ".join(s.get("texts", [])).lower()
                # Check for mention of detail code or keywords
                score = 0
                for w in req_words:
                    if w in sname:
                        score += 3
                    elif w in stexts:
                        score += 1
                if score >= 2 or ("chi tiết" in request_text.lower() and s.get("id") in request_text):
                    matching_sheets.append({
                        "id": s.get("id"),
                        "name": s.get("name") or f"Khung #{s.get('id')}",
                        "kind": s.get("kind"),
                        "score": score
                    })
        except Exception:
            pass

    # 2. Fast relevance pre-filter: check if document contains any numbers or keywords from request
    req_tokens = [w.lower() for w in request_text.replace(',', '.').split() if len(w) >= 2]
    req_numbers = [w for w in req_tokens if any(c.isdigit() for c in w)]
    
    # Check if doc has any candidate match in sheets, filename, or part-graph
    has_candidate_token = any(num in filename.lower() for num in req_numbers)
    if matching_sheets:
        has_candidate_token = True
    elif sheets_file.exists():
        try:
            raw_sheets_text = sheets_file.read_text(encoding="utf-8").lower()
            if any(num in raw_sheets_text for num in req_numbers):
                has_candidate_token = True
        except Exception:
            pass

    # 3. Atlas / BOM resolution (only if document has candidate tokens)
    resolution = None
    if has_candidate_token:
        try:
            job = atlas.submit(document_id)
            for _ in range(30):
                rep = atlas.read(document_id, job["id"])
                if rep.get("status") in ("ready", "failed"):
                    break
                time.sleep(0.1)

            if rep.get("status") == "ready":
                atlas_data = atlas.report(document_id, job["id"])
                resolution = resolve(atlas_data, job["id"], request_text)
        except Exception as e:
            resolution = {"status": "error", "message": str(e)}

    is_affected = False
    status_code = "unaffected"
    explanation = "Không tìm thấy chi tiết hoặc quy cách phù hợp trong bản vẽ này; giữ nguyên 100%."
    matched_targets = []
    part_codes = []

    if resolution and resolution.get("status") == "resolved":
        is_affected = True
        status_code = "affected"
        explanation = resolution.get("message") or "Đã tìm thấy chi tiết cần sửa từ hồ sơ toàn file."
        matched_targets = resolution.get("targets", [])
        part_codes = resolution.get("part_codes", [])
    elif resolution and resolution.get("status") == "needs_target":
        is_affected = True
        status_code = "potential_match"
        explanation = resolution.get("message") or "Có chi tiết trùng số thứ tự hoặc quy cách; cần xác nhận khung."
        matched_targets = resolution.get("candidates", [])
    elif matching_sheets:
        is_affected = True
        status_code = "affected"
        explanation = f"Tìm thấy {len(matching_sheets)} khung bản vẽ có tên hoặc nội dung khớp yêu cầu."
        matched_targets = [{"id": s["id"], "kind": "sheet", "name": s["name"]} for s in matching_sheets]

    return {
        "document_id": document_id,
        "filename": filename,
        "is_affected": is_affected,
        "status": status_code,
        "explanation": explanation,
        "matched_targets": matched_targets,
        "part_codes": part_codes,
        "matching_sheets": matching_sheets,
        "evidence": resolution.get("evidence") if resolution else None,
        "raw_resolution": resolution
    }


def analyze_project(document_ids: Optional[List[str]], request_text: str) -> Dict[str, Any]:
    """Scan and analyze an engineering request across multiple DWG documents in parallel."""
    if not document_ids:
        docs = list_project_documents()
        document_ids = [d["id"] for d in docs]

    affected = []
    unaffected = []
    total = len(document_ids)

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(analyze_document_for_request, doc_id, request_text): doc_id for doc_id in document_ids}
        for f in futures:
            try:
                res = f.result()
                if res.get("is_affected"):
                    affected.append(res)
                else:
                    unaffected.append(res)
            except Exception as e:
                pass

    # Sort affected files so best matches appear first
    affected.sort(key=lambda x: (x.get("status") != "affected", x.get("filename")))
    unaffected.sort(key=lambda x: x.get("filename"))

    summary_msg = (
        f"AI đã phân tích {total} file DWG trong dự án. "
        f"Phát hiện {len(affected)} file DWG chứa chi tiết cần sửa đổi, "
        f"{len(unaffected)} file DWG còn lại không bị tác động và giữ nguyên 100%."
    )

    return {
        "request": request_text,
        "total_documents_scanned": total,
        "affected_count": len(affected),
        "unaffected_count": len(unaffected),
        "summary": summary_msg,
        "affected_documents": affected,
        "unaffected_documents": unaffected
    }


def plan_project_changes(document_ids: List[str], request_text: str) -> Dict[str, Any]:
    """Generate synchronous change plans for all affected documents in the project."""
    analysis = analyze_project(document_ids, request_text)
    affected = analysis["affected_documents"]

    if not affected:
        return {
            "status": "no_changes_needed",
            "message": "Không tìm thấy file DWG nào trong dự án chứa chi tiết yêu cầu.",
            "plans": []
        }

    project_plan_id = uuid.uuid4().hex

    def _plan_single(item):
        doc_id = item["document_id"]
        fname = item["filename"]
        targets = item["matched_targets"]
        evidence = item.get("evidence")

        try:
            plan = plan_change(doc_id, targets, request_text, document_reading=evidence)
            return {
                "document_id": doc_id,
                "filename": fname,
                "plan_id": plan.get("id"),
                "status": "planned",
                "summary": plan.get("plan", {}).get("summary", ""),
                "operations_count": len(plan.get("plan", {}).get("operations", [])),
                "plan_data": plan
            }
        except Exception as e:
            return {
                "document_id": doc_id,
                "filename": fname,
                "status": "plan_error",
                "error": str(e)
            }

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as executor:
        plans = list(executor.map(_plan_single, affected))

    result = {
        "project_plan_id": project_plan_id,
        "request": request_text,
        "plans": plans,
        "created_at": time.time()
    }

    # Save project plan
    plan_path = PROJECT_PLANS_DIR / f"{project_plan_id}.json"
    plan_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def apply_project_changes(project_plan_id: str) -> Dict[str, Any]:
    """Apply the project change plan across all affected DWGs, export full files, and bundle ZIP."""
    plan_path = PROJECT_PLANS_DIR / f"{project_plan_id}.json"
    if not plan_path.exists():
        raise ValueError("Không tìm thấy kế hoạch dự án đa file.")

    pdata = json.loads(plan_path.read_text(encoding="utf-8"))
    plans = pdata.get("plans", [])
    request_text = pdata.get("request", "")

    from backend.services.revision_service import apply_plan
    from backend.services.checked_preview_service import apply as apply_checked_preview

    batch_id = uuid.uuid4().hex
    applied_results = []
    dwg_files_to_zip = []

    for item in plans:
        if item.get("status") != "planned":
            continue

        doc_id = item["document_id"]
        fname = item["filename"]
        plan_id = item["plan_id"]

        try:
            with CAD_LOCK:
                # 1. Apply revision (support both checked preview plans and full plans)
                rev = None
                try:
                    rev = apply_checked_preview(doc_id, plan_id)
                except Exception:
                    rev = apply_plan(doc_id, plan_id)
                rev_id = rev["id"]

                # 2. Export full DWG (scope='document' ensures 100% CAD & block preservation)
                dwg_path = export_dwg(doc_id, rev_id, require_approval=False, scope="document")

            # 3. Create public download URL
            dwg_url = f"/documents/{doc_id}/revisions/{rev_id}/exports"
            
            # File for ZIP archive
            clean_name = f"[DA_SUA]_{Path(fname).stem}.dwg"
            dwg_files_to_zip.append((dwg_path, clean_name))

            applied_results.append({
                "document_id": doc_id,
                "filename": fname,
                "revision_id": rev_id,
                "status": "success",
                "dwg_path": str(dwg_path),
                "clean_filename": clean_name,
                "file_size": dwg_path.stat().st_size,
                "download_url": f"/documents/{doc_id}/revisions/{rev_id}/export"
            })
        except Exception as e:
            applied_results.append({
                "document_id": doc_id,
                "filename": fname,
                "status": "failed",
                "error": str(e)
            })

    # 4. Create ZIP package
    zip_filename = f"DU_AN_AI_CAD_{batch_id[:8]}.zip"
    zip_path = PROJECT_EXPORTS_DIR / zip_filename
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add changelog report
        report_content = f"# BÁO CÁO THAY ĐỔI DỰ ÁN AI CAD\n\n"
        report_content += f"Yêu cầu: {request_text}\n"
        report_content += f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        report_content += f"## Danh sách file DWG đã chỉnh sửa & đồng bộ:\n\n"
        for res in applied_results:
            if res.get("status") == "success":
                report_content += f"- **{res['clean_filename']}** (Gốc: `{res['filename']}`): {res['file_size']:,} bytes\n"
            else:
                report_content += f"- **{res['filename']}**: Thất bại ({res.get('error')})\n"
        zf.writestr("BAO_CAO_THAY_DOI.md", report_content.encode("utf-8"))

        # Add all exported DWG files
        for src_dwg, zip_name in dwg_files_to_zip:
            if src_dwg.exists():
                zf.write(src_dwg, arcname=zip_name)

    return {
        "batch_id": batch_id,
        "project_plan_id": project_plan_id,
        "request": request_text,
        "results": applied_results,
        "archive": {
            "filename": zip_filename,
            "size_bytes": zip_path.stat().st_size,
            "download_url": f"/project/download-archive/{batch_id}"
        }
    }


def get_project_archive_path(batch_id: str) -> Path:
    """Return the absolute path of the generated ZIP archive."""
    clean_id = safe_id(batch_id)
    candidates = list(PROJECT_EXPORTS_DIR.glob(f"*{clean_id[:8]}*.zip"))
    if not candidates:
        raise FileNotFoundError("Không tìm thấy tệp lưu trữ dự án.")
    return candidates[0]
