"""Residual-voice screening and audio-loss diagnostics, never a listening certificate.

AST is an AudioSet classifier, not a calibrated probability of vocal removal.
Empty ASR transcripts and low residual energy are never treated as proof of success.
"""
from pathlib import Path
import gc
import html
import json
import math
import os
import subprocess
import numpy as np
from scipy import signal
from project_runtime import FFMPEG, MODELS
from zoom_local_pipeline import digest, read, save

RATE = 16000
MODEL = 'MIT/ast-finetuned-audioset-10-10-0.4593'
REVISION = 'f826b80d28226b62986cc218e5cec390b1096902'
VOICE_LABELS = {'Singing', 'Choir', 'Chant', 'Male singing', 'Female singing',
                'Child singing', 'Synthetic singing', 'Rapping', 'Humming',
                'Vocal music', 'Speech', 'Male speech, man speaking',
                'Female speech, woman speaking', 'Child speech, kid speaking'}
DEFAULTS = {'voice_threshold': .25, 'window_seconds': 10, 'step_seconds': 5,
            'threads': 2, 'alternatives': ['uvr'], 'asr': True, 'asr_model': 'base',
            'max_asr_windows': 6, 'max_review_clips': 6}


def settings(value=None):
    value = value or {}
    if set(value)-set(DEFAULTS):
        raise ValueError('Unknown audio-quality settings: '+str(sorted(set(value)-set(DEFAULTS))))
    result = {**DEFAULTS, **value}
    for key in ['voice_threshold', 'window_seconds', 'step_seconds', 'threads',
                'max_asr_windows', 'max_review_clips']:
        if not isinstance(result[key], (int, float)) or isinstance(result[key], bool) or not math.isfinite(result[key]):
            raise ValueError('Invalid quality setting: '+key)
    if not 0 < result['voice_threshold'] < 1 or not 1 <= result['threads'] <= 8:
        raise ValueError('Voice threshold must be 0..1; threads must be 1..8')
    if not 1 <= result['step_seconds'] <= result['window_seconds'] <= 10:
        raise ValueError('Require 1 <= step <= window <= 10 seconds')
    if not 0 <= result['max_review_clips'] <= 20 or not 0 <= result['max_asr_windows'] <= 12:
        raise ValueError('Review/ASR window count exceeds the bounded budget')
    for key in ['threads', 'max_review_clips', 'max_asr_windows']:
        if int(result[key]) != result[key]:
            raise ValueError(key+' must be an integer')
        result[key] = int(result[key])
    if not isinstance(result['asr'], bool):
        raise ValueError('asr must be true/false')
    if not isinstance(result['asr_model'], str) or not result['asr_model'].strip():
        raise ValueError('asr_model is required')
    if not isinstance(result['alternatives'], list) or len(result['alternatives']) > 2 or \
            any(x not in ['uvr', 'roformer', 'htdemucs_ft'] for x in result['alternatives']) or \
            len(set(result['alternatives'])) != len(result['alternatives']):
        raise ValueError('alternatives must contain at most two distinct models: uvr, roformer, htdemucs_ft')
    return result


def decode(path):
    from audio_cache import decode as cached_decode
    return cached_decode(path,RATE,2)


def _legacy_decode(path):
    raw = subprocess.run([str(FFMPEG), '-v', 'error', '-i', str(path), '-map', '0:a:0',
                          '-ac', '2', '-ar', str(RATE), '-f', 'f32le', '-'],
                         check=True, capture_output=True).stdout
    out = np.frombuffer(raw, '<f4').reshape(-1, 2)
    if not len(out) or not np.isfinite(out).all():
        raise ValueError('Empty/nonfinite audio: '+str(path))
    return out


def intervals(mask, hop=.1, minimum=.5):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return [{'start': round(a*hop, 3), 'end': round(b*hop, 3)}
            for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])
            if (b-a)*hop >= minimum]


