"""Evaluate cached LaMa on source frames before any video replacement."""
from pathlib import Path
import time
import av
import cv2
import numpy as np
import torch
from PIL import Image
from project_runtime import ROOT
from zoom_local_pipeline import read,save,digest


def main():
    torch.set_num_threads(3)
    checkpoint=ROOT/'models/inpainting/big-lama.pt'
    model=torch.jit.load(str(checkpoint),map_location='cpu').eval()
    source=ROOT/'inputs/Taylor Swift - Babylon - YouTube (1080p).mp4'
    rows=read(ROOT/'reports/babylon-text-cleanup/recognized-boxes.json')
    if digest(source)!=rows['binding']['source']:raise ValueError('Source changed')
    sheet=Image.new('RGB',(960,1080));measurements=[]
    for index,t in enumerate([5,80,160,200]):
        with av.open(str(source)) as media:
            media.seek(int(t*av.time_base))
            frame=next(f for f in media.decode(video=0) if f.time>=t)
            original=frame.to_ndarray(format='rgb24')
        row=min(rows['frames'],key=lambda r:abs(r['time']-t))
        mask=np.zeros(original.shape[:2],np.uint8)
        for x,y,w,h in row['boxes']:mask[y:y+h,x:x+w]=255
        small=cv2.resize(original,(768,432),interpolation=cv2.INTER_AREA)
        smallmask=cv2.resize(mask,(768,432),interpolation=cv2.INTER_NEAREST)
        a=torch.from_numpy(small.transpose(2,0,1).copy()).float()[None]/255
        b=torch.from_numpy(smallmask.copy()).float()[None,None]/255
        start=time.perf_counter()
        with torch.inference_mode():prediction=model(a,b)
        elapsed=time.perf_counter()-start
        pixels=prediction[0].permute(1,2,0).numpy()
        restored=cv2.resize(np.uint8(np.clip(pixels*255,0,255)),(1920,1080))
        result=original.copy();result[mask>0]=restored[mask>0]
        for col,image in enumerate([original,result]):
            tile=Image.fromarray(image);tile.thumbnail((480,270));sheet.paste(tile,(col*480,index*270))
        measurements.append({'source_time':t,'inference_seconds':elapsed})
        print(measurements[-1],flush=True)
    folder=ROOT/'reports/reference-repair'
    sheet.save(folder/'lama-trial.jpg')
    save(folder/'lama-trial.json',{'samples':measurements,'status':'visual trial, not video validation','model_sha256':digest(checkpoint)})


if __name__=='__main__':main()
