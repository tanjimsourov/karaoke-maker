"""Restore title/artist inside the existing five-second countdown."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import av
from zoom_local_pipeline import ROOT, FFMPEG, digest, save

JOBS=[('Zoom_Get_Ready_For_This','Get Ready For This','2 Unlimited'),('Zoom_Whats_Up',"What's Up",'4 Non Blondes')]
def run(index):
    slug,title,artist=JOBS[index]
    work=ROOT/'work/centered_zoom_countdown'
    target=ROOT/'out/zoom'/f'{slug}_Karaoke_5s_Intro.mp4'
    backup=work/'previous'/target.name
    if not backup.exists():shutil.copy2(target,backup)
    source=backup
    ass=work/(slug+'.short-title.ass')
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Intro,Arial,90,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,5,60,60,0,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
    events=[]
    for text,y,size in [(title,820,90),(artist,925,48),('KARAOKE',995,28)]:
        events.append(f'Dialogue: 5,0:00:00.00,0:00:04.45,Intro,,0,0,0,,{{\\pos(960,{y})\\fs{size}\\fad(100,200)}}{text}')
    ass.write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')
    ass_filter=str(ass).replace('\\','/').replace(':','\\:')
    staged=work/(slug+'.titles.rendering.mp4')
    command=[str(FFMPEG),'-nostdin','-y','-filter_threads','1','-threads','1','-i',str(source),'-vf',f"subtitles='{ass_filter}'",'-c:v','libx264','-threads','1','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(staged)]
    with (work/(slug+'.short-title.log')).open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-threads','2','-i',str(staged),'-f','null','-'],check=True)
    with av.open(str(source)) as a,av.open(str(staged)) as b:
        duration=b.duration/av.time_base
        assert abs(duration-a.duration/av.time_base)<.05
        assert (b.streams.video[0].width,b.streams.video[0].height)==(1920,1080)
        def packets(container):
            import hashlib
            sha=hashlib.sha256()
            for packet in container.demux(audio=0):sha.update(bytes(packet))
            return sha.hexdigest()
        assert packets(a)==packets(b),'Audio packets changed'
    shutil.copy2(staged,target)
    save(work/(slug+'.short-title-validation.json'),{'output':str(target),'sha256':digest(target),'duration':duration,'audio_packets_identical':True,'title':title,'artist':artist,'overlay_ends':4.45,'first_highlight_seconds':5,'full_decode_exit':0,'backup':str(backup)})
    print(target,flush=True)

if __name__=='__main__':run(int(sys.argv[1]))
