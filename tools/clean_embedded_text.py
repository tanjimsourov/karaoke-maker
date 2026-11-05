"""Detect embedded text in a source background and interpolate its timed regions.

Run BEFORE karaoke overlays. This is localized interpolation, not reconstruction
of hidden scene detail. Original sources are never overwritten.
"""
import argparse
from pathlib import Path
import subprocess
import av
import cv2
import numpy as np
from project_runtime import FFMPEG
from zoom_local_pipeline import save,read,digest

def detect(source,folder,interval=.5):
    from rapidocr_onnxruntime import RapidOCR
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'text-boxes.json'
    binding={'source':digest(source),'interval':interval,'width':1280,'version':1}
    if target.exists():
        r=read(target)
        if r['binding']!=binding:raise ValueError('Detection cache belongs to different input/settings')
        if r.get('complete'):return r
    else:r={'binding':binding,'frames':[],'complete':False}
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,det_limit_type='max')
    next_time=r['frames'][-1]['time']+interval if r['frames'] else 0
    with av.open(str(source)) as c:
        stream=c.streams.video[0];stream.thread_count=2
        r['width']=stream.width;r['height']=stream.height
        r['duration']=c.duration/av.time_base
        for f in c.decode(video=0):
            if f.time+.0001<next_time:continue
            im=f.to_ndarray(format='bgr24');height=round(im.shape[0]*1280/im.shape[1])
            small=cv2.resize(im,(1280,height))
            boxes,_=engine(small,use_cls=False,use_rec=False)
            found=[]
            for box in boxes or []:
                points=np.asarray(box,dtype=float)*im.shape[1]/1280
                lo=points.min(axis=0);hi=points.max(axis=0)
                x=max(1,int(lo[0])-22);y=max(1,int(lo[1])-18)
                right=min(im.shape[1]-1,int(np.ceil(hi[0]))+22)
                bottom=min(im.shape[0]-1,int(np.ceil(hi[1]))+18)
                if right-x>4 and bottom-y>4:found.append([x,y,right-x,bottom-y])
            r['frames'].append({'time':round(f.time,4),'boxes':found})
            next_time=f.time+interval
            if len(r['frames'])%20==0:save(target,r);print('detected through',round(f.time,1),flush=True)
    r['complete']=True;save(target,r);return r

def recognize_boxes(source,folder,report):
    from rapidocr_onnxruntime import RapidOCR
    target=folder/'recognized-boxes.json'
    if target.exists():
        previous=read(target)
        if previous.get('complete') and previous['binding']==report['binding']:return previous
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
    result={**report,'frames':[],'complete':False,'filter':'crop recognition confidence >= .6 and alphabetic text'}
    rows=iter(report['frames']);row=next(rows,None)
    with av.open(str(source)) as c:
        c.streams.video[0].thread_count=2
        for frame in c.decode(video=0):
            if row is None:break
            if frame.time+.002<row['time']:continue
            im=frame.to_ndarray(format='bgr24');kept=[];texts=[]
            for box in row['boxes']:
                x,y,w,h=box
                recognized,_=engine(im[y:y+h,x:x+w],use_det=False,use_cls=False)
                valid=[r for r in recognized or [] if float(r[1])>=.6 and any(ch.isalpha() for ch in r[0])]
                if valid:kept.append(box);texts.extend(valid)
            result['frames'].append({**row,'boxes':kept,'texts':texts})
            if len(result['frames'])%40==0:save(target,result);print('recognized through',round(frame.time,1),flush=True)
            row=next(rows,None)
    result['complete']=True;save(target,result);return result

def masks(report):
    result=[];pad=report['binding']['interval']+0.25
    for frame in report['frames']:
        boxes=[list(b) for b in frame['boxes']]
        # Adjacent lyric rows must share a single interpolation boundary; a
        # separate row's boundary may contain letters from its neighbour.
        changed=True
        while changed:
            changed=False
            for i in range(len(boxes)):
                for j in range(i+1,len(boxes)):
                    a,b,c,d=boxes[i];x,y,w,h=boxes[j]
                    if min(a+c,x+w)+60>=max(a,x) and min(b+d,y+h)+140>=max(b,y):
                        left=min(a,x);top=min(b,y)
                        boxes[i]=[left,top,max(a+c,x+w)-left,max(b+d,y+h)-top]
                        boxes.pop(j);changed=True;break
                if changed:break
        for x,y,w,h in boxes:
            start=max(0,frame['time']-pad);end=min(report['duration'],frame['time']+pad)
            # Join only nearby overlapping text regions; avoid whole-frame masks.
            match=next((i for i,m in enumerate(result) if start<=m[5]+.1 and end>=m[4]
                        and abs(y-m[1])<45 and abs((y+h)-(m[1]+m[3]))<65
                        and min(x+w,m[0]+m[2])>max(x,m[0])),None)
            if match is None:result.append([x,y,w,h,start,end])
            else:
                a,b,c,d,s,e=result[match];left=min(a,x);top=min(b,y)
                result[match]=[left,top,max(a+c,x+w)-left,max(b+d,y+h)-top,min(s,start),max(e,end)]
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--detect-only',action='store_true')
    p.add_argument('--filter-recognition',action='store_true')
    a=p.parse_args();r=detect(a.source,a.work)
    if a.filter_recognition:r=recognize_boxes(a.source,a.work,r)
    regions=masks(r)
    save(a.work/'masks.json',regions)
    if a.detect_only:return
    if a.output.exists():raise FileExistsError(a.output)
    filters=','.join(f"delogo=x={x}:y={y}:w={w}:h={h}:enable='between(t,{s:.4f},{e:.4f})'" for x,y,w,h,s,e in regions)
    if not filters:filters='null'
    script=a.work/'filter.txt';script.write_text(filters,encoding='utf-8')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    command=[str(FFMPEG),'-v','warning','-n','-i',str(a.source),'-map','0:v:0','-an',
        '-filter_script:v',str(script),'-c:v','libx264','-preset','veryfast','-crf','14','-threads','3',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(a.output)]
    save(a.work/'recipe.json',{'source':str(a.source.resolve()),'source_sha256':r['binding']['source'],
        'output':str(a.output.resolve()),'regions':len(regions),'command':command,
        'limitation':'Interpolated regions may be softer; sampled detection requires visual verification.'})
    subprocess.run(command,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(a.output),'-f','null','-'],check=True)
    save(a.work/'result.json',{'output':str(a.output.resolve()),'sha256':digest(a.output),'strict_decode':True})

if __name__=='__main__':main()
