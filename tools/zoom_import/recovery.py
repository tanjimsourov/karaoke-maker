"""Recover supplied on-screen lyrics and measured colour sweeps, locally."""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import av
import cv2
import numpy as np
from common import ROOT, save, read
CORRECTIONS = {}
SCAN_INTERVAL = 1.0

WORK=ROOT/'work/zoom_screen'
SOURCES=sorted((ROOT/'zoom').glob('*.mp4'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')


def join_rows(lines):
    rows=[]
    for item in sorted(lines,key=lambda a:np.asarray(a['box'])[:,1].mean()):
        y=np.asarray(item['box'])[:,1].mean()
        group=next((g for g in rows if abs(np.asarray(g[0]['box'])[:,1].mean()-y)<24),None)
        if group is None: rows.append([item])
        else: group.append(item)
    output=[]
    for row in rows:
        row.sort(key=lambda a:np.asarray(a['box'])[:,0].mean())
        if len(row)==1: output.append(row[0]); continue
        box=np.concatenate([np.asarray(a['box']) for a in row]);x1,y1=box.min(axis=0);x2,y2=box.max(axis=0)
        letters=[];chars=[]
        for item in row:
            if letters:
                letters.append(' ');chars.append(item['chars'][0])
            letters.extend(item['letters']);chars.extend(item['chars'])
        output.append({'box':[[x1,y1],[x2,y1],[x2,y2],[x1,y2]],'text':' '.join(a['text'].strip() for a in row),
                       'score':float(np.mean([a['score'] for a in row])),'letters':letters,'chars':chars})
    return output


def norm(text):
    return re.sub('[^a-z0-9]','',text.lower())


def scan(k):
    from rapidocr_onnxruntime import RapidOCR
    folder=WORK/str(k); folder.mkdir(parents=True,exist_ok=True)
    cache=folder/'ocr_v2.jsonl'
    records=[json.loads(line) for line in cache.read_text().splitlines()] if cache.exists() else []
    done={round(r['time'],1) for r in records}
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    target=0.
    with av.open(str(SOURCES[k])) as container, cache.open('a',encoding='utf-8') as out:
        for frame in container.decode(video=0):
            t=float(frame.time)
            if t+.001<target: continue
            at=target; target+=SCAN_INTERVAL
            if round(at,1) in done: continue
            bgr=cv2.resize(frame.to_ndarray(format='bgr24'),(1280,720))
            # Exclude logos, but keep every possible lyric row.
            results,_=engine(bgr,return_word_box=True,use_cls=False)
            lines=[]
            for item in results or []:
                box,text,score,chars,letters,char_scores=item
                box=np.asarray(box)
                if score<.75 or box[:,1].max()-box[:,1].min()<25 or box[:,1].mean()<100 or box[:,1].mean()>610: continue
                chars=np.asarray(chars)
                lines.append({'box':box.tolist(),'text':text,'score':float(score),
                              'chars':chars.tolist(),'letters':letters})
            lines=join_rows(lines)
            record={'time':at,'lines':lines}
            out.write(json.dumps(record)+'\n'); out.flush()
            cv2.imwrite(str(folder/f'frame_{at:.3f}.jpg'),bgr)
            print(k,at,[x['text'] for x in lines],flush=True)


def tracks(k):
    records=[json.loads(line) for line in (WORK/str(k)/'ocr_v2.jsonl').read_text().splitlines()]
    groups=[]
    for record in records:
        t=record['time']
        for item in record['lines']:
            text=norm(item['text'])
            if not text or any(s in text for s in ['introduction','instrumental','zoom','karaoke','inthestyleof']): continue
            box=np.asarray(item['box']); x=float(box[:,0].mean()); y=float(box[:,1].mean())
            candidates=[g for g in groups if t-g['last']<=SCAN_INTERVAL*2.1 and t>g['last']
                        and abs(y-g['y'])<22 and abs(x-g['x'])<80
                        and SequenceMatcher(None,text,norm(g['best']['text'])).ratio()>.78]
            if candidates:
                g=max(candidates,key=lambda g:SequenceMatcher(None,text,norm(g['best']['text'])).ratio())
                g['last']=t;g['samples'].append({'time':t,**item})
                if item['score']>g['best']['score']: g['best']={'time':t,**item}
            else:
                groups.append({'first':t,'last':t,'x':x,'y':y,'best':{'time':t,**item},'samples':[{'time':t,**item}]})
    # Select consensus text rather than an isolated OCR variant.
    for i,g in enumerate(groups):
        counts=Counter(norm(s['text']) for s in g['samples'])
        winner=counts.most_common(1)[0][0]
        def quality(s):
            frame=cv2.imread(str(WORK/str(k)/f"frame_{s['time']:.3f}.jpg"))
            box=np.asarray(s['box']);x1,y1=box.min(axis=0).astype(int);x2,y2=box.max(axis=0).astype(int)
            active,base=colours(frame[max(0,y1):y2,max(0,x1):x2],k)
            return float(np.mean(active|base)) + .02*s['score'] + .001*s['text'].count(' ')
        g['best']=max([s for s in g['samples'] if norm(s['text'])==winner],key=quality)
        g['id']=i
    save(WORK/str(k)/'tracks.json',groups)
    print('tracks',k,len(groups))


def colours(frame,k):
    b,g,r=cv2.split(frame.astype(np.float32))
    blue=(b>r+35)&(b>g+20)&(b>65)
    if k==0:
        active=(r>150)&(g>150)&(b<100)&(abs(r-g)<65)
        pink=(r>120)&(b>75)&(g<r*.7)
        base=blue|pink
    else:
        active=blue
        base=(np.minimum(np.minimum(r,g),b)>160)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<45)
    return active,base


def measurements(k):
    groups=read(WORK/str(k)/'tracks.json')
    for g in groups:
        best=g['best']; box=np.asarray(best['box'])
        x1,y1=np.floor(box.min(axis=0)).astype(int);x2,y2=np.ceil(box.max(axis=0)).astype(int)
        x1=max(0,x1);x2=min(1280,x2);y1=max(90,y1);y2=min(625,y2)
        g['rect']=[int(x1),int(y1),int(x2),int(y2)]
        frame=cv2.imread(str(WORK/str(k)/f"frame_{best['time']:.3f}.jpg"))
        active,base=colours(frame[y1:y2,x1:x2],k)
        mask=(active|base).astype(np.uint8)
        # Text glyphs are vertically tall; background specks are usually small.
        count,lab,stats,_=cv2.connectedComponentsWithStats(mask,8)
        valid=np.zeros(count,np.uint8)
        for i in range(1,count):
            if stats[i,cv2.CC_STAT_AREA]>25 and stats[i,cv2.CC_STAT_HEIGHT]>=12: valid[i]=1
        g['_mask']=valid[lab].astype(bool)
        g['measurements']=[]
    target=0.
    with av.open(str(SOURCES[k])) as container:
        for frame in container.decode(video=0):
            t=float(frame.time)
            if t+.001<target: continue
            target=t+.035
            live=[g for g in groups if g['first']-3<=t<=g['last']+3]
            if not live: continue
            bgr=cv2.resize(frame.to_ndarray(format='bgr24'),(1280,720))
            for g in live:
                x1,y1,x2,y2=g['rect']; a,b=colours(bgr[y1:y2,x1:x2],k);mask=g['_mask']
                n=int(mask.sum())
                if n<30: continue
                # Per-column active counts let us recover each word's sweep.
                ac=(a&mask).sum(axis=0); bc=(b&mask).sum(axis=0)
                g['measurements'].append({'t':round(t,3),'active':ac.tolist(),'base':bc.tolist()})
    for g in groups:
        g['mask_counts']=g.pop('_mask').sum(axis=0).tolist()
    save(WORK/str(k)/'measured.json',groups)


def word_ranges(best,x1,width,canonical=None):
    if canonical is not None:
        source=[]; positions=[]
        for letter,box in zip(best['letters'],best['chars']):
            for ch in letter:
                if ch.isalnum() or ch=='.': source.append(ch.lower());positions.append(np.asarray(box)[:,0])
        target=[]; owners=[]; tokens=re.findall(r'[^\s-]+-?',canonical)
        for i,token in enumerate(tokens):
            for ch in token:
                if ch.isalnum() or ch=='.':target.append(ch.lower());owners.append(i)
        mapping={}
        for tag,a,b,c,d in SequenceMatcher(None,source,target,autojunk=False).get_opcodes():
            if tag=='equal':
                for j in range(d-c):mapping[c+j]=a+j
            elif d>c:
                for j in range(d-c):mapping[c+j]=min(len(source)-1,max(0,a+int(j*max(1,b-a)/(d-c))))
        ranges=[]
        for i,token in enumerate(tokens):
            boxes=[positions[mapping[j]] for j,owner in enumerate(owners) if owner==i]
            if not boxes:raise ValueError('No character mapping: '+token)
            ranges.append((token,max(0,int(np.min(boxes))-x1),min(width,int(np.max(boxes))-x1)))
        return ranges
    words=[];letters=[];boxes=[]
    for letter,box in zip(best['letters'],best['chars']):
        if letter.isspace():
            if letters:
                a=np.asarray(boxes);words.append((''.join(letters),max(0,int(a[:,:,0].min())-x1),min(width,int(a[:,:,0].max())-x1)))
                letters=[];boxes=[]
        else: letters.append(letter);boxes.append(box)
    if letters:
        a=np.asarray(boxes);words.append((''.join(letters),max(0,int(a[:,:,0].min())-x1),min(width,int(a[:,:,0].max())-x1)))
    return words


def recover(k):
    groups=read(WORK/str(k)/'measured.json');cues=[];rejected=[]
    for group in groups:
        ms=group['measurements'];n=sum(group['mask_counts'])
        if not ms or n<50:
            rejected.append({'track':group['id'],'text':group['best']['text'],'reason':'Insufficient glyph measurements'})
            continue
        text=CORRECTIONS.get(k, {}).get(group['id'],group['best']['text'])
        if any(x in norm(text) for x in ['instrumental','lnstrumental','introduction','iintroduction','colourkey','malesinger','femalesinger']) or norm(text) in ['2unlimited','4nonblondes']:continue
        ts=np.array([m['t'] for m in ms]);a=np.array([m['active'] for m in ms]);b=np.array([m['base'] for m in ms])
        covered=(a+b).sum(axis=1)/n
        ratios=a.sum(axis=1)/np.maximum(1,(a+b).sum(axis=1))
        valid=covered>.78
        high=valid&(ratios>.04)
        # Ignore isolated coloured background flecks; locate continuous pulses.
        for i in range(1,len(high)-1):
            if high[i-1] and high[i+1]: high[i]=True
        changes=np.diff(np.r_[False,high,False].astype(int))
        pulses=list(zip(np.where(changes==1)[0],np.where(changes==-1)[0]))
        accepted=0
        for begin,stop in pulses:
            peak=float(ratios[begin:stop].max())
            if stop-begin<3 or peak<.75: continue
            # Require a left-to-right rise, not a permanently yellow title.
            before=max(0,begin-3)
            if ratios[begin]>.6 and not np.any(valid[before:begin]&(ratios[before:begin]<.2)):continue
            finish=next((i for i in range(begin,stop) if ratios[i]>=max(.85,peak*.97)),stop-1)
            if ts[finish]-ts[begin]<.18:continue
            geometry=max(group['samples'],key=lambda s:(SequenceMatcher(None,norm(s['text']),norm(text),autojunk=False).ratio(),s['time']==group['best']['time']))
            ranges=word_ranges(geometry,group['rect'][0],a.shape[1],text)
            words=[];issues=[]
            for word,left,right in ranges:
                if right<=left: issues.append('empty word box '+word);continue
                wa=a[:,left:right].sum(axis=1);wb=b[:,left:right].sum(axis=1)
                ratio=wa/np.maximum(1,wa+wb)
                indexes=np.arange(max(0,begin-2),stop)
                hits=indexes[(ratio[indexes]>.02)&valid[indexes]]
                word_peak=float(ratio[indexes][valid[indexes]].max()) if np.any(valid[indexes]) else 0
                ends=indexes[(ratio[indexes]>=word_peak*.995)&valid[indexes]] if word_peak>.65 else []
                if not len(hits) or not len(ends):issues.append('incomplete word sweep '+word);continue
                start=float(ts[hits[0]]);end=float(ts[ends[0]])
                if end<=start: end=start+.04;issues.append('short sweep '+word)
                # Preserve the original source's progress at each video frame,
                # including held notes and pauses, rather than linearising it.
                sweep=[];progress=0.0
                for idx in indexes:
                    if not valid[idx]:continue
                    value=float(np.clip(ratio[idx]/max(word_peak,1e-6),0,1))
                    progress=max(progress,value)
                    sweep.append([float(ts[idx]),round(progress,5)])
                words.append({'word':word,'start':round(start,3),'end':round(end,3),'sweep':sweep})
            if not words:continue
            cues.append({'track':group['id'],'text':text,'start':words[0]['start'],
                         'end':words[-1]['end'],'words':words,'issues':issues,'peak':peak})
            accepted+=1
        if not accepted: rejected.append({'track':group['id'],'text':text,'first':group['first'],'last':group['last'],'peak':float(ratios.max())})
    cues.sort(key=lambda c:c['start'])
    save(WORK/str(k)/'recovered.json',cues);save(WORK/str(k)/'rejected.json',rejected)
    for cue in cues: print(cue['track'],cue['start'],cue['end'],cue['text'],cue['issues'])
    print('TOTAL',len(cues),'rejected',len(rejected))


def contact(k):
    from PIL import Image,ImageDraw
    groups=read(WORK/str(k)/'tracks.json')
    for offset in range(0,len(groups),16):
        sheet=Image.new('RGB',(1600,960),'#333333');draw=ImageDraw.Draw(sheet)
        for pos,g in enumerate(groups[offset:offset+16]):
            best=g['best'];frame=Image.open(WORK/str(k)/f"frame_{best['time']:.3f}.jpg")
            box=np.asarray(best['box']);x1,y1=box.min(axis=0);x2,y2=box.max(axis=0)
            crop=frame.crop((max(0,int(x1)-8),max(0,int(y1)-8),min(1280,int(x2)+8),min(720,int(y2)+8)))
            crop.thumbnail((780,90))
            x=pos%2*800;y=pos//2*120
            draw.text((x+5,y+2),f"Track {g['id']} at {best['time']}s",fill='white')
            sheet.paste(crop,(x+5,y+22))
        sheet.save(WORK/str(k)/f'contact_{offset//16}.jpg')
