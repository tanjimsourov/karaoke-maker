"""Keep five seconds before the first highlight, preserving original exports."""
from pathlib import Path
import json
import subprocess
import sys
import av
from zoom_local_pipeline import ROOT, FFMPEG, audio, check_audio, digest, save

SLUGS=['Zoom_Get_Ready_For_This','Zoom_Whats_Up']
def main(index):
    slug=SLUGS[index]
    record=json.loads((ROOT/f'work/centered_zoom_countdown/{slug}.validation.json').read_text())
    h,m,s=record['first_highlight'].split(':')
    first=int(h)*3600+int(m)*60+float(s)
    cut=round(first-5,2)
    source=ROOT/'out/zoom'/f'{slug}_Karaoke.mp4'
    before=digest(source)
    assert before==record['sha256'],'Current export changed; review before trimming'
    dest=source.with_name(slug+'_Karaoke_5s_Intro.mp4')
    if dest.exists():raise FileExistsError(dest)
    staged=dest.with_name(dest.stem+'.rendering.mp4')
    command=[str(FFMPEG),'-nostdin','-y','-threads','2','-i',str(source),'-ss',str(cut),'-map','0:v:0','-map','0:a:0','-c:v','libx264','-threads','2','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(staged)]
    log=ROOT/f'work/centered_zoom_countdown/{slug}.trim.log'
    with log.open('w') as stream:subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-i',str(staged),'-f','null','-'],check=True)
    with av.open(str(staged)) as c:
        duration=c.duration/av.time_base
        assert (c.streams.video[0].width,c.streams.video[0].height)==(1920,1080)
        assert float(c.streams.video[0].average_rate)==25
    assert abs(duration-(record['duration']-cut))<.1
    expected=audio(source)[round(cut*16000):]
    comparison=check_audio(expected,audio(staged),delay=0)
    assert digest(source)==before,'Original changed'
    staged.replace(dest)
    save(ROOT/f'work/centered_zoom_countdown/{slug}.trim-validation.json',{'output':str(dest),'removed_opening_seconds':cut,'first_highlight_seconds':5,'duration':duration,'full_decode_exit':0,'audio_vs_trimmed_original':comparison,'original_unchanged':True,'sha256':digest(dest)})
    print(dest,flush=True)

if __name__=='__main__':main(int(sys.argv[1]))
