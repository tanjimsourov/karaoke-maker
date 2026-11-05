"""Wait for a completed MP4 download, then start the normal resumable workflow.

Does not approve lyrics/listening or delete data. Resume with the printed job.
"""
import argparse
import json
from pathlib import Path
import subprocess
import struct
import sys
import time
from project_runtime import ROOT, FFMPEG, child_env
from model_queue import model_slot


def complete_mp4(path):
    """Reject a paused download whose declared MP4 atoms extend beyond EOF."""
    size = path.stat().st_size
    seen = set()
    with path.open('rb') as stream:
        offset = 0
        while offset < size:
            stream.seek(offset)
            header = stream.read(8)
            if len(header) != 8: return False
            length, kind = struct.unpack('>I4s', header)
            header_size = 8
            if length == 1:
                extended = stream.read(8)
                if len(extended) != 8: return False
                length, = struct.unpack('>Q', extended)
                header_size = 16
            elif length == 0:
                length = size-offset
            if length < header_size or offset+length > size: return False
            seen.add(kind)
            offset += length
    return {b'ftyp', b'moov', b'mdat'} <= seen


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job', type=Path, required=True)
    p.add_argument('--hours', type=float, default=4)
    args = p.parse_args()
    job = args.job.resolve()
    data = json.loads(job.read_text(encoding='utf-8'))
    source = (job.parent/data['source']).resolve()
    until = time.monotonic()+args.hours*3600
    previous, stable_since = None, time.monotonic()
    while time.monotonic() < until:
        current = (source.stat().st_size, source.stat().st_mtime_ns) if source.exists() else None
        if current != previous:
            previous, stable_since = current, time.monotonic()
            print('Download bytes:', current[0] if current else 0, flush=True)
        if current and current[0] > 1024 and time.monotonic()-stable_since >= 60 and complete_mp4(source):
            check = subprocess.run([str(FFMPEG), '-v','error','-xerror','-nostdin',
                '-i',str(source),'-map','0:v:0','-map','0:a:0','-f','null','-'],
                capture_output=True, timeout=600)
            unchanged = (source.stat().st_size,source.stat().st_mtime_ns) == current
            if check.returncode == 0 and unchanged:
                print('Complete source decoded. Starting:', job, flush=True)
                with model_slot():
                    return subprocess.run([sys.executable,str(ROOT/'karaoke.py'),
                        'run','--job',str(job)],env=child_env()).returncode
            print('Not a complete decodable video yet:', check.stderr[-500:].decode(errors='replace'),flush=True)
            stable_since = time.monotonic()
        time.sleep(15)
    print('Download wait expired. Run this command again to resume.', flush=True)
    return 2


if __name__ == '__main__': raise SystemExit(main())
