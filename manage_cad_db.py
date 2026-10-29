"""
Script quản lý dữ liệu bản vẽ CAD trong SQL và File Storage
Hỗ trợ cả SQLite (mặc định storage/aps.sqlite3) và PostgreSQL (qua DATABASE_URL).
Cách dùng:
    python manage_cad_db.py list           # Xem danh sách file trong SQL & Ổ cứng
    python manage_cad_db.py sync           # Đồng bộ toàn bộ file từ Storage vào SQL
    python manage_cad_db.py stats          # Thống kê tổng quan cơ sở dữ liệu
    python manage_cad_db.py delete <id>    # Xóa sạch 1 bản vẽ trong SQL và Ổ cứng
"""
import sys
import os
import json
import shutil
from pathlib import Path

# Đảm bảo in tiếng Việt / UTF-8 trên console Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Đảm bảo đường dẫn workspace trong sys.path
WORKSPACE_DIR = Path(__file__).resolve().parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE_DIR / '.env', override=True, encoding='utf-8-sig')
except Exception:
    env_file = WORKSPACE_DIR / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip().strip("'\"")

from backend.services.database_service import connection, index_document, status as db_status
from backend.services.catalog_service import ROOT as STORAGE_DOCUMENTS_ROOT


def get_all_storage_docs():
    docs = []
    if not STORAGE_DOCUMENTS_ROOT.exists():
        return docs
    for d in STORAGE_DOCUMENTS_ROOT.iterdir():
        if d.is_dir() and len(d.name) == 32:
            st_path = d / 'status.json'
            data = {}
            if st_path.exists():
                try:
                    data = json.loads(st_path.read_text(encoding='utf-8'))
                except Exception:
                    pass
            docs.append({
                'id': d.name,
                'path': d,
                'filename': data.get('filename') or 'Chưa rõ tên',
                'status': data.get('status') or 'unknown',
                'size': sum(f.stat().st_size for f in d.glob('**/*') if f.is_file())
            })
    return sorted(docs, key=lambda x: x['filename'].lower())


def cmd_stats():
    print("=" * 60)
    print("📊 THỐNG KÊ CƠ SỞ DỮ LIỆU CAD (SQL & FILE STORAGE)")
    print("=" * 60)
    st = db_status()
    print(f"• Hệ quản trị SQL:    {st.get('backend').upper()}")
    print(f"• Trạng thái kết nối: {'✓ ĐANG HOẠT ĐỘNG' if st.get('ready') else '❌ LỖI KẾT NỐI'}")
    print(f"• File SQLite:        storage/aps.sqlite3")
    print(f"• Bản ghi documents:  {st.get('documents', 0)} file trong SQL")
    print(f"• Bản ghi revisions:  {st.get('revisions', 0)} bản sửa trong SQL")
    print(f"• Tác vụ APS/AutoCAD: {st.get('aps_jobs', 0)} jobs")
    storage_docs = get_all_storage_docs()
    total_bytes = sum(d['size'] for d in storage_docs)
    print(f"• Thư mục ổ cứng:     storage/documents/ ({len(storage_docs)} thư mục bản vẽ, {total_bytes / (1024*1024):.2f} MB)")
    print("=" * 60)


def cmd_list():
    storage_docs = get_all_storage_docs()
    print(f"\n📁 DANH SÁCH BẢN VẼ TRONG HỆ THỐNG (Tổng cộng: {len(storage_docs)} file)\n")
    print(f"{'STT':<4} {'ID (32 ký tự)':<34} {'Trạng thái':<12} {'Dung lượng':<12} {'Tên File Bản Vẽ'}")
    print("-" * 95)
    for idx, d in enumerate(storage_docs, 1):
        size_mb = f"{d['size'] / (1024*1024):.1f} MB"
        print(f"{idx:<4} {d['id']:<34} {d['status']:<12} {size_mb:<12} {d['filename']}")
    print("-" * 95)
    print("💡 Mẹo: Bấm sao chép ID ở trên để xóa bằng lệnh: python manage_cad_db.py delete <ID>\n")


def calc_digest(path):
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return None


