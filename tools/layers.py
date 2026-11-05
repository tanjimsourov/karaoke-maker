"""Timeline layers on top of the karaoke video, like Karadeo's extra tracks.

layers.json (per song, all times in song seconds, positions/sizes in pixels
of a 1920x1080 reference canvas; x/y are the item's centre):

{
  "backing": {"volume_db": 0, "mute": false},
  "texts":  [{"text": "Chorus!", "start": 30, "end": 34, "x": 960, "y": 160,
              "size": 70, "colour": "#FFFFFF", "outline": 4, "outline_colour": "#000000",
              "font": "Arial", "bold": true, "opacity": 1, "rotation": 0,
              "fade_in": 0.2, "fade_out": 0.2,
              "keyframes": [{"t": 0, "x": 960, "y": 200, "scale": 1, "opacity": 1, "rotation": 0}]}],
  "media":  [{"file": "work/logo.png", "start": 10, "end": 20, "x": 300, "y": 200,
              "width": 400, "height": null, "source_start": 0, "speed": 1, "opacity": 1,
              "rotation": 0, "fade_in": 0.5, "fade_out": 0.5, "crop": [0, 0, 0, 0],
              "keyframes": [{"t": 0, "x": 300, "y": 200, "scale": 1}]}],
  "audio":  [{"file": "sfx/applause.wav", "start": 200, "source_start": 0, "duration": 8,
              "volume_db": -6, "fade_in": 0, "fade_out": 1, "mute": false}]
(without "duration", an audio fade_out ends at the end of the file)
}

Keyframe "t" is seconds from the item's start; values between keyframes are
interpolated linearly. Text keyframes animate x, y, scale, opacity and
rotation; media keyframes animate x, y, scale and opacity.
"""
from __future__ import annotations
import copy
import math
from pathlib import Path

IMAGE = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
VIDEO = {'.mp4', '.mov', '.webm', '.mkv', '.gif'}
TEXT_KEYS = {'text', 'start', 'end', 'x', 'y', 'size', 'colour', 'outline', 'outline_colour', 'font',
             'bold', 'italic', 'opacity', 'rotation', 'fade_in', 'fade_out', 'keyframes'}
MEDIA_KEYS = {'file', 'start', 'end', 'x', 'y', 'width', 'height', 'source_start', 'speed', 'opacity',
              'rotation', 'fade_in', 'fade_out', 'crop', 'keyframes', 'timeline'}
AUDIO_KEYS = {'file', 'start', 'source_start', 'duration', 'volume_db', 'fade_in', 'fade_out', 'mute'}
KEYFRAME_KEYS = {'t', 'x', 'y', 'scale', 'opacity', 'rotation'}


def empty():
    return {'backing': {'volume_db': 0.0, 'mute': False}, 'texts': [], 'media': [], 'audio': []}


