"""Render the two requested Zoom deliveries with a centered intro countdown."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import av
from zoom_local_pipeline import ROOT, audio, check_audio, digest, save

ORIGINAL=ROOT.parent/'karaoke'
WORK=ROOT/'work/centered_zoom_countdown'
JOBS=[('Zoom_Get_Ready_For_This','Get Ready For This','2 Unlimited','2 Unlimited - Get Ready For This - Karaoke Version from Zoom Karaoke.mp4','Neon bowlinglounge in dromerige bokeh.png'),('Zoom_Whats_Up',"What's Up",'4 Non Blondes',"4 Non Blondes - What's Up (Karaoke Version) with Lyrics On Screen.mp4",'Dromerige neonbowling in Aalborg.png')]

def run(index):
    WORK.mkdir(parents=True,exist_ok=True)
    slug,title,artist,filename,bg=JOBS[index]
    source=ORIGINAL/'zoom'/filename
    timing=ORIGINAL/f'work/zoom_screen/{index}/reviewed.ass'
    output=ROOT/'out/zoom'/f'{slug}_Karaoke.mp4'
    backup=WORK/'previous'/output.name
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(output,backup)
    command=[sys.executable,str(ROOT/'tools/build_bowlnfun_karaoke.py'),'--slug',slug+'_CenteredCountdown','--title',title,'--artist',artist,'--source-ass',str(timing),'--audio-file',str(source),'--background-file',str(ROOT/'audio-bg-sample/14-10/jan-chatgpt'/bg),'--output-dir',str(WORK),'--output-name',output.name,'--approved-intro','--center-intro-countdown','--language-label','KARAOKE','--preset','veryfast']
    if '--verify-only' not in sys.argv:
        with (WORK/(slug+'.log')).open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    new=WORK/output.name
    with av.open(str(new)) as c:
        duration=c.duration/av.time_base
        assert (c.streams.video[0].width,c.streams.video[0].height)==(1920,1080)
        assert float(c.streams.video[0].average_rate)==25
    with av.open(str(backup)) as c:assert abs(duration-c.duration/av.time_base)<.08
    audio_check=check_audio(audio(backup),audio(new),delay=0)
    # The first word must start at exactly the same output timestamp.
    def first_sweep(path):
        lines=path.read_text(encoding='utf-8-sig').splitlines()
        return next(line.split(',',9)[1] for line in lines if line.startswith('Dialogue:') and ',PageSweep,' in line)
    ass=ROOT/'work/bowlnfun'/(slug+'_CenteredCountdown')/'karaoke.ass'
    assert first_sweep(ass)==first_sweep(ROOT/'work/bowlnfun'/slug/'karaoke.ass')
    def seconds(value):
        h,m,s=value.split(':');return int(h)*3600+int(m)*60+float(s)
    first=seconds(first_sweep(ass))
    events=[line.split(',',9) for line in ass.read_text(encoding='utf-8-sig').splitlines() if line.startswith('Dialogue:')]
    lyric_events=[e for e in events if e[3] in ('PageBase','PageSweep') and '\\fs66' in e[9]]
    assert min(seconds(e[1]) for e in lyric_events)>=first,'Logo move overlaps first lyric page'
    numbers=[e for e in events if '\\fs110' in e[9]]
    assert numbers and numbers[-1][9].endswith('}0')
    assert seconds(numbers[-1][2])==first,'Countdown must finish at first highlight'
    save(WORK/(slug+'.validation.json'),{'staged':str(new),'sha256':digest(new),'duration':duration,'audio_vs_previous':audio_check,'first_highlight':first_sweep(ass),'backup':str(backup),'render_and_full_decode_exit':0})
    print('VALIDATED',new,flush=True)

if __name__=='__main__':run(int(sys.argv[1]))
