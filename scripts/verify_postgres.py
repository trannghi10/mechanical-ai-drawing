"""Live PostgreSQL storage smoke check; all synthetic rows are rolled back."""
import json
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from backend.services import database_service as database,aps_repository
from cad.edit_engine import digest


def verify():
    if database.backend()!='postgresql':raise database.DatabaseError('Chưa cấu hình DATABASE_URL PostgreSQL.')
    with database.connection() as db:
        identity=db.execute('SELECT current_database(),current_user').fetchone()
        privileges=db.execute('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()
        if any(privileges):raise database.DatabaseError('Ứng dụng đang dùng role quản trị; cần role riêng không có quyền quản trị.')
        payload_type=db.execute("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='aps_jobs' AND column_name='payload'").fetchone()[0]
        if payload_type!='jsonb':raise database.DatabaseError('APS payload chưa dùng schema JSONB đúng phiên bản.')
        job_id=uuid.uuid4().hex;document_id=uuid.uuid4().hex
        original=aps_repository.connection
        @contextmanager
        def borrowed():yield db
        aps_repository.connection=borrowed
        try:
            with db.raw.transaction(force_rollback=True):
                job=dict(id=job_id,document_id=document_id,status='queued',request='Kiểm tra PostgreSQL — dữ liệu tiếng Việt')
                aps_repository.save(job)
                job['status']='ready';aps_repository.save(job)
                read=aps_repository.read(document_id,job_id)
                assert read['request']==job['request'] and read['status']=='ready'
                assert aps_repository.list_jobs(document_id)[0]['id']==job_id
                aps_repository.artifact(job_id,'smoke-reference',ROOT/'README.md',digest(ROOT/'README.md'))
                assert db.execute('SELECT COUNT(*) FROM aps_artifacts WHERE job_id=?',(job_id,)).fetchone()[0]==1
        finally:aps_repository.connection=original
        assert db.execute('SELECT COUNT(*) FROM aps_jobs WHERE id=?',(job_id,)).fetchone()[0]==0
        counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('cad_documents','cad_revisions','cad_files','aps_jobs')}
    return dict(database=identity[0],application_role=identity[1],admin_privileges=False,
                aps_jsonb_unicode_roundtrip='passed',artifact_relationship='passed',synthetic_rows_rolled_back=True,counts=counts)


if __name__=='__main__':
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    try:
        print(json.dumps(verify(),ensure_ascii=False,indent=2))
    except Exception as error:
        print(str(error) if isinstance(error,database.DatabaseError) else 'Kiểm chứng PostgreSQL chưa đạt; không giữ các bản ghi thử.',file=sys.stderr)
        sys.exit(1)
