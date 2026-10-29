"""Exercise accounts on a disposable PG schema, never production user tables."""
import json
import os
from pathlib import Path
import secrets
import sys
import uuid
from contextlib import contextmanager
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from backend.main import app
    from backend.services import database_service as database, catalog_service as storage, account_service as accounts
    from fastapi.testclient import TestClient
    from psycopg import sql
    if database.backend()!='postgresql':raise ValueError('PostgreSQL must be configured; no fallback test.')
    schema='cad_accounts_check_'+uuid.uuid4().hex
    output=ROOT/'storage/validation-fixtures'/schema;output.mkdir()
    original_connection=database.connection
    with original_connection(initialize_schema=False) as db:
        db.raw.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))

    @contextmanager
    def isolated_connection(**kwargs):
        with original_connection(initialize_schema=False) as db:
            db.raw.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
            if kwargs.get('initialize_schema',True):database.initialize(db)
            yield db

    result=dict(schema=schema,status='failed',production_users_changed=False,checks=[])
    password=secrets.token_urlsafe(32)
    try:
        with patch.object(database,'connection',isolated_connection),patch.object(storage,'ROOT',output/'documents'),patch.object(storage,'queue_process',lambda *args:None):
            os.environ.pop('CAD_REQUIRE_LOGIN',None)
            os.environ['CAD_READ_BACKEND']='oda'
            storage.ROOT.mkdir()
            admin=TestClient(app);anonymous=TestClient(app)
            assert admin.get('/auth/status').json()['setup_needed']
            setup=admin.post('/auth/setup',json=dict(username='pgadmin',display_name='PG test admin',password=password,role='admin'))
            assert setup.status_code==201,setup.status_code
            result['checks'].append('bootstrap_schema_and_hashed_session')
            assert anonymous.get('/documents').status_code==401
            operator=admin.post('/auth/users',json=dict(username='pgoperator',display_name='PG test operator',password=password,role='operator'))
            assert operator.status_code==201,operator.status_code
            worker=TestClient(app)
            assert worker.post('/auth/login',json=dict(username='pgoperator',password=password)).status_code==200
            assert worker.post('/documents/a/revisions/b/approve',json={}).status_code==403
            result['checks'].append('role_enforcement')
            uploaded=worker.post('/documents',files={'file':('synthetic.dxf',b'0\nEOF\n','application/octet-stream')})
            assert uploaded.status_code==202,uploaded.status_code
            state=storage.read_status(uploaded.json()['id'])
            assert state['created_by']['username']=='pgoperator'
            assert any(row['id']==uploaded.headers['x-request-id'] and row['result']==202 for row in admin.get('/auth/audit').json()['items'])
            result['checks'].append('upload_actor_and_durable_audit')
            same=admin.patch('/auth/users/'+operator.json()['id'],json=dict(role='operator',active=True))
            assert same.status_code==200 and worker.get('/documents').status_code==200
            assert admin.patch('/auth/users/'+operator.json()['id'],json=dict(role='viewer',active=True)).status_code==200
            assert worker.get('/documents').status_code==401
            result['checks'].append('session_revocation_and_noop_preservation')
            with isolated_connection() as db:
                encoded=db.execute("SELECT password_hash FROM cad_users WHERE username='pgadmin'").fetchone()[0]
                sessions=[row[0] for row in db.execute('SELECT token_hash FROM cad_sessions')]
                assert password not in encoded and admin.cookies.get(accounts.COOKIE) not in sessions
            resumed=TestClient(app);resumed.cookies.set(accounts.COOKIE,admin.cookies.get(accounts.COOKIE))
            assert resumed.get('/auth/users').status_code==200
            result['checks'].append('new_connection_session_persistence')
            last=admin.patch('/auth/users/'+setup.json()['user']['id'],json=dict(role='viewer',active=False))
            assert last.status_code==409
            for _ in range(5):assert anonymous.post('/auth/login',json=dict(username='pgadmin',password='deliberately incorrect')).status_code==401
            assert anonymous.post('/auth/login',json=dict(username='pgadmin',password='deliberately incorrect')).status_code==429
            result['checks'].append('last_admin_and_persistent_login_limit')
            result['status']='passed'
    finally:
        # Only the exact unique schema created above is disposable.
        with original_connection(initialize_schema=False) as db:
            db.raw.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        result['test_schema_removed']=True
        (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=result['checks'],receipt=str((output/'verification.json').relative_to(ROOT)))))


if __name__=='__main__':main()
