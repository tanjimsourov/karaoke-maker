"""Cover the source's two initial black frames without changing audio/timing."""
import json,concurrent.futures
import av
from make_rei_ami_logo_pair import REPORT,DEST,ROOT
from render_round_compact_batch import ff,info,audio_hash,digest
from restore_compact_intro_footer import pictures

def fix(brand):
 src=DEST/f'REI AMI - 2Loud - {brand}.mp4'
 folder=REPORT/('transition-'+brand);folder.mkdir(exist_ok=True)
 record=folder/'verified.json'
 if record.exists():
  r=json.loads(record.read_text());assert r['sha256']==digest(src);return r
 with av.open(str(src)) as c:
  s=c.streams.video[0];scale=s.time_base.denominator
  boundary=next(float(p.pts*s.time_base) for p in c.demux(s) if p.is_keyframe and p.pts is not None and float(p.pts*s.time_base)>10.07)
 logo=ROOT/('assets/logo.png' if brand=='Karaoke' else 'assets/voxnova-transparent.png')
 graph=('[1:v]scale=1920:1080[still];[2:v]scale=180:180[logo];'
        '[still][logo]overlay=1692:42[patch];'
        "[0:v][patch]overlay=0:0:enable='gte(t,10)*lt(t,10.0666)'[v]")
 ff(['-y','-filter_complex_threads','1','-threads','1','-i',src,
     '-loop','1','-framerate','30','-i',ROOT/'reports/round-compact-batch/11/background.png',
     '-loop','1','-framerate','30','-i',logo,'-filter_complex',graph,'-map','[v]',
     '-an','-t',boundary,'-c:v','libx264','-preset','fast','-crf','18','-threads','2',
     '-pix_fmt','yuv420p','-video_track_timescale',scale,folder/'intro.mp4'],folder,'intro')
 (folder/'concat.txt').write_text(f"file '{(folder/'intro.mp4').as_posix()}'\nfile '{src.as_posix()}'\ninpoint {boundary:.9f}\n",encoding='utf-8')
 out=folder/'patched.mp4'
 ff(['-y','-f','concat','-safe','0','-i',folder/'concat.txt','-i',src,'-map','0:v:0','-map','1:a:0',
     '-c','copy','-map_metadata','1','-movflags','+faststart',out],folder,'mux')
 assert audio_hash(out)==audio_hash(src)
 assert pictures(src,boundary)==pictures(out,boundary)
 assert abs(info(src)['duration']-info(out)['duration'])<.05
 assert out.stat().st_size<180000000
 ff(['-xerror','-threads','2','-i',out,'-f','null','-'],folder,'decode')
 out.replace(src)
 result={'output':str(src),'sha256':digest(src),'bytes':src.stat().st_size,
         'corrected_video_frames':[300,301],'audio_identical':True,'strict_decode':True,
         'song_frames_identical_after':boundary}
 record.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True);return result

if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(fix,['Karaoke','VoxNova']))
 p=REPORT/'verification.json';r=json.loads(p.read_text())
 for brand,x in zip(['karaoke','voxnova'],results):r[brand+'_sha256']=x['sha256'];r[brand+'_bytes']=x['bytes']
 r['transition_black_frames_removed']=True;p.write_text(json.dumps(r,indent=2))
