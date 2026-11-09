"""Duration-aware 100 MB delivery ceiling (decimal bytes, never truncate media)."""
import math
import subprocess
from pathlib import Path
import av
from project_runtime import FFMPEG

MAX_BYTES = 99_999_999
TARGET_BYTES = 90_000_000

def video_budget(duration, audio_bps=192000):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid output duration')
    rate = int(TARGET_BYTES * 8 / duration - audio_bps)
    if rate < 100000:
        raise ValueError('Video is too long for the 100 MB limit with this audio bitrate')
    return rate

def constrained_args(duration, audio_bps=192000):
    rate=video_budget(duration,audio_bps)
    return ['-maxrate',str(rate),'-bufsize',str(rate)]

def enforce(path):
    """Only oversized renders need a second encode; retain processed audio packets."""
    path=Path(path)
    if path.stat().st_size <= MAX_BYTES:return
    from render_round_compact_batch import audio_hash
    with av.open(str(path)) as media:
        duration=media.duration/av.time_base
        width,height=media.streams.video[0].width,media.streams.video[0].height
        fps=media.streams.video[0].average_rate
        audio_bytes=sum(len(bytes(p)) for p in media.demux(audio=0))
    audio_bps=math.ceil(audio_bytes*8/duration)
    rate=video_budget(duration,audio_bps)
    target=path.with_name(path.stem+'.size-limit.mp4')
    if target.exists():raise FileExistsError(target)
    for attempt in range(2):
        print(f'[SIZE] Compressing to <=100 MB, attempt {attempt+1}',flush=True)
        subprocess.run([str(FFMPEG),'-hide_banner','-nostdin','-y','-i',str(path),
            '-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','fast',
            '-threads','4','-b:v',str(rate),'-maxrate',str(rate),'-bufsize',str(rate),
            '-pix_fmt','yuv420p','-c:a','copy','-map_metadata','0','-movflags','+faststart',str(target)],check=True)
        if target.stat().st_size <= MAX_BYTES:break
        rate=int(rate*.85)
    else:raise ValueError('Size limit could not be met; original preserved')
    with av.open(str(target)) as media:
        stream=media.streams.video[0]
        if (stream.width,stream.height,stream.average_rate)!=(width,height,fps):
            raise ValueError('Size correction changed video geometry/frame rate')
        if abs(media.duration/av.time_base-duration)>.1:raise ValueError('Duration changed')
    if audio_hash(path)!=audio_hash(target):raise ValueError('Processed audio changed')
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(target),'-f','null','-'],check=True)
    target.replace(path)
    print(f'[SIZE] Verified {path.stat().st_size/1e6:.1f} MB: {path}',flush=True)

if __name__=='__main__':
    import sys
    enforce(sys.argv[1])


def resolve_fps(value, source=None):
    if value == 'source':
        with av.open(str(source)) as media:
            rate=media.streams.video[0].average_rate
        if rate is None:raise ValueError('Source frame rate unavailable')
        value=min(float(rate),30.)
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 1<=value<=60:
        raise ValueError('Unsupported fps')
    return value


def bitrate_args(duration, target, audio_bps=192000):
    if type(target) is not int or not 100000<=target<=50000000:raise ValueError('Invalid video bitrate')
    rate=min(target,video_budget(duration,audio_bps))
    return ['-b:v',str(rate),'-maxrate',str(rate),'-bufsize',str(rate*2)]
