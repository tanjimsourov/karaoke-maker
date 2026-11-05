"""Generate visual review sheets for verified batch outputs only."""
import json
from pathlib import Path
import av
from PIL import Image, ImageDraw
from project_runtime import ROOT

report=ROOT/'reports/round-compact-batch'
records=[json.loads(p.read_text()) for p in sorted(report.glob('*/verified.json'))]

def frame(path,t):
 with av.open(str(path)) as c:
  stream=c.streams.video[0];c.seek(int(t/stream.time_base),stream=stream)
  for f in c.decode(stream):
   if float(f.time)>=t:return f.to_image().resize((320,180))
 raise ValueError((path,t))

for mode in ['intro','body']:
 cols=4 if mode=='intro' else 2
 sheet=Image.new('RGB',(320*cols,200*len(records)),(20,25,30));draw=ImageDraw.Draw(sheet)
 for row,r in enumerate(records):
  samples=[(r['output'],t) for t in [0.2,5,9.2,10.1]] if mode=='intro' else [(r[k],60) for k in ['source','output']]
  for col,(path,t) in enumerate(samples):sheet.paste(frame(path,t),(320*col,200*row+20))
  draw.text((4,200*row+3),Path(r['output']).stem,fill='white')
 sheet.save(report/f'final-{mode}-preview.jpg')
print(f'Created visual sheets for {len(records)} verified files')
