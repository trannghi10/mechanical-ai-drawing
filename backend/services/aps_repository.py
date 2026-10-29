"""Durable cloud job/artifact index; DWGs stay in storage, not database BLOBs."""
import json
from datetime import datetime, timezone
from pathlib import Path
from backend.services.database_service import connection,decode


def save(job):
    from backend.services.account_service import ACTOR
    job.setdefault('created', datetime.now(timezone.utc).isoformat())
    with connection() as db:
        previous=db.execute('SELECT payload FROM aps_jobs WHERE id=?',(job['id'],)).fetchone()
        actor=ACTOR.get()
        if previous:
            previous=decode(previous[0])
            for key in ('created_by','updated_by'):
                if key in previous:job[key]=previous[key]
                else:job.pop(key,None)
        elif actor:job['created_by']=dict(actor)
        else:job.pop('created_by',None);job.pop('updated_by',None)
        if actor:job['updated_by']=dict(actor)
        db.execute('INSERT INTO aps_jobs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (job['id'], job['document_id'], job['created'], db.json(job)))


def read(document_id, job_id):
    with connection() as db:
        row = db.execute('SELECT payload FROM aps_jobs WHERE document_id=? AND id=?',
                         (document_id, job_id)).fetchone()
    if not row:
        raise FileNotFoundError('Tác vụ APS không tồn tại trong tài liệu này.')
    return decode(row[0])


def list_jobs(document_id):
    with connection() as db:
        return [decode(row[0]) for row in db.execute(
            'SELECT payload FROM aps_jobs WHERE document_id=? ORDER BY created DESC LIMIT 100', (document_id,))]


def artifact(job_id, name, path, digest):
    with connection() as db:
        db.execute('INSERT INTO aps_artifacts VALUES (?,?,?,?) ON CONFLICT(job_id,name) DO UPDATE SET sha256=excluded.sha256,bytes=excluded.bytes',
                   (job_id, name, digest, Path(path).stat().st_size))
