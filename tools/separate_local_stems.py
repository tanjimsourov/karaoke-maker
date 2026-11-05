"""Demucs worker: run with .venv-demucs, not the WhisperX environment.

Optional extra open models (via the audio-separator package, both far below 7B):
--ensemble      averages Demucs with BS-Roformer (~93M params) for cleaner vocals
                and less vocal bleed in the instrumental.
--keep-backing  splits the vocals into lead and backing with UVR MDX Karaoke 2
                (~30M params) and writes instrumental_with_backing.wav, where the
                backing choir stays in the music and only the lead is removed.
"""
ROFORMER = 'model_bs_roformer_ep_317_sdr_12.9755.ckpt'
KARAOKE = 'UVR_MDXNET_KARA_2.onnx'
import argparse
import json
import os
import random
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
from project_runtime import MODELS
import torch
from demucs.api import Separator
from zoom_local_pipeline import ROOT, FFMPEG, digest, save
from device import best_device


def decode(path, sr, channels, length):
    raw = subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-ar',str(sr),'-ac',str(channels),
                          '-f','f32le','-'],capture_output=True,check=True).stdout
    wave = np.frombuffer(raw,dtype='<f4').reshape(-1,channels).T
    out = np.zeros((channels,length),dtype=np.float32)
    n = min(length,wave.shape[1])
    out[:,:n] = wave[:,:n]  # same timeline as Demucs: pad/trim codec padding only
    return out


def run_audio_separator(model, source, work, sr, channels, length):
    """Returns {'vocals': array, 'instrumental': array} from one audio-separator model."""
    from audio_separator.separator import Separator as UVRSeparator
    work.mkdir(parents=True, exist_ok=True)
    separator = UVRSeparator(output_dir=str(work), model_file_dir=str(MODELS/'audio-separator'),
                             output_format='WAV', sample_rate=sr)
    separator.load_model(model_filename=model)
    stems = {}
    for name in separator.separate(str(source)):
        path = Path(name) if Path(name).is_absolute() else work/name
        key = 'vocals' if '(Vocals)' in path.name else 'instrumental' if '(Instrumental)' in path.name else None
        if key:
            stems[key] = decode(path, sr, channels, length)
    if set(stems) != {'vocals','instrumental'}:
        raise ValueError(f'{model} did not return vocals and instrumental')
    return stems


