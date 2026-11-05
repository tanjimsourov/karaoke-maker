"""Place user-supplied lyric lines on the song timeline.

Whisper's own words (often wrong in sung Danish) are only used as timing
anchors: user words are matched to them in order, each line takes the time of
its matched words, and unmatched lines are spread between their neighbours.
WhisperX then aligns every word inside these rough line windows.
"""
from __future__ import annotations
import difflib
import re

PAD = 0.3
MIN_LINE = 0.4


def parse_lyrics(text):
    """One sung line per row. Blank rows and [Chorus]-style labels are ignored."""
    lines = []
    for row in text.splitlines():
        row = re.sub(r'[{}\\]', '', row).strip()
        if not row or re.fullmatch(r'[\[(].*[\])]', row):
            continue
        lines.append(' '.join(row.split()))
    if not lines:
        raise ValueError('Lyrics file has no lines')
    return lines


PART = re.compile(r'^([A-Za-z]{1,3})\s*:\s+(.*)$')


def split_parts(lines):
    """'M: text' / 'F: text' / 'D: text' mark duet singers; the label lasts until changed."""
    texts, parts, current = [], [], None
    for line in lines:
        match = PART.match(line)
        if match:
            current, line = match[1].upper(), match[2]
        texts.append(line)
        parts.append(current)
    return texts, parts


def normal(word):
    return re.sub(r'[^\w]', '', word.lower())


def segment_words(segments):
    """Whisper words; segments without word timing are split by character length."""
    words = []
    for segment in segments:
        if segment.get('words'):
            words += [{'word': w['word'], 'start': w['start'], 'end': w['end']} for w in segment['words']]
            continue
        tokens = segment['text'].split()
        total = sum(len(t) for t in tokens) or 1
        cursor = segment['start']
        for token in tokens:
            length = (segment['end'] - segment['start']) * len(token) / total
            words.append({'word': token, 'start': cursor, 'end': cursor + length})
            cursor += length
    return words


def place_lines(lines, whisper_words, duration):
    user = [(i, normal(w)) for i, line in enumerate(lines) for w in line.split()]
    heard = [normal(w['word']) for w in whisper_words]
    matcher = difflib.SequenceMatcher(None, [w for _, w in user], heard, autojunk=False)
    spans = {}
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            line = user[block.a + k][0]
            word = whisper_words[block.b + k]
            start, end = spans.get(line, (word['start'], word['end']))
            spans[line] = (min(start, word['start']), max(end, word['end']))
    matched_words = sum(b.size for b in matcher.get_matching_blocks())

    # Keep anchors in order; a repeated chorus can match out of sequence.
    anchors, last = {}, 0.0
    for i in sorted(spans):
        start, end = spans[i]
        if start >= last and end > start:
            anchors[i] = (start, end)
            last = end

    timed = [None] * len(lines)
    for i, span in anchors.items():
        timed[i] = list(span)
    i = 0
    while i < len(lines):
        if timed[i]:
            i += 1
            continue
        j = i
        while j < len(lines) and not timed[j]:
            j += 1
        left = timed[i-1][1] if i else 0.0
        right = timed[j][0] if j < len(lines) else duration
        weights = [len(lines[k].split()) for k in range(i, j)]
        cursor, step = left, (right - left) / max(sum(weights), 1)
        for k, weight in zip(range(i, j), weights):
            timed[k] = [cursor, cursor + weight * step]
            cursor += weight * step
        i = j

    segments = []
    for k, (start, end) in enumerate(timed):
        low = timed[k-1][1] if k else 0.0
        high = timed[k+1][0] if k + 1 < len(timed) else duration
        start = max(low, start - PAD, 0.0)
        end = min(high, end + PAD, duration)
        if end - start < MIN_LINE:
            end = max(end, min(high, duration, start + MIN_LINE))
        segments.append({'start': round(start, 3), 'end': round(end, 3), 'text': lines[k]})
    report = {'lines': len(lines), 'anchored_lines': len(anchors),
              'matched_word_ratio': round(matched_words / max(len(user), 1), 3),
              'interpolated_lines': [k for k in range(len(lines)) if k not in anchors]}
    return segments, report
