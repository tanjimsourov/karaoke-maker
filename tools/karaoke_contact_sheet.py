"""Sample exported video frames for visual layout review."""
import argparse
from pathlib import Path
import av
from PIL import Image,ImageDraw

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--video',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--times',required=True)
    a=p.parse_args();times=[float(t) for t in a.times.split(',')]
    sheet=Image.new('RGB',(1440,430*((len(times)+1)//2)),'#222222');draw=ImageDraw.Draw(sheet)
    with av.open(str(a.video)) as c:
        stream=c.streams.video[0]
        for i,t in enumerate(times):
            c.seek(int(t/stream.time_base),stream=stream)
            frame=next(f for f in c.decode(video=0) if float(f.time)>=t)
            im=frame.to_image();im.thumbnail((720,405));x=i%2*720;y=i//2*430
            draw.text((x+8,y+5),f'{t:.2f}s',fill='white');sheet.paste(im,(x,y+25))
    sheet.save(a.output)
