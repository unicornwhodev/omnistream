"""Serialize task-heavy work and lower only this worker's scheduling priority."""
from contextlib import contextmanager
import ctypes
import math
import os
from pathlib import Path
import time


class ByteRateLimit:
    def __init__(self, bytes_per_second, clock=time.monotonic, sleep=time.sleep):
        if not math.isfinite(bytes_per_second) or bytes_per_second <= 0:
            raise ValueError('I/O rate must be positive')
        self.rate = bytes_per_second
        self.clock, self.sleep = clock, sleep
        self.ready = clock()

    def account(self, count):
        if not math.isfinite(count) or count < 0:
            raise ValueError('Byte count must be finite and non-negative')
        now = self.clock()
        self.ready = max(now, self.ready)+count/self.rate
        self.sleep(max(0,self.ready-now))


def background_mode():
    if os.name != 'nt':
        return False
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.SetPriorityClass.argtypes = [wintypes.HANDLE,wintypes.DWORD]
    kernel.SetPriorityClass.restype = wintypes.BOOL
    if not kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x00100000):
        raise ctypes.WinError(ctypes.get_last_error())
    return True


@contextmanager
def exclusive_heavy_work(workspace):
    """OS lock auto-releases on crash; never a stale PID-based lock."""
    path = Path(workspace)/'heavy-work.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as lock:
        if lock.tell()==0:
            lock.write(b'0');lock.flush()
        lock.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Another scene/extension/render operation owns the host budget') from None
        else:
            import fcntl
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Another scene/extension/render operation owns the host budget') from None
        try:yield
        finally:
            lock.seek(0)
            if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(lock,fcntl.LOCK_UN)