def signal_checks(source, candidate, rate=RATE):
    if not len(candidate) or candidate.ndim != 2 or not np.isfinite(candidate).all():
        raise ValueError('Candidate contains empty/invalid samples')
    n = min(len(source), len(candidate))
    a, b = source[:n].astype(np.float64), candidate[:n].astype(np.float64)
    width = max(1, round(rate*.1)); count = n//width
    if not count:
        raise ValueError('At least 100 ms of audio is required')
    levels = lambda x: 10*np.log10(np.maximum(1e-12, np.mean(
        x[:count*width].reshape(count, width, 2)**2, axis=(1, 2))))
    original, processed = levels(a), levels(b)
    active = original > -40
    silence = (processed < -60) & active
    flags = [{'kind': 'new_quiet_gap', **span} for span in intervals(silence)]
    # A drop absent from the original is a warning, not proof of lost instruments.
    drops = (np.diff(processed, prepend=processed[0]) < -18) & \
            (np.diff(original, prepend=original[0]) > -6) & active
    flags += [{'kind': 'unexpected_level_drop', 'start': round(i*.1, 3),
               'end': round(min(n/rate, i*.1+.5), 3)} for i in np.where(drops)[0]]
    ratio = float(np.sum(b*b)/max(np.sum(a*a), 1e-20))
    duration_error = abs(len(source)-len(candidate))/rate
    clipped = float(np.mean(np.abs(b) >= .9999))
    loss = float(np.sum(silence)/max(1, np.sum(active)))
    reasons = []
    if duration_error > .1: reasons.append('duration_mismatch')
    if clipped > .0001: reasons.append('clipping')
    if np.max(np.abs(b)) < 1e-6: reasons.append('silent_output')
    if ratio < .001 and np.any(active): reasons.append('severe_energy_loss')
    if loss > .2: reasons.append('large_new_silent_regions')
    return {'duration_error_seconds': duration_error, 'energy_ratio': ratio,
            'peak': float(np.max(np.abs(b))), 'clipped_fraction': clipped,
            'new_silent_fraction': loss, 'flags': flags, 'reject_reasons': reasons,
            'warning': 'Energy loss can also be genuine a-cappella sections; review the source.'}


class VoiceDetector:
    def __init__(self, config):
        import torch
        from transformers import ASTFeatureExtractor, ASTForAudioClassification
        self.torch = torch
        torch.set_num_threads(config['threads'])
        offline = os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD', '1') != '1'
        opts = {'revision': REVISION, 'cache_dir': str(MODELS/'audioset'), 'local_files_only': offline}
        self.extractor = ASTFeatureExtractor.from_pretrained(MODEL, **opts)
        self.model = ASTForAudioClassification.from_pretrained(MODEL, use_safetensors=True, **opts).eval()
        self.ids = [int(k) for k, label in self.model.config.id2label.items() if label in VOICE_LABELS]
        if not self.ids:
            raise ValueError('Detector voice labels are missing')

    def scan(self, samples, config):
        # Avoid cancelling anti-phase stereo: use the stronger channel per window.
        size = round(config['window_seconds']*RATE); step = round(config['step_seconds']*RATE)
        starts = list(range(0, max(1, len(samples)-size+1), step))
        starts.append(max(0, len(samples)-size))
        windows = []
        for start in sorted(set(starts)):
            x = samples[start:min(len(samples), start+size)]
            mono = x[:, np.argmax(np.mean(x.astype(float)**2, axis=0))]
            score, music = 0., 0.
            if np.sqrt(np.mean(mono.astype(float)**2)) > 1e-5:
                inputs = self.extractor(mono, sampling_rate=RATE, return_tensors='pt')
                with self.torch.inference_mode():
                    values = self.model(**inputs).logits.sigmoid()[0]
                score = float(values[self.ids].max())
                music_id = next((int(k) for k,v in self.model.config.id2label.items() if v == 'Musical instrument'), None)
                if music_id is not None: music = float(values[music_id])
            windows.append({'start': start/RATE, 'end': (start+len(x))/RATE,
                            'voice_score': score, 'instrument_score': music,
                            'flagged': score >= config['voice_threshold']})
            print(f'  voice scan {start/RATE:.1f}s: {score:.3f}', flush=True)
        return windows


