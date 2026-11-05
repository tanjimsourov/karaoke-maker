"""Short video trial: LaMa anchors with motion-warped patches between anchors.

Experimental only: does not publish or replace karaoke exports.
"""
import argparse,bisect,time,subprocess
from pathlib import Path
import av,cv2,numpy as np,torch
from project_runtime import ROOT,FFMPEG
from zoom_local_pipeline import read,save,digest


def mask_for(rows,t,shape):
    times=[r['time'] for r in rows]
    index=bisect.bisect_left(times,t)
    mask=np.zeros(shape[:2],np.uint8)
    for r in rows[max(0,index-2):index+3]:
        if abs(r['time']-t)>1.1:continue
        for x,y,w,h in r['boxes']:mask[y:y+h,x:x+w]=255
    return cv2.dilate(mask,np.ones((65,65),np.uint8))


class Repair:
    def __init__(self):
        torch.set_num_threads(3)
        self.model=torch.jit.load(str(ROOT/'models/inpainting/big-lama.pt'),map_location='cpu').eval()
        self.flow=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.anchor=None;self.time=-100;self.runs=0

    def infer(self,im,mask):
        small=cv2.resize(im,(768,432),interpolation=cv2.INTER_AREA)
        m=cv2.resize(mask,(768,432),interpolation=cv2.INTER_NEAREST)
        a=torch.from_numpy(small[:,:,::-1].transpose(2,0,1).copy()).float()[None]/255
        b=torch.from_numpy(m.copy()).float()[None,None]/255
        with torch.inference_mode():pred=self.model(a,b)
        result=np.uint8(np.clip(pred[0].permute(1,2,0).numpy()*255,0,255))[:,:,::-1]
        result=cv2.resize(result,(im.shape[1],im.shape[0]))
        clean=im.copy();clean[mask>0]=result[mask>0];self.runs+=1
        return clean

    def frame(self,im,mask,t):
        gray=cv2.resize(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),(384,216))
        # A cut triggers a fresh anchor instead of dragging the previous shot.
        cut=self.anchor is not None and np.mean(cv2.absdiff(gray,self.gray))>35
        uncovered=self.anchor is not None and np.count_nonzero((mask>0)&(self.mask==0))>100
        if self.anchor is None or t-self.time>=.5 or cut or uncovered:
            self.anchor=self.infer(im,mask) if np.any(mask) else im.copy()
            self.gray=gray;self.time=t;self.mask=mask.copy()
            return self.anchor.copy()
        if not np.any(mask):return im
        flow=self.flow.calc(gray,self.gray,None)
        tiny=cv2.resize(mask,(384,216),interpolation=cv2.INTER_NEAREST)
        # Interpolate motion across text regions from surrounding scene motion.
        for channel in range(2):
            flow[:,:,channel]=cv2.inpaint(flow[:,:,channel].copy(),tiny,3,cv2.INPAINT_NS)
        flow=cv2.resize(flow,(im.shape[1],im.shape[0]))
        flow[:,:,0]*=im.shape[1]/384;flow[:,:,1]*=im.shape[0]/216
        y,x=np.mgrid[:im.shape[0],:im.shape[1]].astype(np.float32)
        warped=cv2.remap(self.anchor,x+flow[:,:,0],y+flow[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        alpha=cv2.GaussianBlur(mask.astype(np.float32)/255,(31,31),0)
        alpha[mask==0]=0
        output=np.uint8(np.clip(im*(1-alpha[:,:,None])+warped*alpha[:,:,None],0,255))
        return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start',type=float,default=78);p.add_argument('--seconds',type=float,default=4)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    if a.start<0 or a.seconds<=0:raise ValueError('Invalid interval')
    source=ROOT/'inputs/Taylor Swift - Babylon - YouTube (1080p).mp4'
    rows=read(ROOT/'reports/babylon-text-cleanup/recognized-boxes.json')
    if digest(source)!=rows['binding']['source']:raise ValueError('Source changed')
    a.output.parent.mkdir(parents=True,exist_ok=True);repair=Repair();started=time.perf_counter();count=0
    with av.open(str(source)) as c:
        s=c.streams.video[0];c.seek(int(a.start*av.time_base))
        command=[str(FFMPEG),'-v','error','-n','-f','rawvideo','-pix_fmt','bgr24','-s',f'{s.width}x{s.height}',
                 '-r',str(s.average_rate),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','14',
                 '-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output)]
        with a.output.with_suffix('.log').open('w') as log:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log)
            try:
                for f in c.decode(video=0):
                    if f.time<a.start:continue
                    if f.time>=a.start+a.seconds:break
                    im=f.to_ndarray(format='bgr24');mask=mask_for(rows['frames'],f.time,im.shape)
                    process.stdin.write(repair.frame(im,mask,f.time).tobytes());count+=1
                    if count%48==0:print('Processed',f.time,flush=True)
            finally:process.stdin.close();status=process.wait()
            if status:raise RuntimeError('Encoder failed')
    save(a.output.with_suffix('.json'),{'source_sha256':rows['binding']['source'],'output_sha256':digest(a.output),
        'frames':count,'model_calls':repair.runs,'elapsed_seconds':time.perf_counter()-started,
        'status':'unreviewed temporal trial; not a final export'})


if __name__=='__main__':main()
