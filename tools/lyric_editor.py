"""Edit operations on aligned.json (word-timed lyric lines), no UI needed.

Every operation takes the segment list and returns a new one; `validate`
rejects results with words out of order, overlapping or with no duration.
Line and word numbers are 1-based, as printed by `show`.
"""
from __future__ import annotations
import copy
import math

MIN_WORD = 0.02


def _line(segments, line):
    if not 1 <= line <= len(segments):
        raise ValueError(f'Line {line} does not exist (1-{len(segments)})')
    return segments[line - 1]


def _resync(segment):
    """Segment text/start/end follow its words."""
    words = segment['words']
    if words:
        segment['text'] = ' '.join(w['word'].strip() for w in words)
        segment['start'], segment['end'] = words[0]['start'], words[-1]['end']
    return segment


def show(segments, line=None):
    rows = []
    for number, segment in enumerate(segments, 1):
        if line and number != line:
            continue
        words = '  '.join(f"{i}:{w['word'].strip()}[{w.get('start', '?')}-{w.get('end', '?')}]"
                          for i, w in enumerate(segment['words'], 1))
        part = f" ({segment['part']})" if segment.get('part') else ''
        rows.append(f"{number:3d}{part} {segment.get('start', 0):7.2f}-{segment.get('end', 0):7.2f}  {words}")
    return '\n'.join(rows)


def set_text(segments, line, text):
    """New wording for a line. Same word count keeps every word's timing; otherwise
    the new words share the line's time in proportion to their length."""
    result = copy.deepcopy(segments)
    segment = _line(result, line)
    new = text.split()
    if not new or any(c in text for c in '{}\\'):
        raise ValueError('Text must be non-empty and contain no { } \\')
    old = segment['words']
    if len(new) == len(old):
        for word, value in zip(old, new):
            word['word'] = value
    else:
        start, end = old[0]['start'], old[-1]['end']
        total = sum(len(w) for w in new)
        cursor, words = start, []
        for value in new:
            length = (end - start) * len(value) / total
            words.append({'word': value, 'start': round(cursor, 3), 'end': round(cursor + length, 3)})
            cursor += length
        segment['words'] = words
    return [_resync(s) if i == line - 1 else s for i, s in enumerate(result)]


def shift(segments, seconds, line=None, until=None):
    """Move one line, a range of lines, or (no line) the whole song."""
    result = copy.deepcopy(segments)
    first = line or 1
    last = until or line or len(result)
    for number in range(first, last + 1):
        segment = _line(result, number)
        for word in segment['words']:
            word['start'] = round(word['start'] + seconds, 3)
            word['end'] = round(word['end'] + seconds, 3)
        _resync(segment)
    return result


def set_word(segments, line, word, start=None, end=None):
    result = copy.deepcopy(segments)
    words = _line(result, line)['words']
    if not 1 <= word <= len(words):
        raise ValueError(f'Line {line} has words 1-{len(words)}')
    target = words[word - 1]
    if start is not None:
        target['start'] = round(start, 3)
    if end is not None:
        target['end'] = round(end, 3)
    _resync(result[line - 1])
    return result


def stretch(segments, line, start, end):
    """Fit a whole line into new start/end times, keeping relative word timing."""
    result = copy.deepcopy(segments)
    segment = _line(result, line)
    old_start, old_end = segment['words'][0]['start'], segment['words'][-1]['end']
    scale = (end - start) / max(old_end - old_start, 1e-6)
    for word in segment['words']:
        word['start'] = round(start + (word['start'] - old_start) * scale, 3)
        word['end'] = round(start + (word['end'] - old_start) * scale, 3)
    _resync(segment)
    return result


def split(segments, line, at_word):
    """Line `line` becomes two lines; the second starts at word `at_word`."""
    result = copy.deepcopy(segments)
    segment = _line(result, line)
    if not 2 <= at_word <= len(segment['words']):
        raise ValueError(f'Split position must be word 2-{len(segment["words"])}')
    second = {**copy.deepcopy(segment), 'words': segment['words'][at_word - 1:]}
    segment['words'] = segment['words'][:at_word - 1]
    result.insert(line, _resync(second))
    _resync(segment)
    return result


def merge(segments, line):
    """Join line `line` with the following line."""
    result = copy.deepcopy(segments)
    segment, following = _line(result, line), _line(result, line + 1)
    segment['words'] += following['words']
    del result[line]
    _resync(segment)
    return result


def delete(segments, line):
    result = copy.deepcopy(segments)
    _line(result, line)
    del result[line - 1]
    if not result:
        raise ValueError('Cannot delete the last line')
    return result


def set_part(segments, line, part, until=None):
    """Duet part (M/F/D...) for one line or a range; empty removes it."""
    result = copy.deepcopy(segments)
    for number in range(line, (until or line) + 1):
        segment = _line(result, number)
        if part:
            segment['part'] = part.upper()
        else:
            segment.pop('part', None)
    return result


