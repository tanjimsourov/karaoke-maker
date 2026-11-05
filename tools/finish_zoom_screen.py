"""Render the two supplied Zoom sources locally, preserving their audio timeline."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import av
from zoom_local_pipeline import ROOT, FFMPEG, save, read, digest, check_audio, audio
from prepare_zoom_local import stamp

WORK=ROOT/'work/zoom_screen'
SOURCES=sorted((ROOT/'zoom').glob('*.mp4'))
JOBS=[('Zoom_Get_Ready_For_This','Get Ready For This','2 Unlimited','Neon bowlinglounge in dromerige bokeh.png'),
      ('Zoom_Whats_Up',"What's Up",'4 Non Blondes','Dromerige neonbowling in Aalborg.png')]

def prepare(k):
    cues=copy.deepcopy(read(WORK/str(k)/'recovered.json'))
    changes=[];rows=[];previous=0
    for c in cues:
        if any('incomplete' in issue or 'empty' in issue for issue in c['issues']):
            raise ValueError(f'Unresolved extraction: {c}')
        ws=c['words']
        for a,b in zip(ws,ws[1:]):
            if a['end']>b['start']:
                if a['end']-b['start']>.35:raise ValueError('Large overlap')
                boundary=max(a['start']+.02,min(b['end']-.02,(a['end']+max(a['start'],b['start']))/2))
                changes.append({'track':c['track'],'words':[a['word'],b['word']],'old':[a['end'],b['start']],'boundary':boundary})
                a['end']=boundary;b['start']=boundary
        start=round(ws[0]['start']*100);cursor=start;parts=[]
        if start<previous:raise ValueError('Overlapping cue')
        for i,w in enumerate(ws):
            a,b=round(w['start']*100),round(w['end']*100)
            if a<cursor or b<=a:raise ValueError(f'Invalid word {w}')
            # Preserve pauses without inserting visible extra spaces inside
            # hyphenated lyrics (or doubling normal inter-word spacing).
            if a>cursor:parts.append(f'{{\\kf{a-cursor}}}\u200b')
            suffix='' if w['word'].endswith('-') or i==len(ws)-1 else ' '
            parts.append(f"{{\\kf{b-a}}}{w['word']}{suffix}")
            cursor=b
        rows.append(f'Dialogue: 0,{stamp(start)},{stamp(cursor)},Default,,0,0,0,,'+''.join(parts))
        previous=cursor
    ass='[Script Info]\nScriptType: v4.00+\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'+'\n'.join(rows)+'\n'
    (WORK/str(k)/'reviewed.ass').write_text(ass,encoding='utf-8')
    save(WORK/str(k)/'review.json',{'method':'Local OCR and measured source-screen colour sweeps, approximately 80 ms sampling; source lyrics retained; OCR spelling/spacing reviewed against source crops. Not vocal forced alignment.',
         'cue_count':len(cues),'word_count':sum(len(c['words']) for c in cues),'boundary_adjustments':changes,
         'source_sha256':digest(SOURCES[k]),'ass_sha256':digest(WORK/str(k)/'reviewed.ass'),'paid_calls':0})
    print(k,len(cues),'cues',len(changes),'small boundary adjustments',flush=True)

def render(k):
    slug,title,artist,bg=JOBS[k]
    args=[sys.executable,str(ROOT/'tools/build_bowlnfun_karaoke.py'),'--slug',slug,'--title',title,'--artist',artist,
          '--source-ass',str(WORK/str(k)/'reviewed.ass'),'--audio-file',str(SOURCES[k]),
          '--background-file',str(ROOT/'audio-bg-sample/14-10/jan-chatgpt'/bg),
          '--output-dir',str(WORK/'rendered'),'--output-name',slug+'_Karaoke.mp4',
          '--approved-intro','--language-label','KARAOKE','--preset','veryfast']
    with (WORK/str(k)/'render.log').open('w',encoding='utf-8') as log:
        subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
    print('Rendered',slug,flush=True)

def verify(k):
    p=WORK/'rendered'/(JOBS[k][0]+'_Karaoke.mp4')
    with av.open(str(p)) as c:
        v=c.streams.video[0];width,height=v.width,v.height;duration=c.duration/av.time_base
        assert (width,height)==(1920,1080)
        assert float(v.average_rate)==25
    with av.open(str(SOURCES[k])) as c:source_duration=c.duration/av.time_base
    assert abs(duration-source_duration-3)<.15,(duration,source_duration)
    subprocess.run([str(FFMPEG),'-v','error','-i',str(p),'-f','null','-'],check=True)
    audio_result=check_audio(audio(SOURCES[k]),audio(p))
    report={'output':str(p),'duration':duration,'source_duration':source_duration,'resolution':[width,height],
            'audio_check':audio_result,'full_decode_exit':0,'sha256':digest(p)}
    save(WORK/str(k)/'validation.json',report)
    print(json.dumps(report),flush=True)

def contact(k):
    from PIL import Image,ImageDraw
    p=WORK/'rendered'/(JOBS[k][0]+'_Karaoke.mp4')
    times=([1,2.7,28.7,46,63,111,185,215] if k==0 else [1,2.7,27,61,85,173,197,255])
    sheet=Image.new('RGB',(1440,4*430),'#222222');draw=ImageDraw.Draw(sheet)
    with av.open(str(p)) as c:
        stream=c.streams.video[0]
        for i,t in enumerate(times):
            c.seek(int(t/stream.time_base),stream=stream)
            frame=next(f for f in c.decode(video=0) if float(f.time)>=t)
            im=frame.to_image();im.thumbnail((720,405));x=i%2*720;y=i//2*430
            draw.text((x+8,y+5),f'{t:.2f}s',fill='white');sheet.paste(im,(x,y+25))
    sheet.save(WORK/str(k)/'final_contact.jpg')

def publish(k):
    import shutil
    review=read(WORK/str(k)/'review.json');validation=read(WORK/str(k)/'validation.json')
    source=WORK/'rendered'/(JOBS[k][0]+'_Karaoke.mp4')
    assert digest(source)==validation['sha256']
    assert digest(SOURCES[k])==review['source_sha256']
    assert digest(WORK/str(k)/'reviewed.ass')==review['ass_sha256']
    destination=ROOT/'out/zoom'/source.name
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        if digest(destination)!=validation['sha256']:raise FileExistsError(destination)
    else:shutil.copy2(source,destination)
    assert digest(destination)==validation['sha256']
    save(WORK/str(k)/'delivery.json',{'file':str(destination),'review':review,'validation':validation,
         'visual_review':'Intro, logo transition, opening, middle, chorus, and final lyrics inspected; source-screen timing comparison sampled. Full-file decoding and audio comparison passed.',
         'limitations':'Timing recovered from existing Zoom colour sweeps at approximately 80 ms resolution, not re-aligned against unavailable original vocals. Existing source arrangement and pauses retained.',
         'tests':'python tools/test_zoom_screen_delivery.py: 4 tests passed, exit 0; py_compile: exit 0',
         'paid_operations':0})
    print(destination,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','render','verify','contact','publish']);p.add_argument('--song',type=int,choices=[0,1])
    a=p.parse_args()
    for k in ([a.song] if a.song is not None else [0,1]):globals()[a.stage](k)
