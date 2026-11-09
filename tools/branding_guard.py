"""Fail-closed visible source-branding OCR check, not a copyright/licence check.

Scans the full frame at fixed intervals, including corners and the end credits.
No crop excludes our logo area: source marks anywhere in the frame must be found.
Sampling/OCR cannot certify absence of brief, unreadable or invisible watermarks.
"""
import argparse
import hashlib
import json
import re
import numpy as np
import subprocess
import uuid
import os
from collections import OrderedDict
from pathlib import Path
import av
from zoom_local_pipeline import digest,read,save
from project_runtime import FFMPEG

TERMS=('xtendamix','xtenda mix','copyright','all rights reserved','universal music',
       'sony music','warner music','republic records','atlantic records',
       'columbia records','interscope','independent','independant','vevo','sing king')


class BrandingDetected(ValueError):pass


def save_report(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    pending.write_text(json.dumps(value,indent=2),encoding='utf-8')
    pending.replace(path)


def normalize(text):
    return re.sub(r'[^a-z0-9]','',text.casefold())


def matches(text):
    value=normalize(text)
    return [term for term in TERMS if normalize(term) in value] + (
        ['copyright-symbol'] if any(c in text for c in ('©','℗')) else [])


def credit_box(rows,anchor,frame_width,frame_height):
    """Include the whole aligned lower-left caption stack, not only its brand."""
    box=np.asarray(anchor,dtype=float);lo=box.min(axis=0);hi=box.max(axis=0)
    selected=[box]
    if lo[0]<frame_width*.3 and hi[1]>frame_height*.55:
        for row in rows:
            other=np.asarray(row[0],dtype=float);a=other.min(axis=0);b=other.max(axis=0)
            if b[0]<frame_width*.45 and abs(a[0]-lo[0])<max(35,(hi[0]-lo[0])*.4) and (
                    lo[1]-max(240,7*(hi[1]-lo[1]))<=a[1] and b[1]<=hi[1]+70):
                selected.append(other)
    points=np.concatenate(selected);a=points.min(axis=0);b=points.max(axis=0)
    return [float(a[0]),float(a[1]),float(b[0]),float(b[1])]


def scan_binding(video,interval,width):
    return {'video_sha256':digest(video),'code_sha256':digest(Path(__file__)),
            'interval_seconds':interval,'scan_width':width,'terms':list(TERMS)}


def scan(video,report_path,interval=1.0,width=1280,engine=None):
    # Bound production OCR to one inference worker, independent of the audio slot.
    # A complete checksum-bound result needs no model or queue slot.
    if engine is None:
        if Path(report_path).exists():
            prior=read(report_path)
            if prior.get('binding')==scan_binding(video,interval,width) and prior.get('complete'):
                if prior['hits']:raise BrandingDetected(f'Source branding remains; see {report_path}')
                return prior
        from model_queue import resource_slots
        slots=int(os.getenv('KARAOKE_OCR_WORKERS','1'))
        if not 1<=slots<=2:raise ValueError('KARAOKE_OCR_WORKERS must be 1 or 2')
        with resource_slots('ocr',slots):
            return _scan(video,report_path,interval,width,None)
    return _scan(video,report_path,interval,width,engine)


def _scan(video,report_path,interval,width,engine):
    video=Path(video).resolve();report_path=Path(report_path)
    if not .25<=interval<=2 or not 640<=width<=1920:raise ValueError('Invalid branding scan settings')
    binding=scan_binding(video,interval,width)
    prior=None
    if report_path.exists():
        prior=read(report_path)
        if prior.get('binding')==binding and prior.get('complete'):
            if prior['hits']:raise BrandingDetected(f'Source branding remains; see {report_path}')
            return prior
    if engine is None:
        from rapidocr_onnxruntime import RapidOCR
        # 'min' preprocessing leaves native 1080p detector tensors unbounded.
        # Downscale the whole frame, never crop corners; bound recognition batch.
        engine=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1,
                       det_limit_type='max',rec_batch_num=2)
    report_path.parent.mkdir(parents=True,exist_ok=True)
    result={'binding':binding,'complete':False,'sampled_frames':0,'hits':[],
            'limitations':['Full-frame OCR samples, not every decoded frame.',
                'No guarantee for sub-interval, unreadable, graphical or invisible marks.',
                'Does not change ownership or grant distribution rights.']}
    if prior and prior.get('binding')==binding and not prior.get('complete') and 'last_sample_seconds' in prior:
        result=prior
    print('Scanning visible source branding:',video,flush=True)
    save_report(report_path,result)
    last_scanned=result.get('last_sample_seconds',-interval)
    target=last_scanned+interval;last_image=None;last_time=0.
    identical_frames=OrderedDict()
    def inspect(image,t):
        nonlocal last_scanned
        # Convert/rescale only sampled frames; inspect all of their pixels.
        im=image
        if im.shape[1]>width:
            import cv2
            im=cv2.resize(im,(width,round(im.shape[0]*width/im.shape[1])))
        # Exact pixel equality after the same resize: preserve all sample times,
        # coordinates and hits without repeating inference on static frames.
        key=(im.shape,hashlib.sha256(im.tobytes()).digest())
        if key in identical_frames:
            rows=identical_frames[key];identical_frames.move_to_end(key)
            result['reused_identical_samples']=result.get('reused_identical_samples',0)+1
        else:
            rows,_=engine(im,use_cls=False)
            identical_frames[key]=rows
            if len(identical_frames)>32:identical_frames.popitem(last=False)
            result['ocr_inferences']=result.get('ocr_inferences',0)+1
        found=[]
        for row in rows or []:
            box,text,confidence=row[:3]
            terms=matches(text)
            # Branding is a delivery risk even at low OCR confidence.
            if terms:
                found.append({'time':round(t,3),'text':text,'confidence':float(confidence),
                              'terms':terms,'box':np.asarray(box).tolist(),
                              'credit_box':credit_box(rows,box,im.shape[1],im.shape[0]),
                              'scan_size':[im.shape[1],im.shape[0]],
                              'frame_size':[image.shape[1],image.shape[0]]})
        if not found and rows:
            joined=' '.join(row[1] for row in rows)
            terms=matches(joined)
            if terms:found.append({'time':round(t,3),'text':joined,'confidence':None,
                                   'terms':terms,'box':None})
        result['hits']+=found;result['sampled_frames']+=1;last_scanned=t
        result['last_sample_seconds']=t
        save_report(report_path,result)
    if video.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.bmp'}:
        from PIL import Image
        inspect(np.asarray(Image.open(video).convert('RGB'))[:,:,::-1],0)
    else:
        with av.open(str(video)) as c:
            if not c.streams.video:raise ValueError('No video stream for branding scan')
            c.streams.video[0].thread_count=1
            for frame in c.decode(video=0):
                if frame.time is None:raise ValueError('Video frame lacks timestamps')
                t=float(frame.time);last_time=t
                if t+.001>=target:
                    image=frame.to_ndarray(format='bgr24');inspect(image,t);target=t+interval
                last_image=frame
            if last_image is not None and last_time-last_scanned>.05:
                inspect(last_image.to_ndarray(format='bgr24'),last_time)
    if not result['sampled_frames']:raise ValueError('No frames scanned')
    result['complete']=True
    result['status']='blocked_visible_branding' if result['hits'] else 'no_known_branding_detected_in_samples'
    save_report(report_path,result)
    print('Branding scan:',result['status'],result['sampled_frames'],'samples',flush=True)
    if result['hits']:raise BrandingDetected(f'{len(result["hits"])} source branding hit(s); see {report_path}')
    return result


