"""Create countdown/transition evidence for the delivered REI AMI copies."""
import json
import av
from PIL import Image,ImageDraw
from make_rei_ami_logo_pair import REPORT,DEST

def frame(path,t):
 with av.open(str(path)) as c:
  s=c.streams.video[0];c.seek(int(t/s.time_base),stream=s)
  for f in c.decode(s):
   if float(f.time)>=t:return f.to_image()
 raise ValueError((path,t))

for brand in ['Karaoke','VoxNova']:
 path=DEST/f'REI AMI - 2Loud - {brand}.mp4'
 sheet=Image.new('RGB',(1250,1000));draw=ImageDraw.Draw(sheet)
 for i in range(10):
  img=frame(path,i+.2).crop((650,20,1270,1060)).resize((250,419))
  sheet.paste(img,((i%5)*250,(i//5)*500))
  draw.text(((i%5)*250+5,(i//5)*500+5),f'{i+.2:.1f}s',fill='red')
 sheet.save(REPORT/f'{brand}-countdown.jpg')
 sheet=Image.new('RGB',(960,540));draw=ImageDraw.Draw(sheet)
 for i,t in enumerate([9.9,10,10.1,20]):
  sheet.paste(frame(path,t).resize((480,270)),((i%2)*480,(i//2)*270))
  draw.text(((i%2)*480+5,(i//2)*270+5),f'{t:.1f}s',fill='red')
 sheet.save(REPORT/f'{brand}-transition.jpg')
print('Countdown and transition review sheets generated')
