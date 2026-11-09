"""Run the two selected FTP songs through the existing image-background workflow."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def available_memory():
    import ctypes
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total', 'page_available',
                                                  'virtual_total', 'virtual_available', 'extended')]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise OSError('Cannot check available memory')
    return memory.available


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--wait-minutes', type=int, default=45)
    parser.add_argument('--require-model', type=Path)
    parser.add_argument('--wait-pid', type=int)
    args = parser.parse_args()
    root = args.root.resolve()
    report = root / 'tmp/ftp-image-batch'
    report.mkdir(parents=True, exist_ok=True)
    status = {'state': 'waiting_for_dependencies_and_downloads', 'songs': []}
    def save():
        (report / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    save()
    python = root / '.venv-zoom/Scripts/python.exe'
    demucs = root / '.venv-demucs/Scripts/python.exe'
    selections = [('ftp-the-second-you-sleep.json', 15667811), ('ftp-human.json', 9014631)]
    deadline = time.monotonic() + args.wait_minutes * 60
    if args.wait_pid:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x100000, False, args.wait_pid)
        if handle:
            try:
                while kernel.WaitForSingleObject(handle, 15000) == 258:
                    if time.monotonic() >= deadline:
                        status['state'] = 'prior_process_wait_timeout'; save(); return 2
            finally:
                kernel.CloseHandle(handle)
    with (report / 'readiness.log').open('a', encoding='utf-8') as log:
        while True:
            ready = python.is_file() and demucs.is_file()
            if args.require_model:
                ready = ready and args.require_model.is_file()
            ready = ready and available_memory() >= 4 * 1024**3
            for filename, size in selections:
                job = json.loads((root / 'config' / filename).read_text(encoding='utf-8-sig'))
                source = Path(job['source'])
                ready = ready and source.is_file() and source.stat().st_size == size
            if ready:
                ready = all(subprocess.run([str(exe), '-c', code], stdout=log, stderr=log).returncode == 0
                            for exe, code in [(python, 'import whisperx, numpy, PIL, rapidocr_onnxruntime'),
                                              (demucs, 'import demucs, torch, torchaudio, numpy')])
            if ready:
                break
            if time.monotonic() >= deadline:
                status['state'] = 'blocked_dependencies_or_download'; save(); return 2
            time.sleep(15)
    env = {**os.environ, 'KARAOKE_LOGO': str(root / 'assets/logo-karaoke-cmyk-transparent.png'),
           'KARAOKE_OUTPUT_DIR': str(root / 'out/ftp-image-backgrounds'),
           'KARAOKE_FFMPEG_THREADS': '4', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
           'KARAOKE_DISABLE_MKLDNN': '1'}
    status['state'] = 'processing'; save()
    for filename, _ in selections:
        while available_memory() < 4 * 1024**3:
            status['state'] = 'waiting_for_4GB_free_RAM'; save()
            if time.monotonic() >= deadline:
                return 2
            time.sleep(15)
        status['state'] = 'processing'; save()
        job_path = root / 'config' / filename
        job = json.loads(job_path.read_text(encoding='utf-8-sig'))
        row = {'song': job['artist'] + ' - ' + job['title'], 'state': 'verifying_source'}
        status['songs'].append(row); save()
        started = time.monotonic()
        with (report / (job_path.stem + '.log')).open('a', encoding='utf-8') as log:
            result = subprocess.run([str(root / 'tools/ffmpeg/ffmpeg.exe'), '-v', 'error', '-xerror',
                                     '-i', job['source'], '-f', 'null', '-'], stdout=log, stderr=log)
            if result.returncode == 0:
                row['state'] = 'processing'; save()
                result = subprocess.run([str(python), '-u', str(root / 'karaoke.py'), 'run',
                                         '--job', str(job_path), '--draft-export'], cwd=root,
                                        env=env, stdout=log, stderr=subprocess.STDOUT)
        row.update(state='workflow_completed_draft' if result.returncode == 0 else 'failed',
                   exit_code=result.returncode, elapsed_seconds=round(time.monotonic()-started, 1))
        save()
    status['state'] = 'completed_drafts' if all(s['exit_code'] == 0 for s in status['songs']) else 'needs_attention'
    save()
    return 0 if status['state'] == 'completed_drafts' else 2


if __name__ == '__main__':
    raise SystemExit(main())
