"""Correct the centered intro and inset corner logo without changing audio or timing."""
import json
import argparse
from render_round_compact_batch import ROOT,ff,info,audio_hash,digest
from intro_countdown import reference_logo_filter

parser=argparse.ArgumentParser()
parser.add_argument('--song',choices=['saybia','human'],default='saybia')
args=parser.parse_args()
human=args.song=='human'
source=ROOT/'out/ftp-image-backgrounds'/('Human-2c623275af5e_DRAFT.mp4' if human else 'The_Second_You_Sleep-2c9642be5442_DRAFT.mp4')
name='Carpark North - Human' if human else 'Saybia - The Second You Sleep'
output=ROOT/'out/ftp-image-backgrounds/Updated Logo'/(name+' - Centered Smaller Logo - CORRECTED DRAFT.mp4')
background=ROOT/'assets/audio-bg'/('1.jpeg' if human else '2.jpeg')
folder=ROOT/'tmp'/(args.song+'-centered-logo')
folder.mkdir(parents=True,exist_ok=True)
if output.exists():raise FileExistsError(output)
logo=ROOT/'assets/logo-karaoke-cmyk-transparent.png'
graph=(
 '[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,split[bi][bc];'
 '[bi]crop=500:500:710:80,loop=loop=-1:size=1:start=0,setpts=N/(30*TB),trim=duration=10[pi];'
 '[bc]crop=180:182:1692:42,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[pc];'
 "[0:v][pi]overlay=710:80:enable='lt(t,10)'[nointro];"
 "[nointro][pc]overlay=1692:42:enable='gte(t,10)'[clean];"
 '[2:v]split[li][lc];'
 '[li]format=rgba,loop=loop=-1:size=1:start=0,setpts=N/(30*TB),trim=duration=10,'
 +reference_logo_filter(10,.7,'arc','#BB3794')+'[intro];'
 '[lc]scale=180:-1,format=rgba,loop=loop=-1:size=1:start=0,setpts=N/(30*TB)[corner];'
 "[clean][intro]overlay=805:155:enable='lt(t,10)'[centered];"
 "[centered][corner]overlay=W-w-24:24:enable='gte(t,10)',format=yuv420p[v]")
ff(['-y','-filter_complex_threads','2','-i',source,
    '-framerate','30','-i',background,
    '-framerate','30','-i',logo,'-filter_complex',graph,'-map','[v]','-map','0:a:0',
    '-t',info(source)['duration'],'-r','30','-c:v','libx264','-preset','veryfast','-crf','14',
    '-threads','4','-maxrate','4000k','-bufsize','8000k','-c:a','copy',
    '-map_metadata','0','-movflags','+faststart',output],folder,'render')
assert audio_hash(source)==audio_hash(output),'Audio changed'
assert abs(info(source)['duration']-info(output)['duration'])<.05
assert output.stat().st_size<150_000_000
ff(['-xerror','-i',output,'-f','null','-'],folder,'decode')
row={'output':str(output),'audio_identical':True,'intro_scale':.7,'intro_center':[960,330],
     'corner_margins':[24,24],'bytes':output.stat().st_size,'sha256':digest(output),**info(output)}
(folder/'verified.json').write_text(json.dumps(row,indent=2))
print(json.dumps(row),flush=True)
