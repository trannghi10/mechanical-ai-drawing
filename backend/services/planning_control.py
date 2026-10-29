"""Per-request CPU budget, progress and cancellation; no CAD execution here."""
import asyncio
import time
import threading
from contextvars import ContextVar
from contextlib import contextmanager

CURRENT=ContextVar('planning_control',default=None)


class Cancelled(Exception):pass


class Control:
    def __init__(self,progress,seconds=None):
        import os
        self.progress=progress;self.seconds=seconds or int(os.environ.get('PLANNING_TIMEOUT_SECONDS','300'));self.started=time.monotonic()
        self.cancelled=threading.Event();self.lock=threading.Lock();self.abort=None

    def check(self):
        if self.cancelled.is_set():raise Cancelled()

    def remaining(self):
        self.check()
        from backend.services.gemini_service import AIError
        remaining=self.seconds-(time.monotonic()-self.started)
        if remaining<=0:raise AIError(504,'Đã hết thời gian phân tích. Chưa tạo bản sửa; hãy xem phạm vi hoặc yêu cầu cần bổ sung.')
        return remaining

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.abort:self.abort()

    async def run(self,coroutine):
        loop=asyncio.get_running_loop();task=asyncio.create_task(coroutine)
        with self.lock:
            self.abort=lambda:loop.call_soon_threadsafe(task.cancel)
            if self.cancelled.is_set():task.cancel()
        try:return await asyncio.wait_for(task,self.remaining())
        except asyncio.CancelledError as error:raise Cancelled() from error
        except asyncio.TimeoutError as error:
            from backend.services.gemini_service import AIError
            raise AIError(504,'Đã hết ngân sách thời gian phân tích AI; chưa tạo bản sửa.') from error
        finally:
            with self.lock:self.abort=None


def progress(phase,message,**details):
    control=CURRENT.get()
    if control:
        control.check();control.progress(phase,message,**details)


def remaining(default=120):
    control=CURRENT.get()
    return control.remaining() if control else default


@contextmanager
def bounded():
    control=Control(lambda *a,**kw:None);token=CURRENT.set(control)
    try:yield
    finally:CURRENT.reset(token)
