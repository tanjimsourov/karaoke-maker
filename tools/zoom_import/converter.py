"""Zoom-only conversion: recover screen timing and reuse the original backing."""
import argparse
from bisect import bisect_right
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback
import av
import numpy as np
from PIL import Image, ImageFont
from common import ROOT, read, save, digest

PROFILES={'white-blue':2,'blue-yellow':0}

def code_hash():
    sha=hashlib.sha256()
    for name in ('common.py','converter.py','recovery.py'):
        sha.update((ROOT/name).read_bytes())
    return sha.hexdigest()

def seconds(value):
    h,m,s=value.split(':');return int(h)*3600+int(m)*60+float(s)

def stamp(t):
    n=round(max(0,t)*100);h,n=divmod(n,360000);m,n=divmod(n,6000);s,cs=divmod(n,100)
    return f'{h}:{m:02d}:{s:02d}.{cs:02d}'

def text(value):
    return str(value).replace('\\','/').replace('{','(').replace('}',')').replace('\n',' ')

def tokens(value):
    return re.sub(r'\W','',value,flags=re.UNICODE).casefold()

def validate_cues(cues,duration):
    if not cues:raise ValueError('No recovered lyrics; review this layout')
    previous=0
    for cue in cues:
        words=cue.get('words',[])
        if not words or tokens(cue['text'])!=tokens(''.join(w['word'] for w in words)):
            raise ValueError('Missing or mismatched lyric words: '+cue.get('text',''))
        if any('incomplete' in issue or 'empty' in issue for issue in cue.get('issues',[])):
            raise ValueError('Incomplete recovered words must be corrected')
        for w in words:
            if not all(math.isfinite(w[key]) for key in ('start','end')):
                raise ValueError('Nonfinite timestamp')
            if not previous<=w['start']<w['end']<=duration+.04:
                raise ValueError('Overlapping, zero-length or out-of-range word: '+str(w))
            if round(w['end']*100)<=round(w['start']*100):
                raise ValueError('Word is shorter than subtitle resolution')
            if 'sweep' in w:
                last_time=-1.0;last_fraction=-1.0
                for sample in w['sweep']:
                    if len(sample)!=2 or not all(math.isfinite(x) for x in sample):
                        raise ValueError('Invalid source-frame sweep sample')
                    at,fraction=sample
                    if not last_time<at or not 0<=fraction<=1 or fraction<last_fraction:
                        raise ValueError('Source sweep timestamps/progress must increase')
                    last_time,last_fraction=at,fraction
                if not w['sweep']:raise ValueError('Empty source-frame sweep')
            previous=w['end']
        if abs(cue['start']-words[0]['start'])>.02 or abs(cue['end']-words[-1]['end'])>.02:
            raise ValueError('Cue boundaries must match its words')
    return cues

def cut_seconds(cues,variant):
    if variant not in ('full','5s','10s'):raise ValueError('Unknown variant')
    # Negative cuts mean padding a source whose vocals start before 5 seconds.
    return 0 if variant=='full' else round(cues[0]['start']-int(variant[:-1]),2)

def glyph_front(columns,fraction):
    """Map painted glyph area to a horizontal clip, including inter-letter gaps."""
    values=np.asarray(columns,dtype=float)
    if fraction<=0:return 0.0
    if fraction>=1:return float(len(values))
    cumulative=np.cumsum(values)
    if not len(cumulative) or cumulative[-1]<=0:return 0.0
    target=fraction*cumulative[-1]
    index=min(len(values)-1,int(np.searchsorted(cumulative,target)))
    before=cumulative[index-1] if index else 0
    return index+(target-before)/max(values[index],1e-9)

def eased_progress(value,at,start,end,ease=1.0):
    """Optional visual slowdown bounded by the existing word interval."""
    if ease==1:return value
    phase=max(0.0,min(1.0,(at-start)/(end-start)))
    return min(value,phase**ease)


