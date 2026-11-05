"""Logo-only copy of the verified Jennifer edit; copy encoded audio unchanged."""
import json,subprocess,hashlib,argparse
from pathlib import Path
from project_runtime import ROOT,FFMPEG

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--transparent',action='store_true')
    parser.add_argument('--full-circle',action='store_true',help='Keep the entire white ring visible; animate numbers only')
    args=parser.parse_args()
    if args.full_circle:args.transparent=True
    base=ROOT/'out/comparison/ftp-raw-light-heavy/repaired/Charlie Jeer - Jennifer - Light - Updated.mp4'
    raw=ROOT/'Charlie Jeer - Jennifer (1080).mp4'
    logo=ROOT/('assets/voxnova-transparent.png' if args.transparent else 'assets/voxnova.png.jpeg')
    still=ROOT/'work/bowlnfun/Jennifer-light-repaired/intro-background.png'
    out=base.with_name('Charlie Jeer - Jennifer - Light - VoxNova.mp4')
    report=ROOT/'reports/jennifer-voxnova';report.mkdir(parents=True,exist_ok=True)
    if args.transparent:
        out=base.with_name('Charlie Jeer - Jennifer - VoxNova - Transparent - Under 180MB.mp4')
        report=ROOT/'reports/jennifer-voxnova-transparent';report.mkdir(parents=True,exist_ok=True)
    if args.full_circle:
        out=base.parent/'lim/Charlie Jeer - Jennifer - VoxNova - Full Circle - Under 180MB.mp4'
        report=ROOT/'reports/jennifer-voxnova-full-circle';report.mkdir(parents=True,exist_ok=True)
    for p in (base,raw,logo,still):
        if not p.is_file():raise FileNotFoundError(p)
    if out.exists():raise FileExistsError(out)
    # Restore only the old artwork rectangles from the exact source background.
    # All lyrics, countdown numbers and title are outside these rectangles.
    graph=(
        '[1:v]fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,'
        'setsar=1,tpad=start_mode=clone:start_duration=10,setpts=PTS-STARTPTS,'
        'crop=180:180:1692:42[cornerbg];'
        '[2:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,'
        'crop=500:500:710:80[introbg];'
        "[0:v][introbg]overlay=710:80:enable='lt(t,10)'[a];"
        "[a][cornerbg]overlay=1692:42:enable='gte(t,10)':eof_action=pass[b];"
        '[3:v]split=2[li][lc];[li]scale=420:420[intrologo];[lc]scale=180:180[cornerlogo];'
        "[b][intrologo]overlay=750:120:enable='lt(t,10)'[c];"
        "[c][cornerlogo]overlay=1692:42:enable='gte(t,10)'[v]"
    )
    circle_input=[]
    if args.transparent:
        from add_reference_countdown_circle import reference_arc_filter
        graph=graph.replace("[v]","[branded]")
        circle_filter=reference_arc_filter(10)
        if args.full_circle:
            circle_filter="scale=500:500,format=rgba,geq=r=255:g=255:b=255:a='255*between(hypot(X-250,Y-250),210,216)'"
        graph+=f";[4:v]{circle_filter}[arc];[branded][arc]overlay=710:80:eof_action=pass:repeatlast=0:enable='lt(t,10)'[v]"
        circle_input=['-loop','1','-framerate','30','-t','10','-i',str(ROOT/'assets/logo-original.png')]
    rate=['-maxrate','7800k','-bufsize','7800k'] if args.transparent else []
    command=[str(FFMPEG),'-v','warning','-stats','-nostdin','-n','-filter_complex_threads','2',
        '-threads','2','-i',str(base),'-threads','2','-i',str(raw),
        '-loop','1','-framerate','30','-i',str(still),
        '-loop','1','-framerate','30','-i',str(logo),*circle_input,'-filter_complex',graph,
        '-map','[v]','-map','0:a:0','-c:v','libx264','-threads','4','-crf','18' if args.transparent else '14','-preset','fast',*rate,
        '-pix_fmt','yuv420p','-r','30','-c:a','copy','-t','168.66','-map_metadata','0',
        '-movflags','+faststart',str(out)]
    (report/'command.json').write_text(json.dumps(command,indent=2))
    subprocess.run(command,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(out),'-f','null','-'],check=True)
    def audio_hash(p):
        return subprocess.run([str(FFMPEG),'-v','error','-i',str(p),'-map','0:a:0',
            '-c','copy','-f','hash','-hash','sha256','-'],capture_output=True,check=True).stdout.decode().strip()
    assert audio_hash(base)==audio_hash(out),'Encoded audio changed'
    if args.transparent:assert out.stat().st_size<180_000_000,'Output exceeds 180 MB'
    result={'output':str(out),'sha256':sha(out),'source':str(base),'logo':str(logo),
        'strict_decode':True,'encoded_audio_identical':True,'duration':168.66,'size_bytes':out.stat().st_size,
        'full_circle_during_countdown':args.full_circle,
        'scope':'Logo-only copy; inherits unresolved content checks from source video'}
    (report/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
