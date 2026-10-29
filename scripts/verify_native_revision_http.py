"""Verify ready native revision download, preview, undo/redo and stale rejection."""
import hashlib,json
from pathlib import Path
import sys
import requests

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from cad.edit_engine import digest
    evidence=ROOT/'storage/validation-fixtures/native-revision-release-2026-10-22'
    dispatch=json.loads((evidence/'dispatch.json').read_text());rid=dispatch['revision']['id'];doc=dispatch['revision']['document_id']
    session=requests.Session();session.trust_env=False
    base=f'http://127.0.0.1:8765/documents/{doc}/autocad'
    def get(path):
        r=session.get(base+path,timeout=120);r.raise_for_status();return r.json()
    ready=get('/relationship-revisions/'+rid)
    assert ready['status']=='ready' and ready['adapter']=='native_pointrefs'
    assert ready['validation']['native_b_isolation']['challenge_count']==4 and len(ready['validation']['challenges'])==8
    h=get('/relationship-history');assert h['active_revision_id']==rid
    files={}
    for name in ['modified.dwg','modified.dxf']:
        response=session.get(base+f'/relationship-revisions/{rid}/files/{name}',timeout=60);response.raise_for_status()
        actual=hashlib.sha256(response.content).hexdigest();assert actual==ready['artifact_hashes'][name]
        files[name]=actual
    preview=session.get(base+f'/relationship-revisions/{rid}/preview',timeout=120);preview.raise_for_status();assert '<svg' in preview.text
    (evidence/'active-preview.svg').write_text(preview.text,encoding='utf8')
    undo=session.post(base+'/relationship-history/undo',json=dict(expected_version=h['version']),timeout=60);undo.raise_for_status()
    u=undo.json();assert u['active_revision_id']==ready['base_revision_id']
    stale=session.post(base+'/relationship-history/redo',json=dict(expected_version=h['version']),timeout=60);assert stale.status_code==422
    # A native proposal cannot run while its base is not the selected revision.
    redo=session.post(base+'/relationship-history/redo',json=dict(expected_version=u['version']),timeout=60);redo.raise_for_status();after=redo.json();assert after['active_revision_id']==rid
    wrong_base=session.post(base+'/relationship-proposals/'+dispatch['proposal']['id']+'/apply',json=dict(expected_version=after['version']),timeout=120)
    assert wrong_base.status_code==422 and 'base revision' in wrong_base.text
    source=ROOT/'storage/documents'/doc/'original.dwg';assert digest(source)==ready['source_hash']
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=True,encoding='utf-8-sig')
    from backend.services.database_service import connection
    with connection() as db:
        recovering=db.execute('SELECT pg_is_in_recovery()').fetchone()[0];assert not recovering
        row=db.execute('SELECT status,output_hash FROM cad_revisions WHERE document_id=? AND id=?',(doc,rid)).fetchone()
        assert row and tuple(row)==('ready',files['modified.dwg'])
        indexed=db.execute('SELECT sha256,kind FROM cad_files WHERE document_id=? AND revision_id=?',(doc,rid)).fetchall()
        assert (files['modified.dwg'],'dwg_preview') in [tuple(x) for x in indexed]
    result=dict(status='verified_native_revision_http_undo_redo_database',revision_id=rid,download_sha256=files,
        history_before=h,history_after=after,undo_base_revision=u['active_revision_id'],stale_version_status=stale.status_code,
        wrong_active_base_status=wrong_base.status_code,postgres_in_recovery=recovering,source_unchanged=True,
        validated_challenges=12,preview_svg=True,revision_status=ready['status'])
    (evidence/'http-undo-redo.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))


if __name__=='__main__':main()