def ass_geometry_font(size=66):
    """Match libass's line-height font size, rather than Pillow's em size."""
    font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',size)
    ascent,descent=font.getmetrics()
    return font.font_variant(size=round(size*size/(ascent+descent)))


def build_ass(cues,cut,title,artist,sweep_ease=1.0):
    first=cues[0]['start']-cut
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Base,Arial,66,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,5,80,80,0,1
Style: Sweep,Arial,66,&H0000A5FF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,5,80,80,0,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''
    events=[]
    def emit(start,end,style,tags,value,layer=0):
        if end>start:events.append(f'Dialogue: {layer},{stamp(start)},{stamp(end)},{style},,0,0,0,,{{{tags}}}{value}')
    move=first
    title_end=max(0,first-.15)
    for value,y,size in [(title,820,90),(artist,925,48),('KARAOKE',995,28)]:
        emit(0,title_end,'Base',f'\\pos(960,{y})\\fs{size}\\fad(80,160)',text(value),5)
    for remaining in range(math.ceil(first),0,-1):
        emit(max(0,first-remaining),min(first,first-remaining+1),'Base','\\pos(960,690)\\fs110',str(remaining),5)
    # Wrap long lines without altering word timestamps.
    font=ass_geometry_font(66)
    rows=[]
    for cue in cues:
        group=[]
        for word in cue['words']:
            if group and font.getlength(' '.join(w['word'] for w in group+[word]))>1640:
                rows.append(group);group=[]
            group.append(word)
        if group:rows.append(group)
    for offset in range(0,len(rows),4):
        page=rows[offset:offset+4]
        start=page[0][0]['start']-cut
        if offset:
            # A preview lead-in must never cover the previous page's final
            # sung word. Its end and this start must be the same boundary.
            start=max(first,start-.35,rows[offset-1][-1]['end']-cut)
        following=rows[offset+4][0]['start']-cut if offset+4<len(rows) else page[-1][-1]['end']-cut+.1
        end=max(page[-1][-1]['end']-cut,following-.35)
        for i,words in enumerate(page):
            a,b=words[0]['start']-cut,words[-1]['end']-cut
            tags=f'\\pos(960,{285+i*155})'
            plain=' '.join(text(w['word']) for w in words)
            if all(w.get('sweep') for w in words):
                # Drive the new text from measured source-frame positions.
                # A fixed word-duration animation cannot reproduce source holds.
                emit(start,end,'Base',tags,plain)
                width=font.getlength(plain);left=960-width/2
                times=sorted({round(t-cut,3) for w in words for t,_ in w['sweep'] if a<=t-cut<=b}|{a,b})
                prefixes=[font.getlength(' '.join(text(x['word']) for x in words[:j])+(' ' if j else '')) for j in range(len(words))]
                glyphs=[]
                for w in words:
                    mask=font.getmask(text(w['word']))
                    columns=np.asarray(mask,dtype=float).reshape(mask.size[1],mask.size[0]).sum(axis=0)
                    glyphs.append(columns)
                for t,until in zip(times,times[1:]):
                    front=0.0
                    for j,w in enumerate(words):
                        samples=w['sweep'];index=bisect_right([s[0] for s in samples],t+cut+.0001)-1
                        value=samples[index][1] if index>=0 else 0
                        if t+cut<w['start']:value=0
                        if t+cut>=w['end']:value=1.0
                        value=eased_progress(value,t+cut,w['start'],w['end'],sweep_ease)
                        if value>0:front=max(front,prefixes[j]+glyph_front(glyphs[j],value))
                    if front>0:
                        clip=f'\\clip({math.floor(left)-6},{285+i*155-55},{round(left+front)},{285+i*155+55})'
                        emit(t,until,'Sweep',tags+clip,plain)
                emit(b,end,'Sweep',tags,plain)
                continue
            emit(start,a,'Base',tags,plain)
            parts=[];cursor=round(a*100)
            for w in words:
                ws,we=round((w['start']-cut)*100),round((w['end']-cut)*100)
                if ws>cursor:parts.append('{\\kf'+str(ws-cursor)+'}\u200b')
                parts.append('{\\kf'+str(we-ws)+'}'+text(w['word'])+' ')
                cursor=we
            emit(a,b,'Sweep',tags,''.join(parts))
            emit(b,end,'Base',tags,plain)
    return header+'\n'.join(events)+'\n'

