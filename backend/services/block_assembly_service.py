"""Block assembly and spatial part role engine for mechanical drawings.

Identifies each part/block in the product, computes its placement, bounding box,
and spatial position in the assembly, infers its mechanical role (base, cover,
stiffener/brace, bracket, panel), and maps its contacts and detail drawing sheets.
"""
import copy
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from cad.catalog import CAD_LOCK, load_document
from cad.frame_geometry import world
from bom.reader import plain, normalized, part_number_key
from backend.services import catalog_service as storage
from backend.services.part_graph_service import document_graph

VERSION = 2


def get_block_assembly(document_id: str) -> Dict[str, Any]:
    folder = storage.folder(document_id)
    status = storage.read_status(document_id)
    if status.get("status") != "ready":
        raise ValueError("File chưa đọc xong; vui lòng chờ hoặc mở lại file.")

    cache_file = folder / "block-assembly-v1.json"
    source_hash = status.get("source_hash") or ""
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf8"))
            if cached.get("version") == VERSION and (not source_hash or cached.get("source_hash") == source_hash):
                return cached
        except Exception:
            pass

    graph = document_graph(document_id)
    sheets_file = folder / "sheets-v3.json"
    sheets_data = json.loads(sheets_file.read_text(encoding="utf8")) if sheets_file.exists() else {"items": []}
    sheets = sheets_data.get("items", [])

    assembly = analyze_block_assembly(folder, status, graph, sheets)
    storage.write_json(cache_file, assembly)
    return assembly


