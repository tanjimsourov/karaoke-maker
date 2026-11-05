from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/zoom_backgrounds'
BACKGROUNDS=[ROOT/'audio-bg-sample/14-10/jan-chatgpt'/n for n in ['Neon bowlinglounge in dromerige bokeh.png','Dromerige neonbowling in Aalborg.png']]

def background(k):
    b=cv2.imread(str(BACKGROUNDS[k]));h,w=b.shape[:2];s=max(1280/w,720/h)
    b=cv2.resize(b,(round(w*s),round(h*s)));h,w=b.shape[:2]
    return b[(h-720)//2:(h-720)//2+720,(w-1280)//2:(w-1280)//2+1280]

def mask(frame,k):
    b,g,r=[c.astype(np.float32) for c in cv2.split(frame)]
    if k==0:
        seed=((b>r*1.4+12)&(b>g*1.15)&(g>10))|((r>160)&(g>150)&(b<70)&(abs(r-g)<45))|((r>130)&(b>90)&(g<r*.65))|((np.minimum(np.minimum(r,g),b)>180)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<30))
    else:
        seed=(g-np.minimum(r,b)<30)&((np.maximum(np.maximum(r,g),b)>70))
    seed[:175 if k==0 else 180,:]=False
    seed[625:,:]=False;seed[:,:65]=False;seed[:,1215:]=False
    n,labels,stats,_=cv2.connectedComponentsWithStats(seed.astype(np.uint8),8)
    keep=np.zeros(n,np.uint8)
    for i in range(1,n):
        x,y,w,h,area=stats[i]
        if area>=45 and h>=12 and w>=2:keep[i]=1
    core=keep[labels]
    near=cv2.dilate(core,np.ones((15,15),np.uint8))
    dark=np.maximum(np.maximum(r,g),b)<75
    if k==1:
        dark=(g-np.minimum(r,b)<40)&(np.maximum(np.maximum(r,g),b)<100)
    matte=(core | (near & dark)).astype(np.float32)
    matte=cv2.GaussianBlur(matte,(3,3),.5)
    return matte

if __name__=='__main__':
 for k in range(2):
    files=sorted(WORK.glob(f'source_{k}_*.png'))
    sheet=Image.new('RGB',(1280,385*((len(files)+1)//2)),'#222222');draw=ImageDraw.Draw(sheet)
    bg=background(k)
    for i,p in enumerate(files):
        frame=cv2.imread(str(p));m=mask(frame,k)[...,None]
        out=(frame*m+bg*(1-m)).astype(np.uint8)
        cv2.imwrite(str(WORK/(p.stem+'_masked.png')),out)
        im=Image.fromarray(cv2.cvtColor(out,cv2.COLOR_BGR2RGB)).resize((640,360))
        x=i%2*640;y=i//2*385;sheet.paste(im,(x,y));draw.text((x+8,y+362),p.stem,fill='white')
    sheet.save(WORK/f'mask_sheet_{k}.jpg')