def validate(layers, root):
    """Raise ValueError naming the first bad item; returns the layers."""
    unknown = set(layers) - {'backing', 'texts', 'media', 'audio'}
    if unknown:
        raise ValueError(f'Unknown layer section(s): {sorted(unknown)}')
    for kind, allowed in (('texts', TEXT_KEYS), ('media', MEDIA_KEYS), ('audio', AUDIO_KEYS)):
        for number, item in enumerate(layers.get(kind, []), 1):
            where = f'{kind} {number}'
            extra = set(item) - allowed
            if extra:
                raise ValueError(f'{where}: unknown key(s) {sorted(extra)}')
            if kind=='media' and item.get('timeline','source') not in ('source','output'):
                raise ValueError(f'{where}: timeline must be source or output')
            for key, value in item.items():
                if isinstance(value, (float, int)) and not math.isfinite(value):
                    raise ValueError(f'{where}: {key} must be finite')
            if item.get('start', 0) < 0:
                raise ValueError(f'{where}: start must be >= 0')
            if 'end' in allowed and item.get('end') is not None and item['end'] <= item.get('start', 0):
                raise ValueError(f'{where}: end must be after start')
            if 'file' in allowed:
                path = Path(item.get('file', ''))
                path = path if path.is_absolute() else root / path
                if not path.is_file():
                    raise ValueError(f'{where}: file not found {path}')
                if kind == 'media' and path.suffix.lower() not in IMAGE | VIDEO:
                    raise ValueError(f'{where}: unsupported media type {path.suffix}')
            if kind == 'texts' and (not item.get('text') or any(c in item['text'] for c in '{}\\')):
                raise ValueError(f'{where}: text must be non-empty without {{ }} \\')
            if not 0 <= item.get('opacity', 1) <= 1:
                raise ValueError(f'{where}: opacity must be 0-1')
            if item.get('speed', 1) <= 0:
                raise ValueError(f'{where}: speed must be > 0')
            for frame in item.get('keyframes', []):
                if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in frame.values()):
                    raise ValueError(f'{where}: keyframe values must be finite numbers')
                if set(frame) - KEYFRAME_KEYS or 't' not in frame or frame['t'] < 0:
                    raise ValueError(f'{where}: keyframes need t >= 0 and keys {sorted(KEYFRAME_KEYS)}')
    return layers


def resolve(path, root):
    path = Path(path)
    return str(path if path.is_absolute() else root / path)


# ----- editing -------------------------------------------------------------

def add(layers, kind, item):
    result = copy.deepcopy(layers)
    result.setdefault(kind, []).append(item)
    return result


def remove(layers, kind, number):
    result = copy.deepcopy(layers)
    items = result.get(kind, [])
    if not 1 <= number <= len(items):
        raise ValueError(f'No {kind} item {number} (have {len(items)})')
    del items[number - 1]
    return result


def update(layers, kind, number, values):
    result = copy.deepcopy(layers)
    items = result.get(kind, [])
    if not 1 <= number <= len(items):
        raise ValueError(f'No {kind} item {number} (have {len(items)})')
    items[number - 1].update(values)
    return result


def add_keyframe(layers, kind, number, frame):
    """Insert or replace the keyframe at time frame['t'] (seconds from item start)."""
    result = copy.deepcopy(layers)
    items = result.get(kind, [])
    if not 1 <= number <= len(items):
        raise ValueError(f'No {kind} item {number} (have {len(items)})')
    frames = [k for k in items[number - 1].get('keyframes', []) if abs(k['t'] - frame['t']) > 1e-6]
    items[number - 1]['keyframes'] = sorted(frames + [frame], key=lambda k: k['t'])
    return result


def describe(layers):
    rows = [f"backing: {layers.get('backing', {})}"]
    for kind in ('texts', 'media', 'audio'):
        for number, item in enumerate(layers.get(kind, []), 1):
            label = item.get('text') or item.get('file')
            span = f"{item.get('start', 0)}-{item.get('end', 'end')}"
            frames = f", {len(item['keyframes'])} keyframes" if item.get('keyframes') else ''
            rows.append(f'{kind} {number}: {label!r} {span}s{frames}')
    return '\n'.join(rows)


# ----- rendering helpers -----------------------------------------------------

def track(item, key, default):
    """[(absolute time, value)] for one animated property, from keyframes."""
    base = item.get(key, default)
    points = [(item['start'] + k['t'], k[key]) for k in item.get('keyframes', []) if key in k]
    return points or [(item['start'], base)]


def value_at(points, t):
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(t1 - t0, 1e-6)
    return points[-1][1]


def ffmpeg_expression(points, offset=0.0, scale=1.0, var='t'):
    """Piecewise-linear FFmpeg expression of time for keyframe points
    (var 't' in scale/overlay, 'T' in geq)."""
    points = [(t + offset, v * scale) for t, v in points]
    expr = f'{points[-1][1]:.3f}'
    for (t0, v0), (t1, v1) in reversed(list(zip(points, points[1:]))):
        expr = f'if(lt({var},{t1:.3f}),{v0:.3f}+({v1 - v0:.3f})*({var}-{t0:.3f})/{max(t1 - t0, 1e-6):.3f},{expr})'
    return f'if(lt({var},{points[0][0]:.3f}),{points[0][1]:.3f},{expr})'


