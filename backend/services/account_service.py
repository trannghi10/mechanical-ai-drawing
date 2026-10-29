"""Local company accounts. Passwords and session tokens are never stored raw."""
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import time
import uuid
from contextvars import ContextVar
from backend.services import database_service as database

ACTOR=ContextVar('cad_actor',default=None)
ROLES=('viewer','operator','engineer','admin')
COOKIE='cad_session'
SESSION_SECONDS=12*3600
ITERATIONS=600_000


class AccountError(ValueError):
    def __init__(self,status,message):super().__init__(message);self.status=status


def mode_file():
    from backend.services import catalog_service as storage
    return storage.ROOT.parent/'accounts.enabled'


def required():
    return mode_file().is_file() or os.getenv('CAD_REQUIRE_LOGIN','0').lower() in ('1','true','yes')


def initialize(db):
    statements=[
        'CREATE TABLE IF NOT EXISTS cad_security(id INTEGER PRIMARY KEY CHECK(id=1),configured INTEGER NOT NULL DEFAULT 0)',
        "CREATE TABLE IF NOT EXISTS cad_users(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('viewer','operator','engineer','admin')),active INTEGER NOT NULL DEFAULT 1,created_at BIGINT NOT NULL)",
        'CREATE TABLE IF NOT EXISTS cad_sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES cad_users(id),expires_at BIGINT NOT NULL)',
        'CREATE INDEX IF NOT EXISTS cad_sessions_user ON cad_sessions(user_id)',
        'CREATE TABLE IF NOT EXISTS cad_login_limits(bucket TEXT PRIMARY KEY,attempts INTEGER NOT NULL,expires_at BIGINT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS cad_user_audit(id TEXT PRIMARY KEY,user_id TEXT,username TEXT,action TEXT NOT NULL,resource TEXT NOT NULL,result INTEGER NOT NULL,created_at BIGINT NOT NULL)',
    ]
    for statement in statements:db.execute(statement)
    db.execute('INSERT INTO cad_security VALUES (1,0) ON CONFLICT(id) DO NOTHING')


def password_hash(value,salt=None):
    if not isinstance(value,str) or not 12<=len(value)<=128:raise AccountError(422,'Mật khẩu cần từ 12 đến 128 ký tự.')
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',value.encode('utf8'),salt,ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def password_matches(value,encoded):
    try:
        scheme,rounds,salt,expected=encoded.split('$')
        if scheme!='pbkdf2_sha256' or int(rounds)!=ITERATIONS or not isinstance(value,str) or len(value)>128:return False
        actual=hashlib.pbkdf2_hmac('sha256',value.encode('utf8'),bytes.fromhex(salt),int(rounds)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError):return False


def identity(username,display_name,role):
    username=username.strip().lower();display_name=display_name.strip()
    if not re.fullmatch(r'[a-z][a-z0-9._-]{2,63}',username):raise AccountError(422,'Tên đăng nhập gồm 3–64 ký tự a–z, số, dấu chấm, gạch ngang hoặc gạch dưới.')
    if not 1<=len(display_name)<=120 or role not in ROLES:raise AccountError(422,'Tên hiển thị hoặc vai trò không hợp lệ.')
    return username,display_name,role


def public(row):return dict(id=row[0],username=row[1],display_name=row[2],role=row[3],active=bool(row[4]))