def verify_review(folder,state):
    if not (folder/'approval.json').exists():
        raise ValueError('Review the source screens and preview, then run approve --confirm-screen-review')
    approval=read(folder/'approval.json')
    wanted={'source_sha256':state['source_sha256'],'cues_sha256':digest(folder/'cues.json'),'code_sha256':code_hash()}
    if any(approval.get(k)!=v for k,v in wanted.items()):
        raise ValueError('Source, timings or code changed since review; review again')

def load_config(path):
    path=Path(path).resolve();cfg=read(path)
    for key in ('ffmpeg','logo','work_dir','output_dir'):
        cfg[key]=str((path.parent/cfg[key]).resolve())
    cfg['backgrounds']=[str((path.parent/p).resolve()) for p in cfg['backgrounds']]
    if len(cfg['backgrounds'])!=2:raise ValueError('Specify the two approved backgrounds')
    for job in cfg['jobs']:
        job['source']=str((path.parent/job['source']).resolve())
        if job.get('profile') not in PROFILES:raise ValueError('Explicit supported colour profile required')
        if job.get('background',0) not in (0,1):raise ValueError('Background must be 0 or 1')
    return cfg

def job_state(cfg,job):
    source=Path(job['source'])
    sha=digest(source)
    key=hashlib.sha256((str(source)+sha+job['profile']).encode()).hexdigest()[:16]
    folder=Path(cfg['work_dir'])/key;folder.mkdir(parents=True,exist_ok=True)
    with av.open(str(source)) as c:
        if not c.streams.audio or not c.streams.video:raise ValueError('Source needs video and audio')
        duration=c.duration/av.time_base
    state={'source':str(source),'source_sha256':sha,'profile':job['profile'],'duration':duration}
    return folder,state

def extract(cfg,job,folder,state):
    import recovery
    marker=folder/'extraction-complete.json'
    if marker.exists() and read(marker).get('code_sha256')==code_hash() and (folder/'cues.json').exists():
        return
    k=PROFILES[job['profile']]
    recovery.WORK=folder/'extraction';recovery.SOURCES=[Path(job['source'])]*(k+1)
    recovery.CORRECTIONS[k]={}
    cache=recovery.WORK/str(k)
    if not (cache/'ocr_v2.jsonl').exists() or not (folder/'scan-complete.json').exists():
        recovery.scan(k);save(folder/'scan-complete.json',{'source_sha256':state['source_sha256']})
    if not (cache/'tracks.json').exists():recovery.tracks(k)
    if not (cache/'measured.json').exists():recovery.measurements(k)
    recovery.recover(k);recovery.contact(k)
    # Never replace the user's corrected transcript on a resumed extraction.
    if not (folder/'cues.json').exists():save(folder/'cues.json',read(cache/'recovered.json'))
    save(folder/'rejected.json',read(cache/'rejected.json'))
    save(folder/'review-status.json',{'status':'needs_screen_review','notes':'Compare all source lyrics and repetitions, missing tracks, spelling, timing and rejected titles. Extraction alone does not prove completeness.'})
    save(marker,{'code_sha256':code_hash(),'source_sha256':state['source_sha256']})
    # Measurement matrices are large, reproducible scratch data. Keep screen
    # contacts, OCR, tracks and recovered cues for review, but reclaim this file.
    (cache/'measured.json').unlink()

