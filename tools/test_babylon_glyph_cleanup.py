"""Source-specific cleanup experiment; never replaces a delivered karaoke file.

Uses existing OCR locations and masks strokes instead of rectangular scenery.
Outputs are candidates for visual review, not proof of seamless restoration.
"""
import argparse
import bisect
import json
from pathlib import Path
import subprocess
import time

import av
import cv2
import numpy as np
from project_runtime import FFMPEG
from zoom_local_pipeline import digest


def clean(frame, boxes):
    result = frame.copy()
    height, width = frame.shape[:2]
    combined = np.zeros((height, width), np.uint8)
    for x, y, w, h in boxes:
        x, y = max(0, x), max(0, y)
        w, h = min(w, width-x), min(h, height-y)
        if min(w, h) <= 0:
            continue
        roi = frame[y:y+h, x:x+w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
        response = cv2.max(cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel),
                           cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel))
        mask = np.uint8(response > 25)*255
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
        combined[y:y+h, x:x+w] |= mask
    # Inpaint once at half resolution, then replace only detected stroke pixels.
    # Unmasked source pixels remain byte-identical before video encoding.
    small = cv2.resize(frame, (width//2, height//2), interpolation=cv2.INTER_AREA)
    mask_small = cv2.resize(combined, (width//2, height//2), interpolation=cv2.INTER_NEAREST)
    restored = cv2.inpaint(small, mask_small, 3, cv2.INPAINT_TELEA)
    restored = cv2.resize(restored, (width, height), interpolation=cv2.INTER_CUBIC)
    result[combined > 0] = restored[combined > 0]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--detections', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--start', type=float, default=0)
    p.add_argument('--seconds', type=float, default=8)
    a = p.parse_args()
    if a.start < 0 or a.seconds <= 0:
        p.error('Invalid clip bounds')
    if a.output.exists():
        raise FileExistsError(a.output)
    report = json.loads(a.detections.read_text())
    if digest(a.source) != report['binding']['source'] or not report['complete']:
        raise ValueError('OCR cache is incomplete or source has changed')
    rows = report['frames']; times = [r['time'] for r in rows]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter(); count = 0
    with av.open(str(a.source)) as container:
        stream = container.streams.video[0]; stream.thread_count = 2
        rate = str(stream.average_rate)
        command = [str(FFMPEG), '-v', 'error', '-n', '-f', 'rawvideo',
                   '-pix_fmt', 'bgr24', '-s', f'{stream.width}x{stream.height}',
                   '-r', rate, '-i', 'pipe:0', '-an', '-c:v', 'libx264',
                   '-preset', 'veryfast', '-crf', '14', '-threads', '3',
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(a.output)]
        container.seek(int(a.start*av.time_base))
        with a.output.with_suffix('.log').open('w') as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
            try:
                for frame in container.decode(video=0):
                    if frame.time < a.start:
                        continue
                    if frame.time >= a.start+a.seconds:
                        break
                    index = bisect.bisect_left(times, frame.time)
                    candidates = rows[max(0,index-1):min(len(rows),index+1)]
                    boxes = set(tuple(b) for r in candidates
                                if abs(r['time']-frame.time) < .6 for b in r['boxes'])
                    result = clean(frame.to_ndarray(format='bgr24'), sorted(boxes))
                    process.stdin.write(result.tobytes()); count += 1
                    if count % 240 == 0:
                        print(f'Processed source time {frame.time:.2f}s', flush=True)
            finally:
                process.stdin.close()
                status = process.wait()
            if status:
                raise RuntimeError(f'Encoder failed: {status}; see log')
    a.output.with_suffix('.json').write_text(json.dumps({
        'source':str(a.source), 'source_sha256':report['binding']['source'],
        'output_sha256':digest(a.output), 'start':a.start, 'seconds':a.seconds,
        'frames':count, 'elapsed_seconds':time.perf_counter()-started,
        'status':'experimental picture-only candidate; inspect before use',
        'limitations':'OCR-guided stroke masks; may leave ghosts or affect nearby detail'
    }, indent=2))


if __name__ == '__main__':
    main()