def asr_evidence(path, samples, windows, config, language):
    from faster_whisper import WhisperModel
    model = WhisperModel(config['asr_model'], device='cpu', compute_type='int8',
        cpu_threads=config['threads'], download_root=str(MODELS/'whisper'),
        local_files_only=os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD', '1') != '1')
    targets = [w for w in windows if w.get('flagged')]
    targets += [{'start': float(s), 'end': min(len(samples)/RATE, float(s)+10)}
                for s in np.linspace(0, max(0, len(samples)/RATE-10), 3)]
    results = []
    seen = set()
    for w in targets:
        key = round(w['start'], 1)
        if key in seen: continue
        seen.add(key)
        if len(seen) > config['max_asr_windows']: break
        x = samples[round(w['start']*RATE):round(w['end']*RATE)]
        mono = x[:, np.argmax(np.mean(x.astype(float)**2, axis=0))].copy()
        segments, _ = model.transcribe(mono, language=None if language == 'auto' else language,
            beam_size=3, condition_on_previous_text=False, vad_filter=False)
        for s in segments:
            if len(s.text.split()) >= 3 and s.avg_logprob > -1 and s.no_speech_prob < .5:
                results.append({'start': w['start']+s.start, 'end': w['start']+s.end,
                    'text': s.text, 'average_log_probability': s.avg_logprob,
                    'kind': 'possible_recognisable_voice'})
    return results


def evaluate(source, candidate, folder, config=None, language='auto'):
    config = settings(config); folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    binding = {'source': digest(source), 'candidate': digest(candidate), 'config': config,
               'code': digest(__file__), 'detector': MODEL, 'revision': REVISION, 'language': language}
    report_path = folder/'quality.json'
    if report_path.exists():
        previous=read(report_path)
        if previous.get('binding')==binding and previous.get('screening_complete'):
            return previous
        history=folder/'history'; history.mkdir(exist_ok=True)
        backup=history/('quality-'+digest(report_path)[:16]+'.json')
        if not backup.exists(): save(backup,previous)
    original, processed = decode(source), decode(candidate)
    checks = signal_checks(original, processed)
    detector = {'available': False, 'windows': []}
    classifier = None
    try:
        classifier = VoiceDetector(config)
        detector = {'available': True, 'windows': classifier.scan(processed, config)}
    except Exception as exc:
        detector['error'] = str(exc)
    finally:
        del classifier
        gc.collect()
    speech = []
    asr_error = None
    if config['asr']:
        try: speech = asr_evidence(candidate, processed, detector['windows'], config, language)
        except Exception as exc: asr_error = str(exc)
    flags = checks['flags'] + [{'kind': 'possible_singing', **w}
        for w in detector['windows'] if w['flagged']] + speech
    report = {'binding': binding, 'audio': str(Path(candidate).resolve()), 'signal': checks,
              'detector': detector, 'asr': speech, 'asr_error': asr_error, 'flags': flags,
              'screening_complete': detector['available'] and not asr_error,
              'status': 'needs_human_listening',
              'limitations': ['AST scores are uncalibrated screening signals.',
                'No recognised words does not prove no vocals.',
                'Instrument damage cannot be certified without a clean reference.']}
    save(report_path, report)
    return report


def choose(candidates):
    """Reject destructive outputs before comparing voice flags. No energy-only win."""
    eligible = [c for c in candidates if not c['report']['signal']['reject_reasons']]
    if not eligible: return None
    def rank(c):
        r = c['report']; windows = r['detector']['windows']
        return (not r['screening_complete'], len(r['asr']),
                sum(w['flagged'] for w in windows)/max(1, len(windows)),
                max((w['voice_score'] for w in windows), default=1), len(r['signal']['flags']))
    return min(eligible, key=rank)


def review_clips(source, candidate, report, folder, limit=6):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    duration = len(decode(candidate))/RATE
    starts = [max(0, f['start']-1) for f in report['flags']]
    if not starts: starts = np.linspace(0, max(0, duration-5), min(3, limit)).tolist()
    items = []
    version = digest(source)[:8]+'-'+digest(candidate)[:8]
    for start in starts:
        start = min(start, max(0, duration-1))
        if any(abs(start-i['start']) < 3 for i in items): continue
        if len(items) >= limit: break
        length = min(5, duration-start); dest = folder/f'compare-{start:08.2f}-{version}.wav'
        if not dest.exists():
            subprocess.run([str(FFMPEG), '-v', 'error', '-n', '-ss', str(start), '-t', str(length),
                '-i', str(source), '-ss', str(start), '-t', str(length), '-i', str(candidate),
                '-filter_complex', '[0:a]aformat=sample_rates=16000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a];'
                '[1:a]aformat=sample_rates=16000:channel_layouts=stereo,asetpts=PTS-STARTPTS[b];'
                '[a][b]concat=n=2:v=0:a=1[out]', '-map', '[out]', '-c:a', 'pcm_s16le', str(dest)], check=True)
        items.append({'start': start, 'seconds_per_part': length, 'path': str(dest), 'sha256': digest(dest)})
    text = '<!doctype html><meta charset="utf-8"><title>Audio review</title><h1>Audio review</h1>'
    text += '<p>Each clip plays the ORIGINAL first, then the PROCESSED audio. No loudness normalization is applied.</p>'
    text += '<p>Screening cannot certify vocal removal. Review all flagged sections and the full preview.</p>'
    for item in items:
        text += f'<p>Source time {item["start"]:.2f}s</p><audio controls src="{html.escape(Path(item["path"]).name)}"></audio>'
    (folder/'index.html').write_text(text, encoding='utf-8')
    save(folder/'clips.json', items)
    return items


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--candidate',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--config',type=Path)
    p.add_argument('--language',default='auto')
    a=p.parse_args()
    evaluate(a.source,a.candidate,a.output,read(a.config) if a.config else None,a.language)
