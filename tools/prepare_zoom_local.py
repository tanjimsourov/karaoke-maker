"""Offline draft word timings from a VOCAL reference, never from Zoom backing.

Run with .venv-demucs/Scripts/python.exe. Outputs are review drafts, not finals.
Offset maps reference seconds to Zoom seconds; different edits need manual repair.
No Karadeo calls. The renderer's separate 3-second intro is NOT part of offset.
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

from project_runtime import ROOT


def stamp(cs):
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'


def make_ass(segments, offset, duration):
    rows = []
    previous = -1
    for segment in segments:
        words = segment['words']
        if not words:
            raise ValueError('Segment has no word timing')
        tokens = []
        start = round((words[0]['start'] + offset) * 100)
        cursor = start
        for word in words:
            a, b = (round((word[key] + offset) * 100) for key in ('start', 'end'))
            if a < cursor or b <= a or a < 0 or b > round(duration * 100):
                raise ValueError(f'Invalid/overlapping/out-of-range word: {word}')
            if a > cursor:
                tokens.append(f'{{\\kf{a-cursor}}} ')
            text = word['word'].strip()
            if not text or any(c in text for c in '{}\\\r\n'):
                raise ValueError('Empty text or unsafe ASS markup')
            tokens.append(f'{{\\kf{b-a}}}{text} ')
            cursor = b
        if start < previous:
            raise ValueError('Overlapping segments need review')
        # The Name field carries the duet part (M/F/D...) to the renderer.
        part = ''.join(c for c in str(segment.get('part') or '') if c.isalnum())[:8]
        rows.append(f'Dialogue: 0,{stamp(start)},{stamp(cursor)},Default,{part},0,0,0,,'+''.join(tokens).rstrip())
        previous = cursor
    if not rows:
        raise ValueError('No words detected')
    return '[Script Info]\nScriptType: v4.00+\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'+'\n'.join(rows)+'\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vocal-reference', type=Path, required=True)
    p.add_argument('--zoom-video', type=Path, required=True)
    p.add_argument('--slug', required=True)
    p.add_argument('--offset', type=float, required=True, help='Zoom time minus vocal reference time')
    p.add_argument('--model', default='small')
    args = p.parse_args()
    if not args.slug.replace('_', '').isalnum() or not math.isfinite(args.offset):
        p.error('Use an alphanumeric/underscore slug and finite offset')
    for path in (args.vocal_reference, args.zoom_video):
        if not path.is_file():
            p.error(f'Missing input: {path}')
    if args.vocal_reference.resolve() == args.zoom_video.resolve():
        p.error('A separate original vocal track is required')
    import av
    from faster_whisper import WhisperModel
    with av.open(str(args.zoom_video)) as container:
        duration = container.duration / av.time_base
    folder = ROOT / 'work' / 'zoom_local' / args.slug
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'transcription.json').exists():
        p.error('Draft already exists; review it instead of overwriting')
    # Existing cached model only: never silently download or invoke an API.
    model = WhisperModel(args.model, device='cpu', compute_type='int8', local_files_only=True)
    segments, _ = model.transcribe(str(args.vocal_reference), language='en',
        word_timestamps=True, vad_filter=False, beam_size=5, condition_on_previous_text=False)
    records = []
    for segment in segments:
        records.append({'start': segment.start, 'end': segment.end, 'text': segment.text,
            'words': [{'start': w.start, 'end': w.end, 'word': w.word,
                       'probability': w.probability} for w in segment.words or []]})
        print(segment.text, flush=True)
    (folder / 'transcription.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    (folder / 'lyrics.draft.ass').write_text(make_ass(records, args.offset, duration), encoding='utf-8')
    subprocess.run([str(ROOT/'tools/ffmpeg/ffmpeg.exe'), '-v', 'error', '-n', '-i',
        str(args.zoom_video), '-vn', '-c:a', 'copy', str(folder/'backing.m4a')], check=True)
    (folder / 'REVIEW.txt').write_text(
        'DRAFT ONLY. Compare every word and highlight with the original Zoom video.\n'
        'Check matching arrangement and start/middle/end sync; offset alone cannot fix edits.\n'
        'Faster-Whisper is not forced alignment. Correct transcription/timing before rendering.\n'
        'Original Zoom AAC copied unchanged into backing.m4a. No vocal removal performed.\n', encoding='utf-8')
    print(folder)


if __name__ == '__main__':
    main()
