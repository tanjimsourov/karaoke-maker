"""Resumable delivery copies: round intros, original audio, bounded file size."""
import argparse, concurrent.futures, hashlib, json, shutil, subprocess, time
from pathlib import Path
import av
from project_runtime import ROOT, FFMPEG
from intro_countdown import first_visible_frame, reference_logo_filter, events

REPORT = ROOT/'reports/round-compact-batch'
DEST = ROOT/'out/round-compact-2026-11-03'
RAWS = [
 'inputs/Andreas Odbjerg - Foler Mig Selv 100 (1080p).mp4', None, None,
 'inputs/Dua Lipa - Dance The Night (1080p).mp4',
 'inputs/Ed Sheeran - Bad Habits (1080p).mp4',
 'inputs/Geordie Kieffer - American - YouTube (1080p).mp4',
 'inputs/Harry Styles - As It Was (1080p).mp4',
 'inputs/Hilary Duff - CATastrophe (1080p).mp4',None,
 'inputs/Jung - Hun Kommer Tilbage (1080p).mp4',
 'inputs/Kygo and Ava Max - Before You Know It (1080p).mp4',
 'REI AMI - 2Loud (1080).mp4',
 'inputs/Taylor Swift - Babylon - YouTube (1080p).mp4',
 'inputs/Taylor Swift - Shake It Off (1080p).mp4',
 'inputs/Tobias Rahim and Andreas Odbjerg - STOR MAND (1080p).mp4',
 'inputs/Tobias Rahim - Mucki Bar (1080p).mp4']

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def audio_hash(path):
 h=hashlib.sha256()
 with av.open(str(path)) as c:
  for p in c.demux(audio=0):h.update(bytes(p))
 return h.hexdigest()

def info(path):
 with av.open(str(path)) as c:
  s=c.streams.video[0]
  return {'duration':c.duration/av.time_base,'width':s.width,'height':s.height,'fps':float(s.average_rate)}

def stamp(t):
 return f'{int(t//3600)}:{int(t//60)%60:02}:{t%60:05.2f}'

def ff(args, folder, name):
 with (folder/(name+'.log')).open('w') as log:
  subprocess.run([str(FFMPEG),'-nostdin','-v','error',*map(str,args)],stdout=log,stderr=log,check=True)

def prepare_animation():
 cache=REPORT/'logo.mkv'
 valid=False
 if cache.exists():
  try:
   with av.open(str(cache)) as c:
    valid=sum(1 for _ in c.decode(video=0))==300
  except (av.error.FFmpegError, OSError):pass
 if not valid:
  ff(['-y','-threads','1','-loop','1','-framerate','30','-i',ROOT/'assets/logo.png',
      '-filter_threads','1','-vf',reference_logo_filter(10,1,'arc','#FFFFFF'),
      '-t','10','-c:v','ffv1','-threads','1','-pix_fmt','bgra',cache],REPORT,'logo-cache')

def render(index, source):
 started=time.time();src=Path(source);folder=REPORT/f'{index:02}'
 folder.mkdir(parents=True,exist_ok=True);DEST.mkdir(parents=True,exist_ok=True)
 out=DEST/src.name;record=folder/'verified.json';sha=digest(src)
 if record.exists() and out.exists():
  old=json.loads(record.read_text())
  if old['source_sha256']==sha and old['sha256']==digest(out):return old
 if out.exists():raise FileExistsError(f'Unverified existing delivery: {out}')
 original=info(src);partial=folder/'rendering.mp4'
 if RAWS[index] is None:
  shutil.copyfile(src,partial)
 else:
  raw=ROOT/RAWS[index]
  if not raw.is_file():raise FileNotFoundError(raw)
  still=folder/'background.png'
  if index==12:
   # Preserve the existing text-cleaned intro background.
   shutil.copyfile(ROOT/'work/bowlnfun/Babylon-1039d7a138bd-text-clean/intro-background.png',still)
  else:first_visible_frame(raw,still)
  name=src.stem
  for suffix in [' - 2026-10-31 BATCH - BENCHMARK',' - FTP RAW - BENCHMARK',' - htdemucs - BENCHMARK',' - BENCHMARK']:
   name=name.removesuffix(suffix)
  artist,title=name.split(' - ',1)
  header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PageBase,Arial,90,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,5,80,80,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
  lines=events(10,30,1920,1080,stamp)
  footer='DANISH KARAOKE' if index in [0,9,14,15] else 'KARAOKE'
  for text,y,size in [(title,820,90),(artist,925,48),(footer,995,28)]:
   lines.append(f'Dialogue: 5,0:00:00.00,0:00:09.85,PageBase,,0,0,0,,{{\\pos(960,{y})\\fs{size}\\fad(80,160)}}{text}')
  (folder/'intro.ass').write_text(header+'\n'.join(lines),encoding='utf-8')
  ass=(folder/'intro.ass').relative_to(ROOT).as_posix()
  graph=(f'[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[bg];'
   '[2:v]format=rgba[logo];'
   f"[bg][logo]overlay=710:80:shortest=1,subtitles='{ass}'[intro];"
   "[0:v][intro]overlay=0:0:eof_action=pass:repeatlast=0:enable='lt(t,10)',fps=30,format=yuv420p[v]")
  # 170 MB budget includes a conservative allowance for copied audio/muxing.
  budget=min(170000000, max(src.stat().st_size,25000000))
  rate=max(500,int(budget*8/original['duration']/1000)-400)
  ff(['-y','-filter_complex_threads','1','-threads','1','-i',src,
      '-loop','1','-framerate','30','-t','10','-i',still,
      '-i',REPORT/'logo.mkv',
      '-filter_complex',graph,'-map','[v]','-map','0:a:0','-c:a','copy',
      '-c:v','libx264','-preset','fast','-crf','18','-maxrate',f'{rate}k','-bufsize',f'{rate}k',
      '-threads','3','-t',original['duration'],'-map_metadata','0','-movflags','+faststart',
      '-progress',folder/'progress.txt',partial],folder,'render')
 verified=info(partial)
 assert (verified['width'],verified['height'])==(1920,1080)
 assert abs(verified['duration']-original['duration'])<.10,(verified,original)
 assert verified['fps']>=30
 assert partial.stat().st_size<180000000,partial.stat().st_size
 assert audio_hash(src)==audio_hash(partial),'Encoded audio changed'
 ff(['-xerror','-threads','2','-i',partial,'-f','null','-'],folder,'decode')
 partial.replace(out)
 result={'source':str(src),'source_sha256':sha,'output':str(out),'sha256':digest(out),
  'bytes':out.stat().st_size,'original_bytes':src.stat().st_size,'seconds':time.time()-started,
  'audio_identical':True,'strict_decode':True,'footer_restored':True,
  'intro':'preserved' if RAWS[index] is None else 'round closing, 10 seconds',**verified}
 record.write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result),flush=True);return result

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=2);parser.add_argument('--only',type=int)
 args=parser.parse_args();sources=json.loads((REPORT/'selected.json').read_text())
 prepare_animation()
 jobs=list(enumerate(sources)) if args.only is None else [(args.only,sources[args.only])]
 with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(2,args.workers))) as pool:
  futures=[pool.submit(render,*job) for job in jobs];results=[];errors=[]
  for f in concurrent.futures.as_completed(futures):
   try:results.append(f.result())
   except Exception as e:errors.append(repr(e));print('ERROR '+repr(e),flush=True)
 (REPORT/'delivery.json').write_text(json.dumps({'outputs':results,'errors':errors},indent=2),encoding='utf-8')
 if errors:raise SystemExit(1)
