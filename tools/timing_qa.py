"""Automatic word-timing checks after alignment, so problems surface before preview.

Each issue names the line, word and time, so it can be fixed in aligned.json
(or by correcting the lyric line and aligning again).
"""
from __future__ import annotations
import numpy as np

MIN_WORD = 0.06      # shorter is almost always a missed alignment
MAX_WORD = 4.0       # longer usually swallowed an instrumental gap
SILENCE_DB = -45     # vocal-stem level counted as silence
FRAME = 0.05         # seconds per loudness frame


def vocal_activity(samples, rate=16000):
    """Per-frame vocal level in dBFS from the separated vocal stem."""
    hop = int(rate * FRAME)
    frames = len(samples) // hop
    if not frames:
        return np.array([])
    power = np.mean(samples[:frames * hop].reshape(frames, hop) ** 2, axis=1)
    return 10 * np.log10(np.maximum(power, 1e-12))


def silent_fraction(levels, start, end):
    a, b = int(start / FRAME), max(int(start / FRAME) + 1, int(end / FRAME))
    window = levels[a:b]
    return float(np.mean(window < SILENCE_DB)) if len(window) else 1.0


def timing_report(segments, vocal_samples=None, rate=16000):
    levels = vocal_activity(vocal_samples, rate) if vocal_samples is not None else None
    issues = []
    previous_end = 0.0
    for line_no, segment in enumerate(segments, 1):
        text = segment.get('text', '').strip()
        for word in segment.get('words', []):
            label = {'line': line_no, 'text': text, 'word': word.get('word', '').strip()}
            if 'start' not in word or 'end' not in word:
                issues.append({**label, 'problem': 'not aligned (no timing)'})
                continue
            start, end = word['start'], word['end']
            label['time'] = round(start, 2)
            if end - start < MIN_WORD - 1e-6:
                issues.append({**label, 'problem': f'too short ({end - start:.2f}s)'})
            elif end - start > MAX_WORD:
                issues.append({**label, 'problem': f'too long ({end - start:.1f}s): probably spans a gap'})
            if start < previous_end - 0.02:
                issues.append({**label, 'problem': f'overlaps previous word by {previous_end - start:.2f}s'})
            if levels is not None and len(levels) and end - start >= 0.15 and silent_fraction(levels, start, end) > 0.8:
                issues.append({**label, 'problem': 'placed where the vocal stem is silent'})
            previous_end = max(previous_end, end)
    words = sum(len(s.get('words', [])) for s in segments)
    return {'words': words, 'issues': issues,
            'score': round(1 - len({(i['line'], i.get('time')) for i in issues}) / max(words, 1), 3)}
