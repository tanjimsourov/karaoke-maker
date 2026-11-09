"""Fill portrait-photo side bars while preserving the complete central picture."""
import json
from render_round_compact_batch import ROOT,ff,info,audio_hash,digest

source=ROOT/'out/ftp-image-backgrounds/Updated Logo/Saybia - The Second You Sleep - Centered Smaller Logo - CORRECTED DRAFT.mp4'
folder=ROOT/'tmp/saybia-blurred-sides';folder.mkdir(parents=True,exist_ok=True)
output=folder/'Saybia - Full HD Blurred Sides.mp4'
graph=(
 '[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,'
 'gblur=sigma=35,setsar=1,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[back];'
 '[0:v]crop=1196:1080:362:0[center];'
 '[back][center]overlay=362:0[full];'
 '[2:v]scale=180:-1,format=rgba,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[logo];'
 "[full][logo]overlay=W-w-24:24:enable='gte(t,10)',format=yuv420p[v]")
ff(['-y','-filter_complex_threads','2','-i',source,
    '-framerate','30','-i',ROOT/'assets/audio-bg/2.jpeg',
    '-framerate','30','-i',ROOT/'assets/logo-karaoke-cmyk-transparent.png',
    '-filter_complex',graph,'-map','[v]','-map','0:a:0','-t',info(source)['duration'],
    '-r','30','-c:v','libx264','-preset','veryfast','-crf','14','-threads','4',
    '-maxrate','4000k','-bufsize','8000k','-c:a','copy','-map_metadata','0',
    '-movflags','+faststart',output],folder,'render')
assert audio_hash(source)==audio_hash(output),'Audio changed'
assert abs(info(source)['duration']-info(output)['duration'])<.05
assert output.stat().st_size<150_000_000
ff(['-xerror','-i',output,'-f','null','-'],folder,'decode')
row={'output':str(output),'audio_identical':True,'full_picture_preserved':True,
     'bytes':output.stat().st_size,'sha256':digest(output),**info(output)}
(folder/'verified.json').write_text(json.dumps(row,indent=2))
print(json.dumps(row),flush=True)
