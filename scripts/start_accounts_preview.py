"""Isolated loopback UI test; never creates production users or opens LAN."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


if len(sys.argv)==3 and sys.argv[1]=='--serve':
    from backend.main import app
    from backend.services import catalog_service as storage
    directory=Path(sys.argv[2]).resolve()
    if not directory.is_relative_to(ROOT/'storage/validation-fixtures'):raise ValueError('Preview must be isolated')
    os.environ.pop('DATABASE_URL',None);os.environ.pop('CAD_REQUIRE_LOGIN',None)
    storage.ROOT=directory/'documents';storage.ROOT.mkdir(parents=True,exist_ok=True)
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8766)
else:
    with socket.socket() as probe:
        probe.settimeout(.5)
        if probe.connect_ex(('127.0.0.1',8766))==0:raise ValueError('Preview port 8766 is already in use')
    directory=ROOT/'storage/validation-fixtures'/('accounts-ui-'+uuid.uuid4().hex[:12]);directory.mkdir()
    with (directory/'stdout.log').open('ab') as out,(directory/'stderr.log').open('ab') as err:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(directory)],cwd=ROOT,
            stdin=subprocess.DEVNULL,stdout=out,stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS,
            env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    print(process.pid,str(directory.relative_to(ROOT)),flush=True)