def issue(db,user_id):
    token=secrets.token_urlsafe(32);expires=int(time.time())+SESSION_SECONDS
    db.execute('DELETE FROM cad_sessions WHERE expires_at<=?',(int(time.time()),))
    db.execute('INSERT INTO cad_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user_id,expires))
    return token


def current(token):
    if not token or len(token)>128:return None
    with database.connection() as db:
        initialize(db)
        row=db.execute('SELECT u.id,u.username,u.display_name,u.role,u.active FROM cad_sessions s JOIN cad_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',
                       (hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        return public(row) if row else None


def setup(username,display_name,password):
    username,display_name,_=identity(username,display_name,'admin');encoded=password_hash(password)
    user_id=uuid.uuid4().hex
    with database.connection() as db:
        initialize(db)
        # This row lock serializes bootstrap on PostgreSQL and SQLite.
        db.execute('UPDATE cad_security SET configured=configured WHERE id=1')
        if db.execute('SELECT configured FROM cad_security WHERE id=1').fetchone()[0]:raise AccountError(409,'Đã thiết lập quản trị viên; hãy đăng nhập.')
        # Fail closed if a process stops between the filesystem and DB commit.
        marker=mode_file();marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text('enabled\n',encoding='ascii')
        db.execute('INSERT INTO cad_users VALUES (?,?,?,?,?,?,?)',(user_id,username,display_name,encoded,'admin',1,int(time.time())))
        db.execute('UPDATE cad_security SET configured=1 WHERE id=1')
        token=issue(db,user_id)
        db.execute('INSERT INTO cad_user_audit VALUES (?,?,?,?,?,?,?)',(uuid.uuid4().hex,user_id,username,'setup','accounts',201,int(time.time())))
    return dict(id=user_id,username=username,display_name=display_name,role='admin',active=True),token


def status(token=None):
    with database.connection() as db:
        initialize(db);configured=bool(db.execute('SELECT configured FROM cad_security WHERE id=1').fetchone()[0])
    if configured and not mode_file().exists():mode_file().write_text('enabled\n',encoding='ascii')
    return dict(required=required(),setup_needed=not configured,user=current(token) if token else None,roles=list(ROLES))


def login(username,password,peer):
    username=username.strip().lower()[:64];now=int(time.time())
    bucket=hashlib.sha256((username+'\0'+peer).encode()).hexdigest()
    with database.connection() as db:
        initialize(db)
        db.execute('INSERT INTO cad_login_limits VALUES (?,?,?) ON CONFLICT(bucket) DO UPDATE SET attempts=CASE WHEN cad_login_limits.expires_at<=? THEN 1 ELSE cad_login_limits.attempts+1 END,expires_at=CASE WHEN cad_login_limits.expires_at<=? THEN ? ELSE cad_login_limits.expires_at END',
                   (bucket,1,now+900,now,now,now+900))
        attempts=db.execute('SELECT attempts FROM cad_login_limits WHERE bucket=?',(bucket,)).fetchone()[0]
        if attempts>5:failure=AccountError(429,'Đã thử đăng nhập nhiều lần; vui lòng thử lại sau 15 phút.')
        else:
            row=db.execute('SELECT id,username,display_name,role,active,password_hash FROM cad_users WHERE username=?',(username,)).fetchone()
            encoded=row[5] if row else password_hash('unusable-dummy-password',salt=b'\0'*16)
            valid=password_matches(password,encoded)
            if not row or not row[4] or not valid:failure=AccountError(401,'Tên đăng nhập hoặc mật khẩu không đúng.')
            else:
                token=issue(db,row[0]);db.execute('DELETE FROM cad_login_limits WHERE bucket=?',(bucket,))
                db.execute('INSERT INTO cad_user_audit VALUES (?,?,?,?,?,?,?)',(uuid.uuid4().hex,row[0],username,'login','session',200,now))
                return public(row),token
        db.execute('INSERT INTO cad_user_audit VALUES (?,?,?,?,?,?,?)',(uuid.uuid4().hex,None,None,'login_failed','session',failure.status,now))
    raise failure


def logout(token):
    with database.connection() as db:
        initialize(db)
        db.execute('DELETE FROM cad_sessions WHERE token_hash=?',(hashlib.sha256((token or '').encode()).hexdigest(),))


def users():
    with database.connection() as db:
        initialize(db)
        return [public(row) for row in db.execute('SELECT id,username,display_name,role,active FROM cad_users ORDER BY username').fetchall()]


def create_user(username,display_name,password,role):
    username,display_name,role=identity(username,display_name,role);encoded=password_hash(password);user_id=uuid.uuid4().hex
    with database.connection() as db:
        initialize(db);db.execute('UPDATE cad_security SET configured=configured WHERE id=1')
        if db.execute('SELECT id FROM cad_users WHERE username=?',(username,)).fetchone():raise AccountError(409,'Tên đăng nhập đã tồn tại.')
        db.execute('INSERT INTO cad_users VALUES (?,?,?,?,?,?,?)',(user_id,username,display_name,encoded,role,1,int(time.time())))
    return dict(id=user_id,username=username,display_name=display_name,role=role,active=True)


def update_user(user_id,role,active,password=None):
    if role not in ROLES or type(active)!=bool:raise AccountError(422,'Vai trò hoặc trạng thái không hợp lệ.')
    encoded=password_hash(password) if password is not None else None
    with database.connection() as db:
        initialize(db);db.execute('UPDATE cad_security SET configured=configured WHERE id=1')
        row=db.execute('SELECT role,active FROM cad_users WHERE id=?',(user_id,)).fetchone()
        if not row:raise AccountError(404,'Tài khoản không tồn tại.')
        admins=db.execute("SELECT COUNT(*) FROM cad_users WHERE role='admin' AND active=1").fetchone()[0]
        if row==('admin',1) and (role!='admin' or not active) and admins<=1:raise AccountError(409,'Cần giữ ít nhất một quản trị viên hoạt động.')
        if row==(role,int(active)) and not encoded:return
        db.execute('UPDATE cad_users SET role=?,active=? WHERE id=?',(role,int(active),user_id))
        if encoded:db.execute('UPDATE cad_users SET password_hash=? WHERE id=?',(encoded,user_id))
        db.execute('DELETE FROM cad_sessions WHERE user_id=?',(user_id,))


def change_password(user,old,new):
    encoded=password_hash(new)
    with database.connection() as db:
        initialize(db)
        actual=db.execute('SELECT password_hash FROM cad_users WHERE id=? AND active=1',(user['id'],)).fetchone()
        if not actual or not password_matches(old,actual[0]):raise AccountError(401,'Mật khẩu hiện tại không đúng.')
        db.execute('UPDATE cad_users SET password_hash=? WHERE id=?',(encoded,user['id']))
        db.execute('DELETE FROM cad_sessions WHERE user_id=?',(user['id'],))
        return issue(db,user['id'])


def permitted(user,method,path):
    role=user['role']
    if role=='admin':return True
    if path=='/database/health' and method in ('GET','HEAD'):return True
    if path.startswith('/auth/users') or path=='/auth/audit' or path.startswith('/database/'):return False
    if path in ('/auth/logout','/auth/password','/auth/status'):return True
    if method in ('GET','HEAD','OPTIONS'):return True
    if role=='viewer':return False
    if path.startswith('/edit-certifications'):return role=='engineer'
    if path=='/aps/connection' or path.startswith('/ai/'):return False
    if path.endswith('/approve'):return role=='engineer'
    return True


def audit(user,action,resource,result,request_id=None):
    with database.connection() as db:
        initialize(db)
        db.execute('INSERT INTO cad_user_audit VALUES (?,?,?,?,?,?,?)',(request_id or uuid.uuid4().hex,
            user.get('id') if user else None,user.get('username') if user else None,action[:40],resource[:1000],result,int(time.time())))


def audit_rows(limit=100):
    with database.connection() as db:
        initialize(db)
        rows=db.execute('SELECT id,user_id,username,action,resource,result,created_at FROM cad_user_audit ORDER BY created_at DESC,id DESC LIMIT ?',(limit,)).fetchall()
        return [dict(zip(('id','user_id','username','action','resource','result','created_at'),row)) for row in rows]


def finish_audit(request_id,result):
    with database.connection() as db:
        db.execute('UPDATE cad_user_audit SET result=? WHERE id=?',(result,request_id))
