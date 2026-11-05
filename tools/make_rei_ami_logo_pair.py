"""Two compact REI AMI logo versions; preserve source audio and lyric timeline."""
import json,shutil,time
from pathlib import Path
from project_runtime import ROOT
from intro_countdown import reference_logo_filter
from render_round_compact_batch import ff,info,audio_hash,digest

REPORT=ROOT/'reports/rei-ami-logo-pair'
DEST=ROOT/'out/REI AMI - 2Loud - Logo Versions'

def main():
 REPORT.mkdir(parents=True,exist_ok=True);DEST.mkdir(parents=True,exist_ok=True)
 base=ROOT/'out/REI AMI - 2Loud - FTP RAW - BENCHMARK.mp4'
 raw=ROOT/'REI AMI - 2Loud (1080).mp4'
 previous=ROOT/'reports/round-compact-batch/11'
 prior=json.loads((previous/'verified.json').read_text())
 assert digest(base)==prior['source_sha256']
 compact=Path(prior['output']);assert digest(compact)==prior['sha256']
 karaoke=DEST/'REI AMI - 2Loud - Karaoke.mp4'
 output=DEST/'REI AMI - 2Loud - VoxNova.mp4'
 record=REPORT/'verification.json'
 if record.exists() and output.exists() and karaoke.exists():
  saved=json.loads(record.read_text())
  assert digest(output)==saved['voxnova_sha256'] and digest(karaoke)==saved['karaoke_sha256']
  print(saved);return
 if karaoke.exists():assert digest(karaoke)==digest(compact)
 else:shutil.copyfile(compact,karaoke)
 if record.exists() and output.exists():
  saved=json.loads(record.read_text());assert digest(output)==saved['voxnova_sha256'];print(saved);return
 if output.exists():raise FileExistsError(output)
 logo=ROOT/'assets/voxnova-transparent.png'
 still=previous/'background.png'
 ass_text=(previous/'intro.ass').read_text(encoding='utf-8')
 if '\\fs28' not in ass_text:
  ass_text+='\n'+'\n'.join(x for x in (previous/'footer/footer.ass').read_text(encoding='utf-8').splitlines() if x.startswith('Dialogue:'))
 (REPORT/'intro.ass').write_text(ass_text,encoding='utf-8')
 ass=(REPORT/'intro.ass').relative_to(ROOT).as_posix()
 duration=info(base)['duration']
 graph=(
  '[1:v]fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,'
  'tpad=start_mode=clone:start_duration=10,setpts=PTS-STARTPTS,crop=180:180:1692:42[patch];'
  "[0:v][patch]overlay=1692:42:enable='gte(t,10)':eof_action=pass[clean];"
  '[2:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[still];'
  f'[3:v]{reference_logo_filter(10,1,"arc","#FFFFFF")}[intro_logo];'
  f"[still][intro_logo]overlay=710:80:shortest=1,subtitles='{ass}'[intro];"
  "[clean][intro]overlay=0:0:eof_action=pass:repeatlast=0:enable='lt(t,10)'[opening];"
  '[4:v]scale=180:180[corner];'
  "[opening][corner]overlay=1692:42:enable='gte(t,10)',format=yuv420p[v]")
 stage=REPORT/'voxnova-rendering.mp4';start=time.monotonic()
 ff(['-y','-filter_complex_threads','1','-threads','1','-i',base,'-threads','1','-i',raw,
     '-loop','1','-framerate','30','-t','10','-i',still,
     '-loop','1','-framerate','30','-t','10','-i',logo,
     '-loop','1','-framerate','30','-i',logo,
     '-filter_complex',graph,'-map','[v]','-map','0:a:0','-c:a','copy',
     '-c:v','libx264','-threads','4','-preset','fast','-crf','18','-maxrate','7800k','-bufsize','7800k',
     '-r','30','-t',duration,'-map_metadata','0','-movflags','+faststart',
     '-progress',REPORT/'progress.txt',stage],REPORT,'render')
 v=info(stage)
 assert (v['width'],v['height'],v['fps'])==(1920,1080,30)
 assert abs(v['duration']-duration)<.05
 assert stage.stat().st_size<180000000
 assert audio_hash(base)==audio_hash(stage)==audio_hash(karaoke)
 ff(['-xerror','-threads','2','-i',stage,'-f','null','-'],REPORT,'decode')
 stage.replace(output)
 result={'source':str(base),'source_sha256':digest(base),'karaoke':str(karaoke),'voxnova':str(output),
         'karaoke_sha256':digest(karaoke),'voxnova_sha256':digest(output),
         'karaoke_bytes':karaoke.stat().st_size,'voxnova_bytes':output.stat().st_size,
         'audio_packets_identical':True,'strict_decode':True,'countdown_seconds':10,
         'circle':'round clockwise-closing white arc, no shadow track','render_seconds':time.monotonic()-start,**v}
 record.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)

if __name__=='__main__':main()
