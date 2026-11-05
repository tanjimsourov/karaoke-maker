"""Recover a review reference from an inspected lyric band, without approval.

Uses the already installed screen-OCR model. Retains per-sample text and timing
so the operator can compare it with the singing/transcription before alignment.
"""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import av
from model_queue import model_slot
from branding_guard import save_report
from zoom_local_pipeline import digest


def norm(text):return re.sub(r'[^a-z0-9]','',text.casefold())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--crop',required=True,help='x:y:width:height, native source pixels')
    p.add_argument('--step',type=float,default=.5)
    a=p.parse_args();x,y,w,h=map(int,a.crop.split(':'))
    if min(x,y)<0 or min(w,h)<1 or not .25<=a.step<=2:p.error('Invalid crop/step')
    binding={'source_sha256':digest(a.source),'code_sha256':digest(Path(__file__)),
             'crop':[x,y,w,h],'step':a.step}
    prior=json.loads(a.output.read_text()) if a.output.exists() else None
    if prior and prior.get('binding')!=binding:raise ValueError('Reference inputs changed; choose another output')
    if prior and prior.get('complete'):print('Reusing verified source reference');return
    records=prior['samples'] if prior else []
    target=records[-1]['time']+a.step if records else 0
    with model_slot(name='ocr'):
        from rapidocr_onnxruntime import RapidOCR
        engine=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1,det_limit_type='max',rec_batch_num=2)
        with av.open(str(a.source)) as c:
            c.streams.video[0].thread_count=2
            for frame in c.decode(video=0):
                t=float(frame.time)
                if t+.001<target:continue
                image=frame.to_ndarray(format='bgr24')
                if x+w>image.shape[1] or y+h>image.shape[0]:raise ValueError('Crop outside source')
                rows,_=engine(image[y:y+h,x:x+w],use_cls=False)
                good=[r for r in rows or [] if float(r[2])>=.65]
                good.sort(key=lambda r:(round(sum(v[1] for v in r[0])/4/20),sum(v[0] for v in r[0])/4))
                text=' '.join(r[1].strip() for r in good).strip()
                records.append({'time':round(t,3),'text':text})
                save_report(a.output,{'binding':binding,'complete':False,'samples':records})
                target=t+a.step
    groups=[]
    for row in records:
        text=row['text'];t=row['time']
        if not norm(text):continue
        if groups and t-groups[-1]['last']<=a.step*2 and SequenceMatcher(None,norm(text),norm(groups[-1]['text'])).ratio()>=.86:
            group=groups[-1];group['variants'].append(text);group['last']=t;group['end']=t+a.step
            group['text']=Counter(group['variants']).most_common(1)[0][0]
        else:groups.append({'start':t,'end':t+a.step,'last':t,'text':text,'variants':[text]})
    cues=[{k:r[k] for k in ['start','end','text']} for r in groups]
    save_report(a.output,{'binding':binding,'complete':True,'samples':records,'cues':cues,'approved':False})
    for row in cues:print(f"{row['start']:.2f}-{row['end']:.2f} {row['text']}",flush=True)

if __name__=='__main__':main()
