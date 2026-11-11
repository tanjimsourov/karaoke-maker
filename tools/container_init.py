"""Prepare only karaoke output and owned runtime volume roots before the batch."""
import os
import json
from pathlib import Path

def initialize(media=Path('/media'), app=Path('/app'), uid=None, gid=None):
    uid=int(os.getenv('KARAOKE_UID','10001')) if uid is None else uid
    gid=int(os.getenv('KARAOKE_GID','10001')) if gid is None else gid
    if uid<1 or gid<1:raise ValueError('Processing requires a non-root UID/GID')
    if not media.is_dir():raise ValueError('The configured input folder does not exist')
    media_roots=[media]+[Path(v) for v in json.loads(os.getenv('KARAOKE_EXTRA_INPUT_DIRS','[]'))]
    if any(not p.is_dir() for p in media_roots):raise ValueError('An additional input folder does not exist')
    targets=[p/'karaoke' for p in media_roots]+[app/name for name in ('models','work','out','reports','tmp')]
    for target in targets:
        if target.is_symlink():raise ValueError('Refusing linked writable directory: '+str(target))
        target.mkdir(parents=True,exist_ok=True)
        if target.resolve().parent!=target.parent.resolve():raise ValueError('Unsafe writable directory')
        os.chown(target,uid,gid)
        target.chmod(0o775)
    print('Karaoke output folder and runtime volumes ready.',flush=True)

if __name__=='__main__':initialize()
