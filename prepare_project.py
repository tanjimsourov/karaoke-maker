"""Resumable CPU preparation; run with Python 3.11 from any directory.

Installs project-local environments, preloads models, and runs the checks. Keeps
installation logs and downloaded wheels inside tmp; never deletes job data.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent


def download(url, path):
    partial = path.with_suffix(path.suffix+'.partial')
    for attempt in range(2):
        try:
            with urllib.request.urlopen(url, timeout=60) as src, partial.open('wb') as dst:
                expected = int(src.headers['Content-Length'])
                while block := src.read(1024*1024):
                    dst.write(block)
            if partial.stat().st_size != expected:
                raise ValueError('Incomplete wheel download')
            partial.replace(path)
            return
        except Exception:
            if attempt: raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-installed', action='store_true',
                        help='Reuse installed environments; load models and run checks')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        raise SystemExit('Run with Python 3.11')
    def run(command):
        print(subprocess.list2cmdline(list(map(str,command))), flush=True)
        subprocess.run(list(map(str,command)), cwd=ROOT, check=True,
                       env={**os.environ, 'PIP_DISABLE_PIP_VERSION_CHECK':'1'})
    if os.name == 'nt' and not args.verify_installed:
        # Official CPU wheels; avoids a stalled streaming download in pip here.
        wheels = ROOT/'tmp/wheels'; wheels.mkdir(parents=True, exist_ok=True)
        for package in ('torch', 'torchaudio'):
            filename = package+'-2.8.0+cpu-cp311-cp311-win_amd64.whl'
            path = wheels/filename
            if not path.exists():
                download('https://download.pytorch.org/whl/cpu/'+filename.replace('+','%2B'),path)
            # ZIP validation detects incomplete or damaged transfers before install.
            import zipfile
            with zipfile.ZipFile(path) as archive:
                if archive.testzip(): raise ValueError('Corrupt wheel: '+str(path))
        import venv
        for envname in ('.venv-zoom', '.venv-demucs'):
            python = ROOT/envname/'Scripts/python.exe'
            if not python.exists(): venv.create(ROOT/envname, with_pip=True)
            run([python,'-m','pip','install',*sorted(wheels.glob('*.whl'))])
    if not args.verify_installed:
        run([sys.executable,ROOT/'setup.py'])
    python = ROOT/'.venv-zoom'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    run([python,ROOT/'tools/prepare_models.py'])
    run([python,'-m','unittest','discover','-s','tools','-p','test_*.py'])
    run([python,ROOT/'karaoke.py','doctor'])
    (ROOT/'models/project-ready.json').write_text(json.dumps({
        'environment_and_models_ready':True, 'full_song_conversion_verified':False,
        'note':'Song processing and listening/lyric review remain separate.'},indent=2))


if __name__ == '__main__': main()
