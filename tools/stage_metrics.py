"""Append real stage timings, including failures and cache-return invocations."""
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import json
import os
import time
import gc
import sys

@contextmanager
def measure(folder, stage):
    started=time.perf_counter()
    outcome='completed'
    try:
        yield
    except BaseException:
        outcome='interrupted_or_failed'
        raise
    finally:
        folder.mkdir(parents=True,exist_ok=True)
        row={'stage':stage,'wall_seconds':time.perf_counter()-started,
             'finished_utc':datetime.now(timezone.utc).isoformat(),'outcome':outcome,
             'pid':os.getpid(),'resident_models_enabled':os.environ.get('KARAOKE_KEEP_MODELS')=='1',
             'note':'Includes cache validation; a fast call is not evidence of fresh inference.'}
        with (folder/'stage-metrics.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(row)+'\n')

def call(folder,stage,fn,*args,**kwargs):
    started=time.perf_counter()
    print(f'[START] {stage}',flush=True)
    try:
        slots=os.environ.get('KARAOKE_CLOUD_GPU_SLOTS')
        guarded=bool(slots and os.environ.get('KARAOKE_DEVICE')=='cuda' and
                     stage in ('separation','audio_screening','transcription_or_import','alignment'))
        if guarded:
            from model_queue import resource_slots
            gate=resource_slots('cloud-gpu-stage',slots=int(slots))
        else:gate=nullcontext()
        with measure(folder,stage),gate:
            try:result=fn(*args,**kwargs)
            finally:
                if guarded:
                    gc.collect()
                    torch=sys.modules.get('torch')
                    if torch is not None and torch.cuda.is_initialized():torch.cuda.empty_cache()
    except BaseException as exc:
        print(f'[STOP] {stage}: {exc}',flush=True)
        raise
    print(f'[DONE] {stage} ({time.perf_counter()-started:.1f}s)',flush=True)
    return result
