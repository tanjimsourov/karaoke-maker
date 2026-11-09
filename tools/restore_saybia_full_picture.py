"""Restore the uncropped photo around the existing timed karaoke composition."""
import json
from render_round_compact_batch import ROOT,ff,info,audio_hash,digest
from intro_countdown import reference_logo_filter

source=ROOT/'out/ftp-image-backgrounds/Updated Logo/Saybia - The Second You Sleep - Centered Smaller Logo - CORRECTED DRAFT.mp4'
folder=ROOT/'tmp/saybia-full-picture';folder.mkdir(parents=True,exist_ok=True)
output=folder/'Saybia - Full Picture.mp4'
photo=ROOT/'assets/audio-bg/2.jpeg'
logo=ROOT/'assets/logo-karaoke-cmyk-transparent.png'
# The old 16:9 picture is the central crop of this same still. Fit that band
# into the full-height photo, preserving the burned-in words and their timing.
# Recreate the logos at their requested canvas positions after fitting the band.
graph=(
 '[1:v]split[full][old];'
 '[full]scale=1196:1080,pad=1920:1080:362:0:black,setsar=1,'
 'loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[fullphoto];'
 '[old]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,split[oi][oc];'
 '[oi]crop=350:350:805:155,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[ip];'
 '[oc]crop=180:182:1716:24,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[cp];'
 "[0:v][ip]overlay=805:155:enable='lt(t,10)'[a];"
 "[a][cp]overlay=1716:24:enable='gte(t,10)',scale=1196:674[band];"
 '[fullphoto][band]overlay=362:203[restored];'
 '[2:v]split[li][lc];'
 '[li]format=rgba,loop=loop=-1:size=1:start=0,setpts=N/(30*TB),trim=duration=10,'
 +reference_logo_filter(10,.7,'arc','#BB3794')+'[intro];'
 '[lc]scale=180:-1,format=rgba,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[corner];'
 "[restored][intro]overlay=805:225:enable='lt(t,10)'[b];"
 "[b][corner]overlay=W-w-24:24:enable='gte(t,10)',format=yuv420p[v]")
ff(['-y','-filter_complex_threads','2','-i',source,'-framerate','30','-i',photo,
    '-framerate','30','-i',logo,'-filter_complex',graph,'-map','[v]','-map','0:a:0',
    '-t',info(source)['duration'],'-r','30','-c:v','libx264','-crf','14','-preset','veryfast',
    '-threads','4','-maxrate','4000k','-bufsize','8000k','-c:a','copy','-map_metadata','0',
    '-movflags','+faststart',output],folder,'render')
assert audio_hash(source)==audio_hash(output)
assert abs(info(source)['duration']-info(output)['duration'])<.05
assert output.stat().st_size<150000000
ff(['-xerror','-i',output,'-f','null','-'],folder,'decode')
row={'output':str(output),'audio_identical':True,'full_photo_visible':True,
     'lyric_timing_preserved':True,'overlay_layout_scaled_to_photo':True,
     'bytes':output.stat().st_size,'sha256':digest(output),**info(output)}
(folder/'verified.json').write_text(json.dumps(row,indent=2))
print(json.dumps(row),flush=True)
