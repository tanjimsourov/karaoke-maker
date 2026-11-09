"""Explicit full-frame stretch: no blur, bars or picture cropping; round logos."""
import json
from render_round_compact_batch import ROOT,ff,info,audio_hash,digest
from intro_countdown import reference_logo_filter

source=ROOT/'out/ftp-image-backgrounds/Updated Logo/Saybia - The Second You Sleep - Centered Smaller Logo - CORRECTED DRAFT.mp4'
folder=ROOT/'tmp/saybia-full-frame';folder.mkdir(parents=True,exist_ok=True)
output=ROOT/'out/ftp-image-backgrounds/Updated Logo/Saybia - The Second You Sleep - FULL SCREEN NO BLUR.mp4'
if output.exists():raise FileExistsError(output)
graph=(
 '[1:v]scale=1196:1080,pad=1920:1080:362:0:black,setsar=1,crop=350:350:805:225,'
 'loop=loop=-1:size=1:start=0,setpts=N/(30*TB),trim=duration=10[patch];'
 "[0:v][patch]overlay=805:225:enable='lt(t,10)',crop=1196:1080:362:0,scale=1920:1080,setsar=1[full];"
 '[2:v]split[li][lc];'
 '[li]format=rgba,loop=loop=-1:size=1:start=0,setpts=N/(30*TB),trim=duration=10,'
 +reference_logo_filter(10,.7,'arc','#BB3794')+'[intro];'
 '[lc]scale=180:-1,format=rgba,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[corner];'
 "[full][intro]overlay=805:225:enable='lt(t,10)'[opening];"
 "[opening][corner]overlay=W-w-24:24:enable='gte(t,10)',format=yuv420p[v]")
ff(['-y','-filter_complex_threads','2','-i',source,
    '-framerate','30','-i',ROOT/'assets/audio-bg/2.jpeg',
    '-framerate','30','-i',ROOT/'assets/logo-karaoke-cmyk-transparent.png',
    '-filter_complex',graph,'-map','[v]','-map','0:a:0','-t',info(source)['duration'],
    '-r','30','-c:v','libx264','-preset','veryfast','-crf','14','-threads','4',
    '-maxrate','4000k','-bufsize','8000k','-c:a','copy','-map_metadata','0',
    '-movflags','+faststart',output],folder,'render')
assert audio_hash(source)==audio_hash(output)
assert abs(info(source)['duration']-info(output)['duration'])<.05
assert output.stat().st_size<150_000_000
ff(['-xerror','-i',output,'-f','null','-'],folder,'decode')
row={'output':str(output),'audio_identical':True,'full_picture_stretched':True,
     'intro_logo_centered':True,'blur':False,'bars':False,
     'bytes':output.stat().st_size,'sha256':digest(output),**info(output)}
(folder/'verified.json').write_text(json.dumps(row,indent=2))
print(json.dumps(row),flush=True)
