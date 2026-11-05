"""Make a separate magenta-countdown copy; preserve encoded song tail and audio."""
import av,json
from render_round_compact_batch import ROOT,ff,info,audio_hash,digest
from restore_compact_intro_footer import pictures
from intro_countdown import reference_logo_filter
r=ROOT/'reports/new-karaoke-logo-magenta';r.mkdir(exist_ok=True)
src=ROOT/'out/New Logo Preview/Taylor Swift - Shake It Off - New Karaoke Logo.mp4'
out=src.with_name('Taylor Swift - Shake It Off - New Karaoke Logo - Magenta Circle.mp4')
if out.exists():raise FileExistsError(out)
with av.open(str(src)) as c:
 s=c.streams.video[0];scale=s.time_base.denominator
 boundary=next(float(p.pts*s.time_base) for p in c.demux(s) if p.is_keyframe and p.pts is not None and float(p.pts*s.time_base)>=10)
still=ROOT/'reports/round-compact-batch/13/background.png'
logo=ROOT/'assets/logo-karaoke-cmyk-transparent.png'
ass='reports/new-karaoke-logo-preview/intro.ass'
g=(f'[1:v]scale=1920:1080,setsar=1[bg];[2:v]{reference_logo_filter(10,1,"arc","#BB3794")}[logo];'
 f"[bg][logo]overlay=710:80:shortest=1,subtitles='{ass}'[intro];"
 "[0:v][intro]overlay=0:0:eof_action=pass:repeatlast=0:enable='lt(t,10)',format=yuv420p[v]")
ff(['-y','-filter_complex_threads','1','-i',src,'-loop','1','-framerate','30','-t','10','-i',still,'-loop','1','-framerate','30','-t','10','-i',logo,'-filter_complex',g,'-map','[v]','-an','-frames:v',round(boundary*30),'-r','30','-c:v','libx264','-preset','fast','-crf','18','-threads','4','-video_track_timescale',scale,r/'intro.mp4'],r,'render')
(r/'concat.txt').write_text(f"file '{(r/'intro.mp4').as_posix()}'\nfile '{src.as_posix()}'\ninpoint {boundary:.9f}\n")
ff(['-y','-f','concat','-safe','0','-i',r/'concat.txt','-i',src,'-map','0:v:0','-map','1:a:0','-c','copy','-map_metadata','1','-movflags','+faststart',out],r,'mux')
assert audio_hash(src)==audio_hash(out)
assert pictures(src,boundary)==pictures(out,boundary)
assert abs(info(src)['duration']-info(out)['duration'])<.05
ff(['-xerror','-i',out,'-f','null','-'],r,'decode')
(r/'verified.json').write_text(json.dumps({'output':str(out),'colour':'#BB3794','audio_identical':True,'body_bitstream_identical_from':boundary,'sha256':digest(out),**info(out)},indent=2))
print(out,flush=True)
