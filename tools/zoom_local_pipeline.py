"""Local Zoom karaoke pipeline. No paid APIs. Run --help for stages.

prepare -> edit transcript if necessary -> align -> review -> approve -> render.
Automatic sync is a suggestion, never evidence of an identical arrangement.
"""
from __future__ import annotations
import argparse
import re
import hashlib
import importlib.metadata
import json
import math
import os
import shutil
from pathlib import Path
import subprocess
import sys
import numpy as np
from prepare_zoom_local import make_ass, ROOT

from project_runtime import FFMPEG, LOGO, OUT, font_file
RENDERER = ROOT / 'tools/build_bowlnfun_karaoke.py'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def audio(path, rate=16000):
    from audio_cache import decode
    return decode(path,rate,1)


def chroma(samples, sr=16000, hop=1600):
    from scipy.signal import stft
    _, _, spectrum = stft(samples, sr, nperseg=4096, noverlap=4096-hop)
    power = np.abs(spectrum)
    freq = np.fft.rfftfreq(4096, 1/sr)
    valid = (freq >= 65) & (freq <= 2000)
    notes = np.round(69 + 12*np.log2(freq[valid]/440)).astype(int) % 12
    out = np.zeros((12, power.shape[1]))
    for pitch in range(12):
        out[pitch] = power[valid][notes == pitch].sum(axis=0)
    out = np.log1p(out * 100)
    out -= out.mean(axis=0, keepdims=True)
    return out / np.maximum(np.linalg.norm(out, axis=0, keepdims=True), 1e-8)


