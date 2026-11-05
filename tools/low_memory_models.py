"""Value-preserving checkpoint mapping reused from the working bridge."""
from contextlib import contextmanager
from pathlib import Path
import os


@contextmanager
def mapped_checkpoint_load(torch, checkpoint):
    checkpoint=Path(checkpoint).resolve(); original=torch.load
    def load(path,*args,**kwargs):
        if isinstance(path,(str,os.PathLike)) and Path(path).resolve()==checkpoint:
            kwargs.setdefault('mmap',True)
        return original(path,*args,**kwargs)
    torch.load=load
    try: yield
    finally: torch.load=original