def media_seconds(path):
    """Length of an audio/video file in seconds (PyAV), or None if unknown."""
    import av
    with av.open(str(path)) as container:
        return container.duration / av.time_base if container.duration else None


def text_events(item, delay, sx, sy, fs, ass_time, ass_colour, end_default):
    """ASS Dialogue lines for one text overlay; keyframes become \\move and \\t."""
    start, end = item['start'], item.get('end') or end_default
    track_keys = {key: track(item, key, default) for key, default in
                  (('x', 960), ('y', 540), ('scale', 1.0), ('opacity', item.get('opacity', 1.0)),
                   ('rotation', item.get('rotation', 0.0)))}
    cuts = sorted({start, end, *[start + k['t'] for k in item.get('keyframes', []) if start + k['t'] < end]})
    style = (f"\\an5\\fn{item.get('font', 'Arial')}\\fs{round(item.get('size', 70) * fs)}"
             f"\\b{1 if item.get('bold', True) else 0}\\i{1 if item.get('italic') else 0}"
             f"\\1c&H{ass_colour(item.get('colour', '#FFFFFF'))[4:]}&"
             f"\\3c&H{ass_colour(item.get('outline_colour', '#000000'))[4:]}&"
             f"\\bord{item.get('outline', 4) * fs:.1f}\\shad0")
    events = []
    for index, (a, b) in enumerate(zip(cuts, cuts[1:])):
        x0, y0 = value_at(track_keys['x'], a) * sx, value_at(track_keys['y'], a) * sy
        x1, y1 = value_at(track_keys['x'], b) * sx, value_at(track_keys['y'], b) * sy
        s0, s1 = (value_at(track_keys['scale'], t) * 100 for t in (a, b))
        o0, o1 = (value_at(track_keys['opacity'], t) for t in (a, b))
        r0, r1 = (value_at(track_keys['rotation'], t) for t in (a, b))
        alpha = lambda o: f'&H{round((1 - o) * 255):02X}&'
        length = round((b - a) * 1000)
        tags = (f"{style}\\move({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f})"
                f"\\fscx{s0:.0f}\\fscy{s0:.0f}\\alpha{alpha(o0)}\\frz{r0:.1f}"
                f"\\t(0,{length},\\fscx{s1:.0f}\\fscy{s1:.0f}\\alpha{alpha(o1)}\\frz{r1:.1f})")
        fade_in = round(item.get('fade_in', 0) * 1000) if index == 0 else 0
        fade_out = round(item.get('fade_out', 0) * 1000) if b == end else 0
        if fade_in or fade_out:
            tags += f'\\fad({fade_in},{fade_out})'
        events.append(f"Dialogue: 4,{ass_time(a + delay)},{ass_time(b + delay)},PageBase,,0,0,0,,{{{tags}}}{item['text']}")
    return events