def suggest_sync(reference, backing, step=.1, max_shift=60):
    """Match three musical windows; repeated sections may remain ambiguous."""
    width = min(200, reference.shape[1]//5, backing.shape[1]//5)
    if width < 30:
        raise ValueError('At least 15 seconds of audio needed for sync suggestions')
    windows = []
    for fraction in (.2, .5, .8):
        start = int((reference.shape[1]-width)*fraction)
        a = reference[:, start:start+width]
        candidates = []
        for shift in range(-round(max_shift/step), round(max_shift/step)+1):
            b = start+shift
            if b < 0 or b+width > backing.shape[1]:
                continue
            score = float(np.mean(np.sum(a*backing[:, b:b+width], axis=0)))
            candidates.append((score, shift))
        candidates.sort(reverse=True)
        score, shift = candidates[0]
        other = next((s for s, t in candidates if abs(t-shift)*step > 2), score)
        windows.append({'reference': round((start+width/2)*step, 3),
                        'offset': round(shift*step, 3), 'score': score,
                        'alternative_margin': score-other})
    offsets = [w['offset'] for w in windows]
    stable = max(offsets)-min(offsets) <= .3
    confident = all(w['score'] >= .65 and w['alternative_margin'] >= .08 for w in windows)
    return {'status': 'proposal_needs_listening' if stable and confident else 'manual_sync_required',
            'windows': windows, 'proposed_offset': float(np.median(offsets)),
            'warning': 'Check original Zoom lyrics and audio throughout; covers/edits may differ.'}


def map_time(t, anchors):
    if len(anchors) < 2:
        raise ValueError('At least two verified sync anchors required')
    for a, b in zip(anchors, anchors[1:]):
        if not all(math.isfinite(v) for v in (*a, *b)) or b[0] <= a[0] or b[1] <= a[1]:
            raise ValueError('Sync anchors must be finite and strictly increasing')
    if t < anchors[0][0] or t > anchors[-1][0]:
        raise ValueError('Sync anchors must cover every word; no extrapolation allowed')
    return float(np.interp(t, [a[0] for a in anchors], [a[1] for a in anchors]))


def mapped_segments(segments, anchors):
    result = []
    for segment in segments:
        words = []
        for word in segment['words']:
            if 'start' not in word or 'end' not in word:
                raise ValueError(f'Unaligned word needs manual timing: {word}')
            words.append({**word, 'start': map_time(word['start'], anchors),
                          'end': map_time(word['end'], anchors)})
        result.append({**segment, 'words': words})
    return result


def check_audio(original, exported, delay=48000, gain_invariant=False, skip_start=0, skip_end=0):
    """Compare decoded mono 16 kHz backing after the known 3-second intro.

    gain_invariant: a deliberate loudness gain is removed before comparing.
    skip_start/skip_end: samples covered by deliberate fades are not compared.
    """
    if abs(len(exported)-delay-len(original)) > 4000:
        raise ValueError('Rendered audio duration differs from backing')
    n = min(len(original), len(exported)-delay)
    if n <= 0:
        raise ValueError('No rendered backing audio')
    a = original[skip_start:n-skip_end].astype(np.float64)
    b = exported[delay+skip_start:delay+n-skip_end].astype(np.float64)
    if gain_invariant and np.dot(b, b) > 1e-8:
        b *= np.dot(a, a) / max(np.dot(a, b), 1e-12)
    energy = float(np.dot(a,a))
    if energy < 1e-8:
        raise ValueError('Backing is silent; cannot verify audio')
    similarity = float(np.dot(a,b)/max(np.sqrt(energy*np.dot(b,b)), 1e-12))
    relative_error = float(np.sqrt(np.dot(a-b,a-b)/energy))
    if similarity < .98 or relative_error > .15:
        raise ValueError(f'Audio changed or shifted: correlation={similarity}, relative_error={relative_error}')
    for start in range(0, len(a), 8000):
        x, y = a[start:start+8000], b[start:start+8000]
        e = float(np.dot(x,x))
        if e > len(x)*1e-7 and np.sqrt(np.dot(x-y,x-y)/e) > .3:
            raise ValueError(f'Audio mismatch near backing second {start/16000:.2f}')
    return {'correlation': similarity, 'relative_error': relative_error, 'intro_delay_seconds': delay/16000}


def paths(config):
    cfg = read(config)
    if not cfg['slug'].replace('_', '').isalnum():
        raise ValueError('Invalid slug')
    for key in ('vocal_reference', 'zoom_video', 'background'):
        cfg[key] = str((ROOT / cfg[key]).resolve())
    work = ROOT / 'work/zoom_local' / cfg['slug']
    work.mkdir(parents=True, exist_ok=True)
    return cfg, work


def require_inputs(cfg):
    for key in ('vocal_reference', 'zoom_video', 'background'):
        if not Path(cfg[key]).is_file():
            raise ValueError(f'Missing {key}: {cfg[key]}')
    if cfg['vocal_reference'] == cfg['zoom_video']:
        raise ValueError('Use a vocal reference, not the instrumental Zoom file')


def prepare(cfg, work):
    from faster_whisper import WhisperModel
    inputs = {key: digest(cfg[key]) for key in ('vocal_reference', 'zoom_video')}
    if (work/'inputs.json').exists() and read(work/'inputs.json') != inputs:
        raise ValueError('Source changed. Use a new slug to preserve previous work')
    if (work/'transcript.json').exists() and not (work/'inputs.json').exists():
        raise ValueError('Untracked transcript; use a new slug')
    save(work/'inputs.json', inputs)
    vocal, backing = audio(cfg['vocal_reference']), audio(cfg['zoom_video'])
    if not (work/'transcript.json').exists():
        model = WhisperModel(cfg.get('model', 'small'), device='cpu', compute_type='int8')
        segments, _ = model.transcribe(vocal, language=cfg.get('language','en'), beam_size=5,
                                      condition_on_previous_text=False, vad_filter=False)
        save(work/'transcript.json', [{'start': s.start, 'end': s.end, 'text': s.text} for s in segments])
    report = suggest_sync(chroma(vocal), chroma(backing))
    save(work/'sync-report.json', report)
    # Do not auto-approve the offset or silently overwrite corrected anchors.
    if not (work/'sync.json').exists():
        save(work/'sync.json', {'anchors': [], 'suggested_offset': report['proposed_offset'],
                               'instructions': 'Add verified [reference_seconds, Zoom_seconds] anchors covering all lyrics.'})


def align(cfg, work):
    import whisperx
    if read(work/'inputs.json') != {key: digest(cfg[key]) for key in ('vocal_reference', 'zoom_video')}:
        raise ValueError('Source changed since transcription')
    from device import best_device
    device = best_device()
    transcript = read(work/'transcript.json')
    if os.environ.get('KARAOKE_ALLOW_MODEL_DOWNLOAD','1')!='1':
        import torch
        import torchaudio
        model_name=cfg.get('alignment_model')
        if model_name and hasattr(torchaudio.pipelines,model_name):
            bundle=getattr(torchaudio.pipelines,model_name)
            checkpoint=Path(torch.hub.get_dir())/'checkpoints'/Path(bundle._path).name
            if not checkpoint.is_file():
                raise ValueError('Alignment model missing in offline mode: '+str(checkpoint))
    from contextlib import nullcontext
    loading = nullcontext()
    if cfg.get('alignment_model')=='WAV2VEC2_ASR_LARGE_LV60K_960H':
        import torch
        from low_memory_models import mapped_checkpoint_load
        checkpoint=Path(torch.hub.get_dir())/'checkpoints/wav2vec2_fairseq_large_lv60k_asr_ls960.pth'
        loading=mapped_checkpoint_load(torch,checkpoint)
    from phrase_alignment import incremental
    from model_reuse import get
    loaded=[]
    def one(segment):
        if not loaded:
            with loading:
                model,metadata=get('alignment',(cfg.get('language','en'),device,cfg.get('alignment_model')),
                    lambda:whisperx.load_align_model(language_code=cfg.get('language','en'),device=device,
                                                     model_name=cfg.get('alignment_model')))
            loaded.extend([model,metadata,audio(cfg.get('align_audio',cfg['vocal_reference']))])
        return whisperx.align([segment],loaded[0],loaded[1],loaded[2],device,
                              return_char_alignments=False)['segments']
    binding={'audio':digest(cfg.get('align_audio',cfg['vocal_reference'])),
             'language':cfg.get('language','en'),'model':cfg.get('alignment_model'),
             'whisperx':importlib.metadata.version('whisperx'),
             'code':digest(__file__)}
    rows,stats=incremental(transcript,binding,work/'phrase-alignment',one)
    save(work/'aligned.json',rows)
    save(work/'phrase-alignment-report.json',stats)
    save(work/'alignment-inputs.json', {'transcript': digest(work/'transcript.json'),
                                      'vocal_reference': digest(cfg['vocal_reference'])})


def fingerprint(cfg, work):
    from intro_countdown import settings
    merged={**cfg.get('render_defaults',{}),**cfg.get('render',{})}
    countdown=settings(merged.get('countdown_style'),merged.get('countdown_colour'))
    template = Path(cfg.get('render', {}).get('template', 'four_line'))
    if template.suffix != '.json':
        template = ROOT/'config/templates'/(str(template)+'.json')
    elif not template.is_absolute():
        template = ROOT/template
    dependencies = list((ROOT/'tools').glob('*.py')) + [template, font_file()]
    layout={key:os.getenv(key,default) for key,default in {
        'KARAOKE_STILL_FIT':'contain','KARAOKE_INTRO_LOGO_SCALE':'1',
        'KARAOKE_CORNER_MARGIN_X':'48','KARAOKE_CORNER_MARGIN_Y':'42'}.items()}
    return {'config': cfg, 'countdown':countdown, 'layout':layout, 'files': {str(p): digest(p) for p in [
        Path(cfg['vocal_reference']), Path(cfg['zoom_video']), Path(cfg['background']), LOGO,
        work/'aligned.json', work/'sync.json', work/'transcript.json', RENDERER, Path(__file__),
        ROOT/'tools/prepare_zoom_local.py', *dependencies]}}


def assign_parts(segments, transcript):
    """Carry duet parts (transcript 'part': M/F/D...) onto aligned segments by time.

    WhisperX may split or merge lines, so each aligned segment takes the part of
    the transcript line its middle falls into."""
    parts = [(t['start'], t['end'], t['part']) for t in transcript if t.get('part')]
    result = []
    for segment in segments:
        words = segment['words']
        middle = (words[0]['start'] + words[-1]['end']) / 2 if words else segment.get('start', 0)
        # A part set directly on the aligned line (edit --part) wins.
        part = segment.get('part') or next((p for a, b, p in parts if a <= middle <= b), None)
        result.append({**segment, 'part': part} if part else segment)
    return result


def reviewed_ass(cfg, work):
    if read(work/'alignment-inputs.json') != {'transcript': digest(work/'transcript.json'),
                                            'vocal_reference': digest(cfg['vocal_reference'])}:
        raise ValueError('Transcript/source changed; rerun alignment')
    anchors = read(work/'sync.json')['anchors']
    segments = assign_parts(mapped_segments(read(work/'aligned.json'), anchors), read(work/'transcript.json'))
    duration = len(audio(cfg['zoom_video']))/16000
    return make_ass(segments, 0, duration)


def delivery_folder(cfg):
    folder = (ROOT / cfg.get('output_dir', str(OUT))).resolve()
    if not folder.is_relative_to(OUT.resolve()):
        raise ValueError('Delivery folder must stay inside out')
    return folder


def render_options(cfg):
    """Optional per-song `render` block: layout, canvas, export range and audio mix."""
    options = {'template': 'four_line', 'canvas': '1920x1080', 'start': None, 'end': None,
               'video_bitrate': None, 'video_bitrate': None, 'crf': 19, 'preset': 'veryfast', 'encoder':'libx264', 'nvenc_cq':19, 'guide_vocal_level': 0.0, 'pitch_semitones': 0.0,
               'loudness_lufs': None, 'fade_in': 0.0, 'fade_out': 0.0,
               'gap_countdown': False, 'motion': 'none', 'fps': 25,
               'intro_seconds': 3.0, 'intro_countdown': False, 'sync_background': False, 'highlight_colour': None,
               'countdown_style':None,'countdown_colour':None}
    options.update(cfg.get('render_defaults', {}))
    unknown = set(cfg.get('render', {})) - set(options)
    if unknown:
        raise ValueError(f'Unknown render option(s): {sorted(unknown)}')
    options.update(cfg.get('render', {}))
    from intro_countdown import settings
    options.update(settings(options['countdown_style'],options['countdown_colour']))
    if options['guide_vocal_level'] and not cfg.get('guide_vocal'):
        raise ValueError('guide_vocal_level needs separated vocals (local song workflow)')
    args = ['--template', str(options['template']), '--canvas', str(options['canvas']),
            '--crf', str(options['crf']), '--preset', str(options['preset'])]
    if options['video_bitrate'] is not None:
        args += ['--video-bitrate',str(options['video_bitrate'])]
    if options['video_bitrate'] is not None:
        args += ['--video-bitrate',str(options['video_bitrate'])]
    if options['encoder'] != 'libx264':
        args += ['--encoder',str(options['encoder']),'--nvenc-cq',str(options['nvenc_cq'])]
    if options['highlight_colour'] is not None:
        colour=options['highlight_colour']
        if not isinstance(colour,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',colour):
            raise ValueError('highlight_colour must be #RRGGBB')
        args += ['--highlight-colour',colour]
    for key, flag in (('start', '--start'), ('end', '--end')):
        if options[key] is not None:
            args += [flag, str(options[key])]
    if options['guide_vocal_level']:
        args += ['--guide-vocal-file', cfg['guide_vocal'], '--guide-vocal-level', str(options['guide_vocal_level'])]
    if options['pitch_semitones']:
        args += ['--pitch', str(options['pitch_semitones'])]
    if options['loudness_lufs'] is not None:
        args += ['--gain-db', f"{loudness_gain(cfg['zoom_video'], options['loudness_lufs']):.2f}"]
    if options['fade_in'] or options['fade_out']:
        args += ['--fade-in', str(options['fade_in']), '--fade-out', str(options['fade_out'])]
    if options['gap_countdown']:
        args.append('--gap-countdown')
    if options['motion'] != 'none':
        args += ['--motion', options['motion']]
    if options['fps'] != 25:
        args += ['--fps', str(options['fps'])]
    if options['intro_seconds'] != 3.0:
        args += ['--intro-seconds', str(options['intro_seconds'])]
    if options['sync_background']:
        args.append('--sync-background')
    if options['intro_countdown'] and options['intro_seconds'] > 0:
        args.append('--intro-countdown')
        args += ['--countdown-style',options['countdown_style'],'--countdown-colour',options['countdown_colour']]
    return options, args


def loudness_gain(path, target_lufs, ceiling_db=-1.0):
    """Linear gain (dB) to reach the target loudness (EBU R128 / ITU-R BS.1770),
    limited so the sample peak stays under the ceiling: no limiter, no distortion."""
    import re
    result = subprocess.run([str(FFMPEG), '-hide_banner', '-nostdin', '-i', str(path),
        '-map', '0:a:0', '-af', 'ebur128=peak=true', '-f', 'null', '-'],
        capture_output=True, text=True, check=True)
    measured = re.findall(r'I:\s+(-?[\d.]+) LUFS', result.stderr)
    peaks = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', result.stderr)
    if not measured or not peaks:
        raise ValueError('FFmpeg could not measure loudness/true peak')
    loudness, peak_db = float(measured[-1]), float(peaks[-1])
    return min(target_lufs - loudness, ceiling_db - peak_db)


def run_renderer(cfg, work, destination, output_name, ass_only=False):
    """Render work/lyrics.ass with the song's options; returns the options used."""
    options, render_args = render_options(cfg)
    if ass_only:
        render_args.append('--ass-only')
    if cfg.get('branding_plan'):
        plan=cfg['branding_plan']
        if digest(plan['file'])!=plan['sha256']:raise ValueError('Branding plan changed')
        render_args += ['--branding-plan',plan['file']]
    styles = [segment.get('style') for segment in read(work/'aligned.json')] if (work/'aligned.json').exists() else []
    if any(styles):
        # Same order as the Dialogue rows of lyrics.ass (one per aligned line).
        save(work/'line-styles.json', styles)
        render_args += ['--line-styles', str(work/'line-styles.json')]
    if cfg.get('layers'):
        render_args += ['--layers', cfg['layers']['file']]
    if cfg.get('translation'):
        render_args += ['--translation-file', cfg['translation']['file'],
                        '--translation-mode', cfg['translation']['mode']]
    # Feed the original Zoom audio directly; no vocal removal or lossy intermediate.
    subprocess.run([sys.executable, str(RENDERER), '--slug', cfg['slug'],
        '--title', cfg['title'], '--artist', cfg['artist'], '--source-ass', str(work/'lyrics.ass'),
        '--audio-file', cfg['zoom_video'], '--background-file', cfg['background'],
        '--output-dir', str(destination), '--output-name', output_name,
        '--approved-intro', '--language-label', cfg.get('language_label','KARAOKE'), *render_args,
        '--metadata-title', cfg['title'], '--metadata-artist', cfg['artist']], check=True)
    return options


def render(cfg, work, preview=False):
    if not preview:
        if (delivery_folder(cfg)/(cfg['slug']+'_Karaoke.mp4')).exists():
            raise ValueError('Final output already exists; refusing overwrite')
        approval = read(work/'approval.json')
        if approval['fingerprint'] != fingerprint(cfg, work):
            raise ValueError('Inputs/timings changed since review; approve again')
    ass = reviewed_ass(cfg, work)
    (work/'lyrics.ass').write_text(ass, encoding='utf-8')
    destination = work/'preview' if preview else work/'validated-export'
    if preview and cfg.get('preview_versions'):
        key=hashlib.sha256(json.dumps(fingerprint(cfg,work),sort_keys=True).encode()).hexdigest()[:16]
        destination=work/'previews'/key
    output_name = cfg['slug'] + '_Karaoke.mp4'
    if (destination/output_name).exists():
        raise ValueError(f'Output exists, refusing overwrite: {destination/output_name}')
    options = run_renderer(cfg, work, destination, output_name)
    import av
    size = [int(v) for v in options['canvas'].split('x')]
    with av.open(str(destination/output_name)) as media:
        video = media.streams.video[0]
        duration = media.duration / av.time_base
        expected = len(audio(cfg['zoom_video']))/16000 + options['intro_seconds']
        start = options['start'] or 0
        expected = (min(options['end'], expected) if options['end'] is not None else expected) - start
        if [video.width, video.height] != size or abs(duration-expected) > .25:
            raise ValueError('Output format/duration check failed; do not deliver')
    layer_audio = cfg.get('layers', {}).get('changes_audio', False)
    if options['guide_vocal_level'] or options['pitch_semitones'] or start or options['end'] is not None or layer_audio:
        audio_check = {'skipped': 'audio intentionally changed (guide vocal, key, export range or audio layers); listen instead'}
    else:
        # Loudness gain is linear and fades only touch the edges, so the
        # backing must still match sample for sample everywhere else.
        audio_check = check_audio(audio(cfg['zoom_video']), audio(destination/output_name),
                                  delay=round(options['intro_seconds']*16000),
                                  gain_invariant=options['loudness_lufs'] is not None,
                                  skip_start=round(options['fade_in']*16000),
                                  skip_end=round(options['fade_out']*16000))
    validation = {
        'output': str(destination/output_name), 'sha256': digest(destination/output_name),
        'duration': duration, 'expected_duration': expected, 'decode': 'passed_by_renderer',
        'resolution': size, 'render_options': options, 'preview': preview,
        'audio_check': audio_check,
        'fingerprint': fingerprint(cfg, work),
        'note': 'Original backing used; AAC re-encoded by renderer to add the 3-second intro.'}
    if not preview:
        final = delivery_folder(cfg)/output_name
        final.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation: never overwrite existing user delivery files.
        with final.open('xb') as target, (destination/output_name).open('rb') as source:
            shutil.copyfileobj(source, target)
        validation['output'] = str(final)
    save(work/('preview-validation.json' if preview else 'validation.json'), validation)
    if preview and cfg.get('preview_versions'): save(destination/'validation.json',validation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['doctor','prepare','align','preview','approve','render'])
    parser.add_argument('--config', type=Path)
    parser.add_argument('--confirm-listened', action='store_true', help='Confirm full lyric/sync/audio review')
    args = parser.parse_args()
    os.environ['PATH'] = str(FFMPEG.parent) + os.pathsep + os.environ.get('PATH', '')
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    if args.stage == 'doctor':
        for package in ('whisperx','faster-whisper','torch','torchaudio','scipy','av','Pillow'):
            print(package, importlib.metadata.version(package))
        import whisperx
        print('alignment API:', callable(whisperx.align), 'FFmpeg:', FFMPEG.is_file())
        return
    if not args.config:
        parser.error('--config required')
    cfg, work = paths(args.config)
    require_inputs(cfg)
    if args.stage == 'prepare':
        prepare(cfg, work)
    elif args.stage == 'align':
        align(cfg, work)
    elif args.stage == 'approve':
        if not args.confirm_listened:
            parser.error('Listen/check full preview before --confirm-listened')
        reviewed_ass(cfg, work)
        if not (work/'preview-validation.json').exists():
            raise ValueError('Render a preview first')
        if read(work/'preview-validation.json')['fingerprint'] != fingerprint(cfg, work):
            raise ValueError('Preview is stale; move it aside and render a new preview')
        validation = read(work/'preview-validation.json')
        if digest(validation['output']) != validation['sha256']:
            raise ValueError('Preview video changed since validation')
        save(work/'approval.json', {'fingerprint': fingerprint(cfg, work), 'review': 'user_confirmed'})
    else:
        render(cfg, work, preview=args.stage == 'preview')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError) as exc:
        sys.exit(str(exc))
