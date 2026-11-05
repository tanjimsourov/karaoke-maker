"""One local heavy-model job at a time; OS releases the lock after a crash."""
from contextlib import contextmanager
import errno
import os
import re
from pathlib import Path
import time
from project_runtime import ROOT


@contextmanager
def model_slot(root=ROOT, timeout=14400, name='model'):
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}',name):raise ValueError('Invalid processing slot name')
    path=Path(root)/f'work/.{name}-runtime.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0,os.SEEK_END)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        deadline=time.monotonic()+timeout
        announced=False
        while True:
            try:
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):raise
                if time.monotonic()>=deadline:raise TimeoutError('Another model job holds the processing slot') from exc
                if not announced:print(f'Queued: waiting for the current local {name} job.',flush=True);announced=True
                time.sleep(min(1,max(0,deadline-time.monotonic())))
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_UN)
