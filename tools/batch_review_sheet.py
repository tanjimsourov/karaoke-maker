"""Make local contact sheets from completed batch videos for visual QA."""
from pathlib import Path
import json
import av
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/remaining_13'
jobs=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
for kind in ['intro','lyrics']:
    available=[j for j in jobs if (ROOT/'out'/(j['slug']+'_Karaoke.mp4')).exists()]
    sheet=Image.new('RGB',(1280,390*((len(available)+1)//2)), '#222222')
    draw=ImageDraw.Draw(sheet)
    for i,j in enumerate(available):
        t=1.0 if kind=='intro' else j['seconds']*.4+3
        with av.open(str(ROOT/'out'/(j['slug']+'_Karaoke.mp4'))) as c:
            c.seek(int(t*av.time_base))
            for frame in c.decode(video=0):
                if frame.time>=t:
                    picture=frame.to_image().resize((640,360));break
        x=(i%2)*640;y=(i//2)*390
        sheet.paste(picture,(x,y))
        draw.text((x+8,y+365),j['slug'],fill='white')
    sheet.save(WORK/(kind+'_contact.jpg'))
print('Contact sheets saved')
