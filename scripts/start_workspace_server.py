"""Start only this project's server in a detached Windows background process."""
import os,socket,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with socket.socket() as probe:
    probe.settimeout(.5)
    if probe.connect_ex(('127.0.0.1',8765))==0:
        print('Server already listening on 127.0.0.1:8765');sys.exit(0)
logs=root/'storage'/'logs';logs.mkdir(exist_ok=True)
with (logs/'workspace-server.log').open('ab') as out,(logs/'workspace-server-error.log').open('ab') as err:
    p=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8765'],
                       cwd=root,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                       creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
print(p.pid)