def media_graph(items, first_input, root, delay, sx, sy, fps):
    """(input args, filter chains) overlaying media items onto [bg], producing [bgx]."""
    inputs, chains, previous = [], [], 'bg'
    for number, item in enumerate(items):
        item_delay=0 if item.get('timeline')=='output' else delay
        path = resolve(item['file'], root)
        index = first_input + number
        is_image = Path(path).suffix.lower() in IMAGE
        start = item['start'] + item_delay
        end = (item['end'] if item.get('end') is not None else 10 ** 6) + item_delay
        if is_image:
            inputs += ['-loop', '1', '-framerate', str(fps), '-i', path]
        else:
            inputs += ['-ss', f"{item.get('source_start', 0):.3f}", '-i', path]
        steps = [f'fps={fps}']
        left, top, right, bottom = item.get('crop', [0, 0, 0, 0])
        if any((left, top, right, bottom)):
            steps.append(f'crop=iw-{left + right}:ih-{top + bottom}:{left}:{top}')
        speed = item.get('speed', 1)
        steps.append(f'setpts=PTS/{speed:g}-STARTPTS+{start:.3f}/TB')
        if item.get('end') is not None:
            # Stop requesting/decompressing an intro PNG after its interval.
            # Merely disabling overlay still processes its input for the song.
            steps.append(f'trim=end={end:.3f}')
        width, height = item.get('width'), item.get('height')
        scale_points = track(item, 'scale', 1.0)
        w = f'{(width or 0) * sx:.1f}*({ffmpeg_expression(scale_points, item_delay)})' if width else 'iw'
        h = f'{height * sy:.1f}*({ffmpeg_expression(scale_points, item_delay)})' if height else '-1'
        if not width and not height:
            w = f'iw*({ffmpeg_expression(scale_points, item_delay)})'
        steps.append(f"scale=w='{w}':h='{h}':eval=frame")
        steps.append('format=rgba')
        if any('opacity' in k for k in item.get('keyframes', [])):
            # Animated transparency: scale every pixel's alpha by the keyframed opacity at time T.
            opacity = ffmpeg_expression(track(item, 'opacity', item.get('opacity', 1.0)), item_delay, var='T')
            steps.append(f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*clip({opacity},0,1)'")
        elif item.get('opacity', 1) < 1:
            steps.append(f"colorchannelmixer=aa={item['opacity']:.3f}")
        if item.get('rotation') or any('rotation' in k for k in item.get('keyframes', [])):
            angle = ffmpeg_expression(track(item, 'rotation', item.get('rotation', 0)), item_delay)
            steps.append(f"rotate=angle='({angle})*PI/180':c=none:ow='hypot(iw,ih)':oh='hypot(iw,ih)'")
        if item.get('fade_in'):
            steps.append(f"fade=t=in:st={start:.3f}:d={item['fade_in']}:alpha=1")
        if item.get('fade_out') and item.get('end'):
            steps.append(f"fade=t=out:st={end - item['fade_out']:.3f}:d={item['fade_out']}:alpha=1")
        chains.append(f'[{index}:v]' + ','.join(steps) + f'[m{number}]')
        x = ffmpeg_expression(track(item, 'x', 960), item_delay, sx)
        y = ffmpeg_expression(track(item, 'y', 540), item_delay, sy)
        out = 'bgx' if number == len(items) - 1 else f'o{number}'
        chains.append(f"[{previous}][m{number}]overlay=x='{x}-w/2':y='{y}-h/2'"
                      f":enable='between(t,{start:.3f},{end:.3f})':eof_action=pass[{out}]")
        previous = out
    return inputs, (';'.join(chains) + ';') if chains else ''


def audio_graph(tracks, first_input, root, delay):
    """(input args, chain labels, filter chains) for extra audio tracks."""
    inputs, chains, labels = [], [], []
    for number, item in enumerate(t for t in tracks if not t.get('mute')):
        index = first_input + number
        inputs += ['-ss', f"{item.get('source_start', 0):.3f}", '-i', resolve(item['file'], root)]
        steps = [f"volume={item.get('volume_db', 0):.2f}dB"]
        length = item.get('duration')
        if length:
            steps.append(f"atrim=0:{length:.3f}")
        elif item.get('fade_out'):
            # No duration given: the fade-out ends where the file itself ends.
            total = media_seconds(resolve(item['file'], root))
            length = total - item.get('source_start', 0) if total else None
        if item.get('fade_in'):
            steps.append(f"afade=t=in:st=0:d={item['fade_in']}")
        if item.get('fade_out') and length:
            steps.append(f"afade=t=out:st={max(0, length - item['fade_out']):.3f}:d={item['fade_out']}")
        steps.append(f"adelay={round((item['start'] + delay) * 1000)}:all=1")
        chains.append(f'[{index}:a]' + ','.join(steps) + f'[x{number}]')
        labels.append(f'[x{number}]')
    return inputs, labels, chains