def analyze_block_assembly(folder: Path, status: Dict[str, Any], graph: Dict[str, Any], sheets: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes = {n["code"]: n for n in graph.get("nodes", [])}
    drawing_rows = graph.get("drawing_rows", {})
    frame_groups = drawing_rows.get("frame_groups", [])
    structure = graph.get("assembly_structure", {})
    assemblies = structure.get("assemblies", [])

    by_sheet = {s["id"]: s for s in sheets}
    part_occurrences: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    part_detail_sheets: Dict[str, List[str]] = defaultdict(list)
    for code, node in nodes.items():
        part_occurrences[code].extend(node.get("bom_occurrences", []))
        part_detail_sheets[code].extend(node.get("detail_sheets", []))

    # Build marker index: (sheet_id, label) -> marker
    marker_map: Dict[tuple, Dict[str, Any]] = {}
    for fg in frame_groups:
        for m in fg.get("markers", []):
            for sid in m.get("sheet_ids", []):
                marker_map[(sid, part_number_key(m.get("label", "")))] = m

    # Find the main assembly frame(s) with the richest BOM
    assembly_sheets = []
    for asm in assemblies:
        for sid in asm.get("scope_ids", []):
            if sid in by_sheet:
                assembly_sheets.append((len(asm.get("members", [])), sid, asm))
    assembly_sheets.sort(key=lambda x: x[0], reverse=True)

    primary_assembly_sheet_id = assembly_sheets[0][1] if assembly_sheets else (sheets[0]["id"] if sheets else None)
    primary_sheet = by_sheet.get(primary_assembly_sheet_id) if primary_assembly_sheet_id else None

    # Calculate overall assembly bounding box
    asm_bbox = primary_sheet.get("bbox") if primary_sheet else None
    if asm_bbox:
        asm_xmin, asm_ymin, asm_xmax, asm_ymax = asm_bbox
        asm_w = max(1.0, asm_xmax - asm_xmin)
        asm_h = max(1.0, asm_ymax - asm_ymin)
    else:
        asm_xmin, asm_ymin, asm_xmax, asm_ymax = 0, 0, 1000, 1000
        asm_w, asm_h = 1000, 1000

    parts_result = []
    placed_positions = []

    # Map each part node into an assembly component
    for code, node in sorted(nodes.items(), key=lambda x: (x[1].get("bom_occurrences", [{}])[0].get("part_number", "999"))):
        occurrences = node.get("bom_occurrences", [])
        occ = occurrences[0] if occurrences else {}
        part_num = occ.get("part_number") or ""
        desc = occ.get("description") or "Chi tiết cơ khí"
        mat = occ.get("material") or "Sắt"
        qty = occ.get("quantity_text") or "1"
        detail_sheets = sorted(set(node.get("detail_sheets", [])))

        # Find placement marker in primary or any assembly sheet
        marker = None
        marker_sid = None
        if primary_assembly_sheet_id:
            marker = marker_map.get((primary_assembly_sheet_id, part_number_key(part_num)))
            if marker:
                marker_sid = primary_assembly_sheet_id
        if not marker:
            for (sid, pkey), m in marker_map.items():
                if pkey == part_number_key(part_num):
                    marker = m
                    marker_sid = sid
                    break

        # Compute position
        pos_x, pos_y = None, None
        center = marker.get("center") if marker else None
        endpoints = marker.get("leader_endpoints") if marker else []
        if endpoints and len(endpoints[0]) >= 2:
            # The leader points directly to the part geometry!
            pos_x, pos_y = round(float(endpoints[0][0]), 2), round(float(endpoints[0][1]), 2)
        elif center and len(center) >= 2:
            pos_x, pos_y = round(float(center[0]), 2), round(float(center[1]), 2)

        # Estimate local dimensions from description or details
        dim_w, dim_h = parse_dimensions_from_desc(desc)

        # Infer role
        role_info = infer_part_role(desc, pos_x, pos_y, dim_w, dim_h, asm_ymin, asm_h, asm_xmin, asm_w, part_num)

        part_item = {
            "part_code": code,
            "part_number": part_num,
            "description": desc,
            "material": mat,
            "quantity": qty,
            "role": role_info["role"],
            "role_label": role_info["role_label"],
            "role_icon": role_info["role_icon"],
            "role_reason": role_info["role_reason"],
            "placement": {
                "sheet_id": marker_sid or primary_assembly_sheet_id,
                "sheet_name": by_sheet.get(marker_sid or primary_assembly_sheet_id, {}).get("name", "Bản vẽ lắp"),
                "position_x": pos_x,
                "position_y": pos_y,
                "estimated_width_mm": dim_w,
                "estimated_height_mm": dim_h,
                "has_leader_location": bool(endpoints),
            },
            "detail_sheet_ids": detail_sheets,
            "detail_sheet_names": [by_sheet.get(s, {}).get("name", f"Khung #{s}") for s in detail_sheets if s in by_sheet],
            "manufacturing_stages": node.get("manufacturing_stages", []),
            "contacts": [],
        }

        if pos_x is not None and pos_y is not None:
            placed_positions.append((code, pos_x, pos_y, dim_w or 50, dim_h or 50, part_item))

        parts_result.append(part_item)

    # Compute spatial relationships & contacts between placed parts
    relationships = []
    for i, (code1, x1, y1, w1, h1, item1) in enumerate(placed_positions):
        for code2, x2, y2, w2, h2, item2 in placed_positions[i + 1 :]:
            dist = math.hypot(x1 - x2, y1 - y2)
            rel = None

            # Vertical stack contact
            dy = abs(y1 - y2)
            dx = abs(x1 - x2)
            if dy <= (h1 + h2) * 0.6 and dx <= max(w1, w2) * 0.8:
                rel = {
                    "kind": "planar_contact",
                    "label": "Tiếp xúc lắp ghép",
                    "description": f"Chi tiết {item1['part_number']} và chi tiết {item2['part_number']} lắp tiếp xúc trong cụm",
                    "source": code1,
                    "target": code2,
                    "distance_mm": round(dist, 1),
                }
            elif dist < 300.0:
                rel = {
                    "kind": "assembly_neighbor",
                    "label": "Liên kết lân cận",
                    "description": f"Chi tiết {item1['part_number']} nằm gần chi tiết {item2['part_number']} (khoảng cách {round(dist, 1)} mm)",
                    "source": code1,
                    "target": code2,
                    "distance_mm": round(dist, 1),
                }

            if rel:
                relationships.append(rel)
                item1["contacts"].append({"target_code": code2, "target_number": item2["part_number"], "kind": rel["kind"], "label": rel["label"]})
                item2["contacts"].append({"target_code": code1, "target_number": item1["part_number"], "kind": rel["kind"], "label": rel["label"]})

    # Also incorporate graph edges (welds, connections)
    for edge in graph.get("edges", []):
        src, tgt, kind = edge.get("source"), edge.get("target"), edge.get("kind")
        p1 = next((p for p in parts_result if p["part_code"] == src), None)
        p2 = next((p for p in parts_result if p["part_code"] == tgt), None)
        if p1 and p2:
            label = "Liên kết hàn gò" if kind == "weld" else "Lắp ghép chi tiết" if kind == "connection" else "Thành viên BOM"
            relationships.append({
                "kind": kind,
                "label": label,
                "description": f"{label}: chi tiết {p1['part_number']} ({src}) gắn với chi tiết {p2['part_number']} ({tgt})",
                "source": src,
                "target": tgt,
                "distance_mm": 0,
            })
            p1["contacts"].append({"target_code": tgt, "target_number": p2["part_number"], "kind": kind, "label": label})
            p2["contacts"].append({"target_code": src, "target_number": p1["part_number"], "kind": kind, "label": label})

    # Summary
    roles_count = defaultdict(int)
    for p in parts_result:
        roles_count[p["role"]] += 1

    return {
        "version": VERSION,
        "document_id": status.get("id", ""),
        "source_hash": status.get("source_hash", ""),
        "primary_assembly": {
            "sheet_id": primary_assembly_sheet_id,
            "sheet_name": primary_sheet.get("name", "Bản vẽ lắp tổng thể") if primary_sheet else "Bản vẽ lắp",
            "bbox": [round(float(v), 2) for v in (asm_bbox or [0, 0, 1000, 1000])],
            "width_mm": round(asm_w, 2),
            "height_mm": round(asm_h, 2),
        },
        "parts": parts_result,
        "relationships": relationships,
        "summary": {
            "total_parts": len(parts_result),
            "placed_parts": len(placed_positions),
            "total_relationships": len(relationships),
            "roles_breakdown": dict(roles_count),
        },
        "policy": "Block placement and leader coordinates provide assembly context; geometry editing is bound to verified dimensions and detail sheets.",
    }


def parse_dimensions_from_desc(desc: str) -> tuple[Optional[float], Optional[float]]:
    """Extract width/length from descriptions like '3x25x988mm' or '36x31x468mm'."""
    text = desc.replace(",", ".").replace("×", "x").casefold()
    import re
    m = re.findall(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)(?:\s*x\s*(\d+(?:\.\d+)?))?", text)
    if m:
        nums = [float(x) for x in m[0] if x]
        if len(nums) >= 2:
            nums.sort()
            return nums[-2], nums[-1]  # width, length
    return None, None


def infer_part_role(desc: str, pos_x: Optional[float], pos_y: Optional[float], w: Optional[float], h: Optional[float], asm_ymin: float, asm_h: float, asm_xmin: float, asm_w: float, part_num: str) -> Dict[str, str]:
    d = desc.casefold()

    # Rule-based semantic tags first
    if any(k in d for k in ("chan", "chân", "de", "đế", "day", "đáy", "tru", "trụ")):
        if any(k in d for k in ("bas de", "bas đế", "chi chan", "chỉ chân", "bit dau", "bít đầu")):
            return {
                "role": "bracket_fastener",
                "role_label": "Bas đế / Chỉ chân định vị",
                "role_icon": "🔩",
                "role_reason": "Chi tiết nhỏ dùng để định vị, bít đầu hoặc làm đế đỡ dưới chân khung",
            }
        return {
            "role": "base_frame",
            "role_label": "Chân đế / Khung đỡ dưới",
            "role_icon": "🏛️",
            "role_reason": "Chân khung trụ chịu lực chính, đặt ở phần dưới của sản phẩm",
        }

    if any(k in d for k in ("nap", "nắp", "tren", "trên", "vien", "viền", "vong nhom", "vòng nhôm")):
        return {
            "role": "top_cover",
            "role_label": "Nắp / Viền / Cụm trên",
            "role_icon": "🔝",
            "role_reason": "Chi tiết nằm ở phần đỉnh, viền ngoài hoặc nắp che của sản phẩm",
        }

    if any(k in d for k in ("giang", "giằng", "thanh", "la dai", "la dài", "la ngan", "la ngắn", "loi", "lõi")):
        return {
            "role": "stiffener_brace",
            "role_label": "Thanh giằng / Khung giằng liên kết",
            "role_icon": "⚙️",
            "role_reason": "Thanh giằng chịu lực ngang/dọc, liên kết giữa các chân và thành khung",
        }

    if any(k in d for k in ("bas", "tam ma", "bản mã", "chi", "chỉ", "dem", "đệm", "khoa", "khóa")):
        return {
            "role": "bracket_fastener",
            "role_label": "Bas nối / Bản mã liên kết",
            "role_icon": "🔩",
            "role_reason": "Chi tiết phụ trợ lắp ghép, hàn hoặc bắt vít",
        }

    # Fasteners & hardware
    if any(k in d for k in ("vit", "vít", "bulong", "bu lông", "bu-lông", "bolt", "screw", "tan", "tán", "đai ốc", "nut", "long den", "long đền", "vòng đệm", "washer", "chốt", "pin", "csk", "dowel", "bạc", "bearing", "bạc đạn", "o-ring", "oring", "ron", "gioăng")):
        return {
            "role": "standard_fastener",
            "role_label": "Bulong / Ốc vít / Phụ kiện tiêu chuẩn",
            "role_icon": "🔩",
            "role_reason": "Chi tiết lắp xiết hoặc phụ tùng cơ khí tiêu chuẩn",
        }

    # Sheet metal / Panels
    if any(k in d for k in ("tam", "tấm", "plate", "panel", "vach", "vách", "cua", "cửa", "hong", "hông", "lung", "lưng")):
        return {
            "role": "panel_plate",
            "role_label": "Tấm vỏ / Vách kim loại tấm",
            "role_icon": "🔲",
            "role_reason": "Tấm bao che hoặc vách ngăn gia công kim loại tấm",
        }

    # Tube / Hollow sections
    if any(k in d for k in ("ong", "ống", "hop", "hộp", "tube", "pipe")):
        return {
            "role": "tube_section",
            "role_label": "Thép hộp / Ống định hình",
            "role_icon": "📏",
            "role_reason": "Thành phần ống hoặc thép hộp chịu lực khung",
        }

    # Spatial inference if coordinates exist
    if pos_y is not None and asm_h > 0:
        rel_y = (pos_y - asm_ymin) / asm_h
        if rel_y <= 0.35:
            return {
                "role": "base_frame",
                "role_label": "Bộ phận chân đế / Đáy",
                "role_icon": "🏛️",
                "role_reason": f"Vị trí nằm ở vùng chân/đáy của bản vẽ lắp (y = {int(rel_y*100)}%)",
            }
        elif rel_y >= 0.70:
            return {
                "role": "top_cover",
                "role_label": "Bộ phận đỉnh / Nắp trên",
                "role_icon": "🔝",
                "role_reason": f"Vị trí nằm ở vùng đỉnh của bản vẽ lắp (y = {int(rel_y*100)}%)",
            }

    return {
        "role": "stiffener_brace",
        "role_label": "Chi tiết cấu thành cụm",
        "role_icon": "⚙️",
        "role_reason": "Chi tiết lắp ráp cơ khí tiêu chuẩn trong sản phẩm",
    }
