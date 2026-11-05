"""Delivery extras next to an approved karaoke video: word-timed LRC, thumbnail
and a short teaser clip. Times in the LRC include the renderer's intro delay so
they match the MP4."""
from __future__ import annotations
from pathlib import Path
import subprocess

INTRO = 3.0


def lrc_time(seconds):
    minutes, rest = divmod(max(0.0, seconds), 60)
    return f'{int(minutes):02d}:{rest:05.2f}'


def enhanced_lrc(segments, title, artist, offset=INTRO, start=0.0, end=None):
    """Enhanced LRC: [mm:ss.xx] per line and <mm:ss.xx> per word (most karaoke players)."""
    rows = [f'[ti:{title}]', f'[ar:{artist}]', '[re:karaoke-maker]']
    for segment in segments:
        words = [{**w, 'start': max(start, w['start']+offset)-start,
                  'end': min(end, w['end']+offset)-start if end is not None else w['end']+offset-start}
                 for w in segment.get('words', []) if 'start' in w and 'end' in w
                 and w['end']+offset > start and (end is None or w['start']+offset < end)]
        if not words:
            continue
        line = ' '.join(f'<{lrc_time(w["start"])}>{w["word"].strip()}' for w in words)
        rows.append(f'[{lrc_time(words[0]["start"])}]{line} <{lrc_time(words[-1]["end"])}>')
    return '\n'.join(rows) + '\n'


def busiest_moment(segments, window=30.0, offset=INTRO):
    """Start of the 30 s window with the most sung words (usually the chorus)."""
    starts = sorted(w['start'] + offset for s in segments for w in s.get('words', []) if 'start' in w)
    if not starts:
        return offset
    best, best_count, j = starts[0], 0, 0
    for i, start in enumerate(starts):
        while starts[j] < start - window:
            j += 1
        if i - j + 1 > best_count:
            best, best_count = starts[j], i - j + 1
    return max(0.0, best - 1.0)


def write_extras(ffmpeg, video, segments, title, artist, teaser_seconds=30.0, offset=INTRO, start=0.0, end=None):
    video = Path(video)
    stem = video.with_suffix('')
    outputs = {}
    lrc = Path(f'{stem}.lrc')
    if any(Path(str(stem)+suffix).exists() for suffix in ('.lrc', '_thumb.jpg', '_teaser.mp4')):
        raise FileExistsError('Delivery extras already exist; choose a new export revision')
    with lrc.open('x', encoding='utf-8') as stream:
        stream.write(enhanced_lrc(segments, title, artist, offset, start, end))
    outputs['lrc'] = str(lrc)
    import av
    with av.open(str(video)) as media:
        duration = media.duration / av.time_base
    teaser_seconds = min(teaser_seconds, duration)
    moment = min(max(0, busiest_moment(segments, teaser_seconds, offset)-start), max(0, duration-teaser_seconds))
    thumb = Path(f'{stem}_thumb.jpg')
    subprocess.run([str(ffmpeg), '-v', 'error', '-n', '-ss', f'{min(duration-.04,moment+4):.2f}', '-i', str(video),
                    '-frames:v', '1', '-q:v', '2', str(thumb)], check=True)
    outputs['thumbnail'] = str(thumb)
    teaser = Path(f'{stem}_teaser.mp4')
    subprocess.run([str(ffmpeg), '-v', 'error', '-n', '-ss', f'{moment:.2f}', '-i', str(video),
                    '-t', f'{teaser_seconds:g}', '-af', f'afade=t=in:d=0.2,afade=t=out:st={max(0,teaser_seconds-.5):g}:d=0.5',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-c:a', 'aac', '-b:a', '160k',
                    '-movflags', '+faststart', str(teaser)], check=True)
    outputs['teaser'] = str(teaser)
    return outputs
