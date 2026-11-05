"""Add the original reference's white closing arc to a custom-logo video."""
import argparse,json,subprocess,hashlib
from pathlib import Path
from project_runtime import FFMPEG,ROOT

def reference_arc_filter(seconds):
    # Same outer-arc sampling, 1.18 expansion and clockwise wipe as intro_countdown.
    sx='(W/2+(X-W/2)/1.18)';sy='(H/2+(Y-H/2)/1.18)'
    moved=f'gt(hypot({sx}-W/2,{sy}-H/2),160)*gt(b({sx},{sy}),g({sx},{sy})+15)*gt(b({sx},{sy}),r({sx},{sy})-15)'
    angle='mod(atan2(Y-H/2,X-W/2)+PI/2+2*PI,2*PI)'
    alpha=f'if({moved},alpha({sx},{sy})*gte({angle},2*PI*T/{seconds:g}),0)'
    return ('scale=420:420,format=rgba,pad=500:500:40:40:color=black@0,'
            f"geq=r=255:g=255:b=255:a='{alpha}'")

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=a.input.resolve();out=a.output.resolve()
    if out.exists():raise FileExistsError(out)
    report=ROOT/'reports/jennifer-voxnova-circle';report.mkdir(parents=True,exist_ok=True)
    graph=f'[1:v]{reference_arc_filter(10)}[arc];[0:v][arc]overlay=710:80:eof_action=pass:repeatlast=0:enable=\'lt(t,10)\'[v]'
    cmd=[str(FFMPEG),'-v','warning','-stats','-nostdin','-n','-filter_complex_threads','2',
         '-threads','2','-i',str(source),'-loop','1','-framerate','30','-t','10',
         '-i',str(ROOT/'assets/logo-original.png'),'-filter_complex',graph,
         '-map','[v]','-map','0:a:0','-c:v','libx264','-threads','4','-crf','14',
         '-preset','veryfast','-pix_fmt','yuv420p','-c:a','copy','-map_metadata','0',
         '-movflags','+faststart',str(out)]
    (report/'command.json').write_text(json.dumps(cmd,indent=2))
    subprocess.run(cmd,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(out),'-f','null','-'],check=True)
    def ah(path):
        return subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-map','0:a:0',
          '-c','copy','-f','hash','-hash','sha256','-'],capture_output=True,check=True).stdout.decode().strip()
    assert ah(source)==ah(out),'Audio changed'
    import av
    with av.open(str(out)) as c:
        v=c.streams.video[0]
        spec={'width':v.width,'height':v.height,'fps':str(v.average_rate),'duration':float(c.duration/av.time_base)}
    result={'output':str(out),'source':str(source),'strict_decode':True,'audio_identical':True,
      'video':spec,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
      'change':'Reference white closing arc during first 10 seconds only'}
    (report/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
