"""Restore intro footer, re-encoding only through the first song keyframe."""
import concurrent.futures,json,hashlib,argparse
import av
from render_round_compact_batch import REPORT,ROOT,ff,info,audio_hash,digest

def pictures(path,start):
 h=hashlib.sha256();count=0
 with av.open(str(path)) as c:
  s=c.streams.video[0]
  for p in c.demux(s):
   if p.pts is None or float(p.pts*s.time_base)<start-.0001:continue
   data=bytes(p);offset=0
   while offset<len(data):
    n=int.from_bytes(data[offset:offset+4],'big');nal=data[offset+4:offset+4+n]
    assert n and len(nal)==n
    if 1<=nal[0]&31<=5:h.update(nal)
    offset+=4+n
   count+=1
 return h.hexdigest(),count

def restore(record):
 r=json.loads(record.read_text());src=ROOT/r['output'];index=int(record.parent.name)
 if r['intro']=='preserved' or r.get('footer_restored'):return
 folder=record.parent/'footer';folder.mkdir(exist_ok=True)
 with av.open(str(src)) as c:
  s=c.streams.video[0];scale=s.time_base.denominator
  boundary=next(float(p.pts*s.time_base) for p in c.demux(s) if p.is_keyframe and p.pts is not None and float(p.pts*s.time_base)>=10-.0001)
 label='DANISH KARAOKE' if index in [0,9,14,15] else 'KARAOKE'
 original_ass=(record.parent/'intro.ass').read_text(encoding='utf-8')
 header=original_ass.split('Dialogue:')[0]
 (folder/'footer.ass').write_text(header+f'Dialogue: 5,0:00:00.00,0:00:09.85,PageBase,,0,0,0,,{{\\pos(960,995)\\fs28\\fad(80,160)}}{label}\n',encoding='utf-8')
 ass=(folder/'footer.ass').relative_to(ROOT).as_posix()
 ff(['-y','-threads','1','-i',src,'-t',boundary,'-vf',f"subtitles='{ass}'",'-an',
     '-c:v','libx264','-preset','fast','-crf','18','-threads','2','-pix_fmt','yuv420p',
     '-video_track_timescale',scale,folder/'intro.mp4'],folder,'intro')
 concat=f"file '{(folder/'intro.mp4').as_posix()}'\nfile '{src.as_posix()}'\ninpoint {boundary:.9f}\n"
 (folder/'concat.txt').write_text(concat,encoding='utf-8')
 output=folder/'patched.mp4'
 ff(['-y','-f','concat','-safe','0','-i',folder/'concat.txt','-i',src,
     '-map','0:v:0','-map','1:a:0','-c','copy','-map_metadata','1','-movflags','+faststart',output],folder,'mux')
 assert pictures(src,boundary)==pictures(output,boundary),'Song picture changed'
 assert audio_hash(src)==audio_hash(output),'Audio changed'
 assert abs(info(output)['duration']-r['duration'])<.05
 assert output.stat().st_size<180000000
 ff(['-xerror','-threads','1','-i',output,'-f','null','-'],folder,'decode')
 output.replace(src)
 r.update(sha256=digest(src),bytes=src.stat().st_size,footer_restored=True,footer=label,song_frames_preserved_after=boundary)
 record.write_text(json.dumps(r,indent=2),encoding='utf-8')
 print('Footer verified: '+src.name,flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=2);args=parser.parse_args()
 records=sorted(REPORT.glob('*/verified.json'))
 with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(2,args.workers))) as pool:list(pool.map(restore,records))
 (REPORT/'delivery.json').write_text(json.dumps({'outputs':[json.loads(p.read_text()) for p in records],'errors':[]},indent=2),encoding='utf-8')