def write_wav(path, value, gain, sr, channels):
    subprocess.run([str(FFMPEG),'-v','error','-n','-f','f32le','-ar',str(sr),'-ac',str(channels),
                    '-i','-','-c:a','pcm_f32le',str(path)],input=(value.T*gain).astype('<f4').tobytes(),check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--model', choices=['htdemucs_ft','htdemucs'], default='htdemucs_ft')
    p.add_argument('--overlap',type=float,default=.5)
    p.add_argument('--start', type=float, default=0)
    p.add_argument('--seconds', type=float, help='Test excerpt only; never treated as full song')
    p.add_argument('--threads', type=int, default=min(4, os.cpu_count() or 1),
                   help='CPU thread limit; reduce after a native runtime/resource failure')
    p.add_argument('--submodel-index',type=int,choices=range(4),
                   help='Intermediate only: one cached htdemucs_ft component, for process-isolated execution')
    p.add_argument('--seed',type=int,help='Optional reproducible random-shift seed')
    p.add_argument('--random-state-in',type=Path,help='Resume all internal random state from a previous isolated model')
    p.add_argument('--ensemble', action='store_true', help='Average with BS-Roformer for cleaner stems')
    p.add_argument('--keep-backing', action='store_true', help='Keep backing vocals in the instrumental')
    args = p.parse_args()
    if not 0 < args.overlap < 1:
        p.error('--overlap must be between zero and one')
    if args.threads < 1:
        p.error('--threads must be positive')
    if not args.source.is_file() or args.start < 0 or (args.seconds is not None and args.seconds <= 0):
        p.error('Valid source/start/duration required')
    if args.start and args.seconds is None:
        p.error('--start requires --seconds: excerpts must be explicit')
    if args.seed is not None and args.random_state_in is not None:
        p.error('Use seed or random-state-in, not both')
    component=None
    if args.submodel_index is not None:
        if args.model!='htdemucs_ft' or args.ensemble or args.keep_backing:
            p.error('Isolated components require plain htdemucs_ft')
        import yaml
        from huggingface_hub import hf_hub_download
        bag_path=Path(hf_hub_download('adefossez/HTDemucs-ft','htdemucs_ft.yaml',local_files_only=True))
        bag=yaml.safe_load(bag_path.read_text())
        signature=bag['models'][args.submodel_index]
        checkpoint=Path(hf_hub_download('adefossez/HTDemucs-ft',signature+'.safetensors',local_files_only=True))
        component={'index':args.submodel_index,'signature':signature,
                   'checkpoint_sha256':digest(checkpoint),'bag_sha256':digest(bag_path),
                   'execution_version':2}
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = args.output/'separation.json'
    settings = {'source_sha256':digest(args.source), 'model':args.model,
                'start':args.start, 'seconds':args.seconds, 'shifts':1, 'overlap':args.overlap,
                'ensemble':ROFORMER if args.ensemble else None,
                'keep_backing':KARAOKE if args.keep_backing else None}
    if component is not None:settings['component']=component
    if args.seed is not None:settings['shift_seed']=args.seed
    if args.random_state_in is not None:settings['random_state_in_sha256']=digest(args.random_state_in)
    if manifest.exists():
        old = json.loads(manifest.read_text())
        if old['settings'] != settings:
            p.error('Different source/settings: choose a new output directory')
        if all(digest(args.output/name) == sha for name,sha in old['files'].items()):
            print('Reusing verified separated stems'); return
        p.error('Stem file changed; use a new directory')
    if list(args.output.glob('*.wav')):
        p.error('Partial/untracked stems exist; use a new directory')
    torch.manual_seed(0)
    torch.set_num_threads(args.threads)
    start = time.monotonic()
    # Same model/settings on GPU or CPU; only speed differs, so the manifest stays valid.
    if component is None:
        from model_reuse import get
        device=best_device()
        separator = get('separation',(args.model,device,args.overlap),
            lambda:Separator(model=args.model, device=device, shifts=1, overlap=args.overlap, progress=True))
    else:
        # Reuse the installed Demucs loader/API and the EXACT cached checkpoint
        # used by its full bag. Only its lifetime changes; no model is replaced.
        import demucs.api as demucs_api
        from demucs.hf import load_safetensors_model
        original_get=demucs_api.get_model
        demucs_api.get_model=lambda *a,**kw:load_safetensors_model(checkpoint)
        try:separator=Separator(model=args.model,device=best_device(),shifts=1,overlap=args.overlap,progress=True)
        finally:demucs_api.get_model=original_get
    sr, channels = separator.samplerate, separator.audio_channels
    if args.seed is not None:
        random.seed(args.seed)
        torch.manual_seed(args.seed)
    if args.random_state_in is not None:
        state=json.loads(args.random_state_in.read_text())
        def tuples(value):return tuple(tuples(v) for v in value) if isinstance(value,list) else value
        random.setstate(tuples(state['python']))
        torch.set_rng_state(torch.tensor(state['torch'],dtype=torch.uint8))
    from audio_cache import decode
    wave=decode(args.source,sr,channels).T
    begin=round(args.start*sr)
    end=begin+round(args.seconds*sr) if args.seconds is not None else None
    wave=wave[:,begin:end].copy()
    if wave.size == 0 or not np.isfinite(wave).all():
        p.error('Empty or non-finite decoded audio')
    origin, tensors = separator.separate_tensor(torch.from_numpy(wave), sr)
    state_path=None
    if component is not None or args.seed is not None or args.random_state_in is not None:
        state_path=args.output/'random-state-after.json'
        save(state_path,{'python':random.getstate(),'torch':torch.get_rng_state().tolist()})
    stems = {name:t.detach().cpu().numpy() for name,t in tensors.items()}
    if set(stems) != {'vocals','drums','bass','other'}:
        raise ValueError('Unexpected stem contract')
    stems['instrumental'] = sum(stems[name] for name in ('drums','bass','other'))
    method = 'sum of drums, bass, other; no original vocals mixed back'
    if args.ensemble or args.keep_backing:
        scratch = args.output/'_models'
        shutil.rmtree(scratch, ignore_errors=True)  # leftovers of an interrupted run
        scratch.mkdir()
        decoded = scratch/'input.wav'
        write_wav(decoded, wave, 1.0, sr, channels)  # exact samples Demucs saw
        if args.ensemble:
            other = run_audio_separator(ROFORMER, decoded, scratch/'roformer', sr, channels, wave.shape[1])
            # Equal-weight average of two independent models cancels much of each one's bleed.
            stems['vocals'] = (stems['vocals'] + other['vocals']) / 2
            stems['instrumental'] = (stems['instrumental'] + other['instrumental']) / 2
            method = 'average of Demucs (drums+bass+other) and BS-Roformer instrumental'
        if args.keep_backing:
            write_wav(scratch/'vocals.wav', stems['vocals'], 1.0, sr, channels)
            split = run_audio_separator(KARAOKE, scratch/'vocals.wav', scratch/'karaoke', sr, channels, wave.shape[1])
            stems['lead_vocals'] = split['vocals']
            stems['backing_vocals'] = split['instrumental']
            stems['instrumental_with_backing'] = stems['instrumental'] + split['instrumental']
        shutil.rmtree(scratch, ignore_errors=True)
    for value in stems.values():
        if value.shape != wave.shape or not np.isfinite(value).all():
            raise ValueError('Invalid output shape or samples')
    peak = max(float(np.max(np.abs(value))) for value in stems.values())
    gain = min(1., .99/max(peak,1e-9))
    files = {}
    for name,value in stems.items():
        target = args.output/(name+'.wav')
        write_wav(target, value, gain, sr, channels)
        files[target.name] = digest(target)
    save(manifest, {'settings':settings,'files':files,'duration':wave.shape[1]/sr,
                    'sample_rate':sr,'channels':channels,'common_gain':gain,
                    'is_excerpt':args.seconds is not None,'elapsed_seconds':time.monotonic()-start,
                    'is_intermediate':component is not None,'model_sources':list(separator.model.sources),
                    'instrumental':method,
                    'runtime':{'torch':torch.__version__,'cpu_threads':args.threads,
                        **({'random_state_after_sha256':digest(state_path)} if state_path else {})}})
    print(manifest)


if __name__ == '__main__':
    main()
