"""Remove encoder-buffer video-only tail, retaining all audio and source backups."""
from pathlib import Path
import json,subprocess,shutil
import av
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/remaining_13'
backup=WORK/'before_tail_trim'; backup.mkdir(exist_ok=True)
for j in json.loads((WORK/'manifest.json').read_text(encoding='utf-8')):
    path=ROOT/'out'/(j['slug']+'_Karaoke.mp4')
    if not path.exists():continue
    with av.open(str(path)) as c:
        seconds=c.duration/av.time_base
        a=c.streams.audio[0]
        audio_end=float((a.start_time or 0)*a.time_base+a.duration*a.time_base)
    if seconds-j['seconds']-3<.25:continue
    original=backup/path.name
    if not original.exists(): shutil.copy2(path,original)
    staged=WORK/(j['slug']+'.trimmed.mp4')
    subprocess.run([str(ROOT/'tools/ffmpeg/ffmpeg.exe'),'-v','error','-y','-i',str(original),'-t',str(audio_end+.04),'-map','0','-c','copy','-movflags','+faststart',str(staged)],check=True)
    def audiohash(p):
        return subprocess.run([str(ROOT/'tools/ffmpeg/ffmpeg.exe'),'-v','error','-i',str(p),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-'],capture_output=True,check=True).stdout
    assert audiohash(original)==audiohash(staged),'Audio payload changed'
    subprocess.run([str(ROOT/'tools/ffmpeg/ffmpeg.exe'),'-v','error','-i',str(staged),'-f','null','-'],check=True)
    shutil.copy2(staged,path)
    print(j['slug']+': video-only tail removed; audio payload unchanged',flush=True)
