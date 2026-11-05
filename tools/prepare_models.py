"""Download and load the normal English-song model set inside this project.

Run with .venv-zoom Python. Workers release memory between models. Re-running
reuses library-verified caches. No song is processed by this command.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from project_runtime import ROOT, MODELS, DEMUCSPY, child_env


def worker(name):
    if name == 'demucs':
        from demucs.pretrained import get_model
        get_model('htdemucs_ft')
    elif name in ('whisper', 'asr'):
        from faster_whisper import WhisperModel
        WhisperModel('large-v3-turbo' if name == 'whisper' else 'base',
                     device='cpu', compute_type='int8', cpu_threads=2,
                     download_root=str(MODELS/'whisper'),
                     local_files_only=os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD','1')!='1')
    elif name == 'align':
        import torch
        import whisperx
        from low_memory_models import mapped_checkpoint_load
        checkpoint = Path(torch.hub.get_dir())/'checkpoints/wav2vec2_fairseq_large_lv60k_asr_ls960.pth'
        if os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD','1')!='1' and not checkpoint.is_file():
            raise ValueError('Alignment model missing in offline mode')
        with mapped_checkpoint_load(torch, checkpoint):
            whisperx.load_align_model(language_code='en', device='cpu',
                                     model_name='WAV2VEC2_ASR_LARGE_LV60K_960H')
    elif name == 'detector':
        from audio_quality import VoiceDetector
        VoiceDetector({'threads': 2})
    elif name == 'uvr':
        from uvr_instrumental import NAME, URL, SHA, digest
        path = MODELS/'uvr'/NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or digest(path) != SHA:
            if os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD','1')!='1':
                raise ValueError('UVR model missing or corrupt in offline mode')
            partial = path.with_suffix('.partial')
            with urllib.request.urlopen(URL, timeout=60) as src, partial.open('wb') as dst:
                while block := src.read(1024*1024):
                    dst.write(block)
            if digest(partial) != SHA:
                raise ValueError('UVR checksum mismatch')
            partial.replace(path)
        import onnxruntime as ort
        ort.InferenceSession(str(path), providers=['CPUExecutionProvider'])


def main():
    names = ['demucs', 'whisper', 'asr', 'align', 'detector', 'uvr']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=names)
    parser.add_argument('--offline',action='store_true',help='Verify cached models without network downloads')
    args = parser.parse_args()
    if args.offline:
        os.environ.update(KARAOKE_ALLOW_MODEL_DOWNLOAD='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    if args.worker:
        worker(args.worker)
        return
    MODELS.mkdir(parents=True, exist_ok=True)
    report = {}
    for name in names:
        print('Preparing', name, flush=True)
        command = [str(DEMUCSPY) if name == 'demucs' else sys.executable,
                   str(Path(__file__).resolve()), '--worker', name]
        for attempt in range(2):
            result = subprocess.run(command, env=child_env())
            if result.returncode == 0:
                break
        report[name] = {'loaded': result.returncode == 0, 'time': time.time()}
        (MODELS/'preparation.json').write_text(json.dumps(report, indent=2))
        if result.returncode:
            raise SystemExit(result.returncode)
    for name, python in [('zoom', sys.executable), ('demucs', str(DEMUCSPY))]:
        with (ROOT/'config'/('environment-'+name+'.freeze.txt')).open('w') as out:
            subprocess.run([python, '-m', 'pip', 'freeze'], check=True, stdout=out)
    print('All English-song models downloaded and loaded successfully.', flush=True)


if __name__ == '__main__':
    main()