def insert(segments, after, text, start, end):
    """A new line after line `after` (0 = before the first), words spread by length."""
    if not 0 <= after <= len(segments):
        raise ValueError(f'--insert-after must be 0-{len(segments)}')
    new = text.split()
    if not new or any(c in text for c in '{}\\'):
        raise ValueError('Text must be non-empty and contain no { } \\')
    if end <= start:
        raise ValueError('Inserted line needs --start before --end')
    total = sum(len(w) for w in new)
    cursor, words = start, []
    for value in new:
        length = (end - start) * len(value) / total
        words.append({'word': value, 'start': round(cursor, 3), 'end': round(cursor + length, 3)})
        cursor += length
    result = copy.deepcopy(segments)
    result.insert(after, _resync({'text': text, 'words': words}))
    return result


# Per-line style keys (like Karadeo's per-item styling). Colours are #RRGGBB,
# x/y are canvas pixels at 1920x1080 reference, sizes are 1080p pixels.
STYLE_KEYS = {
    'font': str, 'size': float, 'bold': bool, 'italic': bool,
    'colour': str, 'highlight_colour': str, 'outline_colour': str, 'outline': float,
    'highlight_outline_colour': str, 'shadow': float, 'opacity': float,
    'letter_spacing': float, 'rotation': float, 'x': float, 'y': float,
    'fade_in': float, 'fade_out': float, 'box_colour': str,
}


def parse_style(pairs):
    """['size=90', 'colour=#FF0000'] -> {'size': 90.0, 'colour': '#FF0000'}"""
    style = {}
    for pair in pairs:
        key, sep, value = pair.partition('=')
        key = key.strip().lower().replace('color', 'colour')
        if not sep or key not in STYLE_KEYS:
            raise ValueError(f'Unknown style "{pair}"; keys: {", ".join(STYLE_KEYS)}')
        kind = STYLE_KEYS[key]
        if kind is bool:
            style[key] = value.strip().lower() in ('1', 'true', 'yes', 'on')
        elif kind is float:
            style[key] = float(value)
        else:
            value = value.strip()
            if key.endswith('colour') and not (len(value) == 7 and value.startswith('#')):
                raise ValueError(f'{key} must be #RRGGBB')
            style[key] = value
    if 'opacity' in style and not 0 <= style['opacity'] <= 1:
        raise ValueError('opacity must be 0-1')
    return style


def set_style(segments, style, line=None, until=None, clear=False):
    """Style one line, a range, or (no line) every line - Karadeo's styling scope."""
    result = copy.deepcopy(segments)
    first, last = (line or 1), (until or line or len(result))
    for number in range(first, last + 1):
        segment = _line(result, number)
        if clear:
            segment.pop('style', None)
        else:
            segment['style'] = {**segment.get('style', {}), **style}
    return result


def snap_to_beats(segments, beats, line=None, until=None, tolerance=0.12):
    """Move each line so its first word lands on the nearest beat (within tolerance).
    Lines move as a whole, so word rhythm inside a line is kept."""
    import bisect
    if not beats:
        raise ValueError('No beats detected')
    result = copy.deepcopy(segments)
    moved = 0
    for number in range((line or 1), (until or line or len(result)) + 1):
        segment = _line(result, number)
        start = segment['words'][0]['start']
        i = bisect.bisect_left(beats, start)
        nearest = min((b for b in beats[max(0, i - 1):i + 1]), key=lambda b: abs(b - start))
        delta = nearest - start
        if 0 < abs(delta) <= tolerance:
            for word in segment['words']:
                word['start'] = round(word['start'] + delta, 3)
                word['end'] = round(word['end'] + delta, 3)
            _resync(segment)
            moved += 1
    return result, moved


def validate(segments, duration=None):
    """Raise on anything the renderer would draw wrongly."""
    previous = 0.0
    for number, segment in enumerate(segments, 1):
        if not segment.get('words'):
            raise ValueError(f'Line {number} has no words')
        for index, word in enumerate(segment['words'], 1):
            where = f"line {number} word {index} '{word.get('word', '').strip()}'"
            if 'start' not in word or 'end' not in word:
                raise ValueError(f'{where} has no timing')
            if not all(isinstance(word[k], (int, float)) and math.isfinite(word[k]) for k in ('start', 'end')):
                raise ValueError(f'{where} has nonfinite timing')
            if word['start'] < 0 or (duration and word['end'] > duration):
                raise ValueError(f'{where} is outside the song')
            if word['end'] - word['start'] < MIN_WORD:
                raise ValueError(f'{where} ends before it starts or is too short')
            if word['start'] < previous - 1e-3:
                raise ValueError(f'{where} starts at {word["start"]}s, before the previous word ends ({previous}s)')
            previous = word['end']
    return segments