def audio_array(path,rate=16000):
    resampler=av.AudioResampler(format='flt',layout='mono',rate=rate)
    blocks=[]
    with av.open(str(path)) as c:
        for frame in c.decode(audio=0):
            blocks.extend(x.to_ndarray().reshape(-1) for x in resampler.resample(frame))
        blocks.extend(x.to_ndarray().reshape(-1) for x in resampler.resample(None))
    return np.concatenate(blocks) if blocks else np.empty(0)

def check_audio(source,dest,cut):
    original=audio_array(source)
    a=(original[round(cut*16000):] if cut>=0 else np.pad(original,(round(-cut*16000),0))).astype(np.float64)
    b=audio_array(dest).astype(np.float64)
    if abs(len(a)-len(b))>4000:raise ValueError('Audio duration mismatch')
    n=min(len(a),len(b));a,b=a[:n],b[:n]
    energy=float(a@a)
    if energy<1e-8:raise ValueError('Silent source; cannot verify audio')
    corr=float(a@b/max(math.sqrt(energy*float(b@b)),1e-12))
    error=float(math.sqrt(float((a-b)@(a-b))/energy))
    if corr<.98 or error>.15:raise ValueError('Audio changed or shifted')
    return {'correlation':corr,'relative_error':error,'removed_opening_seconds':cut}

def white_circle_logo(image):
    """Whiten the outer purple arc while preserving lettering, artwork and alpha."""
    rgba=np.array(image.convert('RGBA'))
    h,w=rgba.shape[:2];y,x=np.indices((h,w))
    r,g,b=rgba[:,:,:3].astype(np.int16).transpose(2,0,1)
    outer=np.hypot((x-w/2)/w,(y-h/2)/h)>160/420
    sparkle=(x>w*.095)&(x<w*.205)&(y>h*.40)&(y<h*.51)
    arc=outer&(b>g+15)&(b>r-15)&~sparkle
    rgba[arc,:3]=255
    return Image.fromarray(rgba)