def resolved_background(source,folder):
    """Reuse only a checksum-bound, re-scanned clean background."""
    marker=Path(folder)/'cleaned.json'
    if not marker.exists():return str(source)
    result=read(marker)
    if result.get('source_sha256')!=digest(source) or result.get('code_sha256')!=digest(Path(__file__)):
        return str(source)
    output=Path(result['output'])
    if not output.is_file() or digest(output)!=result['sha256']:return str(source)
    check=read(Path(folder)/'clean-scan.json')
    if not check.get('complete') or check['hits'] or check['binding']['video_sha256']!=result['sha256']:
        return str(source)
    return str(output)


def prepare_background(source,folder):
    """Bounded cleanup of detected credit blocks; original source stays intact."""
    source=Path(source).resolve();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    cached=resolved_background(source,folder)
    if cached!=str(source):return cached
    try:
        scan(source,folder/'source-scan.json')
        return str(source)
    except BrandingDetected:
        report=read(folder/'source-scan.json')
    masks=[]
    for hit in report['hits']:
        if 'credit_box' not in hit:raise BrandingDetected('Unlocated source mark; manual mask required')
        sw,sh=hit['scan_size'];fw,fh=hit['frame_size'];x1,y1,x2,y2=hit['credit_box']
        x=max(1,int(x1*fw/sw)-12);y=max(1,int(y1*fh/sh)-12)
        right=min(fw-1,int(np.ceil(x2*fw/sw))+12);bottom=min(fh-1,int(np.ceil(y2*fh/sh))+12)
        masks.append((x,y,right-x,bottom-y,max(0,hit['time']-1.5),hit['time']+1.5))
    # Coalesce temporally adjacent/overlapping detections of the same caption.
    merged=[]
    for mask in sorted(masks,key=lambda m:m[4]):
        x,y,w,h,start,end=mask
        match=next((i for i,m in enumerate(merged) if start<=m[5]+.1 and
                    abs(x-m[0])<80 and abs(y-m[1])<150),None)
        if match is None:merged.append(mask)
        else:
            a,b,c,d,s,e=merged[match];left=min(x,a);top=min(y,b)
            merged[match]=(left,top,max(x+w,a+c)-left,max(y+h,b+d)-top,min(s,start),max(e,end))
    key=hashlib.sha256(json.dumps({'source':digest(source),'masks':merged,'code':digest(Path(__file__))},sort_keys=True).encode()).hexdigest()[:12]
    output=folder/f'clean-{key}.mp4'
    if source.suffix.lower() not in {'.mp4','.mov','.mkv','.webm'}:
        raise BrandingDetected('Branded still image: supply a clean background')
    if output.exists():raise BrandingDetected('Incomplete/unverified cleanup exists; inspect before retry')
    filters=','.join(f"delogo=x={x}:y={y}:w={w}:h={h}:enable='between(t,{start:.3f},{end:.3f})'" for x,y,w,h,start,end in merged)
    command=[str(FFMPEG),'-v','error','-nostdin','-n','-threads','2','-i',str(source),
        '-map','0:v:0','-map','0:a:0?','-c:a','copy','-vf',filters,'-c:v','libx264','-threads','2','-crf','14',
        '-preset','fast','-pix_fmt','yuv420p','-map_metadata','-1','-movflags','+faststart',str(output)]
    save(folder/'cleanup-plan.json',{'source':str(source),'masks':merged,'command':command,
         'note':'Localized interpolation; hidden source detail cannot be recovered.'})
    with (folder/'cleanup.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,stdout=log,stderr=log,check=True)
    subprocess.run([str(FFMPEG),'-v','error','-xerror','-i',str(output),'-f','null','-'],check=True)
    scan(output,folder/'clean-scan.json')
    save(folder/'cleaned.json',{'source_sha256':digest(source),'code_sha256':digest(Path(__file__)),
         'output':str(output),'sha256':digest(output),'status':'no_known_branding_detected_in_samples'})
    return str(output)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path);p.add_argument('--report',required=True,type=Path)
    p.add_argument('--interval',type=float,default=1)
    a=p.parse_args()
    try:
        result=scan(a.video,a.report,interval=a.interval)
        print(result['status'],result['sampled_frames'],flush=True)
    except BrandingDetected as e:p.exit(2,str(e)+'\n')

if __name__=='__main__':main()
