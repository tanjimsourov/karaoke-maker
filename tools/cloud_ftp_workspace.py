"""Prepare/run the existing converter on a cloud Linux host, never on Windows."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def cloud_only():
    if os.name=='nt' or not (Path('/content').is_dir() or os.getenv('KARAOKE_CLOUD_HOST')=='1'):
        raise RuntimeError('Execute on Colab/your cloud Linux host, not the local PC')


def environment():
    env={**os.environ,'KARAOKE_PROJECT_ROOT':str(ROOT),'KARAOKE_MODEL_DIR':str(ROOT/'models'),
         'KARAOKE_DEMUCS_PYTHON':str(ROOT/'.venv-demucs/bin/python'),
         'KARAOKE_LOGO':str(ROOT/'assets/logo-karaoke-cmyk-transparent.png'),
         'KARAOKE_FFMPEG_THREADS':'2','KARAOKE_EXTRA_INPUT_DIRS':'[]',
         'TMPDIR':str(ROOT/'tmp')}
    for name in ('models','tmp'): (ROOT/name).mkdir(exist_ok=True)
    for font in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
        if Path(font).is_file():env['KARAOKE_FONT']=font;break
    else:raise RuntimeError('Install fonts-dejavu-core or fonts-liberation first')
    if not shutil.which('ffmpeg'):raise RuntimeError('FFmpeg is missing from the cloud host')
    return env


def check_hardware(env,compute):
    python=ROOT/'.venv-zoom/bin/python'
    for name in ('.venv-zoom','.venv-demucs'):
        command=['import torch; ']
        command.append("assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.cuda.get_device_name(0))"
                       if compute=='cuda' else "print('CPU',torch.__version__)")
        subprocess.run([str(ROOT/name/'bin/python'),'-c',''.join(command)],env=env,check=True)
    subprocess.run([str(python),str(ROOT/'karaoke.py'),'doctor'],cwd=ROOT,env=env,check=True)


def setup(compute):
    cloud_only();env=environment()
    key=hashlib.sha256((compute+''.join((ROOT/name).read_text() for name in
        ('setup.py','requirements-zoom.txt','requirements-demucs.txt'))).encode()).hexdigest()
    receipt=ROOT/'models/cloud-setup.json'
    if receipt.exists() and json.loads(receipt.read_text()).get('key')==key:
        check_hardware(env,compute);print('[SETUP REUSED]',flush=True);return
    if compute=='cuda':
        subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'],check=True)
    if not shutil.which('uv'):subprocess.run([sys.executable,'-m','pip','install','uv'],check=True)
    subprocess.run([sys.executable,'-m','uv','python','install','3.11'],check=True)
    command=[sys.executable,'-m','uv','run','--python','3.11','python',str(ROOT/'setup.py')]
    if compute=='cuda':command+=['--cuda','cu128']
    subprocess.run(command,cwd=ROOT,env=env,check=True)
    check_hardware(env,compute)
    receipt.write_text(json.dumps({'key':key,'compute':compute}))
    print('[CLOUD WORKSPACE READY]',compute,flush=True)


def run(config_path,compute):
    cloud_only();env=environment();check_hardware(env,compute)
    config=json.loads(config_path.read_text(encoding='utf-8-sig'))
    config['require_gpu']=compute=='cuda'
    for name in (config.get('user_env','KARAOKE_FTP_USER'),config.get('password_env','KARAOKE_FTP_PASSWORD')):
        if not env.get(name):raise RuntimeError('Missing cloud credential variable: '+name)
    env['KARAOKE_DEVICE']=compute
    # Runtime config contains paths/settings only; credentials stay in memory.
    runtime_config=ROOT/'tmp/ftp-cloud-runtime.json'
    runtime_config.write_text(json.dumps(config))
    try:
        return subprocess.run([str(ROOT/'.venv-zoom/bin/python'),'-u',str(ROOT/'tools/ftp_cloud_batch.py'),
            '--config',str(runtime_config)],cwd=ROOT,env=env).returncode
    finally:runtime_config.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','run'])
    parser.add_argument('--compute',choices=['cuda','cpu'],default='cuda')
    parser.add_argument('--config',type=Path,default=ROOT/'config/ftp-mp3-danish.json')
    args=parser.parse_args()
    if args.action=='setup':setup(args.compute);return 0
    return run(args.config.resolve(),args.compute)


if __name__=='__main__':raise SystemExit(main())