def cmd_sync():
    from datetime import datetime, timezone
    print("\n⏳ Đang đồng bộ toàn bộ file từ storage/documents vào bảng cad_documents trong SQL...")
    count = 0
    errors = 0
    if not STORAGE_DOCUMENTS_ROOT.exists():
        print("❌ Thư mục storage/documents không tồn tại.")
        return

    now = datetime.now(timezone.utc).isoformat()
    with connection() as db:
        for d in STORAGE_DOCUMENTS_ROOT.iterdir():
            if d.is_dir() and len(d.name) == 32:
                st_path = d / 'status.json'
                if st_path.exists():
                    try:
                        data = json.loads(st_path.read_text(encoding='utf-8'))
                        doc_id = d.name
                        source = next((p for p in (d / 'original.dwg', d / 'original.dxf') if p.is_file()), None)
                        sha = calc_digest(source) if source else None
                        source_name = source.name if source else None

                        db.execute(
                            'INSERT INTO cad_documents VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                            'filename=excluded.filename,status=excluded.status,source_hash=excluded.source_hash,'
                            'source_path=excluded.source_path,updated_at=excluded.updated_at',
                            (doc_id, data.get('filename', ''), data.get('status', 'unknown'), sha, source_name, now)
                        )
                        if source:
                            rel = source.name
                            db.execute(
                                'INSERT INTO cad_files VALUES (?,?,?,?,?,?,?) ON CONFLICT(document_id,relative_path) DO UPDATE SET '
                                'revision_id=excluded.revision_id,kind=excluded.kind,sha256=excluded.sha256,bytes=excluded.bytes,updated_at=excluded.updated_at',
                                (doc_id, rel, None, 'source', sha, source.stat().st_size, now)
                            )
                        count += 1
                    except Exception as e:
                        if errors < 3:
                            print(f"Chi tiết lỗi {d.name[:8]}: {e}")
                        errors += 1

        sql_count = db.execute('SELECT COUNT(*) FROM cad_documents').fetchone()[0]

    print(f"✓ Đồng bộ thành công {count} file vào SQL! (Lỗi: {errors})")
    print(f"📊 Tổng số bản vẽ hiện có trong bảng cad_documents của SQL: {sql_count}\n")



def cmd_delete(doc_id):
    doc_id = doc_id.strip().lower()
    if len(doc_id) != 32:
        print(f"❌ ID không hợp lệ: '{doc_id}'. ID bản vẽ phải đúng 32 ký tự hex.")
        return

    target_dir = STORAGE_DOCUMENTS_ROOT / doc_id
    filename = "Không xác định"
    if target_dir.exists():
        st_file = target_dir / 'status.json'
        if st_file.exists():
            try:
                filename = json.loads(st_file.read_text(encoding='utf-8')).get('filename', filename)
            except Exception:
                pass

    print(f"\n⚠️ BẠN ĐANG CHUẨN BỊ XÓA BẢN VẼ:")
    print(f"• ID:       {doc_id}")
    print(f"• Tên file: {filename}")
    print(f"• Thư mục:  storage/documents/{doc_id}")

    # 1. Xóa trong SQL
    deleted_sql = 0
    try:
        with connection() as db:
            # Xóa các file liên kết trong cad_files
            db.execute("DELETE FROM cad_files WHERE document_id = ?", (doc_id,))
            # Xóa các bản sửa trong cad_revisions
            db.execute("DELETE FROM cad_revisions WHERE document_id = ?", (doc_id,))
            # Xóa trong cad_documents
            cur = db.execute("DELETE FROM cad_documents WHERE id = ?", (doc_id,))
            deleted_sql = cur.rowcount
    except Exception as e:
        print(f"⚠️ Cảnh báo SQL: {e}")

    # 2. Xóa thư mục vật lý trên ổ cứng
    deleted_dir = False
    if target_dir.exists():
        try:
            shutil.rmtree(target_dir)
            deleted_dir = True
        except Exception as e:
            print(f"❌ Không thể xóa thư mục ổ cứng: {e}")

    print("\n✅ KẾT QUẢ XÓA:")
    print(f"• Dữ liệu trong SQL: {'✓ Đã xóa sạch' if deleted_sql >= 0 else 'Không tìm thấy'}")
    print(f"• File trên ổ cứng:  {'✓ Đã xóa thư mục vật lý' if deleted_dir else 'Thư mục không tồn tại'}")
    print(f"✓ Hoàn tất xóa hoàn toàn bản vẽ #{doc_id[:8]} khỏi hệ thống!\n")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return

    action = args[0].lower()
    if action == 'list':
        cmd_list()
    elif action == 'stats':
        cmd_stats()
    elif action == 'sync':
        cmd_sync()
    elif action == 'delete':
        if len(args) < 2:
            print("❌ Vui lòng cung cấp ID cần xóa: python manage_cad_db.py delete <id>")
            return
        cmd_delete(args[1])
    else:
        print(f"❌ Lệnh không hợp lệ: {action}. Chạy 'python manage_cad_db.py --help' để xem hướng dẫn.")


if __name__ == '__main__':
    main()
