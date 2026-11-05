"""Replace a full-timeline backing track while copying encoded video unchanged."""
import argparse
import math
from pathlib import Path
import subprocess
import av
from project_runtime import FFMPEG
from zoom_local_pipeline import save,digest,audio,check_audio

def duration(path):
    with av.open(str(path)) as c:return c.duration/av.time_base

def video_hash(path):
    return subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-map','0:v:0',
        '-c:v','copy','-f','hash','-hash','sha256','-'],capture_output=True,check=True).stdout.strip().decode()

def replace(video,backing,output,intro=0,copy_audio=False):
    video,backing,output=map(Path,(video,backing,output))
    if output.exists():raise FileExistsError(output)
    if not math.isfinite(intro) or intro<0 or intro>60:raise ValueError('Intro must be 0..60 seconds')
    vd=duration(video);ad=duration(backing)
    if abs(vd-ad-intro)>.15:raise ValueError('Backing duration does not match video timeline plus intro')
    if copy_audio and intro:raise ValueError('Stream-copy requires an already finalized audio timeline')
    if copy_audio:
        with av.open(str(backing)) as c:
            if c.streams.audio[0].codec_context.name!='aac':raise ValueError('MP4 audio-copy profile requires AAC')
    before=video_hash(video)
    output.parent.mkdir(parents=True,exist_ok=True)
    cmd=[str(FFMPEG),'-v','error','-n','-i',str(video),'-i',str(backing),'-map','0:v:0','-map','1:a:0','-c:v','copy']
    if copy_audio:cmd+=['-c:a','copy']
    else:
        if intro:cmd+=['-af',f'adelay={round(intro*1000)}:all=1']
        cmd+=['-c:a','aac','-b:a','320k']
    cmd+=['-map_metadata','-1','-movflags','+faststart',str(output)]
    subprocess.run(cmd,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(output),'-f','null','-'],check=True)
    if video_hash(output)!=before:raise ValueError('Video stream changed during audio-only replacement')
    result=check_audio(audio(backing),audio(output),delay=round(intro*16000))
    receipt={'source_video':str(video),'backing':str(backing),'output':str(output),
        'sha256':digest(output),'video_stream_unchanged':True,'audio_check':result,
        'intro_seconds':intro,'review_status':'new_audio_requires_review'}
    save(output.with_suffix('.replacement.json'),receipt)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('video','backing','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--intro-seconds',type=float,default=0)
    p.add_argument('--copy-audio',action='store_true')
    a=p.parse_args();print(replace(a.video,a.backing,a.output,a.intro_seconds,a.copy_audio))
