"""Portable setup utility, not setuptools packaging. Existing envs are preserved."""
import argparse
import os
import platform
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def python_in(path):
    return path/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cuda', choices=['cu128'], help='Opt-in NVIDIA wheels; CPU is default')
    p.add_argument('--extra-separation', action='store_true')
    p.add_argument('--check', action='store_true', help='Print commands only; no installs')
    args = p.parse_args()
    if sys.version_info[:2] != (3,11): p.error('Use Python 3.11 for the pinned environments')
    if sys.platform == 'darwin' and platform.machine() == 'x86_64':
        p.error('The pinned WhisperX/PyTorch stack requires Apple Silicon on macOS; use a supported Linux/Windows host for Intel Macs')
    if args.cuda and sys.platform=='darwin': p.error('CUDA setup is for NVIDIA hosts on Windows/Linux')
    index = 'https://download.pytorch.org/whl/'+(args.cuda or 'cpu')
    for name, requirement, torch_version in [('.venv-zoom','requirements-zoom.txt','2.8.0'),
                                            ('.venv-demucs','requirements-demucs.txt','2.8.0')]:
        path = ROOT/name; python = python_in(path)
        commands = [[str(python),'-m','pip','install','--upgrade','pip']]
        if torch_version:
            torch_args = ['torch=='+torch_version]
            if name == '.venv-zoom': torch_args.append('torchaudio=='+torch_version)
            wheel_index=[] if sys.platform=='darwin' else ['--index-url',index]
            commands.append([str(python),'-m','pip','install',*wheel_index,*torch_args])
        extra_index=[] if sys.platform=='darwin' else ['--extra-index-url',index]
        commands.append([str(python),'-m','pip','install',*extra_index,'-r',str(ROOT/requirement)])
        if args.extra_separation and name=='.venv-demucs':
            commands.append([str(python),'-m','pip','install','-r',str(ROOT/'requirements-separation-extra.txt')])
        if not args.check and not python.is_file(): venv.create(path, with_pip=True)
        if not args.check and subprocess.run([str(python),'-c',
            'import sys;sys.exit(0 if sys.version_info[:2]==(3,11) else 1)']).returncode:
            raise RuntimeError(f'{path} is not Python 3.11; use a fresh environment')
        for command in commands:
            print(subprocess.list2cmdline(command), flush=True)
            if not args.check: subprocess.run(command, check=True)
    command = [str(python_in(ROOT/'.venv-zoom')),str(ROOT/'karaoke.py'),'doctor']
    if args.check: print(subprocess.list2cmdline(command)); return 0
    if not (ROOT/'.env').exists():
        with (ROOT/'.env').open('x',encoding='utf-8') as out:
            out.write((ROOT/'.env.example').read_text(encoding='utf-8'))
    return subprocess.run(command).returncode


if __name__=='__main__': raise SystemExit(main())
