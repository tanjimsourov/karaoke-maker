"""Pinned UVR MDX-Net Inst HQ 3 fallback; always reads the original audio.

Model/config convention: https://github.com/Anjok07/ultimatevocalremovergui
Weights: https://github.com/TRvlvr/model_repo/releases/tag/all_public_uvr_models
"""
from pathlib import Path
import argparse
import hashlib
import os
import subprocess
import urllib.request
import numpy as np
from scipy.io import wavfile
from project_runtime import MODELS, FFMPEG
from zoom_local_pipeline import read, save, digest

NAME = 'UVR-MDX-NET-Inst_HQ_3.onnx'
SHA = '317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc'
URL = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/' + NAME


def run(source, output, threads=2):
    import torch
    import onnxruntime as ort
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    binding = {'source': digest(source), 'model': SHA, 'code': digest(__file__)}
    manifest = output/'result.json'
    if manifest.exists():
        old = read(manifest)
        if old['binding'] != binding: raise ValueError('UVR inputs changed; select a new work revision')
        if all(digest(output/name) == value for name, value in old['files'].items()): return old
        raise ValueError('UVR outputs changed; refusing reuse')
    model = MODELS/'uvr'/NAME; model.parent.mkdir(parents=True, exist_ok=True)
    if not model.exists():
        if os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD', '1') != '1':
            raise ValueError('UVR model not cached and downloads are disabled')
        partial = model.with_suffix('.partial')
        with urllib.request.urlopen(URL, timeout=60) as src, partial.open('wb') as dest:
            while block := src.read(1024*1024): dest.write(block)
        if digest(partial) != SHA: raise ValueError('UVR download checksum mismatch')
        partial.replace(model)
    if digest(model) != SHA: raise ValueError('UVR model checksum mismatch')
    raw = subprocess.run([str(FFMPEG), '-v', 'error', '-i', str(source), '-ac', '2',
        '-ar', '44100', '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, '<f4').reshape(-1, 2).copy()
    if not len(audio) or not np.isfinite(audio).all(): raise ValueError('Invalid original audio')
    torch.set_num_threads(threads)
    options = ort.SessionOptions(); options.intra_op_num_threads = threads; options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    input_name = session.get_inputs()[0].name
    fft, bins, frames, hop = 6144, 3072, 256, 1024
    size = hop*(frames-1); trim = fft//2; step = size//2
    window = torch.hann_window(fft); blend = np.hanning(size).astype('float32')
    mix = np.pad(audio.T, ((0, 0), (trim, size)))
    result = np.zeros_like(mix); weights = np.zeros(mix.shape[1], np.float32)
    chunks = output/'chunks'; chunks.mkdir(exist_ok=True)
    state_path = chunks/'state.json'
    state = read(state_path) if state_path.exists() else {'binding': binding, 'files': {}}
    if state['binding'] != binding: raise ValueError('Interrupted UVR job has different inputs')
    for number, start in enumerate(range(0, len(audio)+trim, step)):
        path = chunks/f'{number:05d}.npy'
        if path.name in state['files']:
            if digest(path) != state['files'][path.name]: raise ValueError('Cached UVR chunk changed')
            out = np.load(path, allow_pickle=False)
        else:
            with torch.inference_mode():
                s = torch.stft(torch.from_numpy(mix[:, start:start+size]), n_fft=fft,
                    hop_length=hop, window=window, return_complex=True)
                s = torch.view_as_real(s).permute(0, 3, 1, 2).reshape(1, 4, fft//2+1, frames)[:, :, :bins].numpy()
                s[:, :, :3] = 0
                prediction = (session.run(None, {input_name:s})[0]-session.run(None, {input_name:-s})[0])*.5
                padded = torch.nn.functional.pad(torch.from_numpy(prediction), (0,0,0,fft//2+1-bins))
                complex_s = torch.view_as_complex(padded.reshape(2,2,fft//2+1,frames).permute(0,2,3,1).contiguous())
                out = torch.istft(complex_s, n_fft=fft, hop_length=hop, window=window, length=size).numpy()
            np.save(path, out, allow_pickle=False)
            state['files'][path.name] = digest(path); save(state_path, state)
        if out.shape != (2,size) or not np.isfinite(out).all(): raise ValueError('Invalid UVR chunk')
        result[:, start:start+size] += out*blend; weights[start:start+size] += blend
        print('UVR chunk', number+1, flush=True)
    instrumental = (result/np.maximum(weights, 1e-8))[:, trim:trim+len(audio)].T*1.022
    vocals = audio-instrumental
    gain = min(1., .99/max(1e-9, float(np.max(np.abs(instrumental))), float(np.max(np.abs(vocals)))))
    files = {}
    for name, samples in [('instrumental.wav', instrumental), ('vocals.wav', vocals)]:
        dest = output/name
        value = (samples*gain).astype('float32')
        if dest.exists():
            rate, previous = wavfile.read(dest)
            if rate != 44100 or not np.array_equal(previous, value):
                raise FileExistsError('Different UVR output retained: '+str(dest))
        else: wavfile.write(dest, 44100, value)
        files[name] = digest(dest)
    report = {'binding': binding, 'files': files, 'common_gain': gain, 'model': NAME}
    save(manifest, report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p.add_argument('--threads', type=int, default=2)
    a = p.parse_args()
    if not 1 <= a.threads <= 8: p.error('threads must be 1..8')
    run(a.source, a.output, a.threads)
