"""Remove a known source caption region; copy the processed audio unchanged.

Coordinates and time range must be measured for each source, not guessed.
Never overwrites an existing video. Decode and inspect the result before delivery.
"""
import argparse
import subprocess
from pathlib import Path
from project_runtime import FFMPEG

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rect',required=True,help='x:y:width:height in output pixels')
    p.add_argument('--start',type=float,required=True)
    p.add_argument('--end',type=float,required=True)
    p.add_argument('--threads',type=int,default=2)
    a=p.parse_args()
    rect=list(map(int,a.rect.split(':')))
    if len(rect)!=4 or min(rect)<1 or not 0<=a.start<a.end or not 1<=a.threads<=8:
        p.error('Invalid rectangle/time range')
    if a.output.exists():raise FileExistsError(a.output)
    x,y,w,h=rect
    filt=f"delogo=x={x}:y={y}:w={w}:h={h}:enable='between(t,{a.start},{a.end})'"
    subprocess.run([str(FFMPEG),'-v','error','-n','-threads',str(a.threads),'-i',str(a.source),'-vf',filt,
        '-map','0:v:0','-map','0:a:0','-c:v','libx264','-crf','14','-preset','fast',
        '-threads',str(a.threads),'-c:a','copy','-map_metadata','0','-movflags','+faststart',str(a.output)],check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(a.output),
        '-map','0:v:0','-map','0:a:0','-f','null','-'],check=True)
    print(a.output,flush=True)

if __name__=='__main__':main()
