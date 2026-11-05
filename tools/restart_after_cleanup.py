"""Start the fresh REI job only after old work/tmp have been manually cleared.

This script never deletes data. It waits up to four hours for the user's cleanup.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from project_runtime import ROOT, child_env
from model_queue import model_slot


def generated_data_cleared(root=ROOT):
    return all(not path.exists() or (path.is_dir() and not any(path.iterdir()))
               for path in [Path(root)/'work',Path(root)/'tmp'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',type=Path,default=ROOT/'config/rei-ami-2loud.json')
    p.add_argument('--hours',type=float,default=4)
    args=p.parse_args();job=args.job.resolve()
    data=json.loads(job.read_text(encoding='utf-8'))
    if data.get('render',{}).get('fps',0)<30:raise ValueError('Fresh job needs at least 30 fps')
    source=(job.parent/data['source']).resolve()
    if not source.is_file():raise ValueError('Downloaded source is missing')
    deadline=time.monotonic()+args.hours*3600
    while not generated_data_cleared():
        if time.monotonic()>=deadline:return 2
        time.sleep(2)
    # Nothing from an earlier processing attempt is reused. Persistent models
    # and the original downloaded MP4 are intentionally retained.
    logs=ROOT/'tmp';logs.mkdir(parents=True,exist_ok=True)
    with model_slot(), (logs/'rei-fresh-process.log').open('w',encoding='utf-8') as log:
        print('Starting fresh source processing at 1080p/30fps/CRF14.',file=log,flush=True)
        result=subprocess.run([sys.executable,str(ROOT/'karaoke.py'),'run','--job',str(job)],
            stdout=log,stderr=subprocess.STDOUT,env=child_env())
        print('Process exit:',result.returncode,file=log,flush=True)
        return result.returncode


if __name__=='__main__':raise SystemExit(main())
