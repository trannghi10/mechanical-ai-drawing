"""PostgreSQL in production, existing SQLite when DATABASE_URL is unset.

CAD files remain on disk. The database stores identity, paths, hashes and review
status; it must not turn a partial preview into an approved product backup.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


class DatabaseError(ValueError):
    pass


def configured_url():
    return os.getenv('DATABASE_URL','').strip()


def backend():
    url=configured_url()
    if not url:return 'sqlite'
    if urlsplit(url).scheme not in ('postgresql','postgres'):
        raise DatabaseError('DATABASE_URL phải là PostgreSQL URI; bỏ trống để dùng SQLite hiện có.')
    return 'postgresql'


class Database:
    def __init__(self,connection,dialect):
        self.raw=connection;self.dialect=dialect

    def execute(self,query,parameters=()):
        # Only static, internal SQL uses this adapter; no user-supplied queries.
        return self.raw.execute(query.replace('?','%s') if self.dialect=='postgresql' else query,parameters)

    def json(self,value):
        if self.dialect=='postgresql':
            from psycopg.types.json import Jsonb
            return Jsonb(value)
        return json.dumps(value,ensure_ascii=False)


def decode(value):
    return json.loads(value) if isinstance(value,str) else value


def initialize(db):
    payload_type='JSONB' if db.dialect=='postgresql' else 'TEXT'
    statements=[
        'CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)',
        f'CREATE TABLE IF NOT EXISTS aps_jobs(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,created TEXT NOT NULL,payload {payload_type} NOT NULL)',
        'CREATE INDEX IF NOT EXISTS aps_jobs_document_created ON aps_jobs(document_id,created)',
        'CREATE TABLE IF NOT EXISTS aps_artifacts(job_id TEXT NOT NULL REFERENCES aps_jobs(id),name TEXT NOT NULL,sha256 TEXT NOT NULL,bytes BIGINT NOT NULL,PRIMARY KEY(job_id,name))',
        'CREATE TABLE IF NOT EXISTS cad_documents(id TEXT PRIMARY KEY,filename TEXT NOT NULL,status TEXT NOT NULL,source_hash TEXT,source_path TEXT,updated_at TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS cad_revisions(document_id TEXT NOT NULL REFERENCES cad_documents(id),id TEXT NOT NULL,plan_id TEXT,status TEXT NOT NULL,complete_product_backup INTEGER NOT NULL DEFAULT 0,approved_hash TEXT,output_hash TEXT,updated_at TEXT NOT NULL,PRIMARY KEY(document_id,id))',
        'CREATE TABLE IF NOT EXISTS cad_files(document_id TEXT NOT NULL REFERENCES cad_documents(id),relative_path TEXT NOT NULL,revision_id TEXT,kind TEXT NOT NULL,sha256 TEXT NOT NULL,bytes BIGINT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(document_id,relative_path))'
    ]
    for statement in statements:db.execute(statement)
    db.execute('INSERT INTO schema_migrations VALUES (?,?) ON CONFLICT(version) DO NOTHING',
               (1,datetime.now(timezone.utc).isoformat()))


@contextmanager
def connection(*,initialize_schema=True):
    from backend.services import catalog_service as storage
    dialect=backend()
    if dialect=='postgresql':
        try:
            import psycopg
        except ImportError as error:
            raise DatabaseError('Thiếu driver PostgreSQL. Chạy pip install "psycopg[binary]".') from error
        try:
            raw=psycopg.connect(configured_url(),connect_timeout=5,application_name='mechanical-ai-drawing')
        except psycopg.Error:
            raise DatabaseError('Không kết nối được PostgreSQL; kiểm tra dịch vụ, DATABASE_URL và mật khẩu trong .env.') from None
    else:
        root=storage.ROOT.parent;root.mkdir(parents=True,exist_ok=True)
        raw=sqlite3.connect(root/'aps.sqlite3',timeout=30)
        raw.execute('PRAGMA journal_mode=WAL');raw.execute('PRAGMA foreign_keys=ON')
    try:
        with raw:
            db=Database(raw,dialect)
            if initialize_schema:initialize(db)
            yield db
    finally:raw.close()


def status():
    try:
        dialect=backend()
        with connection() as db:
            jobs=db.execute('SELECT COUNT(*) FROM aps_jobs').fetchone()[0]
            documents=db.execute('SELECT COUNT(*) FROM cad_documents').fetchone()[0]
            revisions=db.execute('SELECT COUNT(*) FROM cad_revisions').fetchone()[0]
            info={}
            if dialect=='postgresql':
                name,user=db.execute('SELECT current_database(),current_user').fetchone()
                parsed=urlsplit(configured_url())
                info=dict(host=parsed.hostname,port=parsed.port or 5432,database=name,username=user)
        return dict(backend=dialect,ready=True,aps_jobs=jobs,documents=documents,revisions=revisions,
                    connection_info=info,file_storage='storage/documents',
                    message='Kết nối database hoạt động; file CAD lưu trong storage.')
    except Exception:
        return dict(backend='postgresql' if configured_url() else 'sqlite',ready=False,
                    message='Chưa kết nối được database; kiểm tra cấu hình server. Không tự chuyển backend khi PostgreSQL lỗi.')


def index_document(document_id,status):
    from backend.services import catalog_service as storage
    from cad.edit_engine import digest
    folder=storage.folder(document_id)
    source=next((p for p in (folder/'original.dwg',folder/'original.dxf') if p.is_file()),None)
    now=datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute('INSERT INTO cad_documents VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                   'filename=excluded.filename,status=excluded.status,source_hash=excluded.source_hash,source_path=excluded.source_path,updated_at=excluded.updated_at',
                   (document_id,status.get('filename',''),status.get('status','unknown'),digest(source) if source else None,
                    source.name if source else None,now))
        if source:put_file(db,document_id,folder,source,None,'source',now)


def put_file(db,document_id,folder,path,revision_id,kind,now):
    from cad.edit_engine import digest
    relative=str(path.resolve().relative_to(folder.resolve()))
    db.execute('INSERT INTO cad_files VALUES (?,?,?,?,?,?,?) ON CONFLICT(document_id,relative_path) DO UPDATE SET '
               'revision_id=excluded.revision_id,kind=excluded.kind,sha256=excluded.sha256,bytes=excluded.bytes,updated_at=excluded.updated_at',
               (document_id,relative,revision_id,kind,digest(path),path.stat().st_size,now))


def index_revision(document_id,revision_id,data):
    from backend.services import catalog_service as storage
    folder=storage.folder(document_id)
    status_path=folder/'status.json'
    index_document(document_id,json.loads(status_path.read_text(encoding='utf8')) if status_path.exists() else {})
    now=datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute('INSERT INTO cad_revisions VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(document_id,id) DO UPDATE SET '
                   'plan_id=excluded.plan_id,status=excluded.status,complete_product_backup=excluded.complete_product_backup,'
                   'approved_hash=excluded.approved_hash,output_hash=excluded.output_hash,updated_at=excluded.updated_at',
                   (document_id,revision_id,data.get('plan_id'),data.get('status','unknown'),int(data.get('complete_product_backup') is True),
                    data.get('approved_hash'),data.get('validation',{}).get('output_hash') or data.get('validation',{}).get('output_sha256'),now))
        revision=folder/'revisions'/revision_id
        for relative in ('modified.dxf','modified.dwg','export/modified.dwg','export-selection/modified.dwg'):
            file=revision/relative
            if file.is_file():
                kind='revision' if file.suffix=='.dxf' else ('dwg_backup' if data.get('complete_product_backup') is True and data.get('approved_hash') else 'dwg_preview')
                put_file(db,document_id,folder,file,revision_id,kind,now)


def index_json(path,data):
    """JSON is still authoritative; backfill can retry a failed DB index write."""
    if not configured_url():return
    from backend.services import catalog_service as storage
    try:parts=Path(path).resolve().relative_to(storage.ROOT.resolve()).parts
    except ValueError:return
    if len(parts)==2 and parts[1]=='status.json':index_document(parts[0],data)
    elif len(parts)==4 and parts[1]=='revisions' and parts[3]=='revision.json':index_revision(parts[0],parts[2],data)
