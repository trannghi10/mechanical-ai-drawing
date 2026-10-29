"""Start the pinned, installed vision model without downloading or sending CAD."""
import os
import socket
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
MERGED = 'sha256-16b83be682148a4d8201dbf720ea7eace5de98b69f63f05e0c908b4d7977ecb5'
MODEL = 'sha256-9a5751654a9a0fd2ddd372906dd815519ef041213e8b2e22a142fc073f4a8b7a'
PROJECTOR = 'sha256-84a6711ca18f2e26fa5ed1dfacff4404def73ba0ea47b16b746720d5246498ba'
MODEL_FILES = (MERGED, MODEL)
_lock = threading.Lock()
_process = None


def installed_files():
    runtime = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/lib/ollama/llama-server.exe'
    blobs = Path(os.environ.get('USERPROFILE', str(Path.home()))) / '.ollama/models/blobs'
    if not runtime.is_file():
        raise ValueError('Không tìm thấy llama-server.exe trong Ollama đã cài trên máy.')
    # Ollama may migrate the combined vision GGUF into separate model/projector files.
    for model, projector in ((MODEL, PROJECTOR), (MERGED, MERGED)):
        if (blobs / model).is_file() and (blobs / projector).is_file():
            return runtime, blobs / model, blobs / projector
    raise ValueError('Thiếu file Qwen3-VL 4B hoặc file xử lý ảnh trên máy. Không tự tải model; kiểm tra thư mục Ollama models.')


def start():
    """Idempotent while loading, including across backend restarts on the same port."""
    global _process
    from backend.services.native_ai_service import settings, status
    base, _ = settings()
    url = urlsplit(base)
    if url.hostname != '127.0.0.1' or url.port != 11436:
        raise ValueError('Khởi động tự động chỉ hỗ trợ runtime nội bộ tại 127.0.0.1:11436.')
    with _lock:
        current = status()
        if current['ready'] or current.get('state') == 'loading':
            return current
        if current.get('state') == 'blocked':
            raise ValueError(current['message'])
        if _process is not None and _process.poll() is None:
            return dict(current, state='loading', message='AI đang nạp model trên máy. Có thể tiếp tục kiểm tra yêu cầu bằng CAD engine.')
        # Do not spawn on an occupied port even when another service is not HTTP.
        try:
            with socket.create_connection(('127.0.0.1', 11436), timeout=1):
                raise ValueError('Cổng 11436 đang được tiến trình khác sử dụng; chưa khởi động AI.')
        except OSError:
            pass
        runtime, model, projector = installed_files()
        if os.name != 'nt':
            raise ValueError('Launcher này dùng runtime Ollama đã cài trên Windows.')
        logs = ROOT / 'storage/runtime'
        logs.mkdir(parents=True, exist_ok=True)
        args = [str(runtime), '--model', str(model), '--mmproj', str(projector),
                '--ctx-size', '8192', '--parallel', '1', '--threads', '6',
                '--batch-size', '128', '--ubatch-size', '128', '--no-repack',
                '--no-warmup', '--no-context-shift', '--host', '127.0.0.1',
                '--port', '11436', '--offline', '--no-webui']
        with (logs / 'native.stdout.log').open('ab') as stdout, (logs / 'native.stderr.log').open('ab') as stderr:
            _process = subprocess.Popen(args, cwd=str(runtime.parent), stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
        return dict(current, state='loading', message='Đã khởi động AI; đang nạp model đọc ảnh. Không cần giữ cửa sổ AI riêng.')


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=True, encoding='utf-8-sig')
    from backend.services.ai_provider import settings
    if settings()[0] == 'native':
        try:
            print(start()['message'])
        except ValueError as error:
            print(str(error))
            raise SystemExit(1)
