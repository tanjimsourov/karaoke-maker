"""Two preparation workers; one model job at a time with bounded warm reuse."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import time
from project_runtime import ROOT
from workflow import normalize,preflight,main as workflow_main
from zoom_local_pipeline import read,save

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--stage',choices=['run','separate','audio-qc','transcribe','align','preview','quick-preview'],default='run')
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();started=time.perf_counter()
    raw=read(a.manifest);jobs=raw.get('jobs') if isinstance(raw,dict) else raw
    if not isinstance(jobs,list) or not jobs:raise ValueError('Manifest must contain job objects')
    prepared=[normalize({**j,'profile':'optimized'},a.manifest.resolve().parent) for j in jobs]
    def prepare(pair):
        job,folder=pair
        from workflow import lock
        with lock(folder):preflight(job,folder)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(prepare,prepared))
    # The existing manifest workflow catches per-song failures and saves states.
    previous=sys.argv
    try:
        sys.argv=['karaoke.py',a.stage,'--manifest',str(a.manifest.resolve()),'--profile','optimized','--warm-models']
        code=workflow_main()
    finally:sys.argv=previous
    save(a.report,{'wall_seconds':time.perf_counter()-started,'exit_code':code,
        'jobs':len(jobs),'stage':a.stage,'heavy_concurrency':1,'preparation_concurrency':2,
        'note':'run stops for lyric review; this is not time to approved delivery.'})
    return code

if __name__=='__main__':raise SystemExit(main())
