"""Start existing sung-lyric highlight at 10s; keep audio/video aligned."""
import concurrent.futures,json,shutil
import av
from project_runtime import ROOT
from intro_countdown import reference_logo_filter
from render_round_compact_batch import ff,info,audio_hash,digest
from restore_compact_intro_footer import pictures

REPORT=ROOT/'reports/shake-it-off-immediate-pair'
DEST=ROOT/'out/Taylor Swift - Shake It Off - Logo Versions'
BASE=ROOT/'out/Taylor Swift - Shake It Off - Corrected.mp4'
CUT=463/30  # First orange lyric frame, measured from the existing 30 fps export.
SHIFT=CUT-10

def prepare():
 REPORT.mkdir(parents=True,exist_ok=True);DEST.mkdir(parents=True,exist_ok=True)
 ff(['-y','-i',BASE,'-filter_complex',
     f'[0:a]asplit=2[a][b];[a]atrim=end=10,asetpts=PTS-STARTPTS[h];[b]atrim=start={CUT:.12f},asetpts=PTS-STARTPTS[t];[h][t]concat=n=2:v=0:a=1[audio]',
     '-map','[audio]','-c:a','aac','-b:a','320k',REPORT/'audio.m4a'],REPORT,'audio')

def render(brand):
 folder=REPORT/brand;folder.mkdir(exist_ok=True)
 out=DEST/f'Taylor Swift - Shake It Off - {brand} - Immediate Start.mp4'
 record=folder/'verified.json'
 if record.exists() and out.exists():
  r=json.loads(record.read_text());assert digest(out)==r['sha256'];return r
 if out.exists():raise FileExistsError(out)
 stage=folder/'rendering.mp4';duration=info(BASE)['duration']-SHIFT
 if brand=='Karaoke':
  with av.open(str(BASE)) as c:
   s=c.streams.video[0];scale=s.time_base.denominator
   boundary=next(float(p.pts*s.time_base) for p in c.demux(s) if p.is_keyframe and p.pts is not None and float(p.pts*s.time_base)>CUT)
  graph=f'[0:v]split=2[a][b];[a]trim=end_frame=300,setpts=N/(30*TB)[h];[b]trim=start_frame=463:end_frame={round(boundary*30)},setpts=N/(30*TB)[t];[h][t]concat=n=2:v=1:a=0,fps=30[v]'
  ff(['-y','-filter_complex_threads','1','-threads','1','-i',BASE,'-filter_complex',graph,'-map','[v]',
      '-an','-c:v','libx264','-threads','3','-preset','fast','-crf','18','-pix_fmt','yuv420p',
      '-r','30','-frames:v',round((boundary-SHIFT)*30),'-video_track_timescale',scale,folder/'opening.mp4'],folder,'opening')
  (folder/'concat.txt').write_text(f"file '{(folder/'opening.mp4').as_posix()}'\nfile '{BASE.as_posix()}'\ninpoint {boundary:.12f}\n",encoding='utf-8')
  ff(['-y','-f','concat','-safe','0','-i',folder/'concat.txt','-i',REPORT/'audio.m4a',
      '-map','0:v:0','-map','1:a:0','-c','copy','-t',duration,'-movflags','+faststart',stage],folder,'mux')
  assert pictures(BASE,boundary)==pictures(stage,boundary-SHIFT),'Later coded video changed'
 else:
  previous=ROOT/'reports/round-compact-batch/13'
  ass=(previous/'intro.ass').read_text(encoding='utf-8')
  ass+='\n'+'\n'.join(x for x in (previous/'footer/footer.ass').read_text().splitlines() if x.startswith('Dialogue:'))
  (folder/'intro.ass').write_text(ass,encoding='utf-8')
  ass_path=(folder/'intro.ass').relative_to(ROOT).as_posix()
  logo=ROOT/'assets/voxnova-transparent.png'
  graph=('[1:v]fps=30,scale=1920:1080,setsar=1,tpad=start_mode=clone:start_duration=10,setpts=PTS-STARTPTS,crop=180:180:1692:42[patch];'
      "[0:v][patch]overlay=1692:42:eof_action=pass:enable='gte(t,10)'[clean];"
      '[2:v]scale=1920:1080,setsar=1[still];'
      f'[3:v]{reference_logo_filter(10,1,"arc","#FFFFFF")}[logo];'
      f"[still][logo]overlay=710:80:shortest=1,subtitles='{ass_path}'[intro];"
      "[clean][intro]overlay=0:0:eof_action=pass:repeatlast=0:enable='lt(t,10)'[opening];"
      '[4:v]scale=180:180[corner];'
      "[opening][corner]overlay=1692:42:enable='gte(t,10)'[branded];"
      f'[branded]split=2[a][b];[a]trim=end=10,setpts=PTS-STARTPTS[h];[b]trim=start={CUT:.12f},setpts=PTS-STARTPTS[t];[h][t]concat=n=2:v=1:a=0,format=yuv420p[v]')
  ff(['-y','-filter_complex_threads','1','-threads','1','-i',BASE,'-threads','1','-i',ROOT/'inputs/Taylor Swift - Shake It Off (1080p).mp4',
      '-loop','1','-framerate','30','-t','10','-i',previous/'background.png',
      '-loop','1','-framerate','30','-t','10','-i',logo,'-loop','1','-framerate','30','-i',logo,
      '-i',REPORT/'audio.m4a','-filter_complex',graph,'-map','[v]','-map','5:a:0','-c:a','copy',
      '-c:v','libx264','-threads','4','-preset','fast','-crf','18','-maxrate','5100k','-bufsize','5100k',
      '-r','30','-t',duration,'-movflags','+faststart','-progress',folder/'progress.txt',stage],folder,'render')
 assert audio_hash(stage)==audio_hash(REPORT/'audio.m4a')
 v=info(stage);assert (v['width'],v['height'],v['fps'])==(1920,1080,30)
 assert abs(v['duration']-duration)<.08,(v,duration)
 assert stage.stat().st_size<180000000
 ff(['-xerror','-threads','2','-i',stage,'-f','null','-'],folder,'decode')
 stage.replace(out)
 r={'output':str(out),'sha256':digest(out),'bytes':out.stat().st_size,'cut_source_start':CUT,'removed_seconds':SHIFT,
    'expected_first_highlight':10,'audio_from_shared_trim':True,'strict_decode':True,**v}
 record.write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True);return r

if __name__=='__main__':
 prepare()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(render,['Karaoke','VoxNova']))
 (REPORT/'delivery.json').write_text(json.dumps(results,indent=2))
