"""Repair a fixed source-credit caption with a glyph mask; preserve surrounding pixels."""
import argparse, subprocess
from pathlib import Path
import av,cv2,numpy as np
from PIL import Image,ImageDraw
from project_runtime import FFMPEG
from zoom_local_pipeline import save,digest

def frame_at(source,t):
    with av.open(str(source)) as c:
        s=c.streams.video[0];c.seek(int(t/s.time_base),stream=s)
        return next(f.to_ndarray(format='bgr24') for f in c.decode(video=0) if f.time>=t)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--box',default='130,800,330,210');p.add_argument('--mask-time',type=float,default=42)
    p.add_argument('--start',type=float,default=34.48);p.add_argument('--end',type=float,default=45.52)
    p.add_argument('--trial',action='store_true');a=p.parse_args()
    x,y,w,h=map(int,a.box.split(','));a.output.parent.mkdir(parents=True,exist_ok=True)
    ref=frame_at(a.source,a.mask_time)[y:y+h,x:x+w]
    gray=cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY)
    high=cv2.morphologyEx(gray,cv2.MORPH_TOPHAT,np.ones((13,13),np.uint8))
    mask=np.uint8((high>20)&(gray>65))*255
    mask=cv2.dilate(mask,np.ones((5,5),np.uint8))
    cv2.imwrite(str(a.output.with_suffix('.mask.png')),mask)
    if a.trial:
        sheet=Image.new('RGB',(990,420));draw=ImageDraw.Draw(sheet)
        for row,t in enumerate([36,42]):
            im=frame_at(a.source,t)[y:y+h,x:x+w]
            for col,img in enumerate([im,cv2.inpaint(im,mask,3,cv2.INPAINT_TELEA),cv2.inpaint(im,mask,3,cv2.INPAINT_NS)]):
                sheet.paste(Image.fromarray(img[:,:,::-1]),(col*330,row*210))
        sheet.save(a.output);return
    if a.output.exists():raise FileExistsError(a.output)
    with av.open(str(a.source)) as c:
        s=c.streams.video[0];fps=float(s.average_rate);c.seek(int(a.start/s.time_base),stream=s)
        cmd=[str(FFMPEG),'-v','error','-n','-f','rawvideo','-pix_fmt','bgr24','-s',f'{w}x{h}',
             '-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-crf','0','-preset','veryfast',
             '-threads','2','-pix_fmt','yuv444p',str(a.output)]
        count=0;first=None
        with a.output.with_suffix('.log').open('w') as log:
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
            try:
                for f in c.decode(video=0):
                    t=float(f.time)
                    if t<a.start:continue
                    if t>=a.end:break
                    if first is None:first=t
                    im=f.to_ndarray(format='bgr24')[y:y+h,x:x+w].copy()
                    clean=cv2.inpaint(im,mask,3,cv2.INPAINT_TELEA)
                    proc.stdin.write(clean.tobytes());count+=1
            finally:proc.stdin.close()
            if proc.wait()!=0:raise RuntimeError('Patch encode failed')
    save(a.output.with_suffix('.json'),{'source_sha256':digest(a.source),'sha256':digest(a.output),
        'start':first,'end':first+count/fps,'frames':count,'box':[x,y,w,h],
        'mask_pixels':int(np.count_nonzero(mask)),'review':'candidate, not full visual approval'})

if __name__=='__main__':main()
