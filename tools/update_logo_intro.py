"""Intro-only refresh. Copy original AAC and video packets after 10s intact."""
from pathlib import Path
import hashlib,json,shutil,subprocess
import av

ROOT=Path(__file__).resolve().parents[1]
FF=ROOT/'tools/ffmpeg/ffmpeg.exe'
WORK=ROOT/'work/logo_intro_14_10'
WORK.mkdir(parents=True,exist_ok=True)
(WORK/'originals').mkdir(exist_ok=True)
LOGO=ROOT/'work/webmail/Logo-Karaoke-2025-WHITE.png'
JOBS=[
 ('AEr_lig_Freestyle','AEr_lig_Freestyle_Karaoke_BG2.mp4','org/Bowlnfun_Image_2.png'),
 ('Bliv_her_lidt_endnu','Bliv_her_lidt_endnu_Karaoke.mp4','14-10/Image-1.png'),
 ('Blodigt','Blodigt_Karaoke.mp4','14-10/Image-2.png'),
 ('Barry_Cant_Swim_Kimbara','Barry_Cant_Swim_Kimbara_Karaoke.mp4','14-10/jan-chatgpt/Dromerige neonbowling in Aalborg.png'),
 ('BUNT_TRIPPIN','BUNT_TRIPPIN_Karaoke.mp4','14-10/jan-chatgpt/Neon bowlinglounge in dromerige bokeh.png'),
]
SHIFT=0.4
def payload(path,kind,after=0):
 h=hashlib.sha256()
 with av.open(str(path)) as c:
  stream=(c.streams.audio if kind=='audio' else c.streams.video)[0]
  for p in c.demux(stream):
   if p.pts is not None and (kind=='audio' or float(p.pts*p.time_base)>=after-0.0001):
    data=bytes(p)
    if kind=='video':
     # Concat adds SPS/PPS headers to keyframes; compare encoded picture
     # data rather than those equivalent container-dependent headers.
     offset=0
     while offset+4<=len(data):
      n=int.from_bytes(data[offset:offset+4],'big'); nal=data[offset+4:offset+4+n]
      if nal and nal[0]&31 not in (7,8):h.update(nal)
      offset+=4+n
    else:h.update(data)
 return h.hexdigest()
def run(cmd,log):
 with log.open('a',encoding='utf-8') as fh:subprocess.run([str(FF),'-y','-v','warning',*cmd],stdout=fh,stderr=fh,check=True)
results=[]
for slug,name,pic in JOBS:
 final=ROOT/'out'/name
 original=WORK/'originals'/name
 if not original.exists():shutil.copy2(final,original)
 with av.open(str(original)) as c:
  duration=c.duration/av.time_base
 ass_source=ROOT/'work/bowlnfun'/slug/'karaoke.ass'
 text=ass_source.read_text(encoding='utf-8-sig')
 def stamp(value):
  h,m,s=value.split(':'); return int(h)*3600+int(m)*60+float(s)
 def timecode(value):
  cs=round(value*100); h,cs=divmod(cs,360000); m,cs=divmod(cs,6000); s,cs=divmod(cs,100)
  return f'{h}:{m:02d}:{s:02d}.{cs:02d}'
 lines=[]
 for line in text.splitlines():
  if line.startswith('Dialogue: 2'):
   line=line.replace('pos(960,390)','pos(960,640)').replace('pos(960,510)','pos(960,760)').replace('pos(960,580)','pos(960,830)')
   fields=line.split(',',9); fields[2]=timecode(stamp(fields[2])+SHIFT); line=','.join(fields)
  elif line.startswith('Dialogue:'):
   fields=line.split(',',9); fields[1]=timecode(stamp(fields[1])+SHIFT); fields[2]=timecode(stamp(fields[2])+SHIFT); line=','.join(fields)
  lines.append(line)
 ass=WORK/f'{slug}_intro.ass'
 ass.write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
 ass_filter=str(ass).replace('\\','/').replace(':','\\:')
 prefix=WORK/f'{slug}_prefix.mp4'
 log=WORK/f'{slug}.log'
 q='min(1,max(0,(t-2.4)/0.5))'
 filters=(
  '[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[bg];'
  f"[1:v]format=rgba,scale=w='420-240*{q}':h=-1:eval=frame[logo];"
  f"[bg][logo]overlay=x='960+822*{q}-w/2':y='330-198*{q}-h/2',subtitles='{ass_filter}'[v]"
 )
 print(f'{slug}: updating intro',flush=True)
 run(['-loop','1','-framerate','25','-i',str(ROOT/'audio-bg-sample'/pic),'-loop','1','-framerate','25','-i',str(LOGO),
  '-filter_complex',filters,'-map','[v]','-an','-t',str(10+SHIFT),'-r','25','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',str(prefix)],log)
 concat=WORK/f'{slug}_concat.txt'
 concat.write_text("file '"+prefix.as_posix()+"'\nfile '"+original.as_posix()+"'\ninpoint 10\n",encoding='utf-8')
 staged=WORK/f'{slug}_complete.mp4'
 run(['-f','concat','-safe','0','-i',str(concat),'-itsoffset',str(SHIFT),'-i',str(original),'-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(staged)],log)
 assert payload(original,'audio')==payload(staged,'audio'),'Audio changed'
 assert payload(original,'video',10)==payload(staged,'video',10+SHIFT),'Video after prefix changed'
 with av.open(str(staged)) as c:
  v=c.streams.video[0]
  assert (v.width,v.height)==(1920,1080)
  assert abs(c.duration/av.time_base-duration-SHIFT)<0.06
 run(['-i',str(staged),'-f','null','-'],log)
 shutil.copy2(staged,final)
 results.append({'file':name,'audio_identical':True,'encoded_pictures_after_prefix_identical':True,'intro_seconds':3.0,'audio_and_caption_shift_seconds':SHIFT,'decode_passed':True,'dimensions':[1920,1080]})
 (WORK/'validation.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 print(f'{slug}: READY; audio unchanged; video after 10s unchanged',flush=True)
print('ALL_FIVE_READY',flush=True)