def render(cfg,job,folder,state,variant,preview=False,limit=None):
    cues=validate_cues(read(folder/'cues.json'),state['duration'])
    if cfg.get('require_frame_sweep',True) and not all(w.get('sweep') for cue in cues for w in cue['words']):
        raise ValueError('This job needs fresh frame-based extraction. Legacy word endpoints would use the old straight sweep.')
    if not preview:verify_review(folder,state)
    background=Path(cfg['backgrounds'][job.get('background',0)]);logo=Path(cfg['logo'])
    cut=cut_seconds(cues,variant);first=cues[0]['start']-cut
    font=Path('C:/Windows/Fonts/arialbd.ttf')
    sweep_ease=float(job.get('sweep_ease',cfg.get('sweep_ease',1.0)))
    if not math.isfinite(sweep_ease) or not 1<=sweep_ease<=2:raise ValueError('sweep_ease must be between 1 and 2')
    fingerprint={'source':state['source_sha256'],'cues':digest(folder/'cues.json'),'code':code_hash(),'background':digest(background),'logo':digest(logo),'font':digest(font),'variant':variant,'title':job['title'],'artist':job['artist'],'preview':preview,'limit':limit,'sweep_ease':sweep_ease}
    ident=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
    safe=re.sub(r'[^a-zA-Z0-9_-]+','_',Path(job['source']).stem).strip('_')[:85] or 'Zoom'
    output_dir=folder/'previews' if preview else Path(cfg['output_dir'])
    output_dir.mkdir(parents=True,exist_ok=True)
    suffix='_'+ident[:8] if preview else ''
    dest=output_dir/f'{safe}_{state["source_sha256"][:8]}_{variant}{suffix}_Karaoke.mp4'
    result_path=dest.with_suffix('.json')
    if dest.exists():
        old=read(result_path)
        if old.get('fingerprint')==ident and old.get('sha256')==digest(dest):return dest
        raise FileExistsError('Existing output differs; choose another output directory')
    ass=folder/(variant+'.ass');ass.write_text(build_ass(cues,cut,job['title'],job['artist'],sweep_ease),encoding='utf-8-sig')
    ass_filter=str(ass).replace('\\','/').replace(':','\\:').replace("'",r"\'")
    q=f'gte(t,{first:.3f})'
    # Isolate the coloured outer arc, never the white letters/black outlines.
    # Move that arc outward on a padded canvas before applying the countdown.
    angle='mod(atan2(Y-H/2,X-W/2)+PI/2+2*PI,2*PI)'
    def arc_at(x,y):
        return f'gt(hypot({x}-W/2,{y}-H/2),160)*gt(b({x},{y}),g({x},{y})+15)*gt(b({x},{y}),r({x},{y})-15)'
    sx='(W/2+(X-W/2)/1.18)';sy='(H/2+(Y-H/2)/1.18)'
    moved=arc_at(sx,sy)
    alpha=f"if({moved},alpha({sx},{sy})*gte({angle},2*PI*T/{max(first,.001):.3f}),if({arc_at('X','Y')},0,alpha(X,Y)))"
    channels={c:f'if({moved},255,{c}(X,Y))' for c in 'rgb'}
    corner_logo=folder/'corner-logo-white.png'
    with Image.open(logo) as artwork:white_circle_logo(artwork).save(corner_logo)
    graph=("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[bg];"
           f"[2:v]scale=420:420,format=rgba,pad=500:500:40:40:color=black@0,geq=r='{channels['r']}':g='{channels['g']}':b='{channels['b']}':a='{alpha}':enable='lt(t,{first:.3f})',scale=w='500-(500-180*500/420)*{q}':h=-1:eval=frame[logo];"
           f"[bg][logo]overlay=x='960+822*{q}-w/2':y='330-198*{q}-h/2':enable='lt(t,{first:.3f})'[intro];"
           f"[3:v]scale=180:180,format=rgba[corner];[intro][corner]overlay=x=1692:y=42:enable='gte(t,{first:.3f})',subtitles='{ass_filter}'[v]")
    audio_map='1:a:0'
    if cut<0:
        graph+=f';[1:a]adelay={round(-cut*1000)}:all=1[audio]'
        audio_map='[audio]'
    staged=folder/(variant+'.rendering.mp4')
    duration=state['duration']-cut
    if limit is not None:
        if not preview:raise ValueError('A clip limit is permitted only for preview')
        duration=min(duration,limit)
    command=[cfg['ffmpeg'],'-nostdin','-y','-filter_complex_threads','1','-loop','1','-framerate','25','-i',str(background),'-ss',str(max(0,cut)),'-threads','2','-i',job['source'],'-loop','1','-framerate','25','-i',str(logo),'-loop','1','-framerate','25','-i',str(corner_logo),'-filter_complex',graph,'-map','[v]','-map',audio_map,'-t',str(duration),'-r','25','-c:v','libx264','-threads','2','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(staged)]
    with (folder/(variant+'.render.log')).open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run([cfg['ffmpeg'],'-v','error','-threads','2','-i',str(staged),'-f','null','-'],check=True)
    with av.open(str(staged)) as c:
        actual=c.duration/av.time_base
        if abs(actual-duration)>.15:raise ValueError('Video duration changed')
        if (c.streams.video[0].width,c.streams.video[0].height)!=(1920,1080) or float(c.streams.video[0].average_rate)!=25:raise ValueError('Format mismatch')
    if limit is None:audio_check=check_audio(job['source'],staged,cut)
    else:audio_check={'status':'preview_clip_not_full_audio_check'}
    if digest(job['source'])!=state['source_sha256']:raise ValueError('Source changed during render')
    with staged.open('rb') as src,dest.open('xb') as out:shutil.copyfileobj(src,out)
    save(result_path,{'fingerprint':ident,'inputs':fingerprint,'sha256':digest(dest),'source_sha256':state['source_sha256'],'first_highlight_seconds':first,'duration':actual,'audio':audio_check,'full_decode_exit':0,'status':'preview' if preview else 'reviewed_export'})
    staged.unlink()
    return dest

def doctor(cfg):
    errors=[]
    for key in ('ffmpeg','logo'):
        if not Path(cfg[key]).is_file():errors.append('Missing '+key+': '+cfg[key])
    for path in cfg['backgrounds']:
        if not Path(path).is_file():errors.append('Missing background: '+path)
    spec=importlib.util.find_spec('rapidocr_onnxruntime')
    if spec is None:errors.append('Install rapidocr-onnxruntime to extract new videos')
    else:
        model_dir=Path(spec.origin).parent/'models'
        if len(list(model_dir.glob('*.onnx')))<3:errors.append('RapidOCR model assets were removed; reinstall rapidocr-onnxruntime (no Whisper or Demucs needed)')
    print(json.dumps({'errors':errors,'paid_services':False,'scope':'Zoom screen recovery, source backing, branded render'},indent=2))
    return not errors

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['doctor','extract','import-timings','approve','preview','render','status'])
    p.add_argument('--config',type=Path,default=ROOT/'config.json')
    p.add_argument('--job',type=int,help='Zero-based manifest job; omit to process the folder/manifest sequentially')
    p.add_argument('--timings',type=Path,help='Existing recovered word JSON, for one specified job')
    p.add_argument('--source-sha256',help='Original source hash associated with imported timings')
    p.add_argument('--confirm-screen-review',action='store_true')
    p.add_argument('--variant',choices=['full','5s','10s','both'],default='10s')
    p.add_argument('--limit',type=float,help='Preview clip length only')
    args=p.parse_args();cfg=load_config(args.config)
    if args.limit is not None and (args.stage!='preview' or args.limit<=0):p.error('--limit requires preview and a positive length')
    if args.stage=='doctor':return 0 if doctor(cfg) else 1
    if args.stage=='import-timings' and (args.job is None or not args.timings or not args.source_sha256):p.error('Import requires --job, --timings and --source-sha256')
    jobs=cfg['jobs']
    if args.job is not None:
        if not 0<=args.job<len(jobs):p.error('Job index outside manifest')
        jobs=[jobs[args.job]]
    failures=0;summary=[]
    for job in jobs:
        lock=None;owns_lock=False
        try:
            folder,state=job_state(cfg,job);lock=folder/'.running'
            with lock.open('x') as stream:stream.write(str(os.getpid()))
            owns_lock=True
            save(folder/'source.json',state)
            if args.stage=='extract':extract(cfg,job,folder,state)
            elif args.stage=='import-timings':
                if state['source_sha256']!=args.source_sha256:raise ValueError('Imported timings belong to another source')
                if (folder/'cues.json').exists():raise FileExistsError('Existing timings preserved')
                save(folder/'cues.json',read(args.timings))
            elif args.stage=='approve':
                if not args.confirm_screen_review:raise ValueError('Review original screens, all lyrics/repetitions, rejected tracks and sync, then --confirm-screen-review')
                validate_cues(read(folder/'cues.json'),state['duration'])
                save(folder/'approval.json',{'source_sha256':state['source_sha256'],'cues_sha256':digest(folder/'cues.json'),'code_sha256':code_hash(),'review':'user_confirmed_source_screen_lyrics_and_timing'})
            elif args.stage in ('preview','render'):
                for variant in (['full','5s'] if args.variant=='both' else [args.variant]):
                    print(render(cfg,job,folder,state,variant,args.stage=='preview',args.limit),flush=True)
            print(job['title'],args.stage,'OK',folder,flush=True)
            summary.append({'source':job['source'],'status':'ok','work':str(folder)})
        except Exception as e:
            failures+=1;summary.append({'source':job['source'],'status':'needs_attention','error':str(e)})
            print(job['source'],type(e).__name__,str(e),file=sys.stderr,flush=True)
        finally:
            if owns_lock:lock.unlink()
    save(Path(cfg['work_dir'])/(args.stage+'-summary.json'),summary)
    return 1 if failures else 0

if __name__=='__main__':sys.exit(main())
