"""Recover a stalled model transfer with bounded, checksum-verified range requests."""
import argparse
import hashlib
from pathlib import Path
import time
import requests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    a = p.parse_args()
    partial = a.output.with_suffix('.range-part')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(a.url, headers={'Range': 'bytes=0-0'}, timeout=(20, 45)) as r:
        r.raise_for_status()
        if r.status_code != 206:
            raise ValueError('Server must support ranges')
        total = int(r.headers['Content-Range'].split('/')[-1])
    offset = partial.stat().st_size if partial.exists() else 0
    with partial.open('ab') as f:
        while offset < total:
            end = min(total - 1, offset + 32 * 1024 * 1024 - 1)
            for attempt in range(3):
                try:
                    with requests.get(a.url, headers={'Range': f'bytes={offset}-{end}'}, timeout=(20, 45)) as r:
                        r.raise_for_status()
                        if r.status_code != 206 or r.headers.get('Content-Range') != f'bytes {offset}-{end}/{total}':
                            raise ValueError('Unexpected range response')
                        data = r.content
                    if len(data) != end - offset + 1:
                        raise ValueError('Incomplete range')
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2)
            f.write(data); f.flush(); offset += len(data)
            print(f'{offset}/{total} bytes ({offset/total:.1%})', flush=True)
    with partial.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if actual.lower() != a.sha256.lower():
        raise ValueError('Model checksum mismatch')
    partial.replace(a.output)
    print('Verified model:', a.output, flush=True)


if __name__ == '__main__':
    main()
