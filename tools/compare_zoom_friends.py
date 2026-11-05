"""Local-only screen recovery and rendering for the supplied Zoom Friends video."""
from pathlib import Path
import argparse, json, copy, subprocess, sys
import av
import recover_zoom_screen as screen
from zoom_local_pipeline import ROOT, save

WORK=ROOT/'work/zoom_friends_comparison'
SOURCE=ROOT/'zoom/Wet Wet Wet - With A Little Help From My Friends - Karaoke Version from Zoom Karaoke.mp4'
# Read against all source-screen contact sheets, not inferred from the API text.
TEXT={3:'What would you think',4:'if I sang out of tune',5:'Would you stand up',6:'and walk out on me',7:'Lend me your ears',8:"and I'll sing you a song",9:"And I'll try not to",10:'sing outta key',20:'My friends',21:'What do you do',22:'when our love is away',24:'Does it worry you',25:'to be alone',26:'How does it feel',27:'by the end of the day',28:'Are you sad because',29:"you're on your own",38:'Do you need anybody',40:'I need somebody to love',41:'Could it be anybody',42:'I need somebody to love',43:'to love, to love',44:'Would you believe in',45:'this love at first sight',46:"Yes, I'm certain that",47:'it happens all the time',48:'What do you see',49:'when you turn',50:'Out the lights',51:"I can't tell you",52:"but I know that it's mine",62:'Do you need anybody',63:'Could it be anybody',64:'I need somebody to love',65:'I need somebody to love',73:'With a little help',78:'My friends',79:'My friends',80:'My friends',81:'My friends...'}
for ids,text in [([11,18,30,36,53,58,66,69,75],"Ooh, I'll get by"),([14,34,56,72],"Ooh, I'll get high"),([12,15,17,31,33,37,54,57,60,67,70,76],'with a little help'),([13,16,19,32,35,39,55,59,61,68,71,74,77],'from my friends')]:
    TEXT.update(dict.fromkeys(ids,text))
TEXT[85]='with a little help'
TEXT[86]='from my friends......'

def local(stage):
    screen.WORK=WORK/'local'
    screen.SOURCES=[SOURCE]*6
    screen.CORRECTIONS[5]=TEXT
    {'scan':screen.scan,'tracks':screen.tracks,'measure':screen.measurements,'recover':screen.recover,'contact':screen.contact}[stage](5)
    if stage=='tracks':
        path=screen.WORK/'5/tracks.json';groups=json.loads(path.read_text())
        # Consecutive refrains reuse the same screen slot with changed glyphs.
        # Separate the masks at observed screen changes, preserving both sweeps.
        for ident,boundary,early_new in [(73,140,True),(74,142,False)]:
            old=groups[ident];extra=copy.deepcopy(old);extra['id']=len(groups)
            early=[s for s in old['samples'] if s['time']<boundary]
            late=[s for s in old['samples'] if s['time']>=boundary]
            for item,samples in [(extra,early if early_new else late),(old,late if early_new else early)]:
                item['samples']=samples;item['first']=samples[0]['time'];item['last']=samples[-1]['time']
                item['best']=samples[len(samples)//2]
            groups.append(extra)
        save(path,groups)

def render_local():
    import finish_zoom_screen as finish
    finish.WORK=WORK/'local';finish.SOURCES=[SOURCE]*6
    finish.prepare(5)
    dest=ROOT/'out/zoom/comparison/Friends_Local_REVIEW.mp4'
    if dest.exists():raise FileExistsError(dest)
    command=[sys.executable,str(ROOT/'tools/build_bowlnfun_karaoke.py'),'--slug','Compare_Friends_Local','--title','With A Little Help From My Friends','--artist','Wet Wet Wet','--source-ass',str(WORK/'local/5/reviewed.ass'),'--audio-file',str(SOURCE),'--background-file',str(ROOT/'audio-bg-sample/14-10/jan-chatgpt/Neon bowlinglounge in dromerige bokeh.png'),'--output-dir',str(dest.parent),'--output-name',dest.name,'--approved-intro','--language-label','KARAOKE','--preset','veryfast']
    command.append('--preserve-source-timeline')
    with (WORK/'local-render.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)

def verify():
    from zoom_local_pipeline import audio,check_audio,digest,FFMPEG
    reports=[]
    for kind in ['Local']:
        path=ROOT/f'out/zoom/comparison/Friends_{kind}_REVIEW.mp4'
        with av.open(str(path)) as c:
            resolution=[c.streams.video[0].width,c.streams.video[0].height];seconds=c.duration/av.time_base
            assert resolution==[1920,1080] and float(c.streams.video[0].average_rate)==25
        delay=0
        with av.open(str(SOURCE)) as c:assert abs(seconds-c.duration/av.time_base-delay)<.15
        subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-f','null','-'],check=True)
        reports.append({'file':str(path),'sha256':digest(path),'resolution':resolution,'duration':seconds,'audio_check':check_audio(audio(SOURCE),audio(path),delay=delay*16000),'full_decode_exit':0})
    save(WORK/'validation.json',reports);print(json.dumps(reports),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['scan','tracks','measure','recover','contact','render','verify']);a=p.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    if a.stage=='render':render_local()
    elif a.stage=='verify':verify()
    else:local(a.stage)
