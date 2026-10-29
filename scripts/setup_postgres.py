"""Provision the project's PostgreSQL database without changing server auth.

Admin credentials come from .env, never command-line arguments or stdout.
SQLite and all CAD files are retained. Existing roles/databases are not reset.
"""
import argparse
import json
import os
import re
import secrets
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote,urlsplit,unquote

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv,set_key
from backend.services import database_service as database


def identifier(value):
    if not re.fullmatch('[a-z][a-z0-9_]{0,62}',value):
        raise database.DatabaseError('Tên database/role chỉ dùng chữ thường, số, gạch dưới; tối đa 63 ký tự.')
    return value


def make_url(host,port,name,role,password):
    identifier(name);identifier(role)
    if host not in ('127.0.0.1','localhost','::1'):
        raise database.DatabaseError('Script thiết lập này chỉ tạo database trên PostgreSQL local.')
    host='['+host+']' if ':' in host else host
    return f'postgresql://{quote(role,safe="")}:{quote(password,safe="")}@{host}:{int(port)}/{name}'


def provision(name,role):
    import psycopg
    from psycopg import sql
    name=identifier(name);role=identifier(role)
    host=os.getenv('PGHOST','127.0.0.1');port=int(os.getenv('PGPORT','5432'))
    admin=os.getenv('PG_ADMIN_USER','postgres');admin_password=os.getenv('PG_ADMIN_PASSWORD','')
    if not admin_password:
        raise database.DatabaseError('Thiếu PG_ADMIN_PASSWORD trong .env; không thay đổi xác thực PostgreSQL.')
    make_url(host,port,name,role,'validation')
    current_url=os.getenv('DATABASE_URL','').strip()
    parsed=urlsplit(current_url)
    if current_url and (parsed.scheme not in ('postgresql','postgres') or unquote(parsed.username or '')!=role
            or parsed.path.lstrip('/')!=name or parsed.hostname!=host or (parsed.port or 5432)!=port):
        raise database.DatabaseError('DATABASE_URL đang trỏ sang database khác; không ghi đè cấu hình đó.')
    pending=ROOT/'storage/postgres-setup.pending.json'
    pending.parent.mkdir(exist_ok=True)
    saved=json.loads(pending.read_text(encoding='utf8')) if pending.is_file() else {}
    if saved and (saved['database']!=name or saved['role']!=role or saved['host']!=host or saved['port']!=port):
        raise database.DatabaseError('Có tác vụ thiết lập PostgreSQL khác đang dở; cần kiểm tra trước khi tạo mới.')
    app_password=unquote(parsed.password or '') if current_url else saved.get('password')
    app_password=app_password or secrets.token_urlsafe(32)
    try:
        admin_db=psycopg.connect(host=host,port=port,user=admin,password=admin_password,dbname='postgres',
                                  connect_timeout=5,autocommit=True)
    except psycopg.Error:
        raise database.DatabaseError('Không đăng nhập được PostgreSQL bằng PG_ADMIN_USER/PG_ADMIN_PASSWORD trong .env.') from None
    with admin_db:
        exists=admin_db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
        owner=admin_db.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s',(name,)).fetchone()
        if exists and not current_url and not saved:
            raise database.DatabaseError('Role ứng dụng đã tồn tại nhưng chưa có credential dự án; không đổi mật khẩu role đó.')
        if owner and owner[0]!=role:
            raise database.DatabaseError('Database đã tồn tại và thuộc role khác; không đổi chủ sở hữu hoặc xóa dữ liệu.')
        pending.write_text(json.dumps(dict(database=name,role=role,host=host,port=port,password=app_password)),encoding='utf8')
        if not exists:
            admin_db.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
                             .format(sql.Identifier(role),sql.Literal(app_password)))
        if not owner:
            admin_db.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0")
                             .format(sql.Identifier(name),sql.Identifier(role)))
    url=make_url(host,port,name,role,app_password)
    os.environ['DATABASE_URL']=url
    with database.connection():pass  # Authenticate as app role and create schema.
    set_key(str(ROOT/'.env'),'DATABASE_URL',url,quote_mode='always')
    pending.unlink(missing_ok=True)
    return dict(database=name,role=role,host=host,port=port,connection='ok',schema='ready')


def migrate_sqlite(path=None):
    from backend.services import catalog_service as storage
    path=Path(path) if path else storage.ROOT.parent/'aps.sqlite3'
    counts={'jobs_scanned':0,'artifacts_scanned':0}
    if not path.is_file():return counts
    if database.backend()!='postgresql':raise database.DatabaseError('Cần DATABASE_URL PostgreSQL trước khi migrate.')
    source=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        tables={row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'aps_jobs' not in tables:return counts
        with database.connection() as target:
            for row in source.execute('SELECT id,document_id,created,payload FROM aps_jobs'):
                existing=target.execute('SELECT document_id FROM aps_jobs WHERE id=?',(row[0],)).fetchone()
                if existing and existing[0]!=row[1]:raise database.DatabaseError('Trùng ID APS thuộc tài liệu khác; không hợp nhất dữ liệu.')
                target.execute('INSERT INTO aps_jobs VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING',
                               (*row[:3],target.json(json.loads(row[3]))))
                counts['jobs_scanned']+=1
            if 'aps_artifacts' in tables:
                for row in source.execute('SELECT job_id,name,sha256,bytes FROM aps_artifacts'):
                    target.execute('INSERT INTO aps_artifacts VALUES (?,?,?,?) ON CONFLICT(job_id,name) DO NOTHING',row)
                    counts['artifacts_scanned']+=1
    finally:source.close()
    return counts


def index_existing():
    from backend.services import catalog_service as storage
    counts={'documents':0,'revisions':0}
    for folder in storage.ROOT.iterdir():
        if not folder.is_dir() or not re.fullmatch('[a-f0-9]{32}',folder.name):continue
        file=folder/'status.json'
        if not file.is_file():continue
        database.index_document(folder.name,json.loads(file.read_text(encoding='utf8')));counts['documents']+=1
        for revision in (folder/'revisions').glob('*/revision.json'):
            if not re.fullmatch('[a-f0-9]{32}',revision.parent.name):continue
            database.index_revision(folder.name,revision.parent.name,json.loads(revision.read_text(encoding='utf8')))
            counts['revisions']+=1
    return counts


def main():
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create','migrate','index','status'])
    parser.add_argument('--database',default='mechanical_ai_drawing');parser.add_argument('--role',default='mechanical_ai_app')
    args=parser.parse_args()
    if args.action=='create':
        result=provision(args.database,args.role)
        result['sqlite_migration']=migrate_sqlite()
        result['cad_index']=index_existing()
    elif args.action=='migrate':result=migrate_sqlite()
    elif args.action=='index':result=index_existing()
    else:result=database.status()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    try:main()
    except Exception as error:
        print(str(error) if isinstance(error,database.DatabaseError) else 'Thiết lập PostgreSQL chưa hoàn tất. Dữ liệu cũ được giữ; kiểm tra dịch vụ, cấu hình và chạy lại.',file=sys.stderr)
        sys.exit(1)
