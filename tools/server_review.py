"""Resume a held server job using the exact original work and export directories."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('identity',help='20-character ID from .karaoke-status/<ID>.json')
    p.add_argument('stage',choices=['status','lyrics-review','align','preview','verify','approve','render','edit','check-timing'])
    args,extra=p.parse_known_args()
    if not re.fullmatch(r'[a-f0-9]{20}',args.identity):p.error('Invalid job identity')
    root=Path(__file__).resolve().parents[1]
    output=Path(os.environ.get('KARAOKE_SERVER_OUTPUT_DIR','/media/karaoke'))
    spec=output/'.karaoke-status'/(args.identity+'.job.json')
    if not spec.is_file():p.error('Saved job missing: '+str(spec))
    runtime=root/'work/server-jobs'/args.identity
    env={**os.environ,'KARAOKE_WORK_DIR':str(runtime/'jobs'),
         'KARAOKE_OUTPUT_DIR':str(runtime/'exports'),'KARAOKE_RENDER_WORK_DIR':str(runtime/'render'),
         'KARAOKE_CLEANUP_AFTER_SONG':'0','KARAOKE_SERVER_CONCURRENT':'1',
         'TMPDIR':str(runtime/'tmp'),'TEMP':str(runtime/'tmp'),'TMP':str(runtime/'tmp')}
    return subprocess.call([sys.executable,str(root/'karaoke.py'),args.stage,'--job',str(spec),'--keep-work',*extra],env=env)


if __name__=='__main__':raise SystemExit(main())
